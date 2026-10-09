"""Window chrome: caption bar with quick access toolbar, status bar, zoom slider, rulers."""
from PySide6.QtCore import Qt, QRect, QRectF, QPoint, QPointF, QSize, Signal, QEvent
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QLinearGradient, QFontMetrics, QPainterPath,
                           QPolygonF)
from PySide6.QtWidgets import QWidget, QToolTip

from . import theme as T
from . import icons
from .ribbon import RButton, tip_html
from .canvas import ZOOMS, MARGIN


class TitleBar(QWidget):
    """Custom caption: icon, quick access toolbar, title, min/max/close."""
    minimizeRequested = Signal()
    maximizeRequested = Signal()
    closeRequested = Signal()

    BTN_W = (29, 27, 49)
    BTN_H = 20

    def __init__(self, parent=None, native=False):
        super().__init__(parent)
        self.native = native
        self.title = "Untitled - Paint"
        self.active = True
        self.maximized = False
        self.context = None          # (x0, x1, text) of a contextual tab header
        self._hover = None
        self._down = None
        self.setMouseTracking(True)
        self.setFixedHeight(26 if native else T.TITLE_H)
        self.setFont(T.ui_font())
        self.qat = []
        self._qat_x = 6 if native else 28

    def add_button(self, btn: RButton):
        btn.setParent(self)
        self.qat.append(btn)
        self.layout_qat()
        return btn

    def layout_qat(self):
        x = self._qat_x
        y = (self.height() - T.ROW_H) // 2 + (0 if self.native else 1)
        for b in self.qat:
            if b.isHidden():
                continue
            b.move(x, y)
            x += b.width() + 1
        self._qat_end = x
        self.update()

    def set_title(self, t):
        self.title = t
        self.update()

    def set_context(self, ctx):
        self.context = ctx
        self.update()

    # -- caption buttons -----------------------------------------------------
    def _btn_rects(self):
        if self.native:
            return {}
        x = self.width() - 6
        out = {}
        for name, w in zip(("close", "max", "min"), reversed(self.BTN_W)):
            x -= w
            out[name] = QRect(x, 0, w, self.BTN_H)
        return out

    def _hit(self, pos):
        for k, r in self._btn_rects().items():
            if r.contains(pos):
                return k
        return None

    def mouseMoveEvent(self, e):
        h = self._hit(e.position().toPoint())
        if h != self._hover:
            self._hover = h
            self.update()
        if (e.buttons() & Qt.LeftButton) and self._down == "drag" and not self.native:
            self._down = None
            wh = self.window().windowHandle()
            if wh is not None:
                wh.startSystemMove()

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        h = self._hit(e.position().toPoint())
        self._down = h or "drag"
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        h = self._hit(e.position().toPoint())
        down, self._down = self._down, None
        self.update()
        if h and h == down:
            {"min": self.minimizeRequested, "max": self.maximizeRequested, "close": self.closeRequested}[h].emit()

    def mouseDoubleClickEvent(self, e):
        if self.native or e.button() != Qt.LeftButton:
            return
        pos = e.position().toPoint()
        if self._hit(pos):
            return
        if pos.x() < 26:
            self.closeRequested.emit()
        else:
            self.maximizeRequested.emit()

    def event(self, e):
        if e.type() == QEvent.ToolTip:
            h = self._hit(e.pos())
            if h:
                QToolTip.showText(e.globalPos(), {"min": "Minimize", "close": "Close",
                                                  "max": "Restore Down" if self.maximized else "Maximize"}[h], self)
            else:
                QToolTip.hideText()
            return True
        return super().event(e)

    def paintEvent(self, e):
        p = QPainter(self)
        r = self.rect()
        if self.native:
            p.fillRect(r, T.TABSTRIP_BG)
            p.end()
            return
        g = QLinearGradient(0, 0, 0, r.height())
        if self.active:
            g.setColorAt(0, T.FRAME_TOP)
            g.setColorAt(1, T.FRAME_BOTTOM)
        else:
            g.setColorAt(0, T.FRAME_INACTIVE)
            g.setColorAt(1, T.FRAME_INACTIVE)
        p.fillRect(r, QBrush(g))
        p.setPen(QPen(QColor(255, 255, 255, 120), 1))
        p.drawLine(1, 1, r.width() - 2, 1)
        p.drawPixmap(8, 8, icons.pixmap("app", 16))
        # separator after the quick access toolbar
        x = getattr(self, "_qat_end", 100) + 3
        p.setPen(QPen(QColor(120, 140, 170, 150), 1))
        p.drawLine(x, 9, x, r.height() - 8)
        p.setPen(QPen(QColor(255, 255, 255, 150), 1))
        p.drawLine(x + 1, 9, x + 1, r.height() - 8)
        # contextual tab header
        rects = self._btn_rects()
        right_limit = min(rc.left() for rc in rects.values()) - 8
        tx = x + 8
        if self.context:
            cx0, cx1, text = self.context
            cr = QRect(cx0, 3, cx1 - cx0, r.height() - 3)
            cg = QLinearGradient(0, cr.top(), 0, cr.bottom())
            cg.setColorAt(0, QColor(255, 232, 150, 235))
            cg.setColorAt(1, QColor(255, 244, 205, 150))
            p.fillRect(cr, QBrush(cg))
            p.setPen(QPen(QColor(226, 190, 96), 1))
            p.drawLine(cr.left(), cr.top(), cr.left(), cr.bottom())
            p.drawLine(cr.right(), cr.top(), cr.right(), cr.bottom())
            p.drawLine(cr.left(), cr.top(), cr.right(), cr.top())
            p.setFont(self.font())
            p.setPen(QColor(96, 64, 0))
            p.drawText(cr, Qt.AlignCenter, text)
            tx = max(tx, cx1 + 10)
        # title
        p.setFont(self.font())
        fm = QFontMetrics(self.font())
        text = fm.elidedText(self.title, Qt.ElideRight, max(20, right_limit - tx))
        tr = QRect(tx, 2, max(20, right_limit - tx), r.height() - 2)
        p.setPen(QColor(255, 255, 255, 170))
        for dx, dy in ((1, 1), (-1, 1), (1, -1), (-1, -1), (0, 1), (1, 0), (-1, 0), (0, -1)):
            p.drawText(tr.translated(dx, dy), Qt.AlignLeft | Qt.AlignVCenter, text)
        p.setPen(QColor(0, 0, 0) if self.active else QColor(100, 100, 100))
        p.drawText(tr, Qt.AlignLeft | Qt.AlignVCenter, text)
        # caption buttons
        p.setRenderHint(QPainter.Antialiasing, True)
        for name, br in rects.items():
            rr = QRectF(br).adjusted(0.5, -3, -0.5, -0.5)
            hot = self._hover == name
            down = self._down == name and hot
            g = QLinearGradient(0, 0, 0, br.height())
            if name == "close":
                if down:
                    cols = ("#d98a7c", "#a6352a", "#8c2a20")
                elif hot:
                    cols = ("#f5b3a6", "#e0503c", "#c63a28")
                else:
                    cols = ("#e9a99b", "#c75050", "#b3382a") if self.active else ("#d9dfe8", "#c2ccd9", "#b7c2d1")
            else:
                if down:
                    cols = ("#b8cbe6", "#8faedb", "#7c9fd2")
                elif hot:
                    cols = ("#f2f8ff", "#b9d6f5", "#9ec5f0")
                else:
                    cols = ("#e3ecf7", "#c5d6ec", "#b6cae4")
            g.setColorAt(0, QColor(cols[0]))
            g.setColorAt(0.5, QColor(cols[1]))
            g.setColorAt(1, QColor(cols[2]))
            p.setPen(QPen(QColor(70, 90, 125), 1))
            p.setBrush(QBrush(g))
            path = QPainterPath()
            path.addRoundedRect(rr, 3, 3)
            p.drawPath(path)
            p.setRenderHint(QPainter.Antialiasing, False)
            cx, cy = br.center().x(), br.center().y() - 1
            white = QColor(255, 255, 255)
            dark = QColor(60, 70, 90)
            if name == "min":
                p.fillRect(cx - 5, cy + 3, 11, 3, dark)
                p.fillRect(cx - 4, cy + 4, 9, 1, white)
            elif name == "max":
                if self.maximized:
                    for ox, oy in ((2, -2), (-2, 2)):
                        p.setPen(QPen(dark, 1))
                        p.setBrush(white)
                        p.drawRect(cx - 4 + ox, cy - 2 + oy, 8, 6)
                        p.fillRect(cx - 2 + ox, cy + oy, 5, 3, QColor(cols[1]))
                        p.setPen(QPen(dark, 1))
                        p.drawRect(cx - 2 + ox, cy + oy, 4, 2)
                else:
                    p.setPen(QPen(dark, 1))
                    p.setBrush(white)
                    p.drawRect(cx - 5, cy - 3, 10, 8)
                    p.fillRect(cx - 3, cy - 1, 7, 5, QColor(cols[1]))
                    p.drawRect(cx - 3, cy - 1, 6, 4)
            else:
                p.setRenderHint(QPainter.Antialiasing, True)
                for col, w in ((dark, 4.2), (white, 2.2)):
                    pen = QPen(col, w)
                    pen.setCapStyle(Qt.SquareCap)
                    p.setPen(pen)
                    p.drawLine(QPointF(cx - 3.5, cy - 2.5), QPointF(cx + 4.5, cy + 4.5))
                    p.drawLine(QPointF(cx + 4.5, cy - 2.5), QPointF(cx - 3.5, cy + 4.5))
            p.setRenderHint(QPainter.Antialiasing, True)
        p.end()


