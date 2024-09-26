#include <Python.h>
#include "numpy/arrayobject.h"
#include <cmath>

/* An exception object for this module */
/* created in the init function */
struct ResamplerState
{
    PyObject *error;
};

#define GETSTATE(m) ((struct ResamplerState*)PyModule_GetState(m))

// See https://gist.github.com/folkertdev/6b930c7a7856e36dcad0a72a03e66716
// and https://chao-ji.github.io/jekyll/update/2018/07/19/BilinearResize.html

template <class T>
void doBilinearNoIgnore(PyArrayObject *pInput, PyArrayObject *pOutput)
{
    npy_intp nInYSize = PyArray_DIM(pInput, 0);
    npy_intp nInXSize = PyArray_DIM(pInput, 1);
    npy_intp nOutYSize = PyArray_DIM(pOutput, 0);
    npy_intp nOutXSize = PyArray_DIM(pOutput, 1);
    
    float x_ratio, y_ratio;

    if (nOutXSize > 1) {
        x_ratio = ((float)nInXSize - 1.0) / ((float)nOutXSize - 1.0);
    } else {
        x_ratio = 0;
    }

    if (nOutYSize > 1) {
        y_ratio = ((float)nInYSize - 1.0) / ((float)nOutYSize - 1.0);
    } else {
        y_ratio = 0;
    }

    for (int i = 0; i < nOutYSize; i++) 
    {
        for (int j = 0; j < nOutXSize; j++) 
        {
            float x_l = std::floor(x_ratio * (float)j);
            float y_l = std::floor(y_ratio * (float)i);
            float x_h = std::ceil(x_ratio * (float)j);
            float y_h = std::ceil(y_ratio * (float)i);

            float x_weight = (x_ratio * (float)j) - x_l;
            float y_weight = (y_ratio * (float)i) - y_l;

            T a = *(T*)PyArray_GETPTR2(pInput, (npy_intp)y_l, (npy_intp)x_l); 
            T b = *(T*)PyArray_GETPTR2(pInput, (npy_intp)y_l, (npy_intp)x_h); 
            T c = *(T*)PyArray_GETPTR2(pInput, (npy_intp)y_h, (npy_intp)x_l);
            T d = *(T*)PyArray_GETPTR2(pInput, (npy_intp)y_h, (npy_intp)x_h);

            T pixel = a * (1.0 - x_weight) * (1.0 - y_weight) +
                          b * x_weight * (1.0 - y_weight) +
                          c * y_weight * (1.0 - x_weight) +
                          d * x_weight * y_weight;

            *(T*)PyArray_GETPTR2(pOutput, i, j) = pixel;
        }
    }    
}

template <class T>
void doBilinearHaveIgnore(PyArrayObject *pInput, PyArrayObject *pOutput, double dIgnore)
{
    npy_intp nInYSize = PyArray_DIM(pInput, 0);
    npy_intp nInXSize = PyArray_DIM(pInput, 1);
    npy_intp nOutYSize = PyArray_DIM(pOutput, 0);
    npy_intp nOutXSize = PyArray_DIM(pOutput, 1);
    T typeIgnore = dIgnore;
    
    float x_ratio, y_ratio;

    if (nOutXSize > 1) {
        x_ratio = ((float)nInXSize - 1.0) / ((float)nOutXSize - 1.0);
    } else {
        x_ratio = 0;
    }

    if (nOutYSize > 1) {
        y_ratio = ((float)nInYSize - 1.0) / ((float)nOutYSize - 1.0);
    } else {
        y_ratio = 0;
    }

    for (int i = 0; i < nOutYSize; i++) 
    {
        for (int j = 0; j < nOutXSize; j++) 
        {
            float x_l = std::floor(x_ratio * (float)j);
            float y_l = std::floor(y_ratio * (float)i);
            float x_h = std::ceil(x_ratio * (float)j);
            float y_h = std::ceil(y_ratio * (float)i);

            float x_weight = (x_ratio * (float)j) - x_l;
            float y_weight = (y_ratio * (float)i) - y_l;

            // my approach to ignore values is to just fail if any of the 
            // neighbours is the ignore value. Not sure if something better could be done...
            T a = *(T*)PyArray_GETPTR2(pInput, (npy_intp)y_l, (npy_intp)x_l);
            if( a == typeIgnore )
            {
                *(T*)PyArray_GETPTR2(pOutput, i, j) = typeIgnore;
                continue;
            } 
            T b = *(T*)PyArray_GETPTR2(pInput, (npy_intp)y_l, (npy_intp)x_h); 
            if( b == typeIgnore )
            {
                *(T*)PyArray_GETPTR2(pOutput, i, j) = typeIgnore;
                continue;
            } 
            T c = *(T*)PyArray_GETPTR2(pInput, (npy_intp)y_h, (npy_intp)x_l);
            if( c == typeIgnore )
            {
                *(T*)PyArray_GETPTR2(pOutput, i, j) = typeIgnore;
                continue;
            } 
            T d = *(T*)PyArray_GETPTR2(pInput, (npy_intp)y_h, (npy_intp)x_h);
            if( d == typeIgnore )
            {
                *(T*)PyArray_GETPTR2(pOutput, i, j) = typeIgnore;
                continue;
            } 

            T pixel = a * (1.0 - x_weight) * (1.0 - y_weight) +
                          b * x_weight * (1.0 - y_weight) +
                          c * y_weight * (1.0 - x_weight) +
                          d * x_weight * y_weight;

            *(T*)PyArray_GETPTR2(pOutput, i, j) = pixel;
        }
    }    
}


