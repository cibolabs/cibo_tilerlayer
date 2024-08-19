"""
Supporting functions for creating a tiler.
"""

import io
import threading
import numpy
from osgeo import gdal

gdal.UseExceptions()


TILE_SIZE = 256
# Don't use the numbers from: http://epsg.io/3857
# The correct numbers are here: https://github.com/OSGeo/gdal/blob/master/gdal/swig/python/gdal-utils/osgeo_utils/gdal2tiles.py#L278
# Not sure why the difference...
MERCATOR_X_ORIGIN = -20037508.342789244
MERCATOR_Y_ORIGIN = 20037508.342789244


def getTile(filename, z, x, y, bands=None, rescaling=None, colormap=None, 
        resampling='near'):
    """
    Main function. 
    
    bands is None for all bands or a list of index-1 values
    rescaling is None for no rescaling or list of (minVal, maxVal) tuples. Linear stretch applied
    colormap is a 2d array of shape (4, maxImageVal) with the RGBA values to apply to the data
    TODO: resampling
    """
    ds = gdal.Open(filename)
    metadata = Metadata(ds)

    # TODO: should we always assume WebMercator tiling?

    # https://wiki.osgeo.org/wiki/Tile_Map_Service_Specification#global-mercator
    units_per_pixel = 78271.516 / 2**int(z)
    tile_size = units_per_pixel * TILE_SIZE
    
    tlx = MERCATOR_X_ORIGIN + (tile_size * int(x))
    tly = MERCATOR_Y_ORIGIN - (tile_size * int(y))
    brx = tlx + tile_size
    bry = tly - tile_size

    # bands
    if bands is None:
        bands = range(1, ds.RasterCount + 1)
    elif len(bands) != 1 and len(bands) != 3:
        raise ValueError('invalid number of bands')

    data, dataslice = getRawImageChunk(ds, metadata, 
        TILE_SIZE, TILE_SIZE, tlx, tly, brx, bry, bands)

    # output MEM dataset to write into
    mem = gdal.GetDriverByName('MEM').Create('', TILE_SIZE, 
        TILE_SIZE, 4, gdal.GDT_Byte)

    alphaset = False
    if data is None:
        # no data available for this area - return all zeros
        for n in range(4):
            band = mem.GetRasterBand(n + 1)
            band.Fill(0)
        alphaset = True
    else:
        imgData = numpy.zeros((TILE_SIZE, TILE_SIZE), dtype=numpy.uint8)
        # rescale.
        if rescaling is not None:
            if len(rescaling) == 1:
                # same rescaling to every band
                minVal, maxVal = rescaling[0]
                for n in range(3):
                    imgData[dataslice] = max(data[n] - minVal, 0) * (maxVal - minVal) / 255
                    band = mem.GetRasterBand(n + 1)
                    band.WriteArray(imgData)
            else:
                if len(rescaling) != len(bands):
                    raise ValueError("length of rescaling doesn't math number of bands")
                for n, (minVal, maxVal) in enumerate(rescaling):
                    imgData[dataslice] = max(data[n] - minVal, 0) * (maxVal - minVal) / 255
                    band = mem.GetRasterBand(n + 1)
                    band.WriteArray(imgData)

        elif colormap is not None:
            # Note: currently can't specify rescaling AND colormap
            for n in range(4):
                imgData[dataslice] = colormap[n][data[n]]
                band = mem.GetRasterBand(n + 1)
                band.WriteArray(imgData)
            alphaset = True

    if not alphaset:
        # return alpha=255 - should probably do something better
        # TODO: check nodata values(s)?
        band = mem.GetRasterBand(4)
        band.Fill(255)

    return createPNGBytesIOFromMEM(mem)


