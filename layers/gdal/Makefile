.ONESHELL: # Applies to every targets in the file!

PYTHON_VERSION := $(shell python3 -c 'import sys;print("{}.{}".format(sys.version_info[0], sys.version_info[1]))')

NUMPY_VERSION:=1.26.4
SQLITE_VERSION:=3450200
TIFF_VERSION:=4.5.1
PROJ_VERSION:=9.3.1
GEOS_VERSION:=3.12.1
GDAL_VERSION:=3.8.4

export LD_LIBRARY_PATH := $(ARTIFACTS_DIR)/python/lib:$(ARTIFACTS_DIR)/python/lib64:${LD_LIBRARY_PATH}
export PATH := $(ARTIFACTS_DIR)/python/bin:${PATH}
export PYTHONPATH := $(ARTIFACTS_DIR)/python/lib/python$(PYTHON_VERSION)/site-packages

build-CiboTilerLayer: prereqs pip numpy sqlite tiff proj geos gdal clean

prereqs:
	dnf install -y automake zlib-devel gcc gcc-c++ \
         wget tar zip bzip2 swig make cmake libcurl-devel patch
	dnf clean all

pip:
	# Locally, for building numpy
	pip install cython setuptools

	# cibotiling
	# For use by all the GDAL based Lambdas
	# https://discuss.python.org/t/installing-from-a-read-only-source/4115/3
	cd /tmp/samcli/source/
	tar zcf /tmp/src.tgz .
	pip install /tmp/src.tgz --prefix=$(ARTIFACTS_DIR)/python
	rm /tmp/src.tgz
	# Needs numpy
	#python3 -c 'from cibotiling import cibotiling'


numpy:
	cd /tmp
	wget -q https://github.com/numpy/numpy/releases/download/v$(NUMPY_VERSION)/numpy-$(NUMPY_VERSION).tar.gz
	tar xf numpy-$(NUMPY_VERSION).tar.gz
	cd numpy-$(NUMPY_VERSION)
	pip install . --prefix=$(ARTIFACTS_DIR)/python
	cd ..
	rm -rf numpy-$(NUMPY_VERSION).tar.gz numpy-$(NUMPY_VERSION)

sqlite:
	cd /tmp
	wget -q https://www.sqlite.org/2024/sqlite-autoconf-$(SQLITE_VERSION).tar.gz
	tar xf sqlite-autoconf-$(SQLITE_VERSION).tar.gz
	cd sqlite-autoconf-$(SQLITE_VERSION)
	CFLAGS="-O2 -Wl,-S" ./configure --enable-static=no --prefix=$(ARTIFACTS_DIR)/python
	make -j2 && make install
	cd ..
	rm -rf sqlite-autoconf-$(SQLITE_VERSION).tar.gz sqlite-autoconf-$(SQLITE_VERSION)

tiff:
	cd /tmp
	wget -q https://download.osgeo.org/libtiff/tiff-$(TIFF_VERSION).tar.gz
	tar xf tiff-$(TIFF_VERSION).tar.gz
	cd tiff-$(TIFF_VERSION)
	mkdir -p build
	cd build
	cmake -D cxx=OFF -D CMAKE_BUILD_TYPE=MinSizeRel -D CMAKE_PREFIX_PATH=$(ARTIFACTS_DIR)/python \
	  -D CMAKE_INSTALL_PREFIX=$(ARTIFACTS_DIR)/python -D CMAKE_INSTALL_LIBDIR=lib .. 2>&1
	make -j2 && make install
	cd ../..
	rm -rf libtiff-$(TIFF_VERSION) tiff-$(TIFF_VERSION).tar.gz

proj:
	cd /tmp
	wget -q http://download.osgeo.org/proj/proj-$(PROJ_VERSION).tar.gz
	tar xf proj-$(PROJ_VERSION).tar.gz
	cd proj-$(PROJ_VERSION)
	mkdir build
	cd build
	cmake -D CMAKE_BUILD_TYPE=MinSizeRel -D CMAKE_PREFIX_PATH=$(ARTIFACTS_DIR)/python \
	  -D BUILD_TESTING=OFF \
	  -D CMAKE_INSTALL_PREFIX=$(ARTIFACTS_DIR)/python -D CMAKE_INSTALL_LIBDIR=lib .. 2>&1
	make -j2 && make install
	cd ../..
	rm -rf proj-$(PROJ_VERSION).tar.gz proj-$(PROJ_VERSION)

