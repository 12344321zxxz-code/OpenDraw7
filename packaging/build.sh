#!/bin/bash
# Builds dist/OpenDraw7-<version>-linux-x86_64.tar.gz
# Needs: a Python with PySide6-Essentials, numpy and pyinstaller (set PYTHON=...), curl, dpkg-deb.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(dirname "$here")"
PYTHON="${PYTHON:-python3}"
out="${OUT:-$root/dist}"
work="${WORK:-$root/build}"
version="$("$PYTHON" -c "import sys; sys.path.insert(0, '$root'); import opendraw7; print(opendraw7.__version__)")"

[ -d "$here/vendor/lib" ] || "$here/fetch_vendor.sh"
rm -rf "$work" "$out/opendraw7" "$out/OpenDraw7"
"$PYTHON" -m PyInstaller --noconfirm --distpath "$out" --workpath "$work" "$here/opendraw7.spec"

stage="$out/OpenDraw7"
mv "$out/opendraw7" "$stage"
QT_QPA_PLATFORM=offscreen "$PYTHON" - "$root" "$stage/opendraw7.png" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from PySide6.QtGui import QGuiApplication
app = QGuiApplication([])
from opendraw7 import icons
icons.image("app", 256).save(sys.argv[2])
PY
# third-party licence texts (the package redistributes Qt, PySide6, Python and NumPy)
lic="$stage/_internal/licenses"
mkdir -p "$lic"
cp "$here"/licenses/*.txt "$lic/"
"$PYTHON" - "$lic" <<'PY'
import glob, os, shutil, sys, sysconfig
out = sys.argv[1]
std = os.path.join(sysconfig.get_paths()["stdlib"], "LICENSE.txt")
if os.path.exists(std):
    shutil.copy(std, os.path.join(out, "Python-LICENSE.txt"))
import numpy
hits = glob.glob(os.path.join(os.path.dirname(os.path.dirname(numpy.__file__)), "numpy-*.dist-info", "licenses", "LICENSE.txt"))
if hits:
    shutil.copy(hits[0], os.path.join(out, "NumPy-LICENSE.txt"))
PY
cp "$here/install.sh" "$here/uninstall.sh" "$here/opendraw7.desktop" "$stage/"
cp "$root/LICENSE" "$stage/LICENSE.txt"
cp "$here/README-package.txt" "$stage/README.txt"
chmod +x "$stage/install.sh" "$stage/uninstall.sh" "$stage/opendraw7"
tarball="$out/OpenDraw7-$version-linux-x86_64.tar.gz"
tar -C "$out" -czf "$tarball" OpenDraw7
ls -la "$tarball"
