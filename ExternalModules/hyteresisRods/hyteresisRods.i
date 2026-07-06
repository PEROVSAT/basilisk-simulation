%module hyteresisRods
%{
   #include "hyteresisRods.h"
%}

%pythoncode %{
from Basilisk.architecture.swig_common_model import *
%}
%include "swig_conly_data.i"
%include "sys_model.i"
%include "std_string.i"
%include "swig_eigen.i"

// Forward-declare StateEffector so SWIG understands the inheritance chain
// without generating a full wrapper for it.
%nodefaultctor StateEffector;
class StateEffector {};

// Expose the module header
%include "hyteresisRods.h"

// Expose the message payloads so Python can subscribe/link them
%include "architecture/msgPayloadDefC/MagneticFieldMsgPayload.h"
struct MagneticFieldMsg_C;
%include "architecture/msgPayloadDefC/CmdTorqueBodyMsgPayload.h"
struct CmdTorqueBodyMsg_C;
%include "HysteresisDebugMsgPayload.h"
struct HysteresisDebugMsg_C;

%pythoncode %{
import sys
protectAllClasses(sys.modules[__name__])
%}
