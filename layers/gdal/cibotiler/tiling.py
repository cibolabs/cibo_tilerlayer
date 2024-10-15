"""
Supporting functions for creating a tiler.

Based on code from TuiView. 

Main function is getTile(). An application may want to call
createColorMapFromIntervals()/createColorMapFromPoints() to obtain
a colormap in the correct format to getTile(). 

The other functions in this module are for internal use
and not intended for use by an application.

"""

import io
import threading
import numpy
from osgeo import gdal
from osgeo import gdal_array

from . import resamplerhelper

gdal.UseExceptions()


MERCATOR_TILE_SIZE = 512

# Don't use the numbers from: http://epsg.io/3857
# The correct numbers are here: https://github.com/OSGeo/gdal/blob/master/gdal/swig/python/gdal-utils/osgeo_utils/gdal2tiles.py#L278
# Not sure why the difference...
MERCATOR_X_ORIGIN = -20037508.342789244
MERCATOR_Y_ORIGIN = 20037508.342789244


def getTile(filename, z, x, y, bands=None, rescaling=None, colormap=None, 
        resampling='near', fmt='PNG', tileSize=256, outTileType=numpy.uint8,
        metadata=None):
    """
    Main function. By opening the given file the correct web mercator
    tile is selected and extracted and converted into an image
    format using the methods definited by the parameters to this function.

    Parameters
    ----------
    filename : str or gdal.Dataset
        The name of the file to extract the tile from or an open GDAL
        dataset object. This file should be in webmercator (EPSG:3857) 
        projection. Use a path starting with /vsis3 to open from an 
        S3 bucket. The Lambda must be set up with the correct permissions 
        to access this file.
    z : int
        Zoom level
    x : int
        X position on the web mercator grid
    y : int
        Y position on the web mercator grid
    bands : None or sequence of ints, optional
        Passing None will result in all bands being read from the file.
        Otherwise a sequence of 1-based band indices are required. 
        Note that if you are passing a colormap there needs to be only
        one band, otherwise 3 (and only 3) are required.
    rescaling : sequence of (float, float) tuples, optional
        If the data is to be stretched, pass the range of values that
        the data is to be linearly stretched between. This should be the
        same length as 'bands'. Cannot be passed if colormap is used.
    colormap : numpy.array, optional
        A numpy array of shape (4, maxPixelValue) that defines the colormap
        to be applied to a single band image.
    resampling : str, optional
        Name of resampling method to be used when zoomed in more than the 
        image supported. Currently only 'near' and 'bilinear' is supported.
    fmt : str, optional
        Name of GDAL driver that creates the image format that needs to be
        returned. Defaults to 'PNG'
    tileSize : int, optional
        Size in pixels of the returned tile. The returned tile will be this
        size in both the x and y dimensions. Defaults to 256x256.
    outTileType : numpy dtype, optional
        The type of the returned image. Defaults to uint8.
    metadata : instance of Metadata, optional
        If previously obtained, an instance of a Metadata for filename.
        Default is this will be obtained withing the function.
    
    Returns:
    io.BytesIO
        The binary data that contains the image tile.

    """
    if isinstance(filename, gdal.Dataset):
        ds = filename
    else:
        ds = gdal.Open(filename)
    if metadata is None:
        metadata = Metadata(ds)

    # TODO: should we always assume WebMercator tiling?
    tlx, tly, brx, bry = getExtentforWebMTile(z, x, y)

    # bands
    if bands is None:
        bands = range(1, ds.RasterCount + 1)
    elif len(bands) != 1 and len(bands) != 3 and len(bands) != 4:
        raise ValueError('invalid number of bands (valid: 1, 3 or 4)')

    numOutBands = len(bands)
    if colormap is not None:
        # color map when applied will give us 4 bands
        numOutBands = 4
    elif len(bands) == 3:
        # we'll fake an alpha here
        numOutBands = 4
    # otherwise we 4 bands already or have single band data (?)

    data, dataslice = getRawImageChunk(ds, metadata, 
        tileSize, tileSize, tlx, tly, brx, bry, bands,
        resampling)

    nodataForBands = [metadata.allIgnore[n - 1] for n in bands]
    maxOutVal = numpy.iinfo(outTileType).max

    # output MEM dataset to write into
    gdalType = gdal_array.NumericTypeCodeToGDALTypeCode(outTileType)
    mem = gdal.GetDriverByName('MEM').Create('', tileSize, 
        tileSize, numOutBands, gdalType)

    alphaset = False
    nodataMask = None  # used (if set) when alphaset == False
    if data is None:
        # no data available for this area - return all zeros
        for n in range(4):
            band = mem.GetRasterBand(n + 1)
            band.Fill(0)
        alphaset = True
    else:
        imgData = numpy.zeros((tileSize, tileSize), dtype=outTileType)
        # rescale.
        if rescaling is not None:
            if len(rescaling) == 1:
                # same rescaling to every band
                minVal, maxVal = rescaling[0]
                minMaxRange = maxVal - minVal
                for n in range(len(bands)):
                    # cope with 2d/3d
                    databand = data
                    if len(bands) > 1:
                        databand = data[n]
                    rescaleddata = (databand.astype(float) - minVal).clip(min=0) * (maxOutVal / minMaxRange)
                    imgData[dataslice] = rescaleddata.clip(min=0, max=maxOutVal)
                    band = mem.GetRasterBand(n + 1)
                    band.WriteArray(imgData)
                    if nodataForBands[n] is not None:
                        mask = databand == nodataForBands[n]
                        if nodataMask is None:
                            nodataMask = mask
                        else:
                            nodataMask |= mask

            else:
                if len(rescaling) != len(bands):
                    raise ValueError("length of rescaling doesn't math number of bands")
                for n, (minVal, maxVal) in enumerate(rescaling):
                    minMaxRange = maxVal - minVal
                    rescaleddata = (data[n].astype(float) - minVal).clip(min=0) * (maxOutVal / minMaxRange)
                    imgData[dataslice] = rescaleddata.clip(min=0, max=maxOutVal)
                    band = mem.GetRasterBand(n + 1)
                    band.WriteArray(imgData)
                    if nodataForBands[n] is not None:
                        mask = data[n] == nodataForBands[n]
                        if nodataMask is None:
                            nodataMask = mask
                        else:
                            nodataMask |= mask

            alphaset = len(bands) >= 4

        elif colormap is not None:
            # Note: currently can't specify rescaling AND colormap
            _, maxCol = colormap.shape
            for n in range(4):
                imgData[dataslice] = colormap[n][data.clip(min=0, max=(maxCol - 1))]
                band = mem.GetRasterBand(n + 1)
                band.WriteArray(imgData)
            alphaset = True

        else:
            # just copy data
            for n in range(len(bands)):
                # cope with 2d/3d
                databand = data
                if len(bands) > 1:
                    databand = data[n]
                imgData[dataslice] = databand
                band = mem.GetRasterBand(n + 1)
                band.WriteArray(imgData)
                if nodataForBands[n] is not None:
                    mask = databand == nodataForBands[n]
                    if nodataMask is None:
                        nodataMask = mask
                    else:
                        nodataMask |= mask

            alphaset = len(bands) >= 4

    if not alphaset:
        band = mem.GetRasterBand(4)
        if nodataMask is not None:
            band.WriteArray(numpy.where(nodataMask, 
                outTileType(0), outTileType(maxOutVal)))
        else:
            band.Fill(maxOutVal)

    result = createBytesIOFromMEM(mem, fmt)
    return result


