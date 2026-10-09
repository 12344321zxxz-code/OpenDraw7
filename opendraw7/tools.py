"""Canvas tools. Each tool owns its in-progress object and knows how to commit it."""
import math
from PySide6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, QSize, QTimer
from PySide6.QtGui import (QImage, QPainter, QColor, QPen, QBrush, QPainterPath, QPolygonF, QCursor,
                           QTextDocument, QTextCursor, QTextCharFormat, QFont, QTextOption,
                           QAbstractTextDocumentLayout, QPalette, QGuiApplication, QTransform)

from . import icons
from .brushes import make_stroke, PencilStroke, ReplaceStroke, render_shape
from .document import flood_fill, pixels, flatten
from .shapes import shape_path, is_curved

L, R = Qt.LeftButton, Qt.RightButton
HANDLE_CURSORS = [Qt.SizeFDiagCursor, Qt.SizeVerCursor, Qt.SizeBDiagCursor, Qt.SizeHorCursor,
                  Qt.SizeFDiagCursor, Qt.SizeVerCursor, Qt.SizeBDiagCursor, Qt.SizeHorCursor]


class Ev:
    __slots__ = ("pos", "posf", "view", "button", "buttons", "mods", "gpos")

    def __init__(self, pos, posf, view, button, buttons, mods, gpos):
        self.pos, self.posf, self.view = pos, posf, view
        self.button, self.buttons, self.mods, self.gpos = button, buttons, mods, gpos

    @property
    def shift(self):
        return bool(self.mods & Qt.ShiftModifier)

    @property
    def ctrl(self):
        return bool(self.mods & Qt.ControlModifier)


# ------------------------------------------------------------ overlay bits --
def outline_of(vr: QRect):
    """(x0, y0, x1, y1) of the 1px frame drawn just outside a view rect."""
    return vr.left() - 1, vr.top() - 1, vr.left() + vr.width(), vr.top() + vr.height()


def handle_points(o):
    x0, y0, x1, y1 = o
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    return [(x0, y0), (cx, y0), (x1, y0), (x1, cy), (x1, y1), (cx, y1), (x0, y1), (x0, cy)]


def hit_handle(o, pos, tol=4):
    for i, (hx, hy) in enumerate(handle_points(o)):
        if abs(pos.x() - hx) <= tol and abs(pos.y() - hy) <= tol:
            return i
    return None


def draw_dashed(p: QPainter, o, color=QColor(0, 60, 140)):
    x0, y0, x1, y1 = o
    p.save()
    p.setRenderHint(QPainter.Antialiasing, False)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255), 1))
    p.drawRect(x0, y0, x1 - x0, y1 - y0)
    pen = QPen(color, 1)
    pen.setDashPattern([4, 4])
    p.setPen(pen)
    p.drawRect(x0, y0, x1 - x0, y1 - y0)
    p.restore()


def draw_handles(p: QPainter, pts):
    p.save()
    p.setRenderHint(QPainter.Antialiasing, False)
    p.setPen(QPen(QColor(85, 85, 85), 1))
    p.setBrush(QColor(255, 255, 255))
    for hx, hy in pts:
        p.drawRect(int(hx) - 2, int(hy) - 2, 4, 4)
    p.restore()


def resize_rect(r: QRect, h, dx, dy) -> QRect:
    l, t, rg, b = r.left(), r.top(), r.right(), r.bottom()
    if h in (0, 6, 7):
        l += dx
    if h in (2, 3, 4):
        rg += dx
    if h in (0, 1, 2):
        t += dy
    if h in (4, 5, 6):
        b += dy
    if rg < l:
        l, rg = rg, l
    if b < t:
        t, b = b, t
    return QRect(QPoint(l, t), QPoint(rg, b))


class Tool:
    busy = False

    def __init__(self, canvas):
        self.c = canvas

    def activate(self):
        pass

    def deactivate(self):
        self.commit()

    def commit(self):
        pass

    def cancel(self):
        pass

    def has_pending(self):
        return False

    def press(self, ev):
        pass

    def move(self, ev):
        pass

    def release(self, ev):
        pass

    def double_click(self, ev):
        pass

    def key(self, e):
        return False

    def wants_shortcut(self, e):
        return False

    def composite(self):
        return None

    def paint(self, p):
        pass

    def cursor(self, ev):
        return icons.cursor("cross")

    def style_changed(self, what):
        pass


