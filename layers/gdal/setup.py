from setuptools import setup, Extension
from numpy import get_include as numpy_get_include

ext_module = Extension(name='cibotiler.resampler', sources=['src/resampler.cpp'],
        include_dirs=[numpy_get_include()],
        define_macros=[('NPY_NO_DEPRECATED_API', 'NPY_1_7_API_VERSION')])

setup(ext_modules=[ext_module])