def getExtentforWebMTile(z, x, y):
    """
    Helper function for getting the projected extent for
    a web mercator tile (EPSG: 3857)

    Parameters
    ----------
    z : int
        Zoom level
    x : int
        X position on the web mercator grid
    y : int
        Y position on the web mercator grid

    Returns
    -------
    tuple of floats:
        (tlx, tly, brx, bry)

    """
    # https://wiki.osgeo.org/wiki/Tile_Map_Service_Specification#global-mercator
    units_per_pixel = 78271.516 / 2**int(z)
    tile_size = units_per_pixel * MERCATOR_TILE_SIZE
    
    tlx = MERCATOR_X_ORIGIN + (tile_size * int(x))
    tly = MERCATOR_Y_ORIGIN - (tile_size * int(y))
    brx = tlx + tile_size
    bry = tly - tile_size

    return (tlx, tly, brx, bry)


def createColorMapFromIntervals(intervals):
    """
    Helper function to convert a list of 
    ((minVal, maxVal), (r, g, b, a))
    tuples to a colormap expected by getTile()
    Note that the intervals list should be ordered
    by value.

    Parameters
    ----------
    intervals : sequence of ((min, max), (r, g, b, a)) tuples.
        This defines the colours for each interval. Is expected
        to be sorted. Note that undefined results will occur
        if there are missing ranges in the intervals.
        Note that the actual range set for each colour is
        (min - max-1). So the max for one range should be the
        min for the next range.

    Returns
    -------
    numpy.ndarray
        A colormap of shape (4, maxPixVal).
        

    """
    lastValues, _ = intervals[-1]
    maxVal = lastValues[1]
    result = numpy.empty((4, maxVal), dtype=numpy.uint8)

    for values, rgba in intervals:
        minVal, maxVal = values
        for idx, col in enumerate(rgba):
            result[idx, minVal:maxVal] = col
    return result


