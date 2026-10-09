"""End-to-end smoke test. Drives the real window with synthetic input.

    QT_QPA_PLATFORM=offscreen python tests/smoke_test.py
"""
import math
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from PySide6.QtCore import Qt, QPoint, QPointF, QEvent, QSettings, QSize  # noqa: E402
from PySide6.QtGui import QMouseEvent, QColor, QImage, QGuiApplication  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from opendraw7.app import create_app  # noqa: E402

app = create_app(["opendraw7-test"])
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, tempfile.mkdtemp())

from opendraw7.mainwindow import MainWindow  # noqa: E402
from opendraw7.brushes import BRUSHES  # noqa: E402
from opendraw7.shapes import SHAPES  # noqa: E402
from opendraw7.document import (FORMATS, save_image, load_image, reduce_colors, const_pixels,  # noqa: E402
                                flood_fill)

win = MainWindow()
win.show()
app.processEvents()
st, c, doc = win.state, win.canvas, win.doc
vpw = c.viewport()
checks = 0


def ok(cond, what):
    global checks
    checks += 1
    if not cond:
        raise AssertionError(what)


def vp(x, y):
    p = c.to_view(QPointF(x, y))
    return QPoint(int(p.x()), int(p.y()))


def drag(pts, button=Qt.LeftButton, mods=Qt.NoModifier):
    QTest.mousePress(vpw, button, mods, vp(*pts[0]))
    for pt in pts[1:]:
        ev = QMouseEvent(QEvent.MouseMove, QPointF(vp(*pt)), QPointF(vpw.mapToGlobal(vp(*pt))),
                         Qt.NoButton, button, mods)
        app.sendEvent(vpw, ev)
    QTest.mouseRelease(vpw, button, mods, vp(*pts[-1]))
    app.processEvents()


def px(x, y):
    return QColor(doc.image.pixel(x, y)).name()


def ink():
    """Number of non-white pixels in the picture."""
    return int((const_pixels(doc.image) != 0xFFFFFFFF).sum())


WHITE = "#ffffff"

# ---- start-up state --------------------------------------------------------
ok(doc.size() == QSize(800, 600), "default canvas size")
ok(st.tool == "brush" and st.color1.name() == "#000000" and st.color2.name() == WHITE, "default tool/colours")
ok(win.windowTitle() == "Untitled - Paint", "title")

# ---- every brush leaves ink, and each stroke is one undo step ----------------
for i, (bid, _label) in enumerate(BRUSHES):
    st.set_tool("brush", brush=bid)
    before, depth = ink(), len(doc.undo_stack)
    drag([(20 + k * 6, 30 + i * 50 + math.sin(k / 4.0) * 12) for k in range(50)])
    ok(ink() > before, f"brush {bid} drew nothing")
    ok(len(doc.undo_stack) == depth + 1, f"brush {bid} undo steps")

# ---- pencil sizes and right button uses colour 2 --------------------------------
st.set_tool("pencil")
st.set_size(1)
st.set_color(2, QColor(255, 0, 0))
drag([(400, 20), (500, 20)], button=Qt.RightButton)
ok(px(450, 20) == "#ff0000" and px(450, 21) == WHITE, "pencil right button / 1px")
st.set_size(4)
st.set_color(1, QColor(0, 0, 255))
drag([(400, 40), (500, 40)])
ok(all(px(450, y) == "#0000ff" for y in (38, 39, 40, 41)) and px(450, 42) == WHITE, "pencil 4px")
st.set_color(2, QColor(255, 255, 255))

# ---- eraser: left erases to colour 2, right only replaces colour 1 ---------------
st.set_tool("eraser")
st.set_size(10)
drag([(450, 10), (450, 50)])
ok(px(450, 20) == WHITE and px(450, 40) == WHITE, "eraser")
st.set_color(1, QColor(0, 0, 255))
drag([(480, 10), (480, 50)], button=Qt.RightButton)
ok(px(480, 40) == WHITE and px(480, 20) == "#ff0000", "colour-replace eraser")

