"""Application start-up."""
import argparse
import os
import sys
import traceback

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from . import APP_NAME, __version__
from . import theme as T

TOOLTIP_QSS = """
QToolTip {
    color: #4c4c4c; background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ffffff, stop:1 #e4e5f0);
    border: 1px solid #767676; padding: 4px 6px;
}
"""


def _palette():
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(240, 240, 240))
    pal.setColor(QPalette.WindowText, QColor(0, 0, 0))
    pal.setColor(QPalette.Base, QColor(255, 255, 255))
    pal.setColor(QPalette.AlternateBase, QColor(245, 247, 250))
    pal.setColor(QPalette.Text, QColor(0, 0, 0))
    pal.setColor(QPalette.Button, QColor(240, 240, 240))
    pal.setColor(QPalette.ButtonText, QColor(0, 0, 0))
    pal.setColor(QPalette.Highlight, QColor(51, 153, 255))
    pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    pal.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
    pal.setColor(QPalette.ToolTipText, QColor(76, 76, 76))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(141, 141, 141))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(141, 141, 141))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor(141, 141, 141))
    return pal


def create_app(argv):
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("opendraw7")
    app.setStyle("Fusion")
    app.setPalette(_palette())
    app.setFont(T.ui_font())
    app.setStyleSheet(TOOLTIP_QSS)
    return app


def _excepthook(etype, value, tb):
    traceback.print_exception(etype, value, tb)


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    parser = argparse.ArgumentParser(prog="opendraw7", description="Paint program in the style of the Windows 7 one.")
    parser.add_argument("file", nargs="?", help="picture to open")
    parser.add_argument("--native-frame", action="store_true",
                        help="use the desktop's own title bar instead of the built-in one")
    parser.add_argument("--self-test", action="store_true",
                        help="run the built-in checks without showing a window, then exit")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    args, qt_args = parser.parse_known_args(argv[1:])
    sys.excepthook = _excepthook
    if args.self_test:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    if sys.platform.startswith("linux") and "QT_QPA_PLATFORM" not in os.environ:
        # Prefer X11 (XWayland on Wayland desktops), where the custom title bar is tested;
        # fall back to native Wayland if X11 is not available.
        os.environ["QT_QPA_PLATFORM"] = "xcb;wayland"
    app = create_app([argv[0]] + qt_args)
    from . import icons
    app.setWindowIcon(icons.app_icon())
    if args.self_test:
        from .selftest import run
        return run(app)
    from .mainwindow import MainWindow
    native = args.native_frame or os.environ.get("OPENDRAW7_NATIVE_FRAME") == "1"
    win = MainWindow(native_frame=native)
    if args.file:
        win.open_path(args.file)
    win.show()
    return app.exec()
