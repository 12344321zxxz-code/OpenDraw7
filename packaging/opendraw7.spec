# PyInstaller spec: builds dist/opendraw7/ (one folder, no install needed)
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

EXCLUDES = [
    # Only big, clearly unused parts of the standard library. Do not add small modules here:
    # leaving out "secrets" broke numpy.random (and with it every textured brush) in 0.1.0.
    "tkinter", "sqlite3", "lib2to3", "curses", "distutils", "setuptools", "pkg_resources",
    "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtSvg", "PySide6.QtPdf",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSql", "PySide6.QtXml", "PySide6.QtTest",
    "PySide6.QtConcurrent", "PySide6.QtHelp", "PySide6.QtDesigner", "PySide6.QtUiTools",
    "numpy.f2py", "numpy.testing", "numpy.distutils",
]

a = Analysis(
    [os.path.join(ROOT, "run.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=["secrets", "numpy.random"],
    hookspath=[],
    excludes=EXCLUDES,
    noarchive=False,
)

DROP_PARTS = (
    "/translations/", "libqpdf", "libqsvg", "libqicns", "libqtga", "libqwbmp", "libqeglfs", "libqlinuxfb",
    "libqvnc", "libqvkkhrdisplay", "libqminimalegl", "libQt6Pdf", "libQt6Svg", "libQt6Qml", "libQt6Quick",
    "libQt6Network", "libQt6OpenGL", "libQt6Sql", "/tls/", "/networkinformation/", "/sqldrivers/",
    "/qmltooling/", "/designer/", "libQt6VirtualKeyboard", "/platforminputcontexts/libqtvirtualkeyboard",
    "libQt6WaylandCompositor", "libQt6WaylandEglCompositor", "/wayland-graphics-integration-server/",
    "/egldeviceintegrations/", "/vectorimageformats/", "/generic/", "libQt6EglFS", "libQt6EglFsKms",
    # the GTK theme plugin would restyle dialogs from the desktop theme; keep the look fixed
    "libqgtk3",
)


# Libraries that came from this build machine's own system directories are left out:
# they would tie the build to this distro's C library. The desktop's own copies are used
# instead, plus the few helper libraries fetched by fetch_vendor.sh.
SYSTEM_DIRS = ("/lib/", "/usr/lib/", "/lib64/", "/usr/lib64/")


def keep(entry):
    name = "/" + entry[0].replace(os.sep, "/")
    if any(part in name for part in DROP_PARTS):
        return False
    src = entry[1] or ""
    if entry[2] == "BINARY" and src.startswith(SYSTEM_DIRS):
        return False
    return True


a.binaries = [b for b in a.binaries if keep(b)]
a.datas = [d for d in a.datas if keep(d)]

VENDOR = os.path.join(SPECPATH, "vendor")
if os.path.isdir(os.path.join(VENDOR, "lib")):
    for f in sorted(os.listdir(os.path.join(VENDOR, "lib"))):
        a.binaries.append((f, os.path.join(VENDOR, "lib", f), "BINARY"))
    for f in sorted(os.listdir(os.path.join(VENDOR, "licenses"))):
        a.datas.append((os.path.join("licenses", "vendor", f), os.path.join(VENDOR, "licenses", f), "DATA"))
else:
    print("WARNING: packaging/vendor missing - run packaging/fetch_vendor.sh first")
a.datas.append((os.path.join("licenses", "OpenDraw7-LICENSE"), os.path.join(ROOT, "LICENSE"), "DATA"))

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="opendraw7",
    debug=False,
    strip=True,
    upx=False,
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=True, upx=False, name="opendraw7")
