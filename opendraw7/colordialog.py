"""Edit Colors: the classic Windows colour chooser that Paint opens, rebuilt.

Basic and custom colour swatches on the left; on the right a hue/saturation spectrum, a
luminosity bar, a preview and Hue/Sat/Lum (0-240 scale, hue 0-239) and Red/Green/Blue boxes.
"""
from PySide6.QtCore import Qt, QRect, QPoint, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QImage, QIntValidator, QPolygon, QFontMetrics
from PySide6.QtWidgets import QDialog, QWidget, QLabel, QLineEdit, QPushButton

from . import theme as T

HLSMAX = 240

BASIC = [
    "#ff8080", "#ffff80", "#80ff80", "#00ff80", "#80ffff", "#0080ff", "#ff80c0", "#ff80ff",
    "#ff0000", "#ffff00", "#80ff00", "#00ff40", "#00ffff", "#0080c0", "#8080c0", "#ff00ff",
    "#804040", "#ff8040", "#00ff00", "#008080", "#004080", "#8080ff", "#800040", "#ff0080",
    "#800000", "#ff8000", "#008000", "#008040", "#0000ff", "#0000a0", "#800080", "#8000ff",
    "#400000", "#804000", "#004000", "#004040", "#000080", "#000040", "#400040", "#400080",
    "#000000", "#808000", "#808040", "#808080", "#408080", "#c0c0c0", "#400040", "#ffffff",
]


def to_hsl(c: QColor):
    """Windows-style (hue 0-239, sat 0-240, lum 0-240)."""
    h, s, l, _a = c.getHslF()
    h = 0.0 if h < 0 else h
    return (int(round(h * HLSMAX)) % HLSMAX, int(round(s * HLSMAX)), int(round(l * HLSMAX)))


def from_hsl(h, s, l) -> QColor:
    return QColor.fromHslF((h % HLSMAX) / float(HLSMAX), max(0, min(HLSMAX, s)) / float(HLSMAX),
                           max(0, min(HLSMAX, l)) / float(HLSMAX))


class Swatches(QWidget):
    """Grid of colour cells; one can be the current cell (dotted focus frame)."""
    picked = Signal(int)

    CW, CH, GX, GY = 21, 18, 4, 5

    def __init__(self, colors, cols, parent=None):
        super().__init__(parent)
        self.colors = list(colors)
        self.cols = cols
        self.rows = (len(self.colors) + cols - 1) // cols
        self.current = -1
        self.setFixedSize(cols * (self.CW + self.GX), self.rows * (self.CH + self.GY))
        self.setFocusPolicy(Qt.StrongFocus)

    def cell(self, i):
        r, c = divmod(i, self.cols)
        return QRect(c * (self.CW + self.GX) + 2, r * (self.CH + self.GY) + 2, self.CW, self.CH)

    def mousePressEvent(self, e):
        for i in range(len(self.colors)):
            if self.cell(i).adjusted(-2, -2, 2, 2).contains(e.position().toPoint()):
                self.current = i
                self.update()
                self.picked.emit(i)
                return

    def keyPressEvent(self, e):
        step = {Qt.Key_Left: -1, Qt.Key_Right: 1, Qt.Key_Up: -self.cols, Qt.Key_Down: self.cols}.get(e.key())
        if step is None:
            return super().keyPressEvent(e)
        i = max(0, min(len(self.colors) - 1, (self.current if self.current >= 0 else 0) + step))
        self.current = i
        self.update()
        self.picked.emit(i)

    def paintEvent(self, e):
        p = QPainter(self)
        for i, col in enumerate(self.colors):
            r = self.cell(i)
            # sunken 3D frame
            p.setPen(QColor(160, 160, 160))
            p.drawLine(r.left() - 1, r.top() - 1, r.right() + 1, r.top() - 1)
            p.drawLine(r.left() - 1, r.top() - 1, r.left() - 1, r.bottom() + 1)
            p.setPen(QColor(255, 255, 255))
            p.drawLine(r.left() - 1, r.bottom() + 1, r.right() + 1, r.bottom() + 1)
            p.drawLine(r.right() + 1, r.top() - 1, r.right() + 1, r.bottom() + 1)
            p.fillRect(r, QColor(col))
            if i == self.current:
                pen = QPen(QColor(0, 0, 0), 1)
                pen.setDashPattern([1, 1])
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawRect(r.adjusted(-3, -3, 2, 2))
        p.end()


