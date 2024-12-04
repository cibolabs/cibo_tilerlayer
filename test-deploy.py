#!/usr/bin/env python3

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
Test harness for cibo_tilerlayer.

Also used to deploy the layer and test function

"""

import io
import time
import argparse
import datetime
import subprocess
from osgeo import osr
from pystac_client import Client
import requests
from PIL import Image
import numpy
import boto3

DFLT_STARTWAIT = 20  # seconds
DFLT_AWSREGION = 'us-west-2'

TEST_Z = 7
TEST_X = 115
TEST_Y = 74
# More than 1:1
TEST_ZOOM_Z = 12
TEST_ZOOM_X = 3788  # this tile causes dspLeftExtra=1, so a good test. 3787 has dspLeftExtra=0 so an alternative
TEST_ZOOM_Y = 2373


MERCATOR_TILE_SIZE = 512

# Don't use the numbers from: http://epsg.io/3857
# The correct numbers are here: https://github.com/OSGeo/gdal/blob/master/gdal/swig/python/gdal-utils/osgeo_utils/gdal2tiles.py#L278
# Not sure why the difference...
MERCATOR_X_ORIGIN = -20037508.342789244
MERCATOR_Y_ORIGIN = 20037508.342789244

# back to start of search windor (from today)
DFLT_DAYS_BEFORE_TODAY = 15

osr.UseExceptions()


def getCmdArgs():
    """
    Get the command line args
    """
    p = argparse.ArgumentParser()
    p.add_argument('-e', '--environment', choices=['dev', 'prod'],
        default="dev", help="Environment to use. (default=%(default)s)")
    p.add_argument('-m', '--mode', choices=['test', 'deploy'],
        default='test', 
        help="whether to do a local test or deploy the layer before testing. (default=%(default)s)")
    p.add_argument("--wait", default=DFLT_STARTWAIT,
        help="Number of seconds to wait for api before the child " +
            "process is assumed to be ready for testing. (default=%(default)s)")
    p.add_argument('--skipdeploy', default=False, action="store_true",
        help="don't deploy, just test")
    p.add_argument('--awsregion', default=DFLT_AWSREGION,
        help="AWS Region to use. (default=%(default)s)")
    p.add_argument('--save', default=False, action="store_true",
        help="save output of tests as images")
    p.add_argument('--daysbeforetoday', default=DFLT_DAYS_BEFORE_TODAY, type=int,
        help="Number of days before today to start the STAC search window. (default=%(default)s)")
    p.add_argument('--layerpublic', default=False, action="store_true",
        help="Make deployed layer public (only valid with -m deploy)")
    p.add_argument('--maxdates', default=3, type=int,
        help="Maximum number of dates for testing mosaic functionality. (default=%(default)s)")
    p.add_argument('--ignoresame', default=False, action="store_true",
        help="Ignore the 'All bands are the same value' error which can happen when nodata is returned")

    cmdargs = p.parse_args()
    return cmdargs


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
    
    
def getPathsForTile(z, x, y, cmdargs):
    """
    For the given tile, do a search on the sentinel STAC.
    Return a list of the red, green and blue GDAL
    /vsis3 style paths into the 'sentinel-cogs' bucket
    """
    # Get coords in EPSG 3857 for this tile
    tlx, tly, brx, bry = getExtentforWebMTile(z, x, y)
    
    # convert to lat long for querying STAC
    sr1 = osr.SpatialReference()
    sr1.ImportFromEPSG(3857)
    
    sr2 = osr.SpatialReference()
    sr2.ImportFromEPSG(4326)
    sr2.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    
    trans = osr.CoordinateTransformation(sr1, sr2)
    
    tlx, tly, _ = trans.TransformPoint(tlx, tly)
    brx, bry, _ = trans.TransformPoint(brx, bry)
    
    # Do a daterange from today
    today = datetime.date.today()
    today_s = today.strftime("%Y-%m-%d")
    
    # back a few days
    start = today - datetime.timedelta(days=cmdargs.daysbeforetoday)
    start_s = start.strftime("%Y-%m-%d")
    
    # do stack query
    daterange = f'{start_s}/{today_s}'
    client = Client.open("https://earth-search.aws.element84.com/v1")
    s2Search = client.search(
        collections=['sentinel-2-l2a'],
        datetime=daterange,
        bbox=[tlx, bry, brx, tly],  # xmin, ymin, xmax, ymax
        query={'s2:nodata_pixel_percentage': {'lt': 25}}
    )
    # Show the results of the search
    if s2Search.matched() == 0:
        raise SystemExit("no matching images found")

    tiles = s2Search.items()
    count = 0
    all_paths = []
    for tile in tiles:
        paths = []
        # grab 3 bands
        for band in ['blue', 'green', 'red']:
            url = tile.assets[band].get_absolute_href()
            url = url.replace('https://sentinel-cogs.s3.us-west-2.amazonaws.com', '/vsis3/sentinel-cogs')
            paths.append(url)
        all_paths.append(paths)
        count += 1
        if count >= cmdargs.maxdates:
            break
        
    return all_paths
    

def openPNGAndGetMean(data, cmdargs):
    """
    Open a PNG. Check there are 4 bands. 

    TODO: be more thorough in checks
    """
    img = Image.open(io.BytesIO(data))
    img.save('/tmp/test.png')
    arr = numpy.array(img)
    assert len(arr.shape) == 3
    # Not sure why the indexing is around the other way
    assert arr.shape[-1] == 4
    minMaxs = set()
    for n in range(min(arr.shape[-1], 3)):  # ignore Alpha
        a = arr[:, :, n]
        minMaxs.add((a.min(), a.max(), a.mean()))

    if len(minMaxs) == 1:
        # sometimes PIL coverts 2 band images (val, alpha)
        # to 4 band ones by repeating the first band.
        print('All bands are the same value')
        if not cmdargs.ignoresame:
            return False

    return True
    

def saveImage(data, testName):
    """
    Save image as a .png file
    """
    data = io.BytesIO(data)
    fname = testName + ".png"
    with open(fname, "wb") as f:
        f.write(data.getbuffer())


def createTests(cmdargs):
    """
    Create some tests
    """
    pathsfortest = getPathsForTile(TEST_Z, TEST_X, TEST_Y, cmdargs)
    pathsfortest_zoom = getPathsForTile(TEST_ZOOM_Z, TEST_ZOOM_X, TEST_ZOOM_Y, cmdargs)
    
    tests = {}
    # First tests, just use one image
    tests['test_interval'] = ('/test_colormap_interval/{}/{}/{}'.format(
        TEST_Z, TEST_X, TEST_Y), pathsfortest[0])
    tests['test_point'] = ('/test_colormap_point/{}/{}/{}'.format(
        TEST_Z, TEST_X, TEST_Y), pathsfortest[0])
    tests['test_rescale'] = ('/test_rescale/{}/{}/{}'.format(
        TEST_Z, TEST_X, TEST_Y), pathsfortest[0])
    tests['test_rescale_nn'] = ('/test_rescale_nn/{}/{}/{}'.format(
        TEST_ZOOM_Z, TEST_ZOOM_X, TEST_ZOOM_Y), pathsfortest_zoom[0])
    tests['test_rescale_bilinear'] = ('/test_rescale_bilinear/{}/{}/{}'.format(
        TEST_ZOOM_Z, TEST_ZOOM_X, TEST_ZOOM_Y), pathsfortest_zoom[0])

    # do the first tests again, but using the mosaic functionality, passing multiple images in
    tests['test_interval_mosaic'] = ('/test_colormap_interval_mosaic/{}/{}/{}'.format(
        TEST_Z, TEST_X, TEST_Y), pathsfortest)
    tests['test_point_mosaic'] = ('/test_colormap_point_mosaic/{}/{}/{}'.format(
        TEST_Z, TEST_X, TEST_Y), pathsfortest)
    tests['test_rescale_mosaic'] = ('/test_rescale_mosaic/{}/{}/{}'.format(
        TEST_Z, TEST_X, TEST_Y), pathsfortest)
    tests['test_rescale_nn_mosaic'] = ('/test_rescale_nn_mosaic/{}/{}/{}'.format(
        TEST_ZOOM_Z, TEST_ZOOM_X, TEST_ZOOM_Y), pathsfortest_zoom)
    tests['test_rescale_bilinear_mosaic'] = ('/test_rescale_bilinear_mosaic/{}/{}/{}'.format(
        TEST_ZOOM_Z, TEST_ZOOM_X, TEST_ZOOM_Y), pathsfortest_zoom)
    
    return tests


def getStackOutputs(stackName, cmdargs):
    """
    Helper function to query the CloudFormation stack for outputs.
    """
    client = boto3.client('cloudformation', region_name=cmdargs.awsregion)
    resp = client.describe_stacks(StackName=stackName)
    if len(resp['Stacks']) == 0:
        raise SystemExit("Stack not created")
    outputsRaw = resp['Stacks'][0]['Outputs']
    # convert to a normal dictionary
    outputs = {}
    for out in outputsRaw:
        key = out['OutputKey']
        value = out['OutputValue']
        outputs[key] = value
    return outputs


def main():
    """
    Main function
    """
    cmdargs = getCmdArgs()

    # ensure built first
    cmd = ['sam', 'build', '--config-env', cmdargs.environment]
    subprocess.check_call(cmd)
    ok = False

    if cmdargs.mode == 'test':
        # deploy locally then run tests
        try:
            cmd = ['sam', 'local', 'start-api', '--config-env', cmdargs.environment]
            proc = subprocess.Popen(cmd)
            time.sleep(cmdargs.wait)
            if proc.poll() is not None:
                raise SystemExit("Child exited")

            tests = createTests(cmdargs)
            for testName, (testEndpoint, paths) in tests.items():
                print(testName)
                data = {'paths': paths}
                testURL = 'http://127.0.0.1:3000' + testEndpoint
                r = requests.post(testURL, json=data, 
                    headers={'Accept': 'image/png'})
                outdata = r.content
                ok = False
                ok = openPNGAndGetMean(outdata, cmdargs)
                if cmdargs.save:
                    saveImage(outdata, testName)
                if not ok:
                    break
        finally:
            proc.terminate()
            proc.wait()

    else:
        if not cmdargs.skipdeploy:
            cmd = ['sam', 'deploy', '--config-env', cmdargs.environment]
            subprocess.check_call(cmd)
            time.sleep(30)

        stackName = 'cibo-tilerlayer-' + cmdargs.environment
        stackOutputs = getStackOutputs(stackName, cmdargs)
        url = stackOutputs['ApiURL']

        tests = createTests(cmdargs)
        for testName, (testEndpoint, paths) in tests.items():
            testURL = url + testEndpoint
            print(testName, testURL)
            data = {'paths': paths}
            r = requests.post(testURL, json=data, 
                headers={'Accept': 'image/png'})
            outdata = r.content
            ok = False
            ok = openPNGAndGetMean(outdata, cmdargs)
            if cmdargs.save:
                saveImage(outdata, testName)
            if not ok:
                break

        if cmdargs.layerpublic:
            arn = stackOutputs['LayerARN']
            components = arn.split(':')
            layer_version = int(components[-1])
            layer_name = components[-2]

            lambda_client = boto3.client("lambda", region_name=cmdargs.awsregion)
            lambda_client.add_layer_version_permission(
                LayerName=layer_name,
                VersionNumber=layer_version,
                StatementId="make_public",
                Action="lambda:GetLayerVersion",
                Principal="*",
            )
            
    print('result', ok)


if __name__ == '__main__':
    main()
