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

    float rowscale = (float)nInYSize / (float)nOutYSize;
    float colscale = (float)nInXSize / (float)nOutXSize;

    // (ri, ci) are row/col in input, (ro, co) are row/col in output.
    // These are notionally float coordinate systems, where the whole
    // number values are on the pixel centres.
    for (int ro = 0; ro < nOutYSize; ro++) {
        float ri = (ro + 0.5) * rowscale - 0.5;
        for (int co = 0; co < nOutXSize; co++) {
            float ci = (co + 0.5) * colscale - 0.5;

            // The four surrounding input row/col values i.e. lower/upper,
            // relative to the (ri, ci) coordinate
            float ri_l = std::floor(ri);
            float ri_u = std::ceil(ri);
            float ci_l = std::floor(ci);
            float ci_u = std::ceil(ci);

            // Mostly the edge-of-block values will be stripped off with
            // the margin. Howver, at the edge of the physical file, there is
            // no margin, so restrict to within the block, just in case.
            if (ri_l < 0) ri_l = 0;
            if (ri_u >= nInYSize) ri_u = nInYSize - 1;
            if (ci_l < 0) ci_l = 0;
            if (ci_u >= nInXSize) ci_u = nInXSize - 1;

            // The input pixel values at these 4 points
            T a = *(T*)PyArray_GETPTR2(pInput, (npy_intp)ri_l, (npy_intp)ci_l);
            T b = *(T*)PyArray_GETPTR2(pInput, (npy_intp)ri_l, (npy_intp)ci_u);
            T c = *(T*)PyArray_GETPTR2(pInput, (npy_intp)ri_u, (npy_intp)ci_l);
            T d = *(T*)PyArray_GETPTR2(pInput, (npy_intp)ri_u, (npy_intp)ci_u);

            // Weights, one each for row and col
            float c_w = ci - ci_l;
            float r_w = ri - ri_l;

            // The weighted average of the four, which is our estimate
            // for the output pixel at (ri, ci)
            T pixel = a * (1.0 - c_w) * (1.0 - r_w) +
                          b * c_w * (1.0 - r_w) +
                          c * r_w * (1.0 - c_w) +
                          d * c_w * r_w;

            *(T*)PyArray_GETPTR2(pOutput, (npy_intp)ro, (npy_intp)co) = pixel;
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
    
    float rowscale = (float)nInYSize / (float)nOutYSize;
    float colscale = (float)nInXSize / (float)nOutXSize;

    // (ri, ci) are row/col in input, (ro, co) are row/col in output.
    // These are notionally float coordinate systems, where the whole
    // number values are on the pixel centres.
    for (int ro = 0; ro < nOutYSize; ro++) {
        float ri = (ro + 0.5) * rowscale - 0.5;
        for (int co = 0; co < nOutXSize; co++) {
            float ci = (co + 0.5) * colscale - 0.5;

            // The four surrounding input row/col values i.e. lower/upper,
            // relative to the (ri, ci) coordinate
            float ri_l = std::floor(ri);
            float ri_u = std::ceil(ri);
            float ci_l = std::floor(ci);
            float ci_u = std::ceil(ci);

            // Mostly the edge-of-block values will be stripped off with
            // the margin. Howver, at the edge of the physical file, there is
            // no margin, so restrict to within the block, just in case.
            if (ri_l < 0) ri_l = 0;
            if (ri_u >= nInYSize) ri_u = nInYSize - 1;
            if (ci_l < 0) ci_l = 0;
            if (ci_u >= nInXSize) ci_u = nInXSize - 1;

            // The input pixel values at these 4 points
            T a = *(T*)PyArray_GETPTR2(pInput, (npy_intp)ri_l, (npy_intp)ci_l);
            T b = *(T*)PyArray_GETPTR2(pInput, (npy_intp)ri_l, (npy_intp)ci_u);
            T c = *(T*)PyArray_GETPTR2(pInput, (npy_intp)ri_u, (npy_intp)ci_l);
            T d = *(T*)PyArray_GETPTR2(pInput, (npy_intp)ri_u, (npy_intp)ci_u);

            // Weights, one each for row and col
            float c_w = ci - ci_l;
            float r_w = ri - ri_l;

            float totalWeight = 0.0;
            float pixelSum = 0.0;
            T pixel;

            if (a != typeIgnore)
            {
                pixelSum += a * (1.0 - c_w) * (1.0 - r_w);
                totalWeight += (1.0 - c_w) * (1.0 - r_w);
            }
            if (b != typeIgnore)
            {
                pixelSum += b * c_w * (1.0 - r_w);
                totalWeight += c_w * (1.0 - r_w);
            }
            if (c != typeIgnore)
            {
                pixelSum += c * r_w * (1.0 - c_w);
                totalWeight += r_w * (1.0 - c_w);
            }
            if (d != typeIgnore)
            {
                pixelSum += d * c_w * r_w;
                totalWeight += c_w * r_w;
            }

            if (totalWeight > 0)
            {
                pixel = pixelSum / totalWeight;
            }
            else
            {
                pixel = typeIgnore;
            }

            *(T*)PyArray_GETPTR2(pOutput, (npy_intp)ro, (npy_intp)co) = pixel;
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