class Spectrum(QWidget):
    """Hue across, saturation up; a cross marks the current colour."""
    moved = Signal(int, int)        # hue, sat

    W, H = 175, 187

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.W + 4, self.H + 4)
        self.hue, self.sat = 160, 0
        img = QImage(self.W, self.H, QImage.Format_RGB32)
        for y in range(self.H):
            s = int(round(HLSMAX * (1 - y / float(self.H - 1))))
            for x in range(self.W):
                h = int(x * HLSMAX / float(self.W))
                img.setPixel(x, y, from_hsl(h, s, HLSMAX // 2).rgb())
        self.img = img

    def set_hs(self, h, s):
        self.hue, self.sat = h, s
        self.update()

    def _pick(self, pos):
        x = max(0, min(self.W - 1, pos.x() - 2))
        y = max(0, min(self.H - 1, pos.y() - 2))
        h = min(HLSMAX - 1, int(x * HLSMAX / float(self.W)))
        s = int(round(HLSMAX * (1 - y / float(self.H - 1))))
        self.set_hs(h, s)
        self.moved.emit(h, s)

    def mousePressEvent(self, e):
        self._pick(e.position().toPoint())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._pick(e.position().toPoint())

    def paintEvent(self, e):
        p = QPainter(self)
        T_frame(p, self.rect())
        p.drawImage(2, 2, self.img)
        x = 2 + int(self.hue * self.W / float(HLSMAX))
        y = 2 + int(round((1 - self.sat / float(HLSMAX)) * (self.H - 1)))
        p.setClipRect(QRect(2, 2, self.W, self.H))
        p.fillRect(QRect(x - 10, y - 1, 7, 3), QColor(0, 0, 0))
        p.fillRect(QRect(x + 4, y - 1, 7, 3), QColor(0, 0, 0))
        p.fillRect(QRect(x - 1, y - 10, 3, 7), QColor(0, 0, 0))
        p.fillRect(QRect(x - 1, y + 4, 3, 7), QColor(0, 0, 0))
        p.end()


def T_frame(p, r):
    """Sunken frame around r (2px)."""
    p.setPen(QColor(160, 160, 160))
    p.drawLine(r.left(), r.top(), r.right(), r.top())
    p.drawLine(r.left(), r.top(), r.left(), r.bottom())
    p.setPen(QColor(105, 105, 105))
    p.drawLine(r.left() + 1, r.top() + 1, r.right() - 1, r.top() + 1)
    p.drawLine(r.left() + 1, r.top() + 1, r.left() + 1, r.bottom() - 1)
    p.setPen(QColor(255, 255, 255))
    p.drawLine(r.left(), r.bottom(), r.right(), r.bottom())
    p.drawLine(r.right(), r.top(), r.right(), r.bottom())
    p.setPen(QColor(227, 227, 227))
    p.drawLine(r.left() + 1, r.bottom() - 1, r.right() - 1, r.bottom() - 1)
    p.drawLine(r.right() - 1, r.top() + 1, r.right() - 1, r.bottom() - 1)


class LumBar(QWidget):
    """Luminosity for the current hue and saturation, white at the top; an arrow marks it."""
    moved = Signal(int)

    BAR_W, H = 10, 187

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.BAR_W + 4 + 10, self.H + 4 + 8)
        self.hue, self.sat, self.lum = 160, 0, 0

    def set_hsl(self, h, s, l):
        self.hue, self.sat, self.lum = h, s, l
        self.update()

    def _pick(self, pos):
        y = max(0, min(self.H - 1, pos.y() - 2))
        lum = int(round(HLSMAX * (1 - y / float(self.H - 1))))
        self.lum = lum
        self.update()
        self.moved.emit(lum)

    def mousePressEvent(self, e):
        self._pick(e.position().toPoint())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._pick(e.position().toPoint())

    def paintEvent(self, e):
        p = QPainter(self)
        frame = QRect(0, 0, self.BAR_W + 4, self.H + 4)
        T_frame(p, frame)
        for y in range(self.H):
            lum = int(round(HLSMAX * (1 - y / float(self.H - 1))))
            p.setPen(from_hsl(self.hue, self.sat, lum))
            p.drawLine(2, 2 + y, 1 + self.BAR_W, 2 + y)
        y = 2 + int(round((1 - self.lum / float(HLSMAX)) * (self.H - 1)))
        x = self.BAR_W + 5
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0))
        p.drawPolygon(QPolygon([QPoint(x, y), QPoint(x + 6, y - 5), QPoint(x + 6, y + 5)]))
        p.end()


class Preview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.color = QColor(0, 0, 0)
        self.setFixedSize(66, 42)

    def paintEvent(self, e):
        p = QPainter(self)
        T_frame(p, self.rect())
        p.fillRect(self.rect().adjusted(2, 2, -2, -2), self.color)
        p.end()


