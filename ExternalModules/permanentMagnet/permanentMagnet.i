%module permanentMagnet
%{
   #include "permanentMagnet.h"
%}

%include "swig_conly_data.i"
%include "sys_model.i"
%include "std_string.i"
%include "swig_eigen.i"

// Forward-declare DynamicEffector so SWIG understands the inheritance
// without generating a full wrapper for it. Tell SWIG not to build a constructor.
%nodefaultctor DynamicEffector;
class DynamicEffector {};

// Expose the module header
%include "permanentMagnet.h"

// Expose the message payloads so Python can link them
%include "architecture/msgPayloadDefC/MagneticFieldMsgPayload.h"
struct MagneticFieldMsg_C;
%include "architecture/msgPayloadDefC/CmdTorqueBodyMsgPayload.h"
struct CmdTorqueBodyMsg_C;