# ---- undo / redo ----------------------------------------------------------------
depth = len(doc.undo_stack)
c.undo()
ok(px(480, 40) == "#0000ff" and len(doc.undo_stack) == depth - 1, "undo")
c.redo()
ok(px(480, 40) == WHITE, "redo")

# ---- fill and picker -------------------------------------------------------------
st.set_tool("fill")
st.set_color(1, QColor(181, 230, 29))
QTest.mouseClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(700, 550))
ok(px(700, 550) == "#b5e61d" and px(790, 590) == "#b5e61d", "fill")
c.undo()
ok(px(700, 550) == WHITE, "fill undo")
st.set_tool("pencil")
st.set_tool("picker")
QTest.mouseClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(430, 20))
ok(st.color1.name() == "#ff0000" and st.tool == "pencil", "picker picks and returns to previous tool")

# ---- all shapes --------------------------------------------------------------------
doc.new(800, 600)
st.set_color(1, QColor(0, 0, 0))
st.set_color(2, QColor(255, 242, 0))
st.set_fill("solid")
st.set_outline("solid")
st.set_size(3)
x, y = 20, 20
for sid, _label in SHAPES:
    if sid in ("curve", "polygon"):
        continue
    st.set_tool("shape", shape=sid)
    before = ink()
    drag([(x, y), (x + 30, y + 25), (x + 60, y + 50)])
    ok(c.tool.has_pending(), f"{sid} stays adjustable")
    QTest.keyClick(c, Qt.Key_Return)
    ok(ink() > before and not c.tool.has_pending(), f"shape {sid}")
    x += 75
    if x > 720:
        x, y = 20, y + 70
st.set_tool("shape", shape="rect")
drag([(600, 400), (650, 430), (700, 500)])
shown = c.display_image()                                  # still adjustable, so not in the picture yet
ok(QColor(shown.pixel(650, 450)).name() == "#fff200" and QColor(shown.pixel(600, 400)).name() == "#000000"
   and QColor(shown.pixel(701, 501)).name() == WHITE and px(650, 450) == WHITE, "rect fill/outline/bounds")
st.set_color(2, QColor(0, 162, 232))                     # recolour while still adjustable
drag([(650, 450), (660, 455), (670, 460)])              # ...and move it by (20, 10)
QTest.keyClick(c, Qt.Key_Return)
ok(px(680, 470) == "#00a2e8" and px(720, 510) == "#000000" and px(605, 405) == WHITE, "adjust pending shape")
st.set_tool("shape", shape="oval")
drag([(300, 400), (350, 450), (400, 500)], mods=Qt.ShiftModifier)
ok(c.tool._bbox().width() == c.tool._bbox().height(), "shift makes a circle")
QTest.keyClick(c, Qt.Key_Escape)
ok(not c.tool.has_pending(), "escape cancels shape")
st.set_tool("shape", shape="curve")
before = ink()
drag([(20, 520), (200, 520)])
drag([(80, 480), (90, 470)])
drag([(150, 570), (160, 580)])
ok(ink() > before and not c.tool.has_pending(), "curve")
st.set_tool("shape", shape="polygon")
before = ink()
drag([(240, 520), (300, 510)])
drag([(330, 560), (335, 570)])
drag([(260, 590), (265, 592)])
QTest.mouseDClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(265, 592))
app.processEvents()
ok(ink() > before and not c.tool.has_pending(), "polygon")

