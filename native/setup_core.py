import sys
from setuptools import Extension, setup

flags = ["-O3", "-ffast-math", "-funroll-loops", "-fno-plt", "-std=c++17"]
if sys.platform == "win32":
    flags = ["/O2", "/fp:fast", "/std:c++17"]

setup(
    name="parch_core",
    version="1.0.0",
    ext_modules=[
        Extension(
            "parch_core",
            sources=["cpp/parch_core.cpp"],
            extra_compile_args=flags,
            language="c++",
        )
    ],
)
