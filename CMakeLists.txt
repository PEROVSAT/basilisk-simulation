# =============================================================================
# Boilerplate — copy verbatim from bsk-sdk quick-start, do not modify.
# =============================================================================
cmake_minimum_required(VERSION 3.26)
project(perovsat_plugins LANGUAGES C CXX)

find_package(Python3 REQUIRED COMPONENTS Interpreter Development.Module NumPy)

# Locate bsk-sdk from the active Python environment.
execute_process(
  COMMAND "${Python3_EXECUTABLE}" -c
    "import bsk_sdk; print(bsk_sdk.cmake_config_dir(), end='')"
  OUTPUT_VARIABLE bsk_sdk_dir
  RESULT_VARIABLE rc
)
if(NOT rc EQUAL 0 OR bsk_sdk_dir STREQUAL "")
  message(FATAL_ERROR
    "bsk-sdk not found. Run: pip install bsk-sdk==2.10.2")
endif()
file(TO_CMAKE_PATH "${bsk_sdk_dir}" bsk_sdk_dir)
set(bsk-sdk_DIR "${bsk_sdk_dir}")
find_package(bsk-sdk CONFIG REQUIRED)

# =============================================================================
# Plugin modules
# =============================================================================

set(PLUGIN_PKG_DIR "${SKBUILD_PLATLIB_DIR}/perovsat_plugins")

# Package init imports generated messaging before SWIG wrappers so custom
# message fields (e.g. hysteresisDebugOutMsg) expose recorder().
configure_file(
  "${CMAKE_CURRENT_SOURCE_DIR}/python/perovsat_plugins/__init__.py"
  "${PLUGIN_PKG_DIR}/__init__.py"
  COPYONLY
)

# permanentMagnet — C++ DynamicEffector that applies a permanent dipole torque.
bsk_add_swig_module(
  TARGET permanentMagnet
  INTERFACE "${CMAKE_CURRENT_SOURCE_DIR}/ExternalModules/permanentMagnet/permanentMagnet.i"
  SOURCES   "${CMAKE_CURRENT_SOURCE_DIR}/ExternalModules/permanentMagnet/permanentMagnet.cpp"
  INCLUDE_DIRS
    "${CMAKE_CURRENT_SOURCE_DIR}/ExternalModules/permanentMagnet"
  OUTPUT_DIR "${PLUGIN_PKG_DIR}"
)

# hyteresisRods — C++ StateEffector implementing the Jiles-Atherton hysteresis
# rod model for passive magnetic attitude detumbling.
bsk_add_swig_module(
  TARGET hyteresisRods
  INTERFACE "${CMAKE_CURRENT_SOURCE_DIR}/ExternalModules/hyteresisRods/hyteresisRods.i"
  SOURCES   "${CMAKE_CURRENT_SOURCE_DIR}/ExternalModules/hyteresisRods/hyteresisRods.cpp"
  INCLUDE_DIRS
    "${CMAKE_CURRENT_SOURCE_DIR}/ExternalModules/hyteresisRods"
    "${CMAKE_CURRENT_SOURCE_DIR}/messages"
  OUTPUT_DIR "${PLUGIN_PKG_DIR}"
)

bsk_generate_messages(
  OUTPUT_DIR "${PLUGIN_PKG_DIR}/messaging"
  MSG_HEADERS
    "${CMAKE_CURRENT_SOURCE_DIR}/messages/HysteresisDebugMsgPayload.h"
)