static PyObject *resampler_bilinear(PyObject *self, PyObject *args)
{
    PyArrayObject *pInput;
    PyObject *pIgnore;
    double dIgnore;
    int nWidth, nHeight;
    
    if( !PyArg_ParseTuple(args, "O!Oii:bilinear", &PyArray_Type, &pInput, 
            &pIgnore, &nWidth, &nHeight))
        return NULL;

    bool bHaveIgnore = pIgnore != Py_None;       
    if( bHaveIgnore )
    {
        dIgnore = PyFloat_AsDouble(pIgnore);
        // TODO: PyErr_Occurred
    }
    
    int arrayType = PyArray_TYPE(pInput);
    npy_intp out_dims[] = {nHeight, nWidth};
    PyArrayObject *pOutput = (PyArrayObject*)PyArray_EMPTY(2, out_dims, arrayType, 0);
    
    if( pIgnore == Py_None )
    {
        // no ignore - use optimised version
        switch(arrayType)
        {
            case NPY_INT8:
                doBilinearNoIgnore <npy_int8> (pInput, pOutput);
                break;
            case NPY_UINT8:
                doBilinearNoIgnore <npy_uint8> (pInput, pOutput);
                break;
            case NPY_INT16:
                doBilinearNoIgnore <npy_int16> (pInput, pOutput);
                break;
            case NPY_UINT16:
                doBilinearNoIgnore <npy_uint16> (pInput, pOutput);
                break;
            case NPY_INT32:
                doBilinearNoIgnore <npy_int32> (pInput, pOutput);
                break;
            case NPY_UINT32:
                doBilinearNoIgnore <npy_uint32> (pInput, pOutput);
                break;
            case NPY_INT64:
                doBilinearNoIgnore <npy_int64> (pInput, pOutput);
                break;
            case NPY_UINT64:
                doBilinearNoIgnore <npy_uint64> (pInput, pOutput);
                break;
            case NPY_FLOAT16:
                doBilinearNoIgnore <npy_float16> (pInput, pOutput);
                break;
            case NPY_FLOAT32:
                doBilinearNoIgnore <npy_float32> (pInput, pOutput);
                break;
            case NPY_FLOAT64:
                doBilinearNoIgnore <npy_float64> (pInput, pOutput);
                break;
            default:
                PyErr_SetString(GETSTATE(self)->error, "Unsupported data type");
                Py_DECREF(pOutput);
                return NULL;
        }
    }
    else
    {
        // we have an ignore - use slower version
        dIgnore = PyFloat_AsDouble(pIgnore);
        // TODO: PyErr_Occurred
        switch(arrayType)
        {
            case NPY_INT8:
                doBilinearHaveIgnore <npy_int8> (pInput, pOutput, dIgnore);
                break;
            case NPY_UINT8:
                doBilinearHaveIgnore <npy_uint8> (pInput, pOutput, dIgnore);
                break;
            case NPY_INT16:
                doBilinearHaveIgnore <npy_int16> (pInput, pOutput, dIgnore);
                break;
            case NPY_UINT16:
                doBilinearHaveIgnore <npy_uint16> (pInput, pOutput, dIgnore);
                break;
            case NPY_INT32:
                doBilinearHaveIgnore <npy_int32> (pInput, pOutput, dIgnore);
                break;
            case NPY_UINT32:
                doBilinearHaveIgnore <npy_uint32> (pInput, pOutput, dIgnore);
                break;
            case NPY_INT64:
                doBilinearHaveIgnore <npy_int64> (pInput, pOutput, dIgnore);
                break;
            case NPY_UINT64:
                doBilinearHaveIgnore <npy_uint64> (pInput, pOutput, dIgnore);
                break;
            case NPY_FLOAT16:
                doBilinearHaveIgnore <npy_float16> (pInput, pOutput, dIgnore);
                break;
            case NPY_FLOAT32:
                doBilinearHaveIgnore <npy_float32> (pInput, pOutput, dIgnore);
                break;
            case NPY_FLOAT64:
                doBilinearHaveIgnore <npy_float64> (pInput, pOutput, dIgnore);
                break;
            default:
                PyErr_SetString(GETSTATE(self)->error, "Unsupported data type");
                Py_DECREF(pOutput);
                return NULL;
        }
    }

    return (PyObject*)pOutput;     
}

/* Our list of functions in this module*/
static PyMethodDef ResamplerMethods[] = {
    {"bilinear", resampler_bilinear, METH_VARARGS,
        "call signature: bilinear(input, ignore, width, height)\n"
        "where:\n"
        "  input is a 2d array\n"
        "  ignore is a float (or None) containing the ignore value (if set)\n"  
        "  width is the width of the output image\n"
        "  height is the height of the output image\n"
        "returns: a 2d array of size (height, width). dtype same as input\n"},
    {NULL}
};

static int resampler_traverse(PyObject *m, visitproc visit, void *arg) 
{
    Py_VISIT(GETSTATE(m)->error);
    return 0;
}

static int resampler_clear(PyObject *m) 
{
    Py_CLEAR(GETSTATE(m)->error);
    return 0;
}

static struct PyModuleDef moduledef = {
        PyModuleDef_HEAD_INIT,
        "resampler",
        NULL,
        sizeof(struct ResamplerState),
        ResamplerMethods,
        NULL,
        resampler_traverse,
        resampler_clear,
        NULL
};

PyMODINIT_FUNC 
PyInit_resampler(void)
{
    PyObject *pModule;
    struct ResamplerState *state;

    /* initialize the numpy stuff */
    import_array();

    pModule = PyModule_Create(&moduledef);
    if( pModule == NULL )
        return NULL;
        
    state = GETSTATE(pModule);

    /* Create and add our exception type */
    state->error = PyErr_NewException("resampler.error", NULL, NULL);
    if( state->error == NULL )
    {
        Py_DECREF(pModule);
        return NULL;
    }
    PyModule_AddObject(pModule, "error", state->error);

    return pModule;
}
