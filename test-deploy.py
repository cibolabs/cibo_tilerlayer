#!/usr/bin/env python3

"""
Test harness for cibo_tilerlayer

"""

import io
import time
import argparse
import subprocess
import requests
from PIL import Image
import numpy

DFLT_STARTWAIT = 10 # seconds


def getCmdArgs():
    """
    Get the command line args
    """
    p = argparse.ArgumentParser()
    p.add_argument('-e', '--environment', choices=['dev', 'prod'],
        default="dev", help="Environment to use. (default=%(default)s)")
    p.add_argument('-m', '--mode', choices=['test', 'deploy'],
        default='test', 
        help="whether to do a local test or deploy the layer. (default=%(default)s)")
    p.add_argument("--wait", default=DFLT_STARTWAIT,
        help="Number of seconds to wait for api before the child " +
            "process is assumed to be ready for testing. (default=%(default)s)")

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
    for n in range(arr.shape[-1]):
        a = arr[:, :, n]
        minMaxs.add((a.min(), a.max()))

    if len(minMaxs) == 1:
        # sometimes PIL coverts 2 band images (val, alpha)
        # to 4 band ones by repeating the first band.
        raise SystemExit('All bands are the same value')


def createTests():
    """
    Create some tests
    """
    tests = {}
    tests['tsdm_interval'] = '/test_colormap_interval'
    tests['tsdm_point'] = '/test_colormap_point'
    tests['test_rescale'] = '/test_rescale'
    return tests


def main():
    """
    Main function
    """
    cmdargs = getCmdArgs()

    # ensure built first
    cmd = ['sam', 'build', '--config-env', cmdargs.environment]
    subprocess.check_call(cmd)

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
                openPNGAndGetMean(outdata)
        finally:
            proc.terminate()
            proc.wait()

    else:
        cmd = ['sam', 'deploy', '--config-env', cmdargs.environment]
        subprocess.check_call(cmd)
    

if __name__ == '__main__':
    main()
