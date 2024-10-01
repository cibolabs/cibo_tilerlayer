"""
Helper functions for doing resampling
"""

import numpy
from . import resampler


# nearest neighbour - from TuiView
def replicateArray(arr, outsize, dspLeftExtra, dspTopExtra, dspRightExtra, 
        dspBottomExtra, ignore):
    """
    Replicate the data in the given 2-d array so that it increases
    in size to be outsize (ysize, xsize). 
    
    Replicates each pixel in both directions. 
    
    dspLeftExtra, dspTopExtra are the number of pixels to be shaved off the
    top and left. dspRightExtra, dspBottomExtra are the number of pixels
    to be shaved off the bottom and right of the result. This allows us
    to display fractional pixels.

    Parameters
    ----------
    arr : numpy.ndarray
        2 dimensional input data
    outsize : tuple of int
        The output size (xsize, ysize)
    dspLeftExtra : int
        number of pixels to be shaved off the left
    dspTopExtra : int
        number of pixels to be shaved off the top
    dspRightExtra : int
        number of pixels to be shaved off the right
    dspBottomExtra : int
        number of pixels to be shaved off the bottom
    ignore: float
        ignore value for input - currently ignored

    Returns
    -------
    numpy.ndarray

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

    
def bilinearResample(arr, outsize, dspLeftExtra, dspTopExtra, 
        dspRightExtra, dspBottomExtra, ignore):
    """
    Use bilinear interpolation on the given 2-d array so that it increases
    in size to be outsize (ysize, xsize). 
    
    dspLeftExtra, dspTopExtra are the number of pixels to be shaved off the
    top and left. dspRightExtra, dspBottomExtra are the number of pixels
    to be shaved off the bottom and right of the result. This allows us
    to display fractional pixels.

    Parameters
    ----------
    arr : numpy.ndarray
        2 dimensional input data
    outsize : tuple of int
        The output size (xsize, ysize)
    dspLeftExtra : int
        number of pixels to be shaved off the left
    dspTopExtra : int
        number of pixels to be shaved off the top
    dspRightExtra : int
        number of pixels to be shaved off the right
    dspBottomExtra : int
        number of pixels to be shaved off the bottom
    ignore: float
        ignore value for input. Can be None.

    Returns
    -------
    numpy.ndarray

    """    
    (ysize, xsize) = outsize
    
    # do the biliear over the full area and chop out the bits we
    # need. Did start changing the C++ code to only work
    # over required area, but this got very complex...
    rowCount = ysize + dspTopExtra + dspBottomExtra
    colCount = xsize + dspLeftExtra + dspRightExtra
    outarr = resampler.bilinear(arr, ignore, colCount, rowCount)
    
    outarr = outarr[dspTopExtra:rowCount - dspBottomExtra, 
        dspLeftExtra:colCount - dspRightExtra]
    return outarr
    

# Handy dictionary to lookup method in
RESAMPLE_METHODS = {'near': replicateArray, 'bilinear': bilinearResample}
