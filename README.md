# cibo_tilerlayer

## Install

The install under Ubuntu isn't totally straightforward. The install
instructions are here: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html

However, using their install script and installing into `/usr/local` appears to 
introduce a problem where the `LD_LIBRARY_PATH` in the test Lambda function is set 
incorrectly. There is now an assert in the test function to catch this situation.

The workaround is to cd into the `aws-sam-cli-src` directory and run `pip install .`.
This will install SAM into your home directory. Note that you will need to log out
and log back in before this change is reflected in your environment. Note that 
having a `.bash_profile` file in your home directory will prevent your environment being updated.

## Testing

Testing and deployment are handled by the `test-deploy.py` script. Note that everything
has 2 modes - 'dev' and 'prod' - this is controlled by the `--environment` switch.

`test-deploy.py` does a build of the layer first before running anything else. 

For testing, use the `-m test` mode to `test-deploy.py`. This will spin up a local 
lambda function and run some tests against the layer.

To avoid rebuilding the layer each time you make a change to the `cibotiling.py` module
you can follow the instructions in `tilertest/app.py` to copy it so it is included
in the test function.

## Deployment

Use `test-deploy.py -m deploy` to deploy (the hopefully tested) Lambda function. 
Note that whether the dev or prod mode is used is controlled by the `--environment` switch.

## Using in projects

The name of the created layer (after deployment) is placed in the output of the `cibo-tilerlayer-dev`
or `cibo-tilerlayer-prod` CloudFormation stacks. Use this name in Lambdas that need this
layer. Note that you can't use `Fn::ImportValue` in AWS SAM in local mode and that 
you probably want to use a fixed version of this layer so you don't suddenly get the 
latest on redeploy.

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