# ----------------------------------------------------------------- freehand --
class FreehandTool(Tool):
    def __init__(self, canvas, kind):
        super().__init__(canvas)
        self.kind = kind            # 'pencil' | 'eraser' | 'brush'
        self.stroke = None
        self.button = None
        self.timer = QTimer(canvas)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self._tick)

    @property
    def busy(self):
        return self.stroke is not None

    def _pt(self, ev):
        if self.kind in ("pencil", "eraser"):
            return QPointF(ev.pos)
        return ev.posf

    def press(self, ev):
        if self.stroke is not None:
            self._abort()
            return
        if ev.button not in (L, R):
            return
        c, st = self.c, self.c.state
        c.doc.push_undo()
        left = ev.button == L
        img = c.doc.image
        size = st.size()
        if self.kind == "eraser":
            self.stroke = (PencilStroke(img, st.color2, size) if left
                           else ReplaceStroke(img, st.color2, size, st.color1))
        elif self.kind == "pencil":
            self.stroke = PencilStroke(img, st.color1 if left else st.color2, size)
        else:
            self.stroke = make_stroke(st.brush, img, st.color1 if left else st.color2, size)
        self.button = ev.button
        self.stroke.start(self._pt(ev))
        if self.stroke.needs_timer:
            self.timer.start()
        c.viewport().update()

    def move(self, ev):
        if self.stroke is not None:
            self.stroke.line_to(self._pt(ev))
        if self.stroke is not None or self.kind == "eraser":
            self.c.viewport().update()

    def release(self, ev):
        if self.stroke is None or ev.button != self.button:
            return
        self.stroke.finish()
        self.stroke = None
        self.timer.stop()
        self.c.doc.changed.emit()

    def _tick(self):
        if self.stroke is not None:
            self.stroke.tick()
            self.c.viewport().update()

    def _abort(self):
        self.stroke = None
        self.timer.stop()
        self.c.doc.drop_last_undo()

    def commit(self):
        if self.stroke is not None:
            self.stroke.finish()
            self.stroke = None
            self.timer.stop()

    def paint(self, p):
        if self.kind != "eraser" or self.c.hover is None:
            return
        n = self.c.state.size()
        off = n // 2
        pos = self.c.hover.pos
        vr = self.c.view_rect(QRect(pos.x() - off, pos.y() - off, n, n))
        p.fillRect(vr, self.c.state.color2)
        p.setPen(QPen(QColor(0, 0, 0), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(vr.adjusted(0, 0, -1, -1))

    def cursor(self, ev):
        if self.kind == "pencil":
            return icons.cursor("pencil")
        if self.kind == "eraser":
            return QCursor(Qt.BlankCursor)
        return icons.cursor("cross")


class FillTool(Tool):
    def press(self, ev):
        if ev.button not in (L, R):
            return
        c = self.c
        if not c.doc.rect().contains(ev.pos):
            return
        color = c.state.color1 if ev.button == L else c.state.color2
        c.doc.push_undo()
        if flood_fill(c.doc.image, ev.pos.x(), ev.pos.y(), color):
            c.doc.changed.emit()
        else:
            c.doc.drop_last_undo()

    def cursor(self, ev):
        return icons.cursor("fill")


class PickerTool(Tool):
    def _pick(self, ev):
        if ev.buttons & (L | R) or ev.button in (L, R):
            col = self.c.color_at(ev.pos)
            if col is not None:
                which = 1 if (ev.button == L or ev.buttons & L) else 2
                self.c.state.set_color(which, col)

    def press(self, ev):
        self._pick(ev)

    def move(self, ev):
        if ev.buttons & (L | R):
            self._pick(ev)

    def release(self, ev):
        if ev.button in (L, R):
            self.c.state.restore_tool()

    def cursor(self, ev):
        return icons.cursor("picker")


class MagnifierTool(Tool):
    def press(self, ev):
        if ev.button == L:
            self.c.zoom_step(+1, ev.posf)
        elif ev.button == R:
            self.c.zoom_step(-1, ev.posf)

    def move(self, ev):
        self.c.viewport().update()

    def paint(self, p):
        c = self.c
        if c.hover is None:
            return
        nz = c.next_zoom(+1)
        if nz == c.zoom:
            return
        vw, vh = c.viewport().width(), c.viewport().height()
        w, h = vw * c.zoom / nz, vh * c.zoom / nz
        v = c.hover.view
        p.setRenderHint(QPainter.Antialiasing, False)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255), 1))
        r = QRect(int(v.x() - w / 2), int(v.y() - h / 2), int(w), int(h))
        p.drawRect(r.adjusted(1, 1, -1, -1))
        p.setPen(QPen(QColor(0, 0, 0), 1))
        p.drawRect(r)

    def cursor(self, ev):
        return icons.cursor("magnifier")


# ---------------------------------------------------------------- selection --
class Selection:
    def __init__(self, rect: QRect, path=None, image=None):
        self.rect = QRect(rect)
        self.path = path          # QPainterPath in local coords, or None for the whole rect
        self.image = image        # lifted pixels (ARGB premultiplied) or None
        self.version = 0


