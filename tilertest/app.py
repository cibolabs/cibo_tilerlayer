# This file is part of Cibo Tiler.
# Copyright (C) 2024 Cibolabs.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
Tester for cibo_tilerlayer. Makes a STAC query and uses Sentinel-2 data
for input.

"""
import os
import shutil
import tempfile

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools import Logger
from aws_lambda_powertools import Metrics
from osgeo import gdal

# As a shortcut you can run:
# cp layers/cibo/cibotiler/tiling.py tilertest/
# and import tiling
# instead of the command below when testing. 
# This will mean that you don't need to rebuild the layer
# each time there is a change.
# Remember to revert (and delete tilertest/tiling.py before deploying!
# import tiling
from cibotiler import tiling


# Some test colour intervals
INTERVALS = [((0, 0), [255, 255, 255, 255]), ((1, 1), [215, 25, 28, 255]), 
    ((1, 25), [215, 25, 28, 255]), ((26, 50), [234, 99, 62, 255]), 
    ((51, 75), [253, 174, 97, 255]), ((76, 100), [254, 215, 145, 255]), 
    ((101, 125), [255, 255, 192, 255]), ((126, 500), [211, 236, 149, 255]), 
    ((501, 750), [166, 217, 106, 255]), ((751, 1000), [54, 162, 40, 255]), 
    ((1001, 2000), [8, 96, 9, 255]), ((1001, 2000), [14, 39, 17, 255]), 
    ((2001, 3000), [255, 0, 255, 255]), ((3001, 4000), [148, 33, 225, 255])]

# test colour points
POINTS = [(0, [255, 255, 255, 255]), (1, [215, 25, 28, 255]), 
    (25, [215, 25, 28, 255]), (50, [234, 99, 62, 255]), 
    (75, [253, 174, 97, 255]), (100, [254, 215, 145, 255]), 
    (250, [255, 255, 192, 255]), (500, [211, 236, 149, 255]), 
    (750, [166, 217, 106, 255]), (200, [54, 162, 40, 255]), 
    (300, [8, 96, 9, 255]), (400, [14, 39, 17, 255]), 
    (700, [255, 0, 255, 255]), (1000, [148, 33, 225, 255])]

# If this assert fails then there is something wrong with 
# your SAM install. Try installing locally (in your home dir).
LD_PATH = os.getenv('LD_LIBRARY_PATH')
assert LD_PATH.startswith('/opt/python/lib')

app = APIGatewayRestResolver()
logger = Logger()
metrics = Metrics(namespace="Powertools")

gdal.UseExceptions()


def makeVRT(paths):
    """
    Functions are passed a list of input tiles, wrap this in a vrt
    as EPSG:3857.
    Lambda's share /tmp so we need to be careful - different requests
    could refer to different files so we create a temp dir to hold
    the files.

    Returns a tuple with both the vrt to use and the directory to remove
    when finished.
    """
    tempDir = tempfile.mkdtemp()
    stackVRT = os.path.join(tempDir, 's2stack.vrt')
    warpVRT = os.path.join(tempDir, 's2warp.vrt')

    # first stack
    vrt_options = gdal.BuildVRTOptions(separate=True)
    vrtStack = gdal.BuildVRT(stackVRT, paths, options=vrt_options)
    vrtStack.FlushCache()
    vrtStack = None

    # then warp
    warp_options = gdal.WarpOptions(
        xRes=80, yRes=80, 
        targetAlignedPixels=True, 
        dstSRS='EPSG:3857')
    vrt = gdal.Warp(warpVRT, stackVRT, options=warp_options)
    vrt.FlushCache()
        
    return warpVRT, tempDir


########################################
# Below are the single date tests

@app.post('/test_colormap_interval/<z>/<x>/<y>', cors=True)
def doColorMapIntervalTest(z: int, x: int, y: int):
    """
    Do a simple test of the color map interval stuff
    """
    paths = app.current_event.json_body['paths']
    vrt, tempdir = makeVRT(paths)
    colormap = tiling.createColorMapFromIntervals(INTERVALS)
    tile = tiling.getTile(vrt, z, x, y, bands=[1], 
        colormap=colormap)

    shutil.rmtree(tempdir)

    return Response(body=tile.getvalue(),
                status_code=200, headers={'Content-Type': 'image/png'})


@app.post('/test_colormap_point/<z>/<x>/<y>', cors=True)
def doColorMapPointTest(z: int, x: int, y: int):
    """
    Do a simple test of the color map interpolation stuff
    """
    paths = app.current_event.json_body['paths']
    vrt, tempdir = makeVRT(paths)
    colormap = tiling.createColorMapFromPoints(POINTS)
    tile = tiling.getTile(vrt, z, x, y, bands=[1], 
        colormap=colormap)

    shutil.rmtree(tempdir)

    return Response(body=tile.getvalue(),
                status_code=200, headers={'Content-Type': 'image/png'})


@app.post('/test_rescale/<z>/<x>/<y>', cors=True)
def doRescaleTest(z: int, x: int, y: int):
    """
    Rescale the FC (3 bands, all 100-200).
    """
    paths = app.current_event.json_body['paths']
    vrt, tempdir = makeVRT(paths)
    tile = tiling.getTile(vrt, z, x, y, bands=[1, 2, 3],
        rescaling=[(0, 1000), (0, 1000), (0, 1000)])

    shutil.rmtree(tempdir)

    return Response(body=tile.getvalue(),
                status_code=200, headers={'Content-Type': 'image/png'})


@app.post('/test_rescale_nn/<z>/<x>/<y>', cors=True)
def doRescaleTestNN(z: int, x: int, y: int):
    """
    Rescale the FC (3 bands, all 100-200).
    """
    paths = app.current_event.json_body['paths']
    vrt, tempdir = makeVRT(paths)
    tile = tiling.getTile(vrt, z, x, y, 
        bands=[1, 2, 3], resampling='near',
        rescaling=[(0, 1000), (0, 1000), (0, 1000)])

    shutil.rmtree(tempdir)

    return Response(body=tile.getvalue(),
                status_code=200, headers={'Content-Type': 'image/png'})


@app.post('/test_rescale_bilinear/<z>/<x>/<y>', cors=True)
def doRescaleTestBilinear(z: int, x: int, y: int):
    """
    Rescale the FC (3 bands, all 100-200).
    """
    paths = app.current_event.json_body['paths']
    vrt, tempdir = makeVRT(paths)
    tile = tiling.getTile(vrt, z, x, y,
        bands=[1, 2, 3], resampling='bilinear',
        rescaling=[(0, 1000), (0, 1000), (0, 1000)])

    shutil.rmtree(tempdir)

    return Response(body=tile.getvalue(),
                status_code=200, headers={'Content-Type': 'image/png'})


########################################
# Below are the mosaic tests


def get_all_vrts(paths):
    """
    Helper function for the 'mosaic' testing endpoints
    Takes a list, each item is a list with all the bands
    for a date.
    """
    vrts = []
    tempdirs = []
    for sub_path in paths:
        vrt, tempdir = makeVRT(sub_path)
        vrts.append(vrt)
        tempdirs.append(tempdir)

    return vrts, tempdirs


def clean_tempdirs(tempdirs):
    """
    Helper to remove a each directory in a list
    """
    for t in tempdirs:
        shutil.rmtree(t)


@app.post('/test_colormap_interval_mosaic/<z>/<x>/<y>', cors=True)
def doColorMapIntervalTestMos(z: int, x: int, y: int):
    """
    Do a simple test of the color map interval stuff
    """
    paths = app.current_event.json_body['paths']
    vrts, tempdirs = get_all_vrts(paths)
    colormap = tiling.createColorMapFromIntervals(INTERVALS)
    tile = tiling.getTileMosaic(vrts, z, x, y, bands=[1], 
        colormap=colormap)

    clean_tempdirs(tempdirs)
    return Response(body=tile.getvalue(),
                status_code=200, headers={'Content-Type': 'image/png'})


@app.post('/test_colormap_point_mosaic/<z>/<x>/<y>', cors=True)
def doColorMapPointTestMos(z: int, x: int, y: int):
    """
    Do a simple test of the color map interpolation stuff
    """
    paths = app.current_event.json_body['paths']
    vrts, tempdirs = get_all_vrts(paths)
    colormap = tiling.createColorMapFromPoints(POINTS)
    tile = tiling.getTileMosaic(vrts, z, x, y, bands=[1], 
        colormap=colormap)

    clean_tempdirs(tempdirs)
    return Response(body=tile.getvalue(),
                status_code=200, headers={'Content-Type': 'image/png'})


@app.post('/test_rescale_mosaic/<z>/<x>/<y>', cors=True)
def doRescaleTestMos(z: int, x: int, y: int):
    """
    Rescale the FC (3 bands, all 100-200).
    """
    paths = app.current_event.json_body['paths']
    vrts, tempdirs = get_all_vrts(paths)
    tile = tiling.getTileMosaic(vrts, z, x, y, bands=[1, 2, 3],
        rescaling=[(0, 1000), (0, 1000), (0, 1000)])

    clean_tempdirs(tempdirs)
    return Response(body=tile.getvalue(),
                status_code=200, headers={'Content-Type': 'image/png'})


@app.post('/test_rescale_nn_mosaic/<z>/<x>/<y>', cors=True)
def doRescaleTestNNMos(z: int, x: int, y: int):
    """
    Rescale the FC (3 bands, all 100-200).
    """
    paths = app.current_event.json_body['paths']
    vrts, tempdirs = get_all_vrts(paths)
    tile = tiling.getTileMosaic(vrts, z, x, y, 
        bands=[1, 2, 3], resampling='near',
        rescaling=[(0, 1000), (0, 1000), (0, 1000)])

    clean_tempdirs(tempdirs)
    return Response(body=tile.getvalue(),
                status_code=200, headers={'Content-Type': 'image/png'})


@app.post('/test_rescale_bilinear_mosaic/<z>/<x>/<y>', cors=True)
def doRescaleTestBilinearMos(z: int, x: int, y: int):
    """
    Rescale the FC (3 bands, all 100-200).
    """
    paths = app.current_event.json_body['paths']
    vrts, tempdirs = get_all_vrts(paths)
    tile = tiling.getTileMosaic(vrts, z, x, y,
        bands=[1, 2, 3], resampling='bilinear',
        rescaling=[(0, 1000), (0, 1000), (0, 1000)])

    clean_tempdirs(tempdirs)
    return Response(body=tile.getvalue(),
                status_code=200, headers={'Content-Type': 'image/png'})


# Enrich logging with contextual information from Lambda
@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
# Adding tracer
# See: https://awslabs.github.io/aws-lambda-powertools-python/latest/core/tracer/
# @tracer.capture_lambda_handler
# ensures metrics are flushed upon request completion/failure and capturing ColdStart metric
@metrics.log_metrics(capture_cold_start_metric=True)
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    return app.resolve(event, context)
