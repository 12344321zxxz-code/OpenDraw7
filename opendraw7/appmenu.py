"""The application menu opened by the blue button."""
import os
from PySide6.QtCore import Qt, QRect, QRectF, QPoint, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QLinearGradient, QFontMetrics, QPainterPath

from . import theme as T
from . import icons
from .ribbon import Popup

ITEM_H = 42
LEFT_W = 214
RIGHT_W = 300
TOP = 26
SUB_H = 54

SAVE_AS = [
    ("saveas:png", "PNG picture", "Keeps full quality. Good for drawings, screenshots and the web.", "saveas32"),
    ("saveas:jpeg", "JPEG picture", "Small files for photos, with a little quality lost.", "saveas32"),
    ("saveas:bmp24", "BMP picture", "Uncompressed, full quality, large files.", "saveas32"),
    ("saveas:gif", "GIF picture", "Up to 256 colours. For simple drawings.", "saveas32"),
    ("saveas", "Other formats", "Open the Save As box and choose from every file type.", "saveas32"),
]
PRINT = [
    ("print", "Print", "Choose a printer, the number of copies and other options before printing.", "print32"),
    ("print:setup", "Page setup", "Change how the picture is laid out on the page.", "properties32"),
    ("print:preview", "Print preview", "See the page and make changes before printing.", "print32"),
]
DESKTOP = [
    ("desktop:fill", "Fill", "Fill the whole screen with the picture.", "desktop32"),
    ("desktop:tile", "Tile", "Repeat the picture so it covers the whole screen.", "desktop32"),
    ("desktop:center", "Center", "Centre the picture on the screen.", "desktop32"),
]

ITEMS = [
    {"id": "new", "text": "New", "icon": "new32", "key": "N"},
    {"id": "open", "text": "Open", "icon": "open32", "key": "O"},
    {"id": "save", "text": "Save", "icon": "save32", "key": "S"},
    {"id": "saveas", "text": "Save as", "icon": "saveas32", "key": "a", "sub": ("Save as", SAVE_AS), "sep": True},
    {"id": "print", "text": "Print", "icon": "print32", "key": "P", "sub": ("Print", PRINT)},
    {"id": "scanner", "text": "From scanner or camera", "icon": "scanner32", "key": "m", "disabled": True},
    {"id": "email", "text": "Send in e-mail", "icon": "email32", "key": "d", "sep": True},
    {"id": "desktop:fill", "text": "Set as desktop background", "icon": "desktop32", "key": "b",
     "sub": ("Set as desktop background", DESKTOP)},
    {"id": "properties", "text": "Properties", "icon": "properties32", "key": "e", "sep": True},
    {"id": "about", "text": "About OpenDraw7", "icon": "app", "key": "t"},
    {"id": "exit", "text": "Exit", "icon": "exit32", "key": "x"},
]