def createColorMapFromPoints(points):
    """
    Helper function to convert a list of
    (value, (r, g, b, a))
    tuples to a colormap expected by getTile()
    colors between these values are interpolated.
    It is expected that the list is sorted.

    Parameters
    ----------
    points : sequence of (value, (r, g, b, a)) tuples
        The points to interpolate the rest of the
        values from.

    Returns
    -------
    numpy.ndarray
        A colormap of shape (4, maxPixVal).

    """
    lastValue, _ = points[-1]
    result = numpy.empty((4, lastValue + 1), dtype=numpy.uint8)

    xobs = numpy.array([val for val, _ in points])
    xinterp = numpy.linspace(0, lastValue, lastValue + 1)
    for idx in range(4):
        # TODO: does it make sense to use interpolation for Alpha?
        yobs = [rgba[idx] for _, rgba in points]
        yinterp = numpy.interp(xinterp, xobs, yobs)
        result[idx] = yinterp
    return result


def createColorMapFromRAT(filename, band=1):
    """
    Helper function to create a colormap from the 
    Raster Attribute Table of a file.

    Parameters
    ----------
    filename : str or gdal.Dataset
        The name of the file to extract the RAT from or an open GDAL
        dataset object.
    band : int, optional
        The 1-based index of the band to extrat the RAT from.
        Defaults to the first band.

    Returns
    -------
    numpy.ndarray
        A colormap of shape (4, maxPixVal).

    """
    if isinstance(filename, gdal.Dataset):
        ds = filename
    else:
        ds = gdal.Open(filename)

    bandObj = ds.GetRasterBand(band)
    assert bandObj.GetMetadataItem('LAYER_TYPE') == 'thematic'
    rat = bandObj.GetDefaultRAT()
    redIdx = rat.GetColOfUsage(gdal.GFU_Red)
    blueIdx = rat.GetColOfUsage(gdal.GFU_Blue)
    greenIdx = rat.GetColOfUsage(gdal.GFU_Green)
    alphaIdx = rat.GetColOfUsage(gdal.GFU_Alpha)
    if redIdx == -1 or blueIdx == -1 or greenIdx == -1 or alphaIdx != -1:
        raise ValueError("Unable to find all color columns")

    size = rat.GetRowCount()
    result = numpy.empty((4, size), dtype=numpy.uint8)
    result[0] = rat.ReadAsArray(redIdx)
    result[1] = rat.ReadAsArray(blueIdx)
    result[2] = rat.ReadAsArray(greenIdx)
    result[3] = rat.ReadAsArray(alphaIdx)
    return result