geos:
	cd /tmp
	wget -q http://download.osgeo.org/geos/geos-$(GEOS_VERSION).tar.bz2
	tar jxf geos-$(GEOS_VERSION).tar.bz2
	cd geos-$(GEOS_VERSION)
	mkdir build
	cd build
	cmake -D CMAKE_BUILD_TYPE=MinSizeRel -D CMAKE_PREFIX_PATH=$(ARTIFACTS_DIR)/python \
	  -D BUILD_TESTING=OFF \
	  -D CMAKE_INSTALL_PREFIX=$(ARTIFACTS_DIR)/python \ -DCMAKE_INSTALL_LIBDIR=lib .. 2>&1
	make -j2 2>&1
	make install
	cd ../..
	rm -rf geos-$(GEOS_VERSION) geos-$(GEOS_VERSION).tar.bz2

gdal:
	cd /tmp
	wget -q http://download.osgeo.org/gdal/$(GDAL_VERSION)/gdal-$(GDAL_VERSION).tar.gz
	tar -xzf gdal-$(GDAL_VERSION).tar.gz
	cd gdal-$(GDAL_VERSION)
	mkdir build
	cd build
	cmake -DGDAL_BUILD_OPTIONAL_DRIVERS=OFF -DOGR_BUILD_OPTIONAL_DRIVERS=OFF -DGDAL_ENABLE_DRIVER_PNG=ON \
	  -DGDAL_USE_PNG_INTERNAL=ON -DCMAKE_PREFIX_PATH=$(ARTIFACTS_DIR)/python \
	  -DCMAKE_INSTALL_PREFIX=$(ARTIFACTS_DIR)/python -DCMAKE_BUILD_TYPE=MinSizeRel \
	  -DCMAKE_INSTALL_LIBDIR=lib -DPython_ROOT=/var/lang .. 2>&1
	make -j2 2>&1
	make install
	cd ../..
	rm -rf gdal-$(GDAL_VERSION).tar.gz gdal-$(GDAL_VERSION)

clean:
	# Flag fancy stripping of .py files (and just using pyc) for now
	# also strip .so's (we do this for GDAL etc above but Python libs need to be separate step)
	find $(ARTIFACTS_DIR)/python/lib/python$(PYTHON_VERSION) -type f -a -name '*.so' -exec strip {} \;
	# can also remove numpy's include and tests dir
	rm -rf $(ARTIFACTS_DIR)/python/lib/python$(PYTHON_VERSION)/site-packages/numpy/core/include
	rm -rf $(ARTIFACTS_DIR)/python/lib/python$(PYTHON_VERSION)/site-packages/numpy/core/tests
	# docs
	rm -rf $(ARTIFACTS_DIR)/python/share/doc
	# autoconf and man pages
	rm -rf $(ARTIFACTS_DIR)/python/share/man
	rm -rf $(ARTIFACTS_DIR)/python/share/bash-completion
	# include
	rm -rf $(ARTIFACTS_DIR)/python/include
	# bin
	rm -rf $(ARTIFACTS_DIR)/python/bin
	# cmake, pkgconfig etc
	rm -rf $(ARTIFACTS_DIR)/python/lib/cmake
	rm -rf $(ARTIFACTS_DIR)/python/lib/gdalplugins
	rm -rf $(ARTIFACTS_DIR)/python/lib/pkgconfig
	# any static libs
	find $(ARTIFACTS_DIR)/python/lib -name '*.a' -exec rm {} \;	
	# Put everything from lib64 into lib to make life easier
	mv $(ARTIFACTS_DIR)/python/lib64/* $(ARTIFACTS_DIR)/python/lib
	rm -rf $(ARTIFACTS_DIR)/python/lib64