def createPNGBytesIOFromMEM(mem):
    """
    Given a GDAL in memory dataset ("MEM" driver)
    convert to a PNG and dump as a io.BytesIO for returning
    to client.
    """
    # ensure all data written
    mem.FlushCache()
    
    # see https://lists.osgeo.org/pipermail/gdal-dev/2016-August/045030.html
    # Create an in-memory raster first then using CreateCopy() to create
    # a .png as the PNG driver can't create a brand new file.

    # in case we are being calling from different threads
    # make the filename unique to this thread
    memName = '/vsimem/output_%d.png' % threading.get_ident()

    ds = gdal.GetDriverByName('PNG').CreateCopy(memName, mem)
    ds.FlushCache()
    
    f = gdal.VSIFOpenL(memName, 'rb')
    gdal.VSIFSeekL(f, 0, 2)  # seek to end
    size = gdal.VSIFTellL(f)
    gdal.VSIFSeekL(f, 0, 0)  # seek to beginning
    imageData = gdal.VSIFReadL(1, size, f)
    gdal.VSIFCloseL(f)

    # Cleanup
    gdal.Unlink(memName)
    
    output = io.BytesIO(imageData)
    return output


# overview stuff from tuiview
class OverviewInfo(object):
    """
    Stores size and index of an overview
    """
    def __init__(self, xsize, ysize, fullrespixperpix, index):
        self.xsize = xsize
        self.ysize = ysize
        self.fullrespixperpix = fullrespixperpix
        self.index = index


class OverviewManager(object):
    """
    This class contains a list of valid overviews
    and allows the best overview to be retrieved
    """
    def __init__(self):
        self.overviews = None

    def getFullRes(self):
        "Get the full res overview - ie the non overview image"
        return self.overviews[0]

    def loadOverviewInfo(self, ds, bands):
        """
        Load the overviews from the GDAL dataset into a list
        bands should be a list or tuple of band indices.
        Checks are made that all lists bands contain the
        same sized overviews
        """
        # i think we can assume that all the bands are the same size
        # add an info for the full res - this should always be location 0
        ovi = OverviewInfo(ds.RasterXSize, ds.RasterYSize, 1.0, 0)
        self.overviews = [ovi]

        # for the overviews
        # start with the first band and go from there
        band = ds.GetRasterBand(bands[0])

        count = band.GetOverviewCount()
        for index in range(count):
            ov = band.GetOverview(index)

            # do the other bands have the same resolution overview
            # at the same index?
            overviewok = True
            for bandnum in bands[1:]:
                otherband = ds.GetRasterBand(bandnum)
                otherov = otherband.GetOverview(index)
                if otherov.XSize != ov.XSize or otherov.YSize != ov.YSize:
                    overviewok = False
                    break

            if overviewok:
                # calc the conversion to full res pixels
                fullrespixperpix = float(ds.RasterXSize) / float(ov.XSize) 
                # should do both ways?
                # remember index 0 is full res so all real overviews are +1
                ovi = OverviewInfo(ov.XSize, ov.YSize, fullrespixperpix, 
                    index + 1)
                self.overviews.append(ovi)

        # make sure they are sorted by area - biggest first
        self.overviews.sort(key=lambda ov: ov.xsize * ov.ysize, reverse=True)

    def findBestOverview(self, imgpixperwinpix):
        """
        Finds the best overview for given imgpixperwinpix
        """
        selectedovi = self.overviews[0]
        for ovi in self.overviews[1:]:
            if ovi.fullrespixperpix > imgpixperwinpix:
                break  # gone too far, selectedovi is selected
            else:
                # got here overview must be ok, but keep going
                selectedovi = ovi

        return selectedovi


class Metadata(object):
    """
    Class that holds all the 'metadata' about an object (ie size, projection etc)
    and this can be passed to the browser in one chunk.
    """
    def __init__(self, ds, timeToOpen=-999):
        self.timeToOpen = timeToOpen
        self.RasterXSize = ds.RasterXSize
        self.RasterYSize = ds.RasterYSize
        self.RasterCount = ds.RasterCount
        band1 = ds.GetRasterBand(1)
        self.thematic = band1.GetMetadataItem('LAYER_TYPE') == 'thematic'

        self.transform = ds.GetGeoTransform()

        self.allIgnore = []
        for nband in range(ds.RasterCount):
            bandh = ds.GetRasterBand(nband + 1)

            ignore = bandh.GetNoDataValue()
            self.allIgnore.append(ignore)

        self.overviews = OverviewManager()
        self.overviews.loadOverviewInfo(ds, range(1, self.RasterCount + 1))

        self.tlx, self.tly = gdal.ApplyGeoTransform(self.transform, 0, 0)
        self.brx, self.bry = gdal.ApplyGeoTransform(self.transform, 
            ds.RasterXSize, ds.RasterYSize)

        self.tInverse = gdal.InvGeoTransform(self.transform)