# ---- selections -----------------------------------------------------------------------
doc.new(400, 300)
st.set_color(1, QColor(0, 0, 0))
st.set_color(2, QColor(255, 255, 255))
st.set_tool("shape", shape="rect")
st.set_fill("none")
st.set_tool("pencil")
st.set_size(4)
st.set_color(1, QColor(255, 0, 0))
drag([(20, 20), (60, 20)])
st.set_tool("select")
drag([(10, 10), (40, 20), (70, 30)])
sel = c.select_tool.sel
ok(sel is not None and (sel.rect.x(), sel.rect.y(), sel.rect.width(), sel.rect.height()) == (10, 10, 60, 20), "rect selection")
ok(win.crop_btn.isEnabled() and win.copy_btn.isEnabled(), "ribbon enables crop/copy")
drag([(30, 20), (80, 60), (130, 120)])                  # move by (100, 100)
QTest.keyClick(c, Qt.Key_Escape)
ok(px(140, 120) == "#ff0000" and px(40, 20) == WHITE, "move selection")
drag([(110, 110), (140, 120), (170, 130)])
drag([(130, 120), (180, 120), (230, 120)], mods=Qt.ControlModifier)   # ctrl-drag copy
QTest.keyClick(c, Qt.Key_Escape)
ok(px(140, 120) == "#ff0000" and px(240, 120) == "#ff0000", "ctrl-drag copies")
drag([(110, 110), (140, 120), (170, 130)])
c.copy()
QTest.keyClick(c, Qt.Key_Delete)
ok(px(140, 120) == WHITE and not c.has_selection(), "delete selection")
c.paste()
ok(c.has_selection() and c.select_tool.sel.rect.topLeft() == QPoint(0, 0), "paste lands top-left")
QTest.keyClick(c, Qt.Key_Escape)
ok(px(30, 10) == "#ff0000", "pasted pixels")
c.select_all()
ok(c.select_tool.sel.rect == doc.rect(), "select all")
QTest.keyClick(c, Qt.Key_Escape)
drag([(0, 0), (100, 50), (200, 150)])
c.crop()
ok(doc.size() == QSize(200, 150), "crop")
c.undo()
ok(doc.size() == QSize(400, 300), "crop undo")
st.set_sel_mode("free")
st.set_tool("select")
drag([(50, 50), (150, 50), (150, 150), (50, 150), (50, 60)])
ok(c.select_tool.sel is not None and c.select_tool.sel.path is not None, "free-form selection")
c.invert_selection()
ok(c.select_tool.sel.rect == doc.rect(), "invert selection")
QTest.keyClick(c, Qt.Key_Escape)
st.set_sel_mode("rect")

# ---- whole-picture transforms -----------------------------------------------------------
c.rotate("r90")
ok(doc.size() == QSize(300, 400), "rotate 90")
c.rotate("l90")
c.rotate("fliph")
c.rotate("flipv")
c.rotate("180")
ok(doc.size() == QSize(400, 300), "rotate/flip keep size")
c.resize_skew(200, 150)
ok(doc.size() == QSize(200, 150), "resize")
c.undo()
c.resize_skew(400, 300, 20, 0)
ok(doc.width() > 400, "skew widens")
c.undo()
before = px(5, 5)
c.invert_colors()
ok(px(5, 5) == "#000000" and before == WHITE, "invert colours")
c.undo()

