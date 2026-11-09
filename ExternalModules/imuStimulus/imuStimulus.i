%module imuStimulus
%{
   #include "imuStimulus.h"
%}

%include "swig_conly_data.i"
%include "sys_model.i"
%include "std_string.i"

// Protocol frames cross into and out of Python as bytes objects.
%typemap(out) std::vector<uint8_t> {
    const std::vector<uint8_t> &bytes = $1;
    $result = PyBytes_FromStringAndSize(
        reinterpret_cast<const char *>(bytes.data()), static_cast<Py_ssize_t>(bytes.size()));
}
%typemap(in) (const uint8_t *data, size_t length) (char *buffer = nullptr, Py_ssize_t size = 0) {
    if (PyBytes_AsStringAndSize($input, &buffer, &size) == -1) SWIG_fail;
    $1 = reinterpret_cast<uint8_t *>(buffer);
    $2 = static_cast<size_t>(size);
}

%include "imuStimulus.h"

%include "architecture/msgPayloadDefC/SCStatesMsgPayload.h"
struct SCStatesMsg_C;

%pythoncode %{
PSP_SAMPLE_IMU_STIMULUS = 1
%}
