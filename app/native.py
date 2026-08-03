import logging
import os
import sys

log = logging.getLogger("parch_mp.native")

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)


def _candidates():
    seen = []
    for base in (getattr(sys, "_MEIPASS", None), _ROOT, _HERE):
        if not base:
            continue
        for sub in ("lib", "", "native"):
            path = os.path.join(base, sub) if sub else base
            if path not in seen and os.path.isdir(path):
                seen.append(path)
    return seen


for _path in _candidates():
    if _path not in sys.path:
        sys.path.insert(0, _path)

dsp = None
core = None

try:
    import parch_dsp as dsp
except Exception as exc:
    log.info("rust dsp core unavailable (%s); using python fallback", exc)

try:
    import parch_core as core
except Exception as exc:
    log.info("c++ analysis core unavailable (%s); using numpy fallback", exc)

HAVE_DSP = dsp is not None
HAVE_CORE = core is not None


def backend_name():
    parts = []
    parts.append("rust" if HAVE_DSP else "python")
    parts.append("c++" if HAVE_CORE else "numpy")
    return "+".join(parts)


def summary():
    return {
        "dsp": getattr(dsp, "__version__", None) if HAVE_DSP else None,
        "core": getattr(core, "__version__", None) if HAVE_CORE else None,
        "backend": backend_name(),
    }
