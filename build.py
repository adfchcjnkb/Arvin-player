import argparse
import glob
import os
import shutil
import subprocess
import sys
import sysconfig

ROOT = os.path.dirname(os.path.abspath(__file__))
NATIVE = os.path.join(ROOT, "native")
RUST_CRATE = os.path.join(NATIVE, "rust", "parch_dsp")
LIB_DIR = os.path.join(ROOT, "lib")

WIN = sys.platform == "win32"
MAC = sys.platform == "darwin"
EXT_SUFFIX = sysconfig.get_config_var("EXT_SUFFIX") or (".pyd" if WIN else ".so")


def announce(message):
    print(f"[build] {message}", flush=True)


def run(args, cwd=None, env=None):
    merged = dict(os.environ)
    if env:
        merged.update(env)
    result = subprocess.run(args, cwd=cwd, env=merged)
    return result.returncode == 0


def cargo_binary():
    for candidate in ("cargo", os.path.expanduser("~/.cargo/bin/cargo")):
        if shutil.which(candidate) or os.path.exists(candidate):
            return candidate
    return None


def build_rust():
    cargo = cargo_binary()
    if cargo is None:
        announce("cargo not found, skipping rust core")
        return False
    announce("compiling rust dsp core")
    ok = run([cargo, "build", "--release"], cwd=RUST_CRATE,
             env={"PYO3_PYTHON": sys.executable})
    if not ok:
        announce("rust build failed")
        return False

    target = os.path.join(RUST_CRATE, "target", "release")
    if WIN:
        source, name = os.path.join(target, "parch_dsp.dll"), "parch_dsp.pyd"
    elif MAC:
        source, name = os.path.join(target, "libparch_dsp.dylib"), "parch_dsp.so"
    else:
        source, name = os.path.join(target, "libparch_dsp.so"), "parch_dsp.so"

    if not os.path.exists(source):
        announce(f"missing rust artefact {source}")
        return False
    shutil.copy2(source, os.path.join(LIB_DIR, name))
    announce(f"rust core -> lib/{name}")
    return True


def build_cpp():
    announce("compiling c++ analysis core")
    ok = run([sys.executable, "setup_core.py", "build_ext", "--inplace"], cwd=NATIVE)
    if not ok:
        announce("c++ build failed")
        return False
    produced = glob.glob(os.path.join(NATIVE, "parch_core*" + EXT_SUFFIX)) or \
        glob.glob(os.path.join(NATIVE, "parch_core*.so")) + \
        glob.glob(os.path.join(NATIVE, "parch_core*.pyd"))
    if not produced:
        announce("missing c++ artefact")
        return False
    for path in produced:
        shutil.copy2(path, os.path.join(LIB_DIR, os.path.basename(path)))
        announce(f"c++ core -> lib/{os.path.basename(path)}")
    return True


def verify():
    announce("verifying native cores")
    code = (
        "import sys; sys.path.insert(0, r'%s');"
        "import parch_dsp, parch_core;"
        "print('  parch_dsp', parch_dsp.__version__);"
        "print('  parch_core', parch_core.__version__)" % LIB_DIR
    )
    return run([sys.executable, "-c", code])


def build_app():
    announce("packaging with pyinstaller")
    return run([sys.executable, "-m", "PyInstaller", "--noconfirm", "ParchMP.spec"],
               cwd=ROOT)


def main():
    parser = argparse.ArgumentParser(description="Build Parch MP")
    parser.add_argument("--natives-only", action="store_true")
    parser.add_argument("--skip-natives", action="store_true")
    args = parser.parse_args()

    os.makedirs(LIB_DIR, exist_ok=True)

    if not args.skip_natives:
        rust_ok = build_rust()
        cpp_ok = build_cpp()
        if not (rust_ok and cpp_ok):
            announce("one or more native cores unavailable; python fallbacks will be used")
        verify()

    if args.natives_only:
        return 0

    if not build_app():
        announce("packaging failed")
        return 1

    announce("done -> dist/ParchMP")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
