"""
Tester for cibo_tilerlayer
"""
import os

from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools import Logger
from aws_lambda_powertools import Metrics
from aws_lambda_powertools.metrics import MetricUnit

IN_TSDM_FILE = '/vsis3/cibo-test-oregon/cibo_tilerlayer/median_tsdm_aus_20240129_wm_r80m_v2.vrt'
IN_FC_FILE = '/vsis3/cibo-test-oregon/cibo_tilerlayer/median_fc_aus_20240129_wm_r80m_v1.vrt'
TEST_Z = 7
TEST_X = 115
TEST_Y = 74

TSDM_INTERVALS = [((0, 0), [255, 255, 255, 255]), ((1, 1), [215, 25, 28, 255]), 
    ((1, 250), [215, 25, 28, 255]), ((251, 500), [234, 99, 62, 255]), 
    ((501, 750), [253, 174, 97, 255]), ((751, 1000), [254, 215, 145, 255]), 
    ((1001, 1250), [255, 255, 192, 255]), ((1251, 1500), [211, 236, 149, 255]), 
    ((1501, 1750), [166, 217, 106, 255]), ((1751, 2000), [54, 162, 40, 255]), 
    ((2001, 3000), [8, 96, 9, 255]), ((3001, 4000), [14, 39, 17, 255]), 
    ((4001, 5000), [255, 0, 255, 255]), ((5001, 6000), [148, 33, 225, 255])]

TSDM_POINTS = [(0, [255, 255, 255, 255]), (1, [215, 25, 28, 255]), 
    (250, [215, 25, 28, 255]), (500, [234, 99, 62, 255]), 
    (750, [253, 174, 97, 255]), (1000, [254, 215, 145, 255]), 
    (1250, [255, 255, 192, 255]), (1500, [211, 236, 149, 255]), 
    (1750, [166, 217, 106, 255]), (2000, [54, 162, 40, 255]), 
    (3000, [8, 96, 9, 255]), (4000, [14, 39, 17, 255]), 
    (5000, [255, 0, 255, 255]), (6000, [148, 33, 225, 255])]

app = APIGatewayRestResolver()
logger = Logger()
metrics = Metrics(namespace="Powertools")

# As a shortcut you can run:
# layers/gdal/cibotiling/cibotiling.py tilertest/
# and import cibotiling
# instead of the command below when testing. 
# This will mean that you don't need to rebuild the layer
# each time there is a change.
# Remember to revert (and delete tilertest/cibotiling.py before deploying!
from cibotiling import cibotiling
#import cibotiling

@app.get('/test_colormap_interval', cors=True)
def doColorMapIntervalTest():
    """
    Do a simple test of the color map interval stuff
    """
    colormap = cibotiling.createColorMapFromIntervals(TSDM_INTERVALS)
    tile = cibotiling.getTile(IN_TSDM_FILE, TEST_Z, TEST_X, TEST_Y, bands=[1], 
        colormap=colormap)

    return Response(body=tile.getvalue(),
                status_code=200, headers={'Content-Type': 'image/png'})


@app.get('/test_colormap_point', cors=True)
def doColorMapPointTest():
    """
    Do a simple test of the color map interpolation stuff
    """
    colormap = cibotiling.createColorMapFromPoints(TSDM_POINTS)
    tile = cibotiling.getTile(IN_TSDM_FILE, TEST_Z, TEST_X, TEST_Y, bands=[1], 
        colormap=colormap)

    return Response(body=tile.getvalue(),
                status_code=200, headers={'Content-Type': 'image/png'})


@app.get('/test_rescale', cors=True)
def doRescaleTest():
    """
    Rescale the FC (3 bands, all 100-200).
    """
    tile = cibotiling.getTile(IN_FC_FILE, TEST_Z, TEST_X, TEST_Y, bands=[1, 2, 3],
        rescaling=[(100, 200), (100, 200), (100, 200)])

    return Response(body=tile.getvalue(),
                status_code=200, headers={'Content-Type': 'image/png'})

    
# Enrich logging with contextual information from Lambda
@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
# Adding tracer
# See: https://awslabs.github.io/aws-lambda-powertools-python/latest/core/tracer/
#@tracer.capture_lambda_handler
# ensures metrics are flushed upon request completion/failure and capturing ColdStart metric
@metrics.log_metrics(capture_cold_start_metric=True)
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    return app.resolve(event, context)