# ---- canvas handle resize ------------------------------------------------------------------
h = c._canvas_handles()["rb"]
QTest.mousePress(vpw, Qt.LeftButton, Qt.NoModifier, h)
pt = QPoint(h.x() - 100, h.y() - 50)
app.sendEvent(vpw, QMouseEvent(QEvent.MouseMove, QPointF(pt), QPointF(vpw.mapToGlobal(pt)),
                               Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
QTest.mouseRelease(vpw, Qt.LeftButton, Qt.NoModifier, pt)
ok(abs(doc.width() - 300) <= 4 and abs(doc.height() - 250) <= 4, f"canvas handle resize {doc.size()}")
c.undo()

# ---- text ------------------------------------------------------------------------------------
doc.new(400, 300)
st.set_tool("text")
st.set_color(1, QColor(136, 0, 21))
drag([(20, 20), (100, 60), (300, 100)])
ok(c.text_editing() and win.ribbon.current() == win.text_idx, "text box opens the Text tab")
QTest.keyClicks(c, "Hello")
QTest.keyClick(c, Qt.Key_B, Qt.ControlModifier)
ok(st.bold and win.fmt_btns["bold"].isChecked(), "ctrl+b toggles bold")
QTest.keyClicks(c, " world")
ok(c.text_tool.tdoc.toPlainText() == "Hello world", "typing")
QTest.keyClick(c, Qt.Key_Backspace)
QTest.keyClick(c, Qt.Key_A, Qt.ControlModifier)
QTest.keyClick(c, Qt.Key_C, Qt.ControlModifier)
ok(QGuiApplication.clipboard().text() == "Hello worl", "text copy")
QTest.mouseClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(350, 250))
ok(not c.text_editing() and win.ribbon.current() == win.home_idx and ink() > 0, "text commits on click-away")
st.set_font(bold=False)
depth = len(doc.undo_stack)
drag([(20, 150), (100, 180), (300, 220)])
QTest.keyClicks(c, "gone")
QTest.keyClick(c, Qt.Key_Escape)
ok(not c.text_editing() and len(doc.undo_stack) == depth, "escape discards text")

# ---- zoom, view options, ribbon ----------------------------------------------------------------
st.set_tool("pencil")
c.set_zoom(8)
ok(c.zoom == 8 and win.status.zoomer.zoom == 8 and not win.zoomin_btn.isEnabled(), "zoom in limit")
c.zoom_step(-1)
ok(c.zoom == 7, "zoom step")
c.set_zoom(1)
win.set_rulers(True)
win.set_grid(True)
ok(win.hruler.isVisible() and c.show_grid and win.rulers_chk.isChecked(), "rulers/grid")
win.set_rulers(False)
win.set_grid(False)
win.ribbon.set_minimized(True)
ok(win.ribbon.height() < 40, "ribbon minimizes")
win.ribbon.set_minimized(False)
win.resize(700, 600)
app.processEvents()
ok(any(s.isVisible() for s in win.home_page._stubs.values()), "groups collapse when narrow")
win.resize(1100, 760)
app.processEvents()
ok(not any(s.isVisible() for s in win.home_page._stubs.values()), "groups expand again")

# ---- popups survive the click that opened them ---------------------------------------------------
st.set_tool("brush", brush="brush")
pop = win._brush_menu()
pop.show()
app.processEvents()
QTest.mouseRelease(pop, Qt.LeftButton, Qt.NoModifier, QPoint(-40, -40))
ok(pop.isVisible(), "gallery stays open after the opening click is released")
QTest.mouseClick(pop, Qt.LeftButton, Qt.NoModifier, pop._rect(5).center())
app.processEvents()
ok(st.brush == "crayon" and st.tool == "brush", "gallery pick")
pop = win._size_menu()
pop.show()
app.processEvents()
QTest.mouseClick(pop, Qt.LeftButton, Qt.NoModifier, pop.rows[3].center())
app.processEvents()
ok(st.size() == 40, "size pick")
st.set_tool("pencil")

# ---- file formats ----------------------------------------------------------------------------------
doc.new(120, 90)
st.set_tool("shape", shape="star5")
st.set_fill("solid")
st.set_color(1, QColor(0, 0, 0))
st.set_color(2, QColor(237, 28, 36))
drag([(10, 10), (60, 50), (110, 80)])
st.set_tool("pencil")
tmp = tempfile.mkdtemp()
for key, _label, exts in FORMATS:
    path = os.path.join(tmp, f"t_{key}.{exts[0]}")
    save_image(doc.image, path, key)
    back = load_image(path)
    ok(back.size() == doc.size(), f"{key} size")
    if key != "jpeg":
        want = reduce_colors(doc.image, key).convertToFormat(QImage.Format_RGB32)
        got = back.convertToFormat(QImage.Format_RGB32)
        ok(bool((const_pixels(want) == const_pixels(got)).all()), f"{key} round trip")
path = os.path.join(tmp, "saved.png")
ok(win._write(path, "png") and not doc.modified and win.windowTitle() == "saved.png - Paint", "save")
ok(win.open_path(os.path.join(tmp, "t_bmp24.bmp")) and win.windowTitle() == "t_bmp24.bmp - Paint", "open")
ok(os.path.join(tmp, "saved.png") in win._recent(), "recent pictures")

big = QImage(1500, 1000, QImage.Format_RGB32)
big.fill(QColor(255, 255, 255))
ok(flood_fill(big, 5, 5, QColor(1, 2, 3)) and QColor(big.pixel(1499, 999)).name() == "#010203", "large fill")
ok(not flood_fill(big, 5, 5, QColor(1, 2, 3)), "fill with same colour is a no-op")

doc.modified = False
win.close()
print(f"OK - {checks} checks passed")
