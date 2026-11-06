"""End-to-end smoke test. Drives the real window with synthetic input.

    QT_QPA_PLATFORM=offscreen python tests/smoke_test.py
"""
import math
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from PySide6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, QEvent, QSettings, QSize  # noqa: E402
from PySide6.QtGui import QMouseEvent, QColor, QImage, QGuiApplication, QPainter, QPen  # noqa: E402
import numpy as np  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from opendraw7.app import create_app  # noqa: E402

app = create_app(["opendraw7-test"])
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, tempfile.mkdtemp())

from opendraw7.mainwindow import MainWindow  # noqa: E402
from opendraw7.brushes import BRUSHES, make_stroke  # noqa: E402
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

# filling inside a smoothed outline must not leave a pale ring, nor reach past the outline
ring = QImage(200, 160, QImage.Format_RGB32)
ring.fill(QColor(255, 255, 255))
rp = QPainter(ring)
rp.setRenderHint(QPainter.Antialiasing, True)
rp.setPen(QPen(QColor(0, 0, 0), 3))
rp.drawEllipse(QRectF(20, 20, 160, 120))
rp.end()
flood_fill(ring, 100, 80, QColor(255, 0, 0))
ra = const_pixels(ring).astype(np.int64)
rg = (ra >> 8) & 0xFF
ryy, rxx = np.mgrid[0:160, 0:200]
rin = ((rxx - 100) / 80.0) ** 2 + ((ryy - 80) / 60.0) ** 2 < 1.0   # up to the middle of the outline
ok(int((rin & (rg > 60)).sum()) == 0, "fill leaves no pale ring inside a smoothed outline")
ok(QColor(ring.pixel(2, 2)).name() == "#ffffff" and QColor(ring.pixel(100, 3)).name() == "#ffffff",
   "fill stays inside a smoothed outline")
# fill a thin soft brush loop, fill it back to white, then fill everything: no specks may survive
loop = QImage(300, 220, QImage.Format_RGB32)
loop.fill(QColor(255, 255, 255))
dark = QColor(136, 0, 21)
lst = make_stroke("brush", loop, dark, 1)
lpts = [QPointF(150 + 100 * math.cos(k / 60 * 2 * math.pi) + 8 * math.sin(k / 60 * 2 * math.pi * 7),
                110 + 70 * math.sin(k / 60 * 2 * math.pi)) for k in range(61)]
for la, lb in zip(lpts, lpts[1:]):
    lst.segment(la, lb)
flood_fill(loop, 150, 110, dark)
flood_fill(loop, 150, 110, QColor(255, 255, 255))
la_ = const_pixels(loop).astype(np.int64)
ok(int((((la_ >> 8) & 0xFF) < 230).sum()) == 0, "refilling a filled soft shape leaves no specks")
flood_fill(loop, 2, 2, dark)
la_ = const_pixels(loop).astype(np.int64)
ok(int((((la_ >> 8) & 0xFF) > 24).sum()) == 0, "filling everything after a refill leaves no specks")

st.set_color(1, QColor(0, 0, 0))
st.set_color(2, QColor(255, 255, 255))
# ---- zoom to fit ----------------------------------------------------------------
doc.new(1600, 1200)
c.zoom_to_fit()
app.processEvents()
vps = c.viewport().size()
ok(doc.width() * c.zoom <= vps.width() and doc.height() * c.zoom <= vps.height() and c.zoom < 1, "zoom to fit shrinks")
doc.new(100, 80)
c.zoom_to_fit()
ok(c.zoom > 1 and c.zoom == int(c.zoom), "zoom to fit enlarges small pictures to a whole zoom")
c.set_zoom(1.0)


# ---- magic wand ---------------------------------------------------------------
def paint_test_picture():
    doc.new(400, 300)
    p = QPainter(doc.image)
    p.fillRect(40, 40, 100, 60, QColor(255, 0, 0))
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 255))
    p.drawEllipse(QRectF(200, 100, 120, 120))
    p.end()
    doc.changed.emit()
    app.processEvents()


paint_test_picture()
st.set_tool("select")
st.set_sel_mode("wand")
QTest.mouseClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(60, 60))
app.processEvents()
s = c.select_tool.sel
ok(s is not None and s.rect == QRect(40, 40, 100, 60), "wand selects the red rectangle")
QTest.mouseClick(vpw, Qt.LeftButton, Qt.ShiftModifier, vp(260, 160))
app.processEvents()
s = c.select_tool.sel
ok(s is not None and s.rect.right() >= 318 and s.mask is not None, "shift+wand adds the circle")
ok(len(s.edges()) > 10, "wand selection has an outline")
c.delete_selection()
ok(px(60, 60) == WHITE and px(260, 160) == WHITE and px(10, 10) == WHITE, "deleting a wand selection")
c.undo()
ok(px(60, 60) == "#ff0000" and px(260, 160) == "#0000ff", "undo after wand delete")
QTest.mouseClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(10, 10))
app.processEvents()
c.invert_selection()
s = c.select_tool.sel
ok(s is not None and s.mask is not None and s.mask[60 - s.rect.top(), 60 - s.rect.left()]
   and not s.mask[10 - s.rect.top(), 10 - s.rect.left()] if s.rect.contains(QPoint(10, 10)) else True,
   "invert a wand selection")
