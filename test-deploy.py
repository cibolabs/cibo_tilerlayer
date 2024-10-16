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
import subprocess
import requests
from PIL import Image
import numpy
import boto3

DFLT_STARTWAIT = 20  # seconds
DFLT_AWSREGION = 'us-west-2'


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

    cmdargs = p.parse_args()
    return cmdargs


def openPNGAndGetMean(data):
    """
    Open a PNG. Check there are 4 bands. 

    TODO: be more thorough in checks
    """
    img = Image.open(io.BytesIO(data))
    arr = numpy.array(img)
    assert len(arr.shape) == 3
    # Not sure why the indexing is qround the other way
    assert arr.shape[-1] == 4
    minMaxs = set()
    for n in range(min(arr.shape[-1], 3)):  # ignore Alpha
        a = arr[:, :, n]
        minMaxs.add((a.min(), a.max(), a.mean()))

    if len(minMaxs) == 1:
        # sometimes PIL coverts 2 band images (val, alpha)
        # to 4 band ones by repeating the first band.
        print('All bands are the same value')
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


def createTests():
    """
    Create some tests
    """
    tests = {}
    tests['tsdm_interval'] = '/test_colormap_interval'
    tests['tsdm_point'] = '/test_colormap_point'
    tests['test_rescale'] = '/test_rescale'
    tests['test_rescale_nn'] = '/test_rescale_nn'
    tests['test_rescale_bilinear'] = '/test_rescale_bilinear'
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

            tests = createTests()
            for testName, testEndpoint in tests.items():
                print(testName)
                testURL = 'http://127.0.0.1:3000' + testEndpoint
                r = requests.get(testURL, headers={'Accept': 'image/png'})
                outdata = r.content
                ok = False
                ok = openPNGAndGetMean(outdata)
                if ok and cmdargs.save:
                    saveImage(outdata, testName)
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

        tests = createTests()
        for testName, testEndpoint in tests.items():
            testURL = url + testEndpoint
            print(testName, testURL)
            r = requests.get(testURL, headers={'Accept': 'image/png'})
            outdata = r.content
            ok = False
            ok = openPNGAndGetMean(outdata)
            if not ok:
                break
            if cmdargs.save:
                saveImage(outdata, testName)

    print('result', ok)


if __name__ == '__main__':
    main()