class SelectTool(Tool):
    def __init__(self, canvas):
        super().__init__(canvas)
        self.sel = None
        self.mode = None
        self.anchor = None
        self.cur = None
        self.pts = []
        self.handle = None
        self.start_rect = None
        self.press_pos = None
        self._float_key = None
        self._float_img = None

    @property
    def busy(self):
        return self.mode is not None

    def has_pending(self):
        return self.sel is not None

    # -- helpers -------------------------------------------------------------
    def _clamp(self, pt: QPoint, inclusive=True):
        d = self.c.doc
        hi_x = d.width() if inclusive else d.width() - 1
        hi_y = d.height() if inclusive else d.height() - 1
        return QPoint(max(0, min(hi_x, pt.x())), max(0, min(hi_y, pt.y())))

    def _notify(self):
        self.c.sizeInfo.emit(self.sel.rect.size() if self.sel else None)
        self.c.stateChanged.emit()
        self.c.invalidate()

    def set_selection(self, rect, path=None, image=None):
        self.sel = Selection(rect, path, image)
        self.mode = None
        self._notify()

    def _local_path(self):
        s = self.sel
        if s.path is not None:
            return s.path
        p = QPainterPath()
        p.addRect(QRectF(0, 0, s.rect.width(), s.rect.height()))
        return p

    def lift(self, copy=False):
        s = self.sel
        if s is None or s.image is not None:
            return
        doc = self.c.doc
        doc.push_undo()
        r = s.rect
        img = QImage(r.size(), QImage.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        p.drawImage(0, 0, doc.image, r.x(), r.y(), r.width(), r.height())
        if s.path is not None:
            mask = QImage(r.size(), QImage.Format_ARGB32_Premultiplied)
            mask.fill(0)
            mp = QPainter(mask)
            mp.fillPath(s.path, QColor(255, 255, 255))
            mp.end()
            p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
            p.drawImage(0, 0, mask)
        p.end()
        if not copy:
            dp = QPainter(doc.image)
            dp.translate(r.topLeft())
            dp.fillPath(self._local_path(), self.c.state.color2)
            dp.end()
        s.image = img
        s.version += 1
        self.c.invalidate()

    def floating(self) -> QImage:
        s = self.sel
        st = self.c.state
        key = (id(s), s.version, s.rect.width(), s.rect.height(), st.transparent_sel, st.color2.rgb())
        if key == self._float_key and self._float_img is not None:
            return self._float_img
        img = s.image
        if st.transparent_sel:
            img = img.copy()
            a = pixels(img)
            a[a == (0xFF000000 | (st.color2.rgb() & 0xFFFFFF))] = 0
        if img.size() != s.rect.size():
            img = img.scaled(s.rect.size(), Qt.IgnoreAspectRatio,
                             Qt.FastTransformation if st.transparent_sel else Qt.SmoothTransformation)
        self._float_key, self._float_img = key, img
        return img

    def bake(self):
        """Make the lifted image match the current rect size (after handle scaling)."""
        s = self.sel
        if s.image is not None and s.image.size() != s.rect.size():
            s.image = s.image.scaled(s.rect.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            s.path = None
            s.version += 1

    def composite(self):
        s = self.sel
        if s is None or s.image is None:
            return None
        out = QImage(self.c.doc.image)
        p = QPainter(out)
        p.drawImage(s.rect.topLeft(), self.floating())
        p.end()
        return out

    def commit(self):
        s = self.sel
        self.mode = None
        if s is None:
            return
        if s.image is not None:
            p = QPainter(self.c.doc.image)
            p.drawImage(s.rect.topLeft(), self.floating())
            p.end()
        self.sel = None
        self._float_img = None
        self.c.doc.changed.emit()
        self._notify()

    def cancel(self):
        self.commit()

    # -- commands ------------------------------------------------------------
    def select_all(self):
        self.commit()
        self.set_selection(self.c.doc.rect())

    def invert(self):
        s = self.sel
        if s is None:
            return
        inner = QPainterPath(self._local_path())
        inner.translate(s.rect.left(), s.rect.top())
        self.commit()
        full = QPainterPath()
        full.addRect(QRectF(self.c.doc.rect()))
        self.set_selection(self.c.doc.rect(), full.subtracted(inner))

    def delete(self):
        s = self.sel
        if s is None:
            return
        if s.image is None:
            doc = self.c.doc
            doc.push_undo()
            p = QPainter(doc.image)
            p.translate(s.rect.topLeft())
            p.fillPath(self._local_path(), self.c.state.color2)
            p.end()
        self.sel = None
        self.mode = None
        self.c.doc.changed.emit()
        self._notify()

    def content(self, bg=QColor(255, 255, 255)) -> QImage:
        """Opaque picture of what is selected."""
        s = self.sel
        out = QImage(s.rect.size(), QImage.Format_RGB32)
        out.fill(bg)
        p = QPainter(out)
        if s.image is not None:
            p.drawImage(0, 0, self.floating())
        else:
            if s.path is not None:
                p.setClipPath(s.path)
            p.drawImage(0, 0, self.c.doc.image, s.rect.x(), s.rect.y(), s.rect.width(), s.rect.height())
        p.end()
        return out

    def copy(self):
        if self.sel is not None:
            QGuiApplication.clipboard().setImage(self.content())

    def cut(self):
        if self.sel is not None:
            self.copy()
            self.delete()

    def crop(self):
        s = self.sel
        if s is None:
            return
        doc = self.c.doc
        img = self.content(self.c.state.color2)
        r = QRect(s.rect)
        lifted = s.image is not None
        self.sel = None
        self.mode = None
        if not lifted:
            doc.push_undo()
        visible = r.intersected(doc.rect()) if not lifted else r
        if visible != r and not visible.isEmpty():
            img = img.copy(visible.translated(-r.topLeft()))
        doc.set_image(img)
        self._notify()

    def paste(self, img: QImage):
        c, doc = self.c, self.c.doc
        self.commit()
        img = img.convertToFormat(QImage.Format_ARGB32_Premultiplied)
        doc.push_undo()
        if img.width() > doc.width() or img.height() > doc.height():
            big = QImage(max(img.width(), doc.width()), max(img.height(), doc.height()), QImage.Format_RGB32)
            big.fill(c.state.color2)
            p = QPainter(big)
            p.drawImage(0, 0, doc.image)
            p.end()
            doc.set_image(big)
        tl = c.visible_doc_origin()
        x = min(tl.x(), max(0, doc.width() - img.width()))
        y = min(tl.y(), max(0, doc.height() - img.height()))
        self.set_selection(QRect(QPoint(x, y), img.size()), None, img)

    def transform(self, fn):
        """Apply fn(QImage)->QImage to the lifted selection, keeping its top-left."""
        s = self.sel
        if s is None:
            return
        self.lift()
        self.bake()
        img = fn(s.image).convertToFormat(QImage.Format_ARGB32_Premultiplied)
        s.image = img
        s.path = None
        s.rect = QRect(s.rect.topLeft(), img.size())
        s.version += 1
        self._notify()

    # -- mouse ---------------------------------------------------------------
    def _outline(self):
        return outline_of(self.c.view_rect(self.sel.rect))

    def press(self, ev):
        if ev.button == R:
            if self.mode in ("rubber", "lasso"):
                self.mode = None
                self.c.viewport().update()
                return
            self.c.contextMenuRequested.emit(ev.gpos)
            return
        if ev.button != L:
            return
        s = self.sel
        if s is not None:
            h = hit_handle(self._outline(), ev.view)
            if h is not None:
                self.mode, self.handle = "resize", h
                self.start_rect, self.press_pos = QRect(s.rect), ev.pos
                return
            if s.rect.contains(ev.pos):
                self.mode = "move"
                self.start_rect, self.press_pos = QRect(s.rect), ev.pos
                if ev.ctrl:
                    if s.image is None:
                        self.lift(copy=True)
                    else:
                        p = QPainter(self.c.doc.image)
                        p.drawImage(s.rect.topLeft(), self.floating())
                        p.end()
                return
            self.commit()
        self.anchor = self._clamp(ev.pos)
        self.cur = QRect()
        if self.c.state.sel_mode == "free":
            self.mode = "lasso"
            self.pts = [QPointF(self.anchor)]
        else:
            self.mode = "rubber"

    def move(self, ev):
        s = self.sel
        if self.mode == "rubber":
            pt = self._clamp(ev.pos)
            dx, dy = pt.x() - self.anchor.x(), pt.y() - self.anchor.y()
            if ev.shift:
                m = min(abs(dx), abs(dy))
                dx, dy = math.copysign(m, dx), math.copysign(m, dy)
            x0, x1 = sorted((self.anchor.x(), self.anchor.x() + int(dx)))
            y0, y1 = sorted((self.anchor.y(), self.anchor.y() + int(dy)))
            self.cur = QRect(x0, y0, x1 - x0, y1 - y0)
            self.c.sizeInfo.emit(self.cur.size())
            self.c.viewport().update()
        elif self.mode == "lasso":
            self.pts.append(QPointF(self._clamp(ev.pos)))
            self.c.viewport().update()
        elif self.mode == "move":
            d = ev.pos - self.press_pos
            if d.isNull() and s.image is None:
                return
            self.lift()
            s.rect = self.start_rect.translated(d)
            self.c.invalidate()
        elif self.mode == "resize":
            d = ev.pos - self.press_pos
            if d.isNull() and s.image is None:
                return
            self.lift()
            s.rect = resize_rect(self.start_rect, self.handle, d.x(), d.y())
            self.c.sizeInfo.emit(s.rect.size())
            self.c.invalidate()

    def release(self, ev):
        if ev.button != L:
            return
        mode, self.mode = self.mode, None
        if mode == "rubber":
            if self.cur.width() >= 1 and self.cur.height() >= 1:
                self.set_selection(self.cur)
            else:
                self._notify()
        elif mode == "lasso":
            if len(self.pts) > 2:
                poly = QPolygonF(self.pts)
                br = poly.boundingRect().toAlignedRect().intersected(self.c.doc.rect())
                if br.width() >= 1 and br.height() >= 1:
                    path = QPainterPath()
                    path.addPolygon(poly)
                    path.closeSubpath()
                    path.translate(-br.left(), -br.top())
                    self.set_selection(br, path)
                    return
            self._notify()
        elif mode in ("move", "resize"):
            self._notify()

    def key(self, e):
        s = self.sel
        k = e.key()
        if s is None:
            return False
        if k == Qt.Key_Delete:
            self.delete()
            return True
        if k == Qt.Key_Escape:
            self.commit()
            return True
        step = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0), Qt.Key_Up: (0, -1), Qt.Key_Down: (0, 1)}.get(k)
        if step and not (e.modifiers() & (Qt.ControlModifier | Qt.AltModifier)):
            self.lift()
            s.rect.translate(*step)
            self.c.invalidate()
            return True
        return False

    def style_changed(self, what):
        if what in ("transparent", "colors"):
            self.c.invalidate()

    def paint(self, p):
        c = self.c
        if self.mode == "rubber" and not self.cur.isNull():
            draw_dashed(p, outline_of(c.view_rect(self.cur)))
        elif self.mode == "lasso" and len(self.pts) > 1:
            p.save()
            p.setRenderHint(QPainter.Antialiasing, False)
            pts = [c.to_view(pt) for pt in self.pts]
            p.setPen(QPen(QColor(255, 255, 255), 1))
            p.drawPolyline(QPolygonF(pts))
            pen = QPen(QColor(0, 0, 0), 1)
            pen.setDashPattern([3, 3])
            p.setPen(pen)
            p.drawPolyline(QPolygonF(pts))
            p.restore()
        if self.sel is not None:
            o = self._outline()
            draw_dashed(p, o)
            draw_handles(p, handle_points(o))

    def cursor(self, ev):
        s = self.sel
        if s is not None and self.mode not in ("rubber", "lasso"):
            h = hit_handle(self._outline(), ev.view)
            if h is not None:
                return QCursor(HANDLE_CURSORS[h])
            if s.rect.contains(ev.pos):
                return QCursor(Qt.SizeAllCursor)
        return icons.cursor("cross")


