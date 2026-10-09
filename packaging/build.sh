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
rm -f "$stage"/_internal/libQt6EglFS* "$stage"/_internal/PySide6/Qt/lib/libQt6EglFS* "$stage"/_internal/libQt6EglFsKms* "$stage"/_internal/PySide6/Qt/lib/libQt6EglFsKms*
QT_QPA_PLATFORM=offscreen "$PYTHON" - "$root" "$stage/opendraw7.png" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from PySide6.QtGui import QGuiApplication
app = QGuiApplication([])
from opendraw7 import icons
icons.image("app", 256).save(sys.argv[2])
PY
cp "$here/install.sh" "$here/uninstall.sh" "$here/opendraw7.desktop" "$stage/"
cp "$root/LICENSE" "$stage/LICENSE.txt"
cp "$here/README-package.txt" "$stage/README.txt"
chmod +x "$stage/install.sh" "$stage/uninstall.sh" "$stage/opendraw7"
tarball="$out/OpenDraw7-$version-linux-x86_64.tar.gz"
tar -C "$out" -czf "$tarball" OpenDraw7
ls -la "$tarball"
