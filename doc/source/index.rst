.. CiboTiler documentation master file, created by
   sphinx-quickstart on Mon Oct 21 14:05:20 2024.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

CiboTiler documentation
=======================

.. toctree::
   :maxdepth: 2
   :caption: Contents:

Introduction
------------

CiboTiler is for those who:

- want to be able to serve up imagery in a web tiler without running gdal2tiles
- have imagery already in EPSG:3857
- are comfortable deploying solutions with AWS Lambda or similar

What it does
------------

Given a GDAL readable image and a X/Y/Z tile location (plus some information on bands/how you want it displayed etc)
it returns an image file to display in the client. For best performance, ensure a reasonable
set of overview layers are present in the input image.

How you would likely use it
---------------------------

To create an HTTP endpoint (using AWS Lambda or similar) to serve up tiles from your image(s).

Example
-------

:meth:`cibotiler.tiling.getTile` is the main interface. For the simplest case when you already 
have pre-stretched image here is how you might use this package::

    from cibotiler import tiling
    
    # X, Y, Z obtained from the client somehow, for example as path or query parameters
    img = tiling.getTile('/path/to/image.tif', Z, X, Y, bands=[1, 2, 3])
    # return img to the client
    

For a more complex situation where you wish to rescale imagery on the fly (usually between
0-255) use the `rescaling` parameter::

    img = tiling.getTile('/path/to/image.tif', Z, X, Y, bands=[1, 2, 3],
        rescaling=[[90, 123], [32, 211], [87, 198]])
        

For applying a colormap to a single band, use the :meth:`cibotiler.tiling.createColorMapFromIntervals` or
:meth:`cibotiler.tiling.createColorMapFromPoints` functions::

    cmap = tiling.createColorMapFromPoints([(0, [255, 255, 255, 0]), (50, [32, 58, 102, 255]), (80, [10, 67, 21, 255)])
    img = tiling.getTile('/path/to/image.tif', Z, X, Y, colormap=cmap)
    

See `tilertest/app.py` for a working example.

Download
--------

`Releases <https://github.com/cibolabs/cibo_tilerlayer/releases>`__
and
`Source code <https://github.com/cibolabs/cibo_tilerlayer>`__
from Github.

Installation
------------

See `README.md <https://github.com/cibolabs/cibo_tilerlayer/blob/main/README.md>`__ for information.

Guides
=======

.. toctree::
   :maxdepth: 1
   
   api

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