class AppMenu(Popup):
    triggered = Signal(str)

    def __init__(self, recent, parent=None):
        super().__init__(parent)
        self.recent = list(recent)[:9]
        self._hover = None          # ('item', i) | ('sub', i) | ('recent', i)
        self._pane = None           # index of item whose submenu is shown
        self.rows = []
        y = TOP + 4
        for it in ITEMS:
            self.rows.append(QRect(4, y, LEFT_W - 4, ITEM_H))
            y += ITEM_H + (5 if it.get("sep") else 0)
        self.setFixedSize(LEFT_W + RIGHT_W + 6, max(y + 6, TOP + 4 + 5 * SUB_H + 34))

    # -- geometry ------------------------------------------------------------
    def _right(self):
        return QRect(LEFT_W + 2, TOP + 4, RIGHT_W, self.height() - TOP - 8)

    def _sub_rects(self):
        if self._pane is None:
            return []
        r = self._right()
        n = len(ITEMS[self._pane]["sub"][1])
        return [QRect(r.left() + 3, r.top() + 26 + i * SUB_H, r.width() - 6, SUB_H) for i in range(n)]

    def _recent_rects(self):
        r = self._right()
        return [QRect(r.left() + 3, r.top() + 26 + i * 23, r.width() - 6, 23) for i in range(len(self.recent))]

    def _hit(self, pos):
        for i, r in enumerate(self.rows):
            if r.contains(pos):
                return ("item", i)
        if self._pane is not None:
            for i, r in enumerate(self._sub_rects()):
                if r.contains(pos):
                    return ("sub", i)
        else:
            for i, r in enumerate(self._recent_rects()):
                if r.contains(pos):
                    return ("recent", i)
        return None

    # -- events --------------------------------------------------------------
    def mouseMoveEvent(self, e):
        h = self._hit(e.position().toPoint())
        if h != self._hover:
            self._hover = h
            if h and h[0] == "item":
                self._pane = h[1] if ITEMS[h[1]].get("sub") else None
            self.update()

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    def mouseReleaseEvent(self, e):
        pos = e.position().toPoint()
        if not self.rect().contains(pos) or pos.y() < TOP:
            self.close()
            return
        h = self._hit(pos)
        if not h:
            return
        if h[0] == "item":
            it = ITEMS[h[1]]
            if it.get("disabled"):
                return
            self._fire(it["id"])
        elif h[0] == "sub":
            self._fire(ITEMS[self._pane]["sub"][1][h[1]][0])
        elif h[0] == "recent":
            self._fire("recent:" + self.recent[h[1]])

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()
            return
        ch = e.text().lower()
        if ch.isdigit() and 1 <= int(ch) <= len(self.recent):
            self._fire("recent:" + self.recent[int(ch) - 1])
            return
        for it in ITEMS:
            if ch and it["key"].lower() == ch and not it.get("disabled"):
                self._fire(it["id"])
                return

    def _fire(self, action):
        self.close()
        self.triggered.emit(action)

    # -- painting ------------------------------------------------------------
    def paintEvent(self, e):
        p = QPainter(self)
        r = self.rect()
        g = QLinearGradient(0, 0, 0, r.height())
        g.setColorAt(0, QColor(214, 226, 242))
        g.setColorAt(1, QColor(196, 212, 234))
        p.fillRect(r, QBrush(g))
        p.setPen(QPen(QColor(104, 128, 164), 1))
        p.drawRect(0, 0, r.width() - 1, r.height() - 1)
        # the pressed application button, drawn where the real one sits
        ar = QRectF(2.5, 1.5, 55, 23)
        ag = QLinearGradient(0, ar.top(), 0, ar.bottom())
        ag.setColorAt(0, QColor(30, 86, 176))
        ag.setColorAt(1, QColor(52, 116, 210))
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(T.APP_BTN_BORDER, 1))
        p.setBrush(QBrush(ag))
        p.drawRoundedRect(ar, 3, 3)
        p.setRenderHint(QPainter.Antialiasing, False)
        gx, gy = 17, 7
        p.fillRect(gx, gy, 14, 11, QColor(255, 255, 255))
        p.fillRect(gx + 1, gy + 1, 12, 2, QColor(41, 103, 196))
        for i in range(3):
            p.fillRect(gx + 2, gy + 4 + i * 2, 10, 1, QColor(120, 160, 220))
        T.draw_arrow(p, gx + 22, gy + 6, QColor(255, 255, 255))
        # left pane
        left = QRect(2, TOP + 2, LEFT_W - 1, r.height() - TOP - 5)
        p.fillRect(left, QColor(251, 252, 253))
        p.setPen(QPen(QColor(160, 178, 204), 1))
        p.drawRect(left.adjusted(0, 0, -1, -1))
        p.setFont(self.font())
        fm = QFontMetrics(self.font())
        for i, (it, row) in enumerate(zip(ITEMS, self.rows)):
            en = not it.get("disabled")
            hot = en and (self._hover == ("item", i) or (self._pane == i and self._hover and self._hover[0] == "sub"))
            if hot:
                T.draw_hot(p, row.adjusted(1, 0, -3, 0), "hover")
            p.drawPixmap(row.left() + 8, row.top() + 5, icons.pixmap(it["icon"], 32, en))
            p.setPen(T.TEXT_BLACK if en else T.TEXT_DISABLED)
            tx = row.left() + 50
            text = it["text"]
            p.drawText(QRect(tx, row.top(), row.width() - 70, row.height()), Qt.AlignLeft | Qt.AlignVCenter, text)
            k = text.lower().find(it["key"].lower()) if it["key"].islower() else text.find(it["key"])
            if k >= 0:
                ux = tx + fm.horizontalAdvance(text[:k])
                uw = fm.horizontalAdvance(text[k])
                uy = row.center().y() + fm.ascent() // 2 + 2
                p.drawLine(ux, uy, ux + uw - 1, uy)
            if it.get("sub"):
                ax = row.right() - 14
                ay = row.center().y()
                if hot:
                    p.setPen(QPen(T.HOT_BORDER, 1))
                    p.drawLine(ax - 9, row.top() + 2, ax - 9, row.bottom() - 2)
                col = T.TEXT_BLACK if en else T.TEXT_DISABLED
                for j in range(4):
                    p.fillRect(ax + j, ay - 3 + j, 1, 7 - 2 * j, col)
            if it.get("sep"):
                p.setPen(QPen(QColor(197, 205, 216), 1))
                p.drawLine(row.left() + 46, row.bottom() + 3, row.right() - 6, row.bottom() + 3)
        # right pane
        right = self._right()
        p.fillRect(right, QColor(238, 243, 250))
        p.setPen(QPen(QColor(160, 178, 204), 1))
        p.drawRect(right.adjusted(0, -2, -1, 1))
        head = "Recent pictures" if self._pane is None else ITEMS[self._pane]["sub"][0]
        p.setFont(T.ui_font(bold=True))
        p.setPen(QColor(30, 57, 91))
        p.drawText(QRect(right.left() + 8, right.top(), right.width() - 12, 22), Qt.AlignLeft | Qt.AlignVCenter, head)
        p.setPen(QPen(QColor(160, 178, 204), 1))
        p.drawLine(right.left() + 4, right.top() + 22, right.right() - 5, right.top() + 22)
        if self._pane is None:
            p.setFont(self.font())
            for i, (path, rr) in enumerate(zip(self.recent, self._recent_rects())):
                if self._hover == ("recent", i):
                    T.draw_hot(p, rr, "hover")
                p.setPen(T.TEXT_BLACK)
                num = str(i + 1)
                p.drawText(QRect(rr.left() + 8, rr.top(), 14, rr.height()), Qt.AlignLeft | Qt.AlignVCenter, num)
                uy = rr.center().y() + fm.ascent() // 2 + 2
                p.drawLine(rr.left() + 8, uy, rr.left() + 8 + fm.horizontalAdvance(num) - 1, uy)
                name = fm.elidedText(os.path.basename(path), Qt.ElideMiddle, rr.width() - 34)
                p.drawText(QRect(rr.left() + 26, rr.top(), rr.width() - 30, rr.height()),
                           Qt.AlignLeft | Qt.AlignVCenter, name)
        else:
            subs = ITEMS[self._pane]["sub"][1]
            for i, ((aid, title, desc, icon), rr) in enumerate(zip(subs, self._sub_rects())):
                if self._hover == ("sub", i):
                    T.draw_hot(p, rr, "hover")
                p.drawPixmap(rr.left() + 6, rr.top() + 11, icons.pixmap(icon, 32))
                p.setFont(T.ui_font(bold=True))
                p.setPen(T.TEXT_BLACK)
                p.drawText(QRect(rr.left() + 46, rr.top() + 4, rr.width() - 50, 16), Qt.AlignLeft | Qt.AlignVCenter, title)
                p.setFont(self.font())
                p.setPen(QColor(70, 70, 70))
                p.drawText(QRect(rr.left() + 46, rr.top() + 20, rr.width() - 52, 32),
                           Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, desc)
        p.end()