# See https://chao-ji.github.io/jekyll/update/2018/07/19/BilinearResize.html
# for bilinear alternative
def replicateArray(arr, outsize, dspLeftExtra, dspTopExtra, dspRightExtra, 
        dspBottomExtra):
    """
    Replicate the data in the given 2-d array so that it increases
    in size to be (ysize, xsize). 
    
    Replicates each pixel in both directions. 
    
    dspLeftExtra, dspTopExtra are the number of pixels to be shaved off the
    top and left. dspRightExtra, dspBottomExtra are the number of pixels
    to be shaved off the bottom and right of the result. This allows us
    to display fractional pixels.
    """
    (ysize, xsize) = outsize
    (nrows, ncols) = arr.shape
    nRptsX = float(xsize + dspLeftExtra + dspRightExtra) / float(ncols)
    nRptsY = float(ysize + dspTopExtra + dspBottomExtra) / float(nrows)

    rowCount = int(numpy.ceil(nrows * nRptsY))
    colCount = int(numpy.ceil(ncols * nRptsX))
    
    # create the lookup table (up to nrows/ncols-1)
    # using the complex number stuff in numpy.mgrid
    # doesn't work too well since you end up with unevenly
    # spaced divisions...
    row, col = numpy.mgrid[dspTopExtra:rowCount - dspBottomExtra, 
        dspLeftExtra:colCount - dspRightExtra]
    # try to be a little frugal with memory
    numpy.multiply(row, nrows / float(rowCount), out=row, casting='unsafe')
    numpy.multiply(col, ncols / float(colCount), out=col, casting='unsafe')
    # need to index with ints
    row = row.astype(numpy.int32)
    col = col.astype(numpy.int32)

    # do the lookup
    outarr = arr[row, col]

    # chop out the extra pixels (if any)
    outarr = outarr[0:ysize, 0:xsize]

    return outarr


def pixel2displayF(col, row, origCol, origRow, imgPixPerWinPix):
    """
    From tuiview - convert pixel coordinates to display as float
    """
    x = (col - origCol) / imgPixPerWinPix
    y = (row - origRow) / imgPixPerWinPix
    return (x, y)


def pixel2display(col, row, origCol, origRow, imgPixPerWinPix):
    """
    From tuiview - convert pixel coordinates to display - integer version
    """
    x = int((col - origCol) / imgPixPerWinPix)
    y = int((row - origRow) / imgPixPerWinPix)
    return (x, y)


