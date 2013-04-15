#include "Python.h"
#include "exceptions.h"

void define_exceptions(PyObject *module)
{

   SetupException = PyErr_NewException("RPi.GPIO.SetupException", NULL, NULL);
   PyModule_AddObject(module, "SetupException", SetupException);
}