class EditColorsDialog(QDialog):
    def __init__(self, color: QColor, custom, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Colors")
        self.setFont(T.ui_font())
        self.setFixedSize(456, 330)
        self.custom = [QColor(c) if c is not None else QColor(255, 255, 255) for c in list(custom)[:16]]
        self.custom += [QColor(255, 255, 255)] * (16 - len(self.custom))
        self._sync = False

        def label(text, x, y, w=120):
            lb = QLabel(text, self)
            lb.setFont(self.font())
            lb.move(x, y)
            lb.setFixedWidth(w)
            return lb

        lb_basic = label("&Basic colors:", 8, 8)
        self.basic = Swatches(BASIC, 8, self)
        self.basic.move(6, 24)
        lb_basic.setBuddy(self.basic)
        lb_custom = label("&Custom colors:", 8, 172)
        self.customs = Swatches([c.name() for c in self.custom], 8, self)
        self.customs.move(6, 188)
        lb_custom.setBuddy(self.customs)
        self.define = QPushButton("&Define Custom Colors >>", self)
        self.define.setGeometry(8, 245, 208, 23)
        self.define.setEnabled(False)
        ok = QPushButton("OK", self)
        ok.setGeometry(8, 297, 66, 23)
        ok.setDefault(True)
        cancel = QPushButton("Cancel", self)
        cancel.setGeometry(80, 297, 66, 23)
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)

        self.spectrum = Spectrum(self)
        self.spectrum.move(226, 8)
        self.lumbar = LumBar(self)
        self.lumbar.move(414, 8)
        self.preview = Preview(self)
        self.preview.move(226, 210)
        label("Color|Solid", 232, 254, 70).setAlignment(Qt.AlignLeft)

        self.edits = {}
        fm = QFontMetrics(self.font())
        for i, (key, text, hi) in enumerate((("h", "Hu&e:", HLSMAX - 1), ("s", "&Sat:", HLSMAX),
                                              ("l", "&Lum:", HLSMAX), ("r", "&Red:", 255),
                                              ("g", "&Green:", 255), ("b", "Bl&ue:", 255))):
            col, row = divmod(i, 3)
            x = 300 + col * 80
            y = 210 + row * 24
            lb = QLabel(text, self)
            lb.setGeometry(x, y + 2, 40, 18)
            lb.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            ed = QLineEdit(self)
            ed.setGeometry(x + 43, y, max(30, fm.horizontalAdvance("2400")), 21)
            ed.setValidator(QIntValidator(0, hi, ed))
            ed.setMaxLength(3)
            lb.setBuddy(ed)
            ed.textEdited.connect(lambda _t, k=key: self._edited(k))
            self.edits[key] = ed
        self.add = QPushButton("&Add to Custom Colors", self)
        self.add.setGeometry(226, 297, 222, 23)
        self.add.clicked.connect(self._add_custom)

        self.basic.picked.connect(lambda i: self.set_color(QColor(BASIC[i])))
        self.customs.picked.connect(lambda i: self.set_color(QColor(self.custom[i])))
        self.spectrum.moved.connect(self._hs_moved)
        self.lumbar.moved.connect(self._lum_moved)

        self.h, self.s, self.l = to_hsl(color)
        self.color = QColor(color)
        for i, c in enumerate(BASIC):
            if QColor(c).rgb() == color.rgb():
                self.basic.current = i
        self._show()

    # -- state ------------------------------------------------------------------
    def set_color(self, c: QColor):
        self.color = QColor(c)
        self.h, self.s, self.l = to_hsl(c)
        self._show()

    def current_color(self) -> QColor:
        return QColor(self.color)

    def _hs_moved(self, h, s):
        self.h, self.s = h, s
        if self.l in (0, HLSMAX):      # pure black or white: picking a hue should show something
            self.l = HLSMAX // 2
        self.color = from_hsl(self.h, self.s, self.l)
        self._show()

    def _lum_moved(self, lum):
        self.l = lum
        self.color = from_hsl(self.h, self.s, self.l)
        self._show()

    def _edited(self, key):
        try:
            v = {k: int(e.text() or 0) for k, e in self.edits.items()}
        except ValueError:
            return
        if key in "hsl":
            self.h, self.s, self.l = v["h"], v["s"], v["l"]
            self.color = from_hsl(self.h, self.s, self.l)
        else:
            self.color = QColor(min(255, v["r"]), min(255, v["g"]), min(255, v["b"]))
            self.h, self.s, self.l = to_hsl(self.color)
        self._show(skip=key)

    def _show(self, skip=None):
        vals = {"h": self.h, "s": self.s, "l": self.l,
                "r": self.color.red(), "g": self.color.green(), "b": self.color.blue()}
        for k, e in self.edits.items():
            if k != skip:
                e.setText(str(vals[k]))
        self.spectrum.set_hs(self.h, self.s)
        self.lumbar.set_hsl(self.h, self.s, self.l)
        self.preview.color = self.color
        self.preview.update()

    def _add_custom(self):
        i = self.customs.current if self.customs.current >= 0 else self._next_free()
        self.custom[i] = QColor(self.color)
        self.customs.colors[i] = self.color.name()
        self.customs.current = (i + 1) % 16
        self.customs.update()

    def _next_free(self):
        for i, c in enumerate(self.custom):
            if c.rgb() == QColor(255, 255, 255).rgb():
                return i
        return 0