def getRawImageChunk(ds, metadata, xsize, ysize, tlx, tly, brx, bry, bands):
    """
    Also adapted from tuiview. returns requested chunk of image. Returns 
    the data and the dataslice that the data fits into the (ysize, xsize)
    output data (caller to do this). data can be None - no data for requested
    bounds. 
    """
    # then pixel/row
    imgPix_x = (brx - tlx) / metadata.transform[1]
    imgPix_y = (bry - tly) / metadata.transform[5]
    imgPixPerWinPix = imgPix_x / xsize

    origPixLeft, origPixTop = gdal.ApplyGeoTransform(metadata.tInverse, tlx, tly)
    origPixRight = origPixLeft + imgPix_x
    origPixBottom = origPixTop + imgPix_y
    imgPixPerWinPix = (origPixRight - origPixLeft) / xsize
    selectedovi = metadata.overviews.findBestOverview(imgPixPerWinPix)

    # from TuiView
    # first check that we are out of the area
    dataslice = None
    if origPixTop < 0 and origPixBottom < 0:
        data = None
    elif origPixLeft < 0 and origPixRight < 0:
        data = None
    elif origPixLeft > metadata.RasterXSize and origPixRight > metadata.RasterXSize:
        data = None
    elif origPixTop > metadata.RasterYSize and origPixBottom > metadata.RasterYSize:
        data = None
    else:
        fullrespixperovpix = selectedovi.fullrespixperpix

        pixTop = max(origPixTop, 0)
        pixLeft = max(origPixLeft, 0)
        pixBottom = min(origPixBottom, metadata.RasterYSize)
        pixRight = min(origPixRight, metadata.RasterXSize)
        ovtop = int(pixTop / fullrespixperovpix)
        ovleft = int(pixLeft / fullrespixperovpix)
        ovbottom = int(numpy.ceil(pixBottom / fullrespixperovpix))
        ovright = int(numpy.ceil(pixRight / fullrespixperovpix))
        ovtop = max(ovtop, 0)
        ovleft = max(ovleft, 0)
        ovbottom = min(ovbottom, selectedovi.ysize)
        ovright = min(ovright, selectedovi.xsize)
        ovxsize = ovright - ovleft
        ovysize = ovbottom - ovtop

        # The display coordinates of the top-left corner of the raster data.
        #  Often this
        # is (0, 0), but need not be if there is blank area left/above the 
        # raster data
        # because we have the display in ints, other metrics floats,
        # we need to do the size calculations as floats, convert
        # to int at last. Otherwise black lines appear around side
        
        (dspRastLeft, dspRastTop) = pixel2displayF(pixLeft, pixTop, origPixLeft, 
                                            origPixTop, imgPixPerWinPix)
        (dspRastRight, dspRastBottom) = pixel2displayF(pixRight, pixBottom, origPixLeft, 
                                            origPixTop, imgPixPerWinPix)
        dspRastLeft = int(numpy.round(dspRastLeft))
        dspRastTop = int(numpy.round(dspRastTop))
        dspRastRight = int(numpy.round(dspRastRight))
        dspRastBottom = int(numpy.round(dspRastBottom))
        dspRastXSize = dspRastRight - dspRastLeft
        dspRastYSize = dspRastBottom - dspRastTop

        if imgPixPerWinPix < 1:
            # need to calc 'extra' around the edge as we have partial pixels
            # GDAL reads in full pixels
            (dspRastAbsLeft, dspRastAbsTop) = pixel2display(numpy.floor(pixLeft), 
                 numpy.floor(pixTop), origPixLeft, origPixTop, imgPixPerWinPix)
            (dspRastAbsRight, dspRastAbsBottom) = pixel2display(
                numpy.ceil(pixRight), numpy.ceil(pixBottom), origPixLeft, 
                origPixTop, imgPixPerWinPix)
            dspLeftExtra = ((dspRastLeft - dspRastAbsLeft) /
                fullrespixperovpix)
            dspTopExtra = ((dspRastTop - dspRastAbsTop) /
                fullrespixperovpix)
            dspRightExtra = ((dspRastAbsRight - dspRastRight) /
                fullrespixperovpix)
            dspBottomExtra = ((dspRastAbsBottom - dspRastBottom) /
                fullrespixperovpix)
            # be aware rounding errors
            dspRightExtra = max(dspRightExtra, 0)
            dspBottomExtra = max(dspBottomExtra, 0)

        dataslice = (slice(dspRastTop, dspRastTop + dspRastYSize),
            slice(dspRastLeft, dspRastLeft + dspRastXSize))

        if len(bands) == 1:
            band = ds.GetRasterBand(bands[0])
            if selectedovi.index > 0:
                band = band.GetOverview(selectedovi.index - 1)

            if imgPixPerWinPix >= 1:
                data = band.ReadAsArray(ovleft, ovtop, 
                        ovxsize, ovysize,
                        dspRastXSize, dspRastYSize)
            else:
                dataTmp = band.ReadAsArray(ovleft, ovtop, 
                        ovxsize, ovysize)
                data = replicateArray(dataTmp, (dspRastYSize, dspRastXSize), 
                    dspLeftExtra, dspTopExtra, dspRightExtra,
                         dspBottomExtra)

        else:
            datalist = []
            for bandnum in bands:
                band = ds.GetRasterBand(bandnum)
                if selectedovi.index > 0:
                    band = band.GetOverview(selectedovi.index - 1)

                if imgPixPerWinPix >= 1:
                    data = band.ReadAsArray(ovleft, ovtop, 
                            ovxsize, ovysize,
                            dspRastXSize, dspRastYSize)
                else:
                    dataTmp = band.ReadAsArray(ovleft, ovtop, 
                            ovxsize, ovysize)
                    data = replicateArray(dataTmp, (dspRastYSize, dspRastXSize), 
                                dspLeftExtra, dspTopExtra, dspRightExtra,
                                dspBottomExtra)

                datalist.append(data)

            # stack 
            data = numpy.array(datalist)

    return data, dataslice

