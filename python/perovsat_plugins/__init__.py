import sys

from Basilisk.architecture import cSysModel as _cSysModel

# SWIG-generated wrappers import cSysModel by short name at module load time.
sys.modules.setdefault("cSysModel", _cSysModel)

# Register custom Message/Recorder bindings before loading SWIG module wrappers.
# Without this, plugin output messages expose only a bare SwigPyObject and
# lack methods such as recorder().
from . import messaging  # noqa: F401
from . import permanentMagnet  # noqa: F401
from . import hyteresisRods  # noqa: F401

__all__ = ["hyteresisRods", "permanentMagnet", "messaging"]