def createBytesIOFromMEM(mem, fmt):
    """
    Given a GDAL in memory dataset ("MEM" driver)
    convert to the given format and dump as a io.BytesIO for returning
    to client.

    Parameters
    ----------
    mem : GDALDataset
        An open GDAL Dataset object for the 'MEM' driver that
        has the data to be turned into a BytesIO.
    fmt : str
        Name of GDAL driver that creates the image format that needs to be
        returned. 

    Returns
    -------
    io.BytesIO
        The binary data that contains the image tile.

    """
    # ensure all data written
    mem.FlushCache()
    
    # see https://lists.osgeo.org/pipermail/gdal-dev/2016-August/045030.html
    # Create an in-memory raster first then using CreateCopy() to create
    # a .png as the PNG driver can't create a brand new file.

    # in case we are being calling from different threads
    # make the filename unique to this thread
    memName = '/vsimem/output_%d.png' % threading.get_ident()

    ds = gdal.GetDriverByName(fmt).CreateCopy(memName, mem)
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
class OverviewInfo:
    """
    Stores size and index of an overview.

    Parameters
    ----------
    xsize : int
        Number of columns in the overview
    ysize : int
        Numer of rows inthe overview
    fullrespixperpix : float
        Number of pixels at full resolution that each
        overview pixel covers
    index : int
        The index of the overview. 0 is the full res image.
    """
    def __init__(self, xsize, ysize, fullrespixperpix, index):
        self.xsize = xsize
        self.ysize = ysize
        self.fullrespixperpix = fullrespixperpix
        self.index = index


class OverviewManager:
    """
    This class contains a list of valid overviews
    and allows the best overview to be retrieved

    Attributes
    ----------
    overviews : list of OverviewInfo instances
        The overviews

    """
    def __init__(self):
        self.overviews = None

    def loadOverviewInfo(self, ds, bands):
        """
        Load the overviews from the GDAL dataset into a list
        bands should be a list or tuple of band indices.
        Checks are made that all lists bands contain the
        same sized overviews

        Parameters
        ----------
        ds : GDALDataset object
            The file to load the overviews in from
        bands : sequence of int
            The bands we are interested in

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

        Parameters
        ----------
        imgpixperwinpix : float
            The number of image pixels per pixels we want to display

        Returns
        -------
        Instance of OverviewInfo
            The overview that most closely matches (but has more
            pixels than required) the requested imgpixperwinpix
        """
        selectedovi = self.overviews[0]
        for ovi in self.overviews[1:]:
            if ovi.fullrespixperpix > imgpixperwinpix:
                break  # gone too far, selectedovi is selected
            else:
                # got here overview must be ok, but keep going
                selectedovi = ovi

        return selectedovi


class Metadata:
    """
    Class that holds all the 'metadata' about an object (ie size, projection etc)
    and can be passed around without re-requesting the data again.

    Parameters
    ----------
    ds : GDALDataset 
        Dataset to query

    Attributes
    ----------
    RasterXSize : int
        X Size of raster
    RasterYSize : int
        Y Size of raster
    RasterCount : int
        Number of bands
    thematic : bool
        Whether image is thematic or not
    transform : sequence of floats
        the geo transform of the image
    allIgnore : sequence of float
        The ignore value (or None if not set) for each band
    overviews : OverviewManager
        Information about the overview
    tlx, tly, brx, bry : floats
        Bounding box of the image in projected coords
    iInverse : sequence of floats
        The inverse geo transform of the image
    """
    def __init__(self, ds):
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


def pixel2displayF(col, row, origCol, origRow, imgPixPerWinPix):
    """
    From tuiview - convert pixel coordinates to display as float

    Parameters
    ----------
    col : int
        The column
    row : int
        The row
    origCol : int
        The column of the origin of the tile
    origRow : int
        The row of the origin of the tile
    imgPixPerWinPix : float
        The number of image pixels per tile pixel

    Returns
    -------
    tuple of float
        (x, y)

    """
    x = (col - origCol) / imgPixPerWinPix
    y = (row - origRow) / imgPixPerWinPix
    return (x, y)


def pixel2display(col, row, origCol, origRow, imgPixPerWinPix):
    """
    From tuiview - convert pixel coordinates to display - integer version

    Parameters
    ----------
    col : int
        The column
    row : int
        The row
    origCol : int
        The column of the origin of the tile
    origRow : int
        The row of the origin of the tile
    imgPixPerWinPix : float
        The number of image pixels per tile pixel

    Returns
    -------
    tuple of int
        (x, y)
    """
    x = int((col - origCol) / imgPixPerWinPix)
    y = int((row - origRow) / imgPixPerWinPix)
    return (x, y)


