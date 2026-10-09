"""The scrolling work area: draws the picture and routes input to the tools."""
import math
import traceback
from PySide6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, QSize, Signal, QEvent
from PySide6.QtGui import (QImage, QPainter, QColor, QPen, QCursor, QTransform, QGuiApplication)
from PySide6.QtWidgets import QAbstractScrollArea, QFrame

from . import theme as T
from . import icons
from .document import flatten, load_image
from .tools import (Ev, FreehandTool, FillTool, PickerTool, MagnifierTool, SelectTool, ShapeTool,
                    CurveTool, PolygonTool, TextTool)

ZOOMS = [0.125, 0.25, 0.5, 1, 2, 3, 4, 5, 6, 7, 8]
MARGIN = 5


class Canvas(QAbstractScrollArea):
    cursorMoved = Signal(object)        # QPoint | None
    sizeInfo = Signal(object)           # QSize | None
    zoomChanged = Signal(float)
    stateChanged = Signal()
    textActive = Signal(bool)
    textFormat = Signal(object)
    viewChanged = Signal()
    contextMenuRequested = Signal(QPoint)

    def __init__(self, doc, state, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.state = state
        self.zoom = 1.0
        self.show_grid = False
        self.hover = None
        self._display = None
        self._resize = None             # [handle, QSize] while dragging a canvas handle
        self.setFrameShape(QFrame.NoFrame)
        self.viewport().setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_InputMethodEnabled, True)

        self.select_tool = SelectTool(self)
        self.text_tool = TextTool(self)
        self._tools = {
            "pencil": FreehandTool(self, "pencil"), "eraser": FreehandTool(self, "eraser"),
            "brush": FreehandTool(self, "brush"), "fill": FillTool(self), "picker": PickerTool(self),
            "magnifier": MagnifierTool(self), "select": self.select_tool, "text": self.text_tool,
            "shape": ShapeTool(self), "curve": CurveTool(self), "polygon": PolygonTool(self),
        }
        self.tool = self._tools[self._tool_key()]
        doc.changed.connect(self.invalidate)
        doc.sizeChanged.connect(self._doc_resized)
        state.changed.connect(self._state_changed)
        self.horizontalScrollBar().setSingleStep(20)
        self.verticalScrollBar().setSingleStep(20)
        self._update_scrollbars()
        self._apply_cursor(None)

    # -- tool switching ------------------------------------------------------
    def _tool_key(self):
        t = self.state.tool
        if t == "shape":
            return {"curve": "curve", "polygon": "polygon"}.get(self.state.shape, "shape")
        return t

    def _state_changed(self, what):
        if what == "tool":
            new = self._tools[self._tool_key()]
            if new is not self.tool or self.state.tool == "shape":
                self.tool.deactivate()
                self.tool = new
                self.tool.activate()
            self.sizeInfo.emit(None)
            self._apply_cursor(None)
            self.stateChanged.emit()
            self.invalidate()
        elif what == "selmode":
            self.select_tool.commit()
        else:
            self.tool.style_changed(what)
            self.viewport().update()

    def commit_pending(self):
        try:
            self.tool.commit()
        except Exception:
            traceback.print_exc()
            self._drop_pending()
            self.invalidate()

    def has_selection(self):
        return self.tool is self.select_tool and self.select_tool.sel is not None

    def text_editing(self):
        return self.tool is self.text_tool and self.text_tool.box is not None

    # -- coordinates ---------------------------------------------------------
    def origin(self):
        return QPoint(MARGIN - self.horizontalScrollBar().value(), MARGIN - self.verticalScrollBar().value())

    def to_view(self, pt: QPointF) -> QPointF:
        o = self.origin()
        return QPointF(o.x() + pt.x() * self.zoom, o.y() + pt.y() * self.zoom)

    def view_rect(self, r: QRect) -> QRect:
        o = self.origin()
        z = self.zoom
        x0, y0 = int(round(r.left() * z)), int(round(r.top() * z))
        x1, y1 = int(round((r.left() + r.width()) * z)), int(round((r.top() + r.height()) * z))
        return QRect(o.x() + x0, o.y() + y0, max(1, x1 - x0), max(1, y1 - y0))

    def visible_doc_origin(self) -> QPoint:
        o = self.origin()
        return QPoint(max(0, int(math.ceil(-o.x() / self.zoom))), max(0, int(math.ceil(-o.y() / self.zoom))))

    def _ev(self, e, button=None):
        v = e.position()
        o = self.origin()
        z = self.zoom
        posf = QPointF((v.x() + 0.5 - o.x()) / z, (v.y() + 0.5 - o.y()) / z)
        pos = QPoint(int(math.floor((v.x() - o.x()) / z)), int(math.floor((v.y() - o.y()) / z)))
        return Ev(pos, posf, v, e.button() if button is None else button, e.buttons(), e.modifiers(),
                  e.globalPosition().toPoint())

    def color_at(self, pos: QPoint):
        img = self.display_image()
        if img.rect().contains(pos):
            return QColor(img.pixel(pos))
        return None

    # -- display -------------------------------------------------------------
    def display_image(self) -> QImage:
        if self._display is None:
            try:
                comp = self.tool.composite()
            except Exception:
                traceback.print_exc()
                comp = None
                self._drop_pending()
            self._display = comp if comp is not None else self.doc.image
        return self._display

    def _drop_pending(self):
        """Throw away whatever the tool has in progress after it failed."""
        try:
            self.tool.cancel()
        except Exception:
            traceback.print_exc()

    def invalidate(self):
        self._display = None
        self.viewport().update()

    def _doc_resized(self):
        self._update_scrollbars()
        self.viewChanged.emit()
        self.invalidate()

    def _content_size(self):
        return QSize(int(self.doc.width() * self.zoom) + MARGIN + 18, int(self.doc.height() * self.zoom) + MARGIN + 18)

    def _update_scrollbars(self):
        cs = self._content_size()
        vp = self.viewport().size()
        hb, vb = self.horizontalScrollBar(), self.verticalScrollBar()
        hb.setRange(0, max(0, cs.width() - vp.width()))
        vb.setRange(0, max(0, cs.height() - vp.height()))
        hb.setPageStep(vp.width())
        vb.setPageStep(vp.height())

    def resizeEvent(self, e):
        self._update_scrollbars()
        self.viewChanged.emit()

    def scrollContentsBy(self, dx, dy):
        self.viewport().update()
        self.viewChanged.emit()

    # -- zoom ----------------------------------------------------------------
    def next_zoom(self, d):
        i = min(range(len(ZOOMS)), key=lambda k: abs(ZOOMS[k] - self.zoom))
        if d > 0 and ZOOMS[i] <= self.zoom:
            i += 1
        elif d < 0 and ZOOMS[i] >= self.zoom:
            i -= 1
        return ZOOMS[max(0, min(len(ZOOMS) - 1, i))]

    def zoom_step(self, d, center_doc=None):
        self.set_zoom(self.next_zoom(d), center_doc)

    def set_zoom(self, z, center_doc=None):
        z = max(ZOOMS[0], min(ZOOMS[-1], float(z)))
        vp = self.viewport().size()
        if center_doc is None:
            o = self.origin()
            vis_w = min(vp.width(), o.x() + self.doc.width() * self.zoom)
            vis_h = min(vp.height(), o.y() + self.doc.height() * self.zoom)
            center_doc = QPointF((vis_w / 2.0 - o.x()) / self.zoom, (vis_h / 2.0 - o.y()) / self.zoom)
        if z == self.zoom:
            return
        self.zoom = z
        self._update_scrollbars()
        self.horizontalScrollBar().setValue(int(round(center_doc.x() * z + MARGIN - vp.width() / 2.0)))
        self.verticalScrollBar().setValue(int(round(center_doc.y() * z + MARGIN - vp.height() / 2.0)))
        self.zoomChanged.emit(z)
        self.viewChanged.emit()
        self.viewport().update()

    # -- painting ------------------------------------------------------------
    def paintEvent(self, e):
        img = self.display_image()
        p = QPainter(self.viewport())
        try:
            self._paint(p, e, img)
        except Exception:
            traceback.print_exc()
            self._drop_pending()
        finally:
            p.end()

    def _paint(self, p, e, img):
        p.fillRect(e.rect(), T.WORKSPACE)
        o = self.origin()
        z = self.zoom
        w, h = img.width(), img.height()
        full = QRect(o.x(), o.y(), int(round(w * z)), int(round(h * z)))
        vis = e.rect().intersected(full)
        if not vis.isEmpty():
            sx0 = max(0, int(math.floor((vis.left() - o.x()) / z)))
            sy0 = max(0, int(math.floor((vis.top() - o.y()) / z)))
            sx1 = min(w, int(math.ceil((vis.right() + 1 - o.x()) / z)))
            sy1 = min(h, int(math.ceil((vis.bottom() + 1 - o.y()) / z)))
            p.setRenderHint(QPainter.SmoothPixmapTransform, z < 1)
            p.drawImage(QRectF(o.x() + sx0 * z, o.y() + sy0 * z, (sx1 - sx0) * z, (sy1 - sy0) * z),
                        img, QRectF(sx0, sy0, sx1 - sx0, sy1 - sy0))
            p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        # soft shadow along the right and bottom edges
        for i, a in enumerate((70, 30, 12)):
            p.setPen(QPen(QColor(60, 80, 110, a), 1))
            p.drawLine(full.right() + 1 + i, full.top() + 2, full.right() + 1 + i, full.bottom() + 1 + i)
            p.drawLine(full.left() + 2, full.bottom() + 1 + i, full.right() + i, full.bottom() + 1 + i)
        if self.show_grid:
            self._paint_grid(p, full, vis)
        p.save()
        try:
            self.tool.paint(p)
        finally:
            p.restore()
        if not self.tool.has_pending():
            p.setPen(QPen(QColor(85, 85, 85), 1))
            p.setBrush(QColor(255, 255, 255))
            for pt in self._canvas_handles().values():
                p.drawRect(pt.x() - 2, pt.y() - 2, 4, 4)
        if self._resize is not None:
            s = self._resize[1]
            pen = QPen(QColor(0, 0, 0), 1)
            pen.setDashPattern([1, 1])
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(o.x(), o.y(), int(round(s.width() * z)), int(round(s.height() * z)))

    def _paint_grid(self, p, full, vis):
        if vis.isEmpty():
            return
        z = self.zoom
        step = 1 if z >= 4 else 10
        pen = QPen(QColor(120, 120, 120, 170), 1)
        pen.setDashPattern([1, 1])
        p.setPen(pen)
        o = self.origin()
        x = int(math.floor((vis.left() - o.x()) / z / step)) * step
        while True:
            vx = o.x() + int(round(x * z))
            if vx > vis.right():
                break
            if vx >= vis.left() and x > 0:
                p.drawLine(vx, vis.top(), vx, vis.bottom())
            x += step
        y = int(math.floor((vis.top() - o.y()) / z / step)) * step
        while True:
            vy = o.y() + int(round(y * z))
            if vy > vis.bottom():
                break
            if vy >= vis.top() and y > 0:
                p.drawLine(vis.left(), vy, vis.right(), vy)
            y += step

    # -- canvas resize handles -----------------------------------------------
    def _canvas_handles(self):
        o = self.origin()
        w, h = int(round(self.doc.width() * self.zoom)), int(round(self.doc.height() * self.zoom))
        return {"r": QPoint(o.x() + w + 3, o.y() + h // 2), "b": QPoint(o.x() + w // 2, o.y() + h + 3),
                "rb": QPoint(o.x() + w + 3, o.y() + h + 3)}

    def _canvas_handle_at(self, v):
        if self.tool.has_pending() or self.tool.busy:
            return None
        for k, pt in self._canvas_handles().items():
            if abs(v.x() - pt.x()) <= 4 and abs(v.y() - pt.y()) <= 4:
                return k
        return None

    # -- mouse ---------------------------------------------------------------
    def _apply_cursor(self, ev):
        if ev is not None:
            h = self._canvas_handle_at(ev.view) if self._resize is None else self._resize[0]
            if h:
                self.viewport().setCursor({"r": Qt.SizeHorCursor, "b": Qt.SizeVerCursor,
                                           "rb": Qt.SizeFDiagCursor}[h])
                return
            self.viewport().setCursor(self.tool.cursor(ev))
        else:
            self.viewport().setCursor(icons.cursor("cross"))

    def mousePressEvent(self, e):
        self.setFocus()
        ev = self._ev(e)
        self.hover = ev
        if e.button() == Qt.LeftButton and self._resize is None:
            h = self._canvas_handle_at(ev.view)
            if h:
                self.commit_pending()
                self._resize = [h, self.doc.size()]
                return
        if self._resize is not None:
            if e.button() == Qt.RightButton:
                self._resize = None
                self.sizeInfo.emit(None)
                self.viewport().update()
            return
        self.tool.press(ev)
        self._apply_cursor(ev)

    def mouseMoveEvent(self, e):
        ev = self._ev(e, Qt.NoButton)
        self.hover = ev
        if self._resize is not None:
            h, s = self._resize
            w = max(1, int(round((ev.view.x() - self.origin().x()) / self.zoom))) if "r" in h else s.width()
            hh = max(1, int(round((ev.view.y() - self.origin().y()) / self.zoom))) if "b" in h else s.height()
            self._resize[1] = QSize(w, hh)
            self.sizeInfo.emit(QSize(w, hh))
            self.viewport().update()
            return
        self.tool.move(ev)
        self._apply_cursor(ev)
        self.cursorMoved.emit(ev.pos if self.doc.rect().contains(ev.pos) else None)

    def mouseReleaseEvent(self, e):
        ev = self._ev(e)
        if self._resize is not None:
            if e.button() == Qt.LeftButton:
                s = self._resize[1]
                self._resize = None
                self.sizeInfo.emit(None)
                self.doc.resize_canvas(s.width(), s.height(), self.state.color2)
                self.viewport().update()
            return
        self.tool.release(ev)
        self._apply_cursor(ev)

    def mouseDoubleClickEvent(self, e):
        ev = self._ev(e)
        self.tool.press(ev)
        self.tool.double_click(ev)

    def leaveEvent(self, e):
        self.hover = None
        self.cursorMoved.emit(None)
        self.viewport().update()

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            d = e.angleDelta().y()
            if d:
                o = self.origin()
                v = e.position()
                self.zoom_step(1 if d > 0 else -1,
                               QPointF((v.x() - o.x()) / self.zoom, (v.y() - o.y()) / self.zoom))
            e.accept()
            return
        super().wheelEvent(e)

    # -- keyboard ------------------------------------------------------------
    def event(self, e):
        if e.type() == QEvent.ShortcutOverride and self.tool.wants_shortcut(e):
            e.accept()
            return True
        return super().event(e)

    def keyPressEvent(self, e):
        if self.tool.key(e):
            self.stateChanged.emit()
            e.accept()
            return
        if self.text_editing():
            e.accept()
            return
        e.ignore()

    def inputMethodEvent(self, e):
        if self.text_editing() and e.commitString():
            self.text_tool.insert_text(e.commitString())
        e.accept()

    def inputMethodQuery(self, q):
        if q == Qt.ImEnabled:
            return self.text_editing()
        return super().inputMethodQuery(q)

    # -- edit commands -------------------------------------------------------
    def undo(self):
        self.commit_pending()
        self.doc.undo()
        self.stateChanged.emit()

    def redo(self):
        self.commit_pending()
        self.doc.redo()
        self.stateChanged.emit()

    def _use_select(self):
        if self.state.tool != "select":
            self.state.set_tool("select")

    def select_all(self):
        if self.text_editing():
            from PySide6.QtGui import QTextCursor
            self.text_tool.cur.select(QTextCursor.Document)
            self.viewport().update()
            return
        self._use_select()
        self.select_tool.select_all()

    def invert_selection(self):
        if self.has_selection():
            self.select_tool.invert()

    def delete_selection(self):
        if self.has_selection():
            self.select_tool.delete()

    def crop(self):
        if self.has_selection():
            self.select_tool.crop()

    def copy(self):
        if self.text_editing():
            cur = self.text_tool.cur
            if cur.hasSelection():
                QGuiApplication.clipboard().setText(cur.selectedText().replace(" ", "\n"))
        elif self.has_selection():
            self.select_tool.copy()

    def cut(self):
        if self.text_editing():
            cur = self.text_tool.cur
            if cur.hasSelection():
                QGuiApplication.clipboard().setText(cur.selectedText().replace(" ", "\n"))
                cur.removeSelectedText()
                self.viewport().update()
        elif self.has_selection():
            self.select_tool.cut()

    def can_paste(self):
        md = QGuiApplication.clipboard().mimeData()
        if md is None:
            return False
        return md.hasImage() or (self.text_editing() and md.hasText())

    def paste(self):
        cb = QGuiApplication.clipboard()
        md = cb.mimeData()
        if md is None:
            return
        if self.text_editing() and md.hasText() and not md.hasImage():
            self.text_tool.paste_text(cb.text())
            return
        if md.hasImage():
            img = cb.image()
            if not img.isNull():
                self.paste_image(img)

    def paste_image(self, img: QImage):
        self.commit_pending()
        self._use_select()
        self.select_tool.paste(img)

    def paste_from(self, path):
        self.paste_image(load_image(path))

    def _apply(self, fn):
        """Run an image transform on the selection, or on the whole picture."""
        if self.has_selection():
            self.select_tool.transform(fn)
        else:
            self.commit_pending()
            self.doc.push_undo()
            self.doc.set_image(flatten(fn(self.doc.image), self.state.color2))
        self.stateChanged.emit()

    def rotate(self, kind):
        t = QTransform()
        if kind == "r90":
            t.rotate(90)
        elif kind == "l90":
            t.rotate(-90)
        elif kind == "180":
            t.rotate(180)
        elif kind == "flipv":
            t.scale(1, -1)
        elif kind == "fliph":
            t.scale(-1, 1)
        self._apply(lambda img: img.transformed(t, Qt.FastTransformation))

    def resize_skew(self, w, h, skew_h=0.0, skew_v=0.0):
        """Scale to w x h pixels, then skew by the given angles (degrees)."""
        def fn(img):
            out = img
            if w != img.width() or h != img.height():
                out = out.scaled(max(1, w), max(1, h), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            if skew_h or skew_v:
                t = QTransform()
                t.shear(math.tan(math.radians(skew_h)), math.tan(math.radians(skew_v)))
                out = out.convertToFormat(QImage.Format_ARGB32_Premultiplied).transformed(t, Qt.SmoothTransformation)
            return out
        self._apply(fn)

    def invert_colors(self):
        def fn(img):
            out = img.copy()
            out.invertPixels(QImage.InvertRgb)
            return out
        self._apply(fn)

    def target_size(self) -> QSize:
        """Size that Resize/Skew will act on."""
        if self.has_selection():
            return self.select_tool.sel.rect.size()
        return self.doc.size()
