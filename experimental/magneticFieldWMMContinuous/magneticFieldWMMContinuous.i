%module magneticFieldWMMContinuous
%{
   #include "magneticFieldWMMContinuous.h"
%}

%include "swig_contex.i"
%include "sys_model.i"
%include "simulation/environment/_GeneralModuleFiles/magneticFieldBaseContinuous.h"

%include "std_string.i"
%include "std_vector.i"
%include "eigen.i"

%include "magneticFieldWMMContinuous.h"

%pythoncode %{
import sys
protectAllClasses(sys.modules[__name__])
%}