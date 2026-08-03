import plistlib
import sys

target = sys.argv[1]
version = sys.argv[2] if len(sys.argv) > 2 else "9.0.0"

data = {
    "CFBundleName": "Parch Music Player",
    "CFBundleDisplayName": "Parch Music Player",
    "CFBundleExecutable": "ParchMP",
    "CFBundleIdentifier": "org.parch.musicplayer",
    "CFBundleVersion": version,
    "CFBundleShortVersionString": version,
    "CFBundleIconFile": "parch-mp.icns",
    "CFBundlePackageType": "APPL",
    "CFBundleSignature": "????",
    "LSMinimumSystemVersion": "11.0",
    "NSHighResolutionCapable": True,
    "LSApplicationCategoryType": "public.app-category.music",
}

with open(target, "wb") as handle:
    plistlib.dump(data, handle)
print("wrote", target)
