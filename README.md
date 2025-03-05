# cibo_tilerlayer

## What is cibo_tilerlayer?

Please refer to the [documentation](https://cibotilerlayer.readthedocs.io/).

## Current Layer Versions

| Layer Version | ARN | Python Version | Architecture |
| ------------- | --- | -------------- | ------------ |
| 1 | arn:aws:lambda:us-west-2:331561773057:layer:CiboTilerLayer-python312-arm64-prod:1 | 3.12 | arm64 |

## Documentation 

Use one of the layers above in your Lambda function. You should now be able to import the 
`cibotiling` module as documented below.

If you wish to install the `cibotiling` package in your existing Python environment, run ::

    cd layers/cibo
    pip install .


For more information on how to use this package, please refer to the [documentation](https://cibotilerlayer.readthedocs.io/).


## Developer Guide

Building CiboTiler is a little bit more complex than just installing some Python files.
We need to have GDAL available with the Python bindings, plus all enough of the GDAL 
dependencies (GEOS, PROJ etc). See [our makefile](https://github.com/cibolabs/cibo_tilerlayer/blob/main/layers/cibo/Makefile)
for more information.

Currently, we are focused on building for ARM on a AWS Graviton machines and make layers
available for this architecture. We will make `x86_64` builds available if there is demand. Do do this yourself
you will need to pass through the `Architecture` parameter as `x86_64` into `template.yaml`.

AWS SAM needs to be installed first. 

The install of SAM under Ubuntu isn't totally straightforward. The install
instructions are here: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html

These instructions seem to indicate that installing SAM globally on the machine
works. However, we have discovered that this appears to 
introduce a problem where the `LD_LIBRARY_PATH` in the test Lambda function is set 
incorrectly. There is now an assert in the test function to catch this situation.

We instead recommend that SAM is installed into a Python virtual env as shown below:

```
python3 -m venv .sam_venv
source .sam_venv/bin/activate
wget https://github.com/aws/aws-sam-cli/releases/latest/download/aws-sam-cli-linux-arm64.zip
unzip aws-sam-cli-linux-arm64.zip
cd aws-sam-cli-src
pip install .
```

You will need to activate this virtual env each time you wish to work on cibo_tilerlayer.

### Testing

NOTE: if you get a 'port in use' error when running `test-deploy.py`, run ::

	ps -ef | grep sam

And look for the process that starts with `/usr/bin/python3 /path/to/sam` and
`kill` it.

Testing and deployment are handled by the `test-deploy.py` script. Note that everything
has 2 modes - 'dev' and 'prod' - this is controlled by the `--environment` switch.

`test-deploy.py` does a build of the layer first before running anything else. 

Note that the test data uses the Sentinel-2 COGS STAC index to find suitable images
to test with and this data is within the us-west-2 AWS Region.

For testing, use the `-m test` mode to `test-deploy.py`. This will spin up a local 
lambda function and run some tests against the layer.

To avoid rebuilding the layer each time you make a change to the `cibotiling.py` module
you can follow the instructions in `tilertest/app.py` to copy it so it is included
in the test function.

### Deployment

Use `test-deploy.py -m deploy` to deploy (the hopefully tested) Lambda function. 
Note that whether the dev or prod mode is used is controlled by the `--environment` switch.
The envrionments are identical but prod is more stable where dev is more cutting edge.

### Using in projects

The ARN of the created layer (after deployment) is placed in the output of the `CiboTilerLayerARN-arm64-dev`
or `CiboTilerLayerARN-arm64-prod` CloudFormation stacks. Use this name in Lambdas that need this
layer. Note that you can't use `Fn::ImportValue` in AWS SAM in local mode and that 
you probably want to use a fixed version of this layer so you don't suddenly get the 
latest on redeploy.

### Upgrading to a newer cibo_tilerlayer

Note that if you change the layer version, this gets change picked up when you run `sam local` in your
project. However this doesn't seem to be changed when you run `sam deploy`... The only way to address 
this appears to select the Lambda function in the AWS Console and click on 'Layers' and then 'Edit' 
and bump the version here too.

### Environment Variables

In client Lambdas, to be able to find the shared libraries the `LD_LIBRARY_PATH` should be set 
in the Environment/Variables section like this::

    LD_LIBRARY_PATH: "/opt/python/lib:/var/lang/lib:/lib64:/usr/lib64:/var/runtime:/var/runtime/lib:/var/task:/opt/lib"

You may also wish to set some of the other GDAL options like this::

    GDAL_DATA: "/opt/python/share/gdal"
    PROJ_LIB: "/opt/python/share/proj"
    GDAL_CACHEMAX: "75%"
    VSI_CACHE: "TRUE"
    VSI_CACHE_SIZE: "536870912"
    GDAL_DISABLE_READDIR_ON_OPEN: "TRUE"
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS: ".tif,.tif.aux.xml,.vrt"
    GDAL_MAX_DATASET_POOL_SIZE: "512"
    CPL_TMPDIR: "/tmp"
    GDAL_FORCE_CACHING: "YES"
    GDAL_HTTP_MAX_RETRY: "10"
    GDAL_HTTP_RETRY_DELAY: "1"
    
## License

See [LICENSE](https://github.com/cibolabs/cibo_tilerlayer/blob/main/LICENSE)

## Changes

See [CHANGES.md](https://github.com/cibolabs/cibo_tilerlayer/blob/main/CHANGES.md)