class ZoomControl(QWidget):
    """'100%  (-) ----|---- (+)' at the right of the status bar."""
    zoomRequested = Signal(float)
    stepRequested = Signal(int)

    TRACK_W = 101

    def __init__(self, parent=None):
        super().__init__(parent)
        self.zoom = 1.0
        self._hover = None
        self._drag = False
        self.setMouseTracking(True)
        self.setFont(T.ui_font())
        self.setFixedSize(46 + 18 + self.TRACK_W + 12 + 18 + 8, T.STATUS_H)

    def set_zoom(self, z):
        self.zoom = z
        self.update()

    # geometry
    def _minus(self):
        return QRect(46, 3, 17, 17)

    def _track(self):
        return QRect(46 + 18 + 6, 0, self.TRACK_W, self.height())

    def _plus(self):
        return QRect(46 + 18 + self.TRACK_W + 12, 3, 17, 17)

    @staticmethod
    def _frac(z):
        """0..1 slider position; 100% sits in the middle."""
        if z <= 1:
            idx = ZOOMS.index(min(ZOOMS[:4], key=lambda v: abs(v - z)))
            return 0.5 * idx / 3.0
        idx = ZOOMS.index(min(ZOOMS[3:], key=lambda v: abs(v - z))) - 3
        return 0.5 + 0.5 * idx / 7.0

    def _zoom_at(self, x):
        t = self._track()
        f = max(0.0, min(1.0, (x - t.left()) / float(t.width() - 1)))
        return min(ZOOMS, key=lambda v: abs(self._frac(v) - f))

    def _hit(self, pos):
        if self._minus().contains(pos):
            return "minus"
        if self._plus().contains(pos):
            return "plus"
        if self._track().adjusted(-5, 0, 5, 0).contains(pos):
            return "track"
        return None

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._drag:
            self.zoomRequested.emit(self._zoom_at(pos.x()))
            return
        h = self._hit(pos)
        if h != self._hover:
            self._hover = h
            self.update()

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        pos = e.position().toPoint()
        h = self._hit(pos)
        if h == "minus":
            self.stepRequested.emit(-1)
        elif h == "plus":
            self.stepRequested.emit(1)
        elif h == "track":
            self._drag = True
            self.zoomRequested.emit(self._zoom_at(pos.x()))

    def mouseReleaseEvent(self, e):
        self._drag = False

    def event(self, e):
        if e.type() == QEvent.ToolTip:
            h = self._hit(e.pos())
            tip = {"minus": "Zoom out", "plus": "Zoom in", "track": "Zoom"}.get(h)
            if tip:
                QToolTip.showText(e.globalPos(), tip, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(e)

    def _round_btn(self, p, r, plus, hot):
        p.setRenderHint(QPainter.Antialiasing, True)
        g = QLinearGradient(0, r.top(), 0, r.bottom())
        g.setColorAt(0, QColor(255, 255, 255) if not hot else QColor(255, 250, 225))
        g.setColorAt(1, QColor(206, 219, 238) if not hot else QColor(255, 222, 140))
        p.setPen(QPen(QColor(110, 132, 165) if not hot else QColor(210, 160, 60), 1))
        p.setBrush(QBrush(g))
        p.drawEllipse(QRectF(r).adjusted(0.5, 0.5, -0.5, -0.5))
        p.setRenderHint(QPainter.Antialiasing, False)
        c = r.center()
        col = QColor(50, 70, 105)
        p.fillRect(c.x() - 4, c.y(), 9, 2, col)
        if plus:
            p.fillRect(c.x(), c.y() - 4, 2, 9 + 1, col)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setFont(self.font())
        p.setPen(T.TEXT_BLACK)
        pct = self.zoom * 100
        label = f"{pct:g}%"
        p.drawText(QRect(0, 0, 42, self.height()), Qt.AlignRight | Qt.AlignVCenter, label)
        self._round_btn(p, self._minus(), False, self._hover == "minus")
        self._round_btn(p, self._plus(), True, self._hover == "plus")
        t = self._track()
        cy = t.center().y() + 1
        p.setPen(QPen(QColor(120, 140, 170), 1))
        p.drawLine(t.left(), cy, t.right(), cy)
        p.setPen(QPen(QColor(255, 255, 255), 1))
        p.drawLine(t.left(), cy + 1, t.right(), cy + 1)
        mid = t.left() + t.width() // 2
        p.setPen(QPen(QColor(120, 140, 170), 1))
        p.drawLine(mid, cy - 5, mid, cy + 5)
        x = t.left() + int(round(self._frac(self.zoom) * (t.width() - 1)))
        thumb = QPolygonF([QPointF(x - 4.5, cy - 7.5), QPointF(x + 4.5, cy - 7.5), QPointF(x + 4.5, cy + 2.5),
                           QPointF(x, cy + 7.5), QPointF(x - 4.5, cy + 2.5)])
        p.setRenderHint(QPainter.Antialiasing, True)
        hot = self._hover == "track" or self._drag
        g = QLinearGradient(0, cy - 8, 0, cy + 8)
        g.setColorAt(0, QColor(255, 255, 255) if not hot else QColor(255, 250, 225))
        g.setColorAt(1, QColor(196, 211, 233) if not hot else QColor(255, 216, 128))
        p.setPen(QPen(QColor(100, 122, 158) if not hot else QColor(205, 150, 50), 1))
        p.setBrush(QBrush(g))
        p.drawPolygon(thumb)
        p.end()


class StatusBar(QWidget):
    SEG_W = 152

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(T.STATUS_H)
        self.setFont(T.ui_font())
        self.pos_text = ""
        self.sel_text = ""
        self.size_text = ""
        self.file_text = ""
        self.zoomer = ZoomControl(self)

    def resizeEvent(self, e):
        self.zoomer.move(self.width() - self.zoomer.width() - 14, 0)

    def set_pos(self, pt):
        t = f"{pt.x()}, {pt.y()}px" if pt is not None else ""
        if t != self.pos_text:
            self.pos_text = t
            self.update()

    def set_sel(self, size):
        t = f"{size.width()} × {size.height()}px" if size is not None else ""
        if t != self.sel_text:
            self.sel_text = t
            self.update()

    def set_image_size(self, size):
        self.size_text = f"{size.width()} × {size.height()}px"
        self.update()

    def set_file_size(self, nbytes):
        if nbytes is None:
            self.file_text = ""
        elif nbytes < 1024:
            self.file_text = f"Size: {nbytes} bytes"
        elif nbytes < 1024 * 1024:
            self.file_text = f"Size: {nbytes / 1024.0:.1f}KB"
        else:
            self.file_text = f"Size: {nbytes / 1048576.0:.1f}MB"
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        r = self.rect()
        g = QLinearGradient(0, 0, 0, r.height())
        g.setColorAt(0, T.STATUS_TOP)
        g.setColorAt(1, T.STATUS_BOTTOM)
        p.fillRect(r, QBrush(g))
        p.setPen(QPen(T.STATUS_SEP, 1))
        p.drawLine(0, 0, r.width(), 0)
        p.setPen(QPen(QColor(255, 255, 255), 1))
        p.drawLine(0, 1, r.width(), 1)
        p.setFont(self.font())
        x = 4
        limit = self.zoomer.x() - 10
        for icon, text in (("pos", self.pos_text), ("selsize", self.sel_text),
                           ("imgsize", self.size_text), ("disk", self.file_text)):
            if x + self.SEG_W > limit:
                break
            p.drawPixmap(x + 3, 4, icons.pixmap(icon))
            p.setPen(T.TEXT_BLACK)
            p.drawText(QRect(x + 24, 1, self.SEG_W - 28, r.height() - 1), Qt.AlignLeft | Qt.AlignVCenter, text)
            x += self.SEG_W
            p.setPen(QPen(T.STATUS_SEP, 1))
            p.drawLine(x - 2, 4, x - 2, r.height() - 4)
            p.setPen(QPen(QColor(255, 255, 255), 1))
            p.drawLine(x - 1, 4, x - 1, r.height() - 4)
        # resize grip dots
        p.setPen(Qt.NoPen)
        for i in range(3):
            for j in range(3 - i):
                gx, gy = r.width() - 4 - i * 3, r.height() - 4 - j * 3
                p.fillRect(gx, gy, 2, 2, QColor(150, 165, 188))
        p.end()


class Ruler(QWidget):
    THICK = 17

    def __init__(self, canvas, horizontal=True, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.horizontal = horizontal
        self.mark = None
        self.setFont(T.ui_font(9))
        if horizontal:
            self.setFixedHeight(self.THICK)
        else:
            self.setFixedWidth(self.THICK)

    def set_mark(self, pt):
        m = None if pt is None else (pt.x() if self.horizontal else pt.y())
        if m != self.mark:
            self.mark = m
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        r = self.rect()
        p.fillRect(r, QColor(241, 245, 251))
        c = self.canvas
        z = c.zoom
        o = c.origin()
        off = o.x() if self.horizontal else o.y()
        length = r.width() if self.horizontal else r.height()
        p.setPen(QPen(QColor(160, 175, 197), 1))
        if self.horizontal:
            p.drawLine(0, r.height() - 1, r.width(), r.height() - 1)
        else:
            p.drawLine(r.width() - 1, 0, r.width() - 1, r.height())
        # choose tick spacing: minor ticks at least 5px apart on screen
        minor = 10
        for cand in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000):
            if cand * z >= 5:
                minor = cand
                break
        major = minor * 10
        mid = minor * 5
        p.setFont(self.font())
        first = int(max(0, -off / z) // minor * minor)
        v = first
        th = self.THICK
        while True:
            pos = off + int(round(v * z))
            if pos > length:
                break
            if pos >= 0:
                if v % major == 0:
                    ln = th - 2
                elif v % mid == 0:
                    ln = 7
                else:
                    ln = 4
                p.setPen(QPen(QColor(110, 125, 148), 1))
                if self.horizontal:
                    p.drawLine(pos, th - 1 - ln, pos, th - 2)
                else:
                    p.drawLine(th - 1 - ln, pos, th - 2, pos)
                if v % major == 0:
                    p.setPen(QColor(60, 70, 90))
                    if self.horizontal:
                        p.drawText(pos + 3, 9, str(v))
                    else:
                        p.save()
                        p.translate(9, pos + 3)
                        p.rotate(90)
                        p.drawText(0, 0, str(v))
                        p.restore()
            v += minor
        if self.mark is not None:
            pos = off + int(round((self.mark + 0.5) * z))
            p.setPen(QPen(QColor(30, 60, 120), 1))
            if self.horizontal:
                p.drawLine(pos, 0, pos, th)
            else:
                p.drawLine(0, pos, th, pos)
        p.end()


class RulerCorner(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(Ruler.THICK, Ruler.THICK)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(241, 245, 251))
        p.setPen(QPen(QColor(160, 175, 197), 1))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        p.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        p.end()