c.commit_pending()
# wand selection moves its exact shape: drag the circle and the square stays
QTest.mouseClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(260, 160))
app.processEvents()
drag([(260, 160), (230, 160), (200, 160)])
c.commit_pending()
ok(px(200, 160) == "#0000ff" and px(60, 60) == "#ff0000" and px(315, 160) == WHITE, "move a wand selection")
st.set_sel_mode("rect")

# ---- shift-drag trail ---------------------------------------------------------------
paint_test_picture()
st.set_tool("select")
drag([(39, 39), (141, 101)])
before = int((const_pixels(doc.image) == 0xFFFF0000).sum())
drag([(80, 70), (110, 70), (140, 70), (170, 70), (200, 70)], mods=Qt.ShiftModifier)
c.commit_pending()
after = int((const_pixels(doc.image) == 0xFFFF0000).sum())
ok(px(60, 60) == "#ff0000" and px(150, 60) == "#ff0000" and after > before * 1.8, "shift-drag leaves a trail")

# ---- transparency -------------------------------------------------------------------
paint_test_picture()
doc.set_transparent(True)
ok(doc.transparent and px(60, 60) == "#ff0000", "turn on transparent background")
st.set_tool("eraser")
drag([(150, 20), (190, 20), (190, 60)])
ok(QColor.fromRgba(doc.image.pixel(170, 20)).alpha() == 0, "eraser clears to transparent")
st.set_tool("select")
drag([(39, 39), (141, 101)])
c.delete_selection()
ok(QColor.fromRgba(doc.image.pixel(60, 60)).alpha() == 0, "delete clears to transparent")
st.set_tool("fill")
QTest.mouseClick(vpw, Qt.LeftButton, Qt.NoModifier, vp(60, 60))
app.processEvents()
ok(QColor.fromRgba(doc.image.pixel(60, 60)).alpha() == 255, "fill a transparent area")
c.undo()
tmp = tempfile.mkdtemp()
for ext, fmt, keeps in (("png", "png", True), ("gif", "gif", True), ("tif", "tiff", True), ("jpg", "jpeg", False),
                        ("bmp", "bmp24", False)):
    path = os.path.join(tmp, "clear." + ext)
    save_image(doc.image, path, fmt)
    back = load_image(path)
    ok(back.hasAlphaChannel() == keeps and (QColor.fromRgba(back.pixel(60, 60)).alpha() == 0) == keeps,
       f"transparency round trip through {ext}")
    ok(QColor.fromRgba(back.pixel(260, 160)).name() in ("#0000ff", "#0000fe", "#0100ff"), f"colours survive {ext}")
c.rotate("r90")
ok(doc.transparent, "rotating keeps transparency")
c.undo()
st.set_tool("select")
drag([(149, 9), (196, 66)])
c.crop()
ok(doc.transparent and doc.size() == QSize(47, 57) and QColor.fromRgba(doc.image.pixel(21, 11)).alpha() == 0,
   "crop keeps transparency")
c.undo()
doc.set_transparent(False)
ok(not doc.transparent and px(60, 60) == WHITE, "turn off transparent background")
c.undo()
ok(doc.transparent, "undo brings transparency back")
c.undo()
c.undo()
doc.new(800, 600)

# ---- autosave and crash recovery ------------------------------------------------------
import json  # noqa: E402
from opendraw7.recovery import AutoSaver, leftovers  # noqa: E402
rdir = tempfile.mkdtemp()
saver = AutoSaver(win, interval=10 ** 9, folder=rdir)
ok(not saver.save_now(wait=True), "nothing to autosave on an unchanged picture")
paint_test_picture()
doc.push_undo()
doc.changed.emit()
ok(saver.save_now(wait=True) and os.path.exists(saver.png) and os.path.exists(saver.json), "autosave writes a copy")
ok(not leftovers(rdir), "a running window's copy is not offered for recovery")
meta = json.load(open(saver.json))
meta["pid"] = 2 ** 22 + 12345                 # pretend it was left by a process that is gone
json.dump(meta, open(saver.json, "w"))
found = leftovers(rdir)
ok(len(found) == 1, "a crashed window's copy is found")
doc.new(800, 600)
ok(not os.path.exists(saver.png), "starting a new picture removes the copy")
from PySide6.QtGui import QImage as _QI  # noqa: E402
doc.restore(_QI(found[0][1]) if os.path.exists(found[0][1]) else doc.image, None, "png")
paint_test_picture()
doc.push_undo()
doc.changed.emit()
saver.save_now(wait=True)
img_copy = _QI(saver.png)
doc.new(800, 600)
doc.restore(img_copy, "/tmp/somewhere/pic.png", "png")
ok(doc.modified and doc.path == "/tmp/somewhere/pic.png" and px(60, 60) == "#ff0000" and doc.size() == QSize(400, 300),
   "restore brings the picture back unsaved")
