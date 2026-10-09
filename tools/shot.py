"""Offscreen screenshot / scripting helper for development.

    QT_QPA_PLATFORM=offscreen python tools/shot.py out.png            # main window
    QT_QPA_PLATFORM=offscreen python tools/shot.py - script.py        # run a script

A script gets: app, win, grab(path), vp(x, y), drag(points, button, mods), QTest, Qt, QColor.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from PySide6.QtCore import Qt, QPoint, QPointF, QEvent  # noqa: E402
from PySide6.QtGui import QMouseEvent, QColor  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from opendraw7.app import create_app  # noqa: E402

app = create_app(["opendraw7"])
from opendraw7.mainwindow import MainWindow  # noqa: E402

win = MainWindow()
win.show()
app.processEvents()


def grab(path):
    app.processEvents()
    win.grab().save(path)


def vp(x, y):
    """Picture coordinates -> point in the canvas viewport."""
    p = win.canvas.to_view(QPointF(x, y))
    return QPoint(int(p.x()), int(p.y()))


def drag(pts, button=Qt.LeftButton, mods=Qt.NoModifier):
    v = win.canvas.viewport()
    QTest.mousePress(v, button, mods, vp(*pts[0]))
    for pt in pts[1:]:
        app.sendEvent(v, QMouseEvent(QEvent.MouseMove, QPointF(vp(*pt)), QPointF(v.mapToGlobal(vp(*pt))),
                                     Qt.NoButton, button, mods))
    QTest.mouseRelease(v, button, mods, vp(*pts[-1]))
    app.processEvents()


if __name__ == "__main__":
    if len(sys.argv) > 2:
        exec(open(sys.argv[2]).read())
    elif len(sys.argv) > 1:
        grab(sys.argv[1])
    win.doc.modified = False