# ------------------------------------------------------------------- shapes --
class ShapeBase(Tool):
    """Shared colour/size logic for the shape tools."""

    def _colors(self, left):
        st = self.c.state
        return (st.color1, st.color2) if left else (st.color2, st.color1)

    def _render(self, target: QImage, path: QPainterPath, left, closed, round_join=False):
        st = self.c.state
        oc, fc = self._colors(left)
        p = QPainter(target)
        outline = st.outline
        if not closed and outline == "none":
            outline = "solid"
        render_shape(p, path, st.sizes["shape"], outline, oc, st.fill, fc, closed, round_join=round_join)
        p.end()

    def style_changed(self, what):
        if self.has_pending():
            self.c.invalidate()

    def composite(self):
        if not self.has_pending():
            return None
        out = QImage(self.c.doc.image)
        self.draw(out)
        return out

    def commit(self):
        if self.has_pending():
            self.c.doc.push_undo()
            self.draw(self.c.doc.image)
            self._clear()
            self.c.doc.changed.emit()
        else:
            self._clear()
        self.c.sizeInfo.emit(None)
        self.c.invalidate()

    def cancel(self):
        self._clear()
        self.c.sizeInfo.emit(None)
        self.c.invalidate()


class ShapeTool(ShapeBase):
    """Line and all box-fitted shapes, adjustable until committed."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self._clear()

    def _clear(self):
        self.kind = None
        self.p0 = self.p1 = None
        self.left = True
        self.mode = None
        self.moved = False

    @property
    def busy(self):
        return self.mode is not None

    def has_pending(self):
        return self.kind is not None and (self.p0 != self.p1 or self.moved)

    def _bbox(self) -> QRect:
        x0, x1 = sorted((self.p0.x(), self.p1.x()))
        y0, y1 = sorted((self.p0.y(), self.p1.y()))
        return QRect(x0, y0, x1 - x0 + 1, y1 - y0 + 1)

    def draw(self, target):
        st = self.c.state
        w = st.sizes["shape"]
        if self.kind == "line":
            path = QPainterPath()
            path.moveTo(self.p0.x() + 0.5, self.p0.y() + 0.5)
            path.lineTo(self.p1.x() + 0.5, self.p1.y() + 0.5)
            self._render(target, path, self.left, False)
            return
        b = self._bbox()
        inset = w / 2.0 if st.outline != "none" else 0.0
        iw, ih = max(0.5, b.width() - 2 * inset), max(0.5, b.height() - 2 * inset)
        sx = -1 if self.p1.x() < self.p0.x() else 1
        sy = -1 if self.p1.y() < self.p0.y() else 1
        left = b.left() + inset + (iw if sx < 0 else 0)
        top = b.top() + inset + (ih if sy < 0 else 0)
        self._render(target, shape_path(self.kind, QRectF(left, top, iw * sx, ih * sy)), self.left, True,
                     round_join=is_curved(self.kind))

    def _outline(self):
        return outline_of(self.c.view_rect(self._bbox()))

    def _handles(self):
        if self.kind == "line":
            return [tuple(map(int, (self.c.to_view(QPointF(pt.x() + 0.5, pt.y() + 0.5)).x(),
                                    self.c.to_view(QPointF(pt.x() + 0.5, pt.y() + 0.5)).y())))
                    for pt in (self.p0, self.p1)]
        return handle_points(self._outline())

    def _hit(self, view):
        for i, (hx, hy) in enumerate(self._handles()):
            if abs(view.x() - hx) <= 4 and abs(view.y() - hy) <= 4:
                return i
        return None

    def _inside(self, ev):
        if self.kind == "line":
            a, b = QPointF(self.p0), QPointF(self.p1)
            d = b - a
            ln = d.x() * d.x() + d.y() * d.y()
            t = 0 if ln == 0 else max(0.0, min(1.0, ((ev.posf.x() - a.x()) * d.x() + (ev.posf.y() - a.y()) * d.y()) / ln))
            px, py = a.x() + d.x() * t, a.y() + d.y() * t
            tol = max(4.0 / self.c.zoom, self.c.state.sizes["shape"] / 2.0 + 2)
            return math.hypot(ev.posf.x() - px, ev.posf.y() - py) <= tol
        return self._bbox().contains(ev.pos)

    def press(self, ev):
        if self.mode == "drag":
            self.cancel()
            return
        if ev.button not in (L, R):
            return
        if self.has_pending():
            h = self._hit(ev.view)
            if h is not None:
                self.mode, self.handle = "resize", h
                self.start, self.press_pos = (QPoint(self.p0), QPoint(self.p1)), ev.pos
                return
            if self._inside(ev):
                self.mode = "move"
                self.start, self.press_pos = (QPoint(self.p0), QPoint(self.p1)), ev.pos
                return
            self.commit()
        self.kind = self.c.state.shape
        self.p0 = QPoint(ev.pos)
        self.p1 = QPoint(ev.pos)
        self.left = ev.button == L
        self.mode = "drag"
        self.moved = False

    def _constrain(self, ev):
        pt = QPoint(ev.pos)
        if not ev.shift:
            return pt
        dx, dy = pt.x() - self.p0.x(), pt.y() - self.p0.y()
        if self.kind == "line":
            ang = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
            ln = max(abs(dx), abs(dy))
            return QPoint(self.p0.x() + int(round(math.cos(ang) * ln)) if abs(math.cos(ang)) > 0.01 else self.p0.x(),
                          self.p0.y() + int(round(math.sin(ang) * ln)) if abs(math.sin(ang)) > 0.01 else self.p0.y())
        m = max(abs(dx), abs(dy))
        return QPoint(self.p0.x() + int(math.copysign(m, dx if dx else 1)),
                      self.p0.y() + int(math.copysign(m, dy if dy else 1)))

    def move(self, ev):
        if self.mode == "drag":
            self.p1 = self._constrain(ev)
            if self.p1 != self.p0:
                self.moved = True
        elif self.mode == "move":
            d = ev.pos - self.press_pos
            self.p0, self.p1 = self.start[0] + d, self.start[1] + d
        elif self.mode == "resize":
            d = ev.pos - self.press_pos
            a, b = QPoint(self.start[0]), QPoint(self.start[1])
            if self.kind == "line":
                if self.handle == 0:
                    a += d
                else:
                    b += d
            else:
                h = self.handle
                lx = a if a.x() <= b.x() else b
                rx = b if a.x() <= b.x() else a
                ty = a if a.y() <= b.y() else b
                by = b if a.y() <= b.y() else a
                if h in (0, 6, 7):
                    lx.setX(lx.x() + d.x())
                if h in (2, 3, 4):
                    rx.setX(rx.x() + d.x())
                if h in (0, 1, 2):
                    ty.setY(ty.y() + d.y())
                if h in (4, 5, 6):
                    by.setY(by.y() + d.y())
            self.p0, self.p1 = a, b
        else:
            return
        b = self._bbox()
        self.c.sizeInfo.emit(b.size())
        self.c.invalidate()

    def release(self, ev):
        if self.mode is None:
            return
        if self.mode == "drag" and not self.moved:
            self._clear()
            self.c.sizeInfo.emit(None)
        self.mode = None
        self.c.stateChanged.emit()
        self.c.invalidate()

    def key(self, e):
        if not self.has_pending():
            return False
        k = e.key()
        if k in (Qt.Key_Escape, Qt.Key_Delete):
            self.cancel()
            return True
        if k in (Qt.Key_Return, Qt.Key_Enter):
            self.commit()
            return True
        step = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0), Qt.Key_Up: (0, -1), Qt.Key_Down: (0, 1)}.get(k)
        if step:
            self.p0 += QPoint(*step)
            self.p1 += QPoint(*step)
            self.c.invalidate()
            return True
        return False

    def paint(self, p):
        if not self.has_pending() or self.mode == "drag":
            return
        if self.kind != "line":
            draw_dashed(p, self._outline())
        draw_handles(p, self._handles())

    def cursor(self, ev):
        if self.has_pending() and self.mode != "drag":
            h = self._hit(ev.view)
            if h is not None:
                return QCursor(Qt.SizeAllCursor if self.kind == "line" else HANDLE_CURSORS[h])
            if self._inside(ev):
                return QCursor(Qt.SizeAllCursor)
        return icons.cursor("cross")


class CurveTool(ShapeBase):
    """Drag a line, then drag up to twice to bend it."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self._clear()

    def _clear(self):
        self.stage = 0
        self.a = self.b = self.c1 = self.c2 = None
        self.left = True
        self.dragging = False

    @property
    def busy(self):
        return self.dragging

    def has_pending(self):
        return self.a is not None and self.a != self.b

    def draw(self, target):
        path = QPainterPath()
        h = QPointF(0.5, 0.5)
        path.moveTo(QPointF(self.a) + h)
        if self.c1 is None:
            path.lineTo(QPointF(self.b) + h)
        else:
            path.cubicTo(QPointF(self.c1) + h, QPointF(self.c2 or self.c1) + h, QPointF(self.b) + h)
        self._render(target, path, self.left, False)

    def press(self, ev):
        if self.dragging:
            self.cancel()
            return
        if ev.button not in (L, R):
            return
        self.dragging = True
        if self.stage == 0:
            self.a = QPoint(ev.pos)
            self.b = QPoint(ev.pos)
            self.left = ev.button == L
        elif self.stage == 1:
            self.c1 = QPoint(ev.pos)
            self.c2 = QPoint(ev.pos)
        else:
            self.c2 = QPoint(ev.pos)
        self.c.invalidate()

    def move(self, ev):
        if not self.dragging:
            return
        if self.stage == 0:
            self.b = QPoint(ev.pos)
        elif self.stage == 1:
            self.c1 = QPoint(ev.pos)
            self.c2 = QPoint(ev.pos)
        else:
            self.c2 = QPoint(ev.pos)
        self.c.invalidate()

    def release(self, ev):
        if not self.dragging:
            return
        self.dragging = False
        if self.stage == 0:
            if self.a == self.b:
                self._clear()
            else:
                self.stage = 1
        elif self.stage == 1:
            self.stage = 2
        else:
            self.commit()
        self.c.stateChanged.emit()
        self.c.invalidate()

    def key(self, e):
        if self.has_pending() and e.key() in (Qt.Key_Escape, Qt.Key_Delete):
            self.cancel()
            return True
        if self.has_pending() and e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.commit()
            return True
        return False