saver.clear()
saver.timer.stop()
doc.new(800, 600)

# ---- text on a picture made by convertToFormat (opened file, transparent) keeps the picture alive ----
import gc  # noqa: E402
for transparent in (True, False):
    doc.new(300, 200)
    doc.set_transparent(transparent)
    st.set_tool("text")
    c.text_tool._create(QRect(10, 10, 200, 40))
    c.text_tool.insert_text("Hello")
    win.grab()
    c.commit_pending()
    gc.collect()
    app.processEvents()
    alive = True
    try:
        doc.image.width()
    except RuntimeError:
        alive = False
    ok(alive, f"text keeps the picture alive (transparent={transparent})")
doc.new(800, 600)

# ---- 0.2.1 regressions -----------------------------------------------------------------
from PySide6.QtWidgets import QMessageBox  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from opendraw7.brushes import ReplaceStroke  # noqa: E402
_warned = []
_orig_warning = QMessageBox.warning
QMessageBox.warning = staticmethod(lambda *a, **k: _warned.append(a[2]) or QMessageBox.Ok)
doc.new(800, 600)
c.resize_skew(30000, 30000)
ok(doc.size() == QSize(800, 600) and _warned, "a too-large resize is refused with a message")
_warned.clear()
c.resize_skew(800, 600, 89, 89)
ok(doc.size() == QSize(800, 600) and _warned, "a too-large skew is refused with a message")
ok(not doc.resize_canvas(30000, 30000, QColor(255, 255, 255)) and doc.size() == QSize(800, 600),
   "a too-large canvas is refused")
c.resize_skew(1600, 1200)
ok(doc.size() == QSize(1600, 1200), "ordinary resizes still work")
c.undo()
QMessageBox.warning = _orig_warning
# right-button eraser leaves see-through pixels alone
doc.new(200, 100)
doc.set_transparent(True)
pp = QPainter(doc.image)
pp.setCompositionMode(QPainter.CompositionMode_Clear)
pp.fillRect(0, 0, 100, 100, QColor(0, 0, 0))
pp.end()
rs = ReplaceStroke(doc.image, QColor(255, 255, 255), 10, QColor(0, 0, 0))
rs.start(QPointF(50, 50))
rs.line_to(QPointF(60, 50))
ok(doc.image.pixel(50, 50) == 0, "right-button eraser keeps see-through pixels see-through")
doc.new(800, 600)
# big photos open (Qt refuses over 256 MB by default)
bigp = os.path.join(tempfile.mkdtemp(), "big.png")
bimg = QImage(12000, 6000, QImage.Format_RGB32)
bimg.fill(QColor(10, 20, 30))
bimg.save(bigp)
del bimg
ok(load_image(bigp).size() == QSize(12000, 6000), "a 12000 x 6000 photo opens")
# zoom label after fit to window
lab = win.status.zoomer.label
ok(lab(0.634722) == "63%" and lab(0.125) == "12.5%" and lab(0.25) == "25%" and lab(8) == "800%",
   "zoom label is rounded")

# ---- key tips -------------------------------------------------------------------------
win.activateWindow()
QTest.qWait(100)
if win.isActiveWindow():
    QTest.keyPress(c, Qt.Key_Alt)
    QTest.keyRelease(c, Qt.Key_Alt)
    ok(win.keytips.level == 1 and {"F", "H", "V"} <= {t.keys for t in win.keytips.overlay.tips}, "alt shows key tips")
    QTest.keyClick(c, Qt.Key_H)
    QTest.keyClick(c, Qt.Key_P)
    QTest.qWait(30)
    ok(st.tool == "pencil" and win.keytips.level == 0, "key tips H, P pick the pencil")
    QTest.keyClick(c, Qt.Key_F10)
    QTest.keyClick(c, Qt.Key_V)
    QTest.keyClick(c, Qt.Key_G)
    QTest.qWait(30)
    ok(c.show_grid and win.ribbon.current() == win.view_idx, "key tips F10, V, G show gridlines")
    win.set_grid(False)
    win.ribbon.set_current(win.home_idx)
    QTest.keyClick(c, Qt.Key_F10)
    QTest.keyClick(c, Qt.Key_Escape)
    ok(win.keytips.level == 0, "esc hides key tips")
    for seq in ([(QEvent.KeyPress, Qt.Key_Alt, Qt.NoModifier), (QEvent.KeyRelease, Qt.Key_Alt, Qt.AltModifier | Qt.ShiftModifier)],
                [(QEvent.KeyPress, Qt.Key_Shift, Qt.NoModifier), (QEvent.KeyPress, Qt.Key_Alt, Qt.ShiftModifier),
                 (QEvent.KeyRelease, Qt.Key_Alt, Qt.AltModifier | Qt.ShiftModifier)]):
        for typ, key, mod in seq:
            app.sendEvent(c, QKeyEvent(typ, key, mod))
        ok(win.keytips.level == 0, "alt+shift (keyboard layout switch) does not show key tips")
        win.keytips.hide()

doc.modified = False
win.close()
print(f"OK - {checks} checks passed")