def getRawImageChunk(ds, metadata, xsize, ysize, tlx, tly, brx, bry, bands,
        resampling):
    """
    Also adapted from tuiview. returns requested chunk of image. Returns 
    the data and the dataslice that the data fits into the (ysize, xsize)
    output data.

    Parameters
    ----------
    ds : GDALDataset
        File to read the data from
    metadata : Metadata
        Metadata for the file
    xsize : int
        Number of columns to return
    ysize : int
        Number of rows to return
    tlx, tly, brx, bry : floats
        The bounds of the image in projected coords
    bands : sequence of ints
        The bands to read from
    resampling : str
        Name of resampling method to be used when zoomed in more than the 
        image supported. Currently only 'near' is supported.

    Returns
    -------
    tuple 
        The output data and slice. The first element of the tuple is the data
        read from the file. This may be None if the requested bounds are outside 
        of the file. If a single band was requested this will be a 2 dimensional
        array, otherwise it will be 3 dimensional
        The second element of the tuple is a slice object that defines where
        in the output tile to write the data. If the size of the returned
        data array is smaller than (ysize, xsize) this will be the location
        in the tile to write the data. For situations where only part of the
        requested bounds is within the image.

    """
    
    if resampling not in resamplerhelper.RESAMPLE_METHODS:
        raise ValueError('Unknown resample method {}'.format(resampling))
    resampleMethod = resamplerhelper.RESAMPLE_METHODS[resampling]

    # work out number of pixels
    imgPix_x = (brx - tlx) / metadata.transform[1]
    imgPix_y = (bry - tly) / metadata.transform[5]
    imgPixPerWinPix = imgPix_x / xsize

    # now work out which overview to use
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
            dspLeftExtra = int((dspRastLeft - dspRastAbsLeft) /
                fullrespixperovpix)
            dspTopExtra = int((dspRastTop - dspRastAbsTop) /
                fullrespixperovpix)
            dspRightExtra = int((dspRastAbsRight - dspRastRight) /
                fullrespixperovpix)
            dspBottomExtra = int((dspRastAbsBottom - dspRastBottom) /
                fullrespixperovpix)
            # be aware rounding errors
            dspRightExtra = max(dspRightExtra, 0)
            dspBottomExtra = max(dspBottomExtra, 0)

        dataslice = (slice(dspRastTop, dspRastTop + dspRastYSize),
            slice(dspRastLeft, dspRastLeft + dspRastXSize))

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
                marg = MarginsForResample(resampling, ovleft, ovtop,
                    ovxsize, ovysize, band)
                dataTmp = band.ReadAsArray(
                    ovleft - marg.left,
                    ovtop - marg.top,
                    ovxsize + marg.left + marg.right,
                    ovysize + marg.top + marg.bottom)
                ignore = metadata.allIgnore[bandnum - 1]
                data = resampleMethod(dataTmp,
                    (dspRastYSize, dspRastXSize),
                    dspLeftExtra + int(round(marg.left / imgPixPerWinPix)),
                    dspTopExtra + int(round(marg.top / imgPixPerWinPix)),
                    dspRightExtra + int(round(marg.right / imgPixPerWinPix)),
                    dspBottomExtra + int(round(marg.bottom / imgPixPerWinPix)),
                    ignore)

            datalist.append(data)

        if len(datalist) == 1:
            # For single band, we return a 2-d array
            data = datalist[0]
        else:
            # A 3-d array of all bands
            data = numpy.array(datalist)

    return data, dataslice


class MarginsForResample:
    """
    handle the margin information.
    TODO: add this to resamplehelper.py
    """
    def __init__(self, resampling, ovleft, ovtop, ovxsize, ovysize, band):
        if resampling == 'bilinear':
            # Desired margin
            margin = 1
            # For each block edge, the amount of margin actually possible
            # without going off the edge of the file
            self.left = min(margin, ovleft)
            self.right = min(margin, band.XSize - (ovleft + ovxsize))
            self.top = min(margin, ovtop)
            self.bottom = min(margin, band.YSize - (ovtop + ovysize))
        elif resampling == 'near':
            self.left = 0
            self.right = 0
            self.top = 0
            self.bottom = 0
        else:
            raise ValueError("Unknown resampling method '{}'".format(resampling))