class PolygonTool(ShapeBase):
    """Drag the first side, click to add corners, double-click to close."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self._clear()

    def _clear(self):
        self.pts = []
        self.cur = None
        self.left = True
        self.dragging = False
        self.closed = False

    @property
    def busy(self):
        return self.dragging

    def has_pending(self):
        return len(self.pts) >= 1 and (len(self.pts) >= 2 or self.cur is not None)

    def draw(self, target):
        h = QPointF(0.5, 0.5)
        pts = [QPointF(pt) + h for pt in self.pts]
        if self.cur is not None and not self.closed:
            pts.append(QPointF(self.cur) + h)
        path = QPainterPath()
        if len(pts) < 2:
            return
        path.addPolygon(QPolygonF(pts))
        if self.closed and len(pts) >= 3:
            path.closeSubpath()
            self._render(target, path, self.left, True)
        else:
            self._render(target, path, self.left, False)

    def press(self, ev):
        if ev.button not in (L, R):
            return
        if not self.pts:
            self.pts = [QPoint(ev.pos)]
            self.left = ev.button == L
        self.cur = QPoint(ev.pos)
        self.dragging = True
        self.c.invalidate()

    def move(self, ev):
        if self.dragging:
            self.cur = QPoint(ev.pos)
            self.c.invalidate()

    def release(self, ev):
        if not self.dragging:
            return
        self.dragging = False
        pt = QPoint(ev.pos)
        if len(self.pts) >= 3:
            first = self.pts[0]
            tol = max(2.0, 6.0 / self.c.zoom)
            if math.hypot(pt.x() - first.x(), pt.y() - first.y()) <= tol:
                self.finish()
                return
        if pt != self.pts[-1]:
            self.pts.append(pt)
        self.cur = None
        self.c.stateChanged.emit()
        self.c.invalidate()

    def double_click(self, ev):
        self.finish()

    def finish(self):
        self.cur = None
        self.dragging = False
        self.commit()

    def commit(self):
        if len(self.pts) >= 2:
            self.cur = None
            self.closed = len(self.pts) >= 3
            super().commit()
        else:
            self.cancel()

    def key(self, e):
        if self.pts and e.key() in (Qt.Key_Escape, Qt.Key_Delete):
            self.cancel()
            return True
        if self.pts and e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.finish()
            return True
        return False


# --------------------------------------------------------------------- text --
class TextTool(Tool):
    PAD = 3

    def __init__(self, canvas):
        super().__init__(canvas)
        self.box = None
        self.tdoc = None
        self.cur = None
        self.fmt = None
        self.mode = None
        self.rubber = QRect()
        self.caret_on = True
        self.blink = QTimer(canvas)
        self.blink.setInterval(530)
        self.blink.timeout.connect(self._blink)

    @property
    def busy(self):
        return self.mode is not None

    def has_pending(self):
        return self.box is not None

    # -- format --------------------------------------------------------------
    def state_format(self) -> QTextCharFormat:
        st = self.c.state
        f = QFont(st.font_family)
        f.setPointSizeF(float(st.font_size))
        f.setBold(st.bold)
        f.setItalic(st.italic)
        f.setUnderline(st.underline)
        f.setStrikeOut(st.strike)
        fmt = QTextCharFormat()
        fmt.setFont(f)
        fmt.setForeground(QBrush(st.color1))
        return fmt

    def style_changed(self, what):
        if self.box is None:
            return
        if what in ("font", "colors"):
            fmt = self.state_format()
            if self.cur.hasSelection():
                self.cur.mergeCharFormat(fmt)
            self.fmt = fmt
            if self.tdoc.isEmpty():
                self.cur.setBlockCharFormat(fmt)
                self.cur.setCharFormat(fmt)
                self.tdoc.setDefaultFont(fmt.font())
            self._grow()
        self.c.viewport().update()

    def _blink(self):
        self.caret_on = not self.caret_on
        self.c.viewport().update()

    def _show_caret(self):
        self.caret_on = True
        self.blink.start()

    # -- box life cycle ------------------------------------------------------
    def _create(self, rect: QRect):
        self.tdoc = QTextDocument()
        self.tdoc.setDocumentMargin(self.PAD)
        self.tdoc.documentLayout().setPaintDevice(self.c.doc.image)
        opt = QTextOption()
        opt.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.tdoc.setDefaultTextOption(opt)
        self.fmt = self.state_format()
        self.tdoc.setDefaultFont(self.fmt.font())
        self.cur = QTextCursor(self.tdoc)
        self.cur.setBlockCharFormat(self.fmt)
        self.cur.setCharFormat(self.fmt)
        self.box = QRect(rect)
        self.tdoc.setTextWidth(self.box.width())
        self._grow()
        self._show_caret()
        self.c.textActive.emit(True)
        self.c.stateChanged.emit()
        self.c.viewport().update()

    def _grow(self):
        h = int(math.ceil(self.tdoc.size().height()))
        if h > self.box.height():
            self.box.setHeight(h)

    def _close(self):
        self.box = None
        self.tdoc = None
        self.cur = None
        self.mode = None
        self.blink.stop()
        self.c.textActive.emit(False)
        self.c.stateChanged.emit()
        self.c.viewport().update()

    def _draw_text(self, p: QPainter, caret=False):
        st = self.c.state
        box = self.box
        if st.text_opaque:
            p.fillRect(QRect(0, 0, box.width(), box.height()), st.color2)
        ctx = QAbstractTextDocumentLayout.PaintContext()
        ctx.palette.setColor(QPalette.Text, st.color1)
        if caret:
            ctx.cursorPosition = self.cur.position() if self.caret_on else -1
            if self.cur.hasSelection():
                sel = QAbstractTextDocumentLayout.Selection()
                sel.cursor = self.cur
                f = QTextCharFormat()
                f.setBackground(QBrush(QColor(51, 153, 255)))
                f.setForeground(QBrush(QColor(255, 255, 255)))
                sel.format = f
                ctx.selections = [sel]
        p.setClipRect(QRectF(0, 0, box.width(), box.height()))
        self.tdoc.documentLayout().draw(p, ctx)

    def commit(self):
        if self.box is None:
            return
        if not self.tdoc.isEmpty():
            doc = self.c.doc
            doc.push_undo()
            p = QPainter(doc.image)
            p.setRenderHint(QPainter.TextAntialiasing, True)
            p.translate(self.box.topLeft())
            self._draw_text(p)
            p.end()
            doc.changed.emit()
        self._close()

    def cancel(self):
        if self.box is not None:
            self._close()

    # -- geometry ------------------------------------------------------------
    def _outline(self):
        return outline_of(self.c.view_rect(self.box))

    def _zone(self, ev):
        """'handle', 'border', 'inside' or None for a view position."""
        o = self._outline()
        h = hit_handle(o, ev.view)
        if h is not None:
            return "handle", h
        x0, y0, x1, y1 = o
        vx, vy = ev.view.x(), ev.view.y()
        if x0 - 4 <= vx <= x1 + 4 and y0 - 4 <= vy <= y1 + 4:
            if vx <= x0 + 3 or vx >= x1 - 3 or vy <= y0 + 3 or vy >= y1 - 3:
                return "border", None
            return "inside", None
        return None, None

    def _hit_text(self, ev):
        local = QPointF(ev.posf.x() - self.box.left(), ev.posf.y() - self.box.top())
        return max(0, self.tdoc.documentLayout().hitTest(local, Qt.FuzzyHit))

    def press(self, ev):
        if ev.button != L:
            return
        if self.box is not None:
            zone, h = self._zone(ev)
            if zone == "handle":
                self.mode, self.handle = "resize", h
                self.start_rect, self.press_pos = QRect(self.box), ev.pos
            elif zone == "border":
                self.mode = "move"
                self.start_rect, self.press_pos = QRect(self.box), ev.pos
            elif zone == "inside":
                self.mode = "select"
                pos = self._hit_text(ev)
                self.cur.setPosition(pos, QTextCursor.KeepAnchor if ev.shift else QTextCursor.MoveAnchor)
                self._caret_moved()
            else:
                self.commit()
            return
        self.mode = "rubber"
        self.anchor = QPoint(ev.pos)
        self.rubber = QRect(ev.pos, QSize(0, 0))

    def move(self, ev):
        if self.mode == "rubber":
            x0, x1 = sorted((self.anchor.x(), ev.pos.x()))
            y0, y1 = sorted((self.anchor.y(), ev.pos.y()))
            self.rubber = QRect(x0, y0, x1 - x0, y1 - y0)
            self.c.sizeInfo.emit(self.rubber.size())
        elif self.mode == "select":
            self.cur.setPosition(self._hit_text(ev), QTextCursor.KeepAnchor)
            self._show_caret()
        elif self.mode == "move":
            self.box = self.start_rect.translated(ev.pos - self.press_pos)
        elif self.mode == "resize":
            d = ev.pos - self.press_pos
            r = resize_rect(self.start_rect, self.handle, d.x(), d.y())
            if r.width() < 12:
                r.setWidth(12)
            self.box = r
            self.tdoc.setTextWidth(r.width())
            self._grow()
            self.c.sizeInfo.emit(self.box.size())
        else:
            return
        self.c.viewport().update()

    def release(self, ev):
        if ev.button != L:
            return
        mode, self.mode = self.mode, None
        if mode == "rubber":
            r = QRect(self.rubber)
            doc = self.c.doc
            fm_h = int(math.ceil(self.c.state.font_size * 96 / 72.0 * 1.45)) + 2 * self.PAD
            if r.width() < 16:
                r.setWidth(max(60, min(240, doc.width() - r.left())))
            if r.height() < fm_h:
                r.setHeight(fm_h)
            self.rubber = QRect()
            self.c.sizeInfo.emit(None)
            self._create(r)

    # -- keyboard ------------------------------------------------------------
    def wants_shortcut(self, e):
        if self.box is None:
            return False
        if e.modifiers() & Qt.ControlModifier and not e.modifiers() & Qt.AltModifier:
            return e.key() in (Qt.Key_A, Qt.Key_C, Qt.Key_X, Qt.Key_V, Qt.Key_B, Qt.Key_I, Qt.Key_U,
                               Qt.Key_Left, Qt.Key_Right, Qt.Key_Home, Qt.Key_End)
        return e.key() in (Qt.Key_Delete, Qt.Key_Backspace, Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter)

    def _caret_moved(self):
        self._show_caret()
        if not self.cur.hasSelection() and not self.tdoc.isEmpty():
            self.fmt = self.cur.charFormat()
            self.c.textFormat.emit(self.fmt)
        self.c.viewport().update()

    def _edited(self):
        self._grow()
        self._show_caret()
        self.c.viewport().update()

    def key(self, e):
        if self.box is None:
            return False
        k, m = e.key(), e.modifiers()
        ctrl = bool(m & Qt.ControlModifier)
        cur = self.cur
        keep = QTextCursor.KeepAnchor if m & Qt.ShiftModifier else QTextCursor.MoveAnchor
        moves = {
            Qt.Key_Left: QTextCursor.WordLeft if ctrl else QTextCursor.Left,
            Qt.Key_Right: QTextCursor.WordRight if ctrl else QTextCursor.Right,
            Qt.Key_Up: QTextCursor.Up, Qt.Key_Down: QTextCursor.Down,
            Qt.Key_Home: QTextCursor.Start if ctrl else QTextCursor.StartOfLine,
            Qt.Key_End: QTextCursor.End if ctrl else QTextCursor.EndOfLine,
        }
        if k in moves:
            cur.movePosition(moves[k], keep)
            self._caret_moved()
            return True
        if k == Qt.Key_Escape:
            self.cancel()
            return True
        if k == Qt.Key_Backspace:
            if ctrl and not cur.hasSelection():
                cur.movePosition(QTextCursor.WordLeft, QTextCursor.KeepAnchor)
            if cur.hasSelection():
                cur.removeSelectedText()
            else:
                cur.deletePreviousChar()
            self._edited()
            return True
        if k == Qt.Key_Delete:
            if cur.hasSelection():
                cur.removeSelectedText()
            else:
                cur.deleteChar()
            self._edited()
            return True
        if k in (Qt.Key_Return, Qt.Key_Enter):
            cur.insertBlock()
            cur.setCharFormat(self.fmt)
            self._edited()
            return True
        if ctrl and not (m & Qt.AltModifier):
            cb = QGuiApplication.clipboard()
            if k == Qt.Key_A:
                cur.select(QTextCursor.Document)
                self._show_caret()
                self.c.viewport().update()
                return True
            if k in (Qt.Key_C, Qt.Key_X):
                if cur.hasSelection():
                    cb.setText(cur.selectedText().replace(" ", "\n"))
                    if k == Qt.Key_X:
                        cur.removeSelectedText()
                        self._edited()
                return True
            if k == Qt.Key_V:
                t = cb.text()
                if t:
                    cur.insertText(t, self.fmt)
                    self._edited()
                return True
            st = self.c.state
            if k == Qt.Key_B:
                st.set_font(bold=not st.bold)
                return True
            if k == Qt.Key_I:
                st.set_font(italic=not st.italic)
                return True
            if k == Qt.Key_U:
                st.set_font(underline=not st.underline)
                return True
            return False
        t = e.text()
        if k == Qt.Key_Tab:
            t = "\t"
        if t and (t.isprintable() or t == "\t") and not (m & Qt.AltModifier):
            cur.insertText(t, self.fmt)
            self._edited()
            return True
        return False

    def insert_text(self, t):
        """Text from an input method."""
        if self.box is not None and t:
            self.cur.insertText(t, self.fmt)
            self._edited()

    def paste_text(self, t):
        self.insert_text(t)

    # -- painting ------------------------------------------------------------
    def paint(self, p):
        c = self.c
        if self.mode == "rubber" and not self.rubber.isNull():
            draw_dashed(p, outline_of(c.view_rect(self.rubber)))
        if self.box is None:
            return
        vr = c.view_rect(self.box)
        p.save()
        p.translate(vr.topLeft())
        p.scale(c.zoom, c.zoom)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        self._draw_text(p, caret=True)
        p.restore()
        o = self._outline()
        draw_dashed(p, o)
        draw_handles(p, handle_points(o))

    def cursor(self, ev):
        if self.box is not None and self.mode != "rubber":
            zone, h = self._zone(ev)
            if zone == "handle":
                return QCursor(HANDLE_CURSORS[h])
            if zone == "border":
                return QCursor(Qt.SizeAllCursor)
            if zone == "inside":
                return QCursor(Qt.IBeamCursor)
        return icons.cursor("cross")
