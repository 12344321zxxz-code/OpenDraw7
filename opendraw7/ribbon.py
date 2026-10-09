"""Ribbon widgets: buttons, groups, tab strip, galleries and popups."""
from PySide6.QtCore import Qt, QRect, QRectF, QPoint, QSize, Signal, QEvent, QTimer
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QFontMetrics, QLinearGradient, QPainterPath,
                           QCursor, QGuiApplication, QPixmap, QIcon, QAction)
from PySide6.QtWidgets import QWidget, QMenu, QToolTip, QWidgetAction, QLabel, QApplication

from . import theme as T
from . import icons


def tip_html(title, body="", shortcut=""):
    head = title + (f" ({shortcut})" if shortcut else "")
    if body:
        return f"<div style='white-space:nowrap'><b>{head}</b></div><div style='margin-top:4px'>{body}</div>"
    return f"<b>{head}</b>"


def popup_at(widget: QWidget, popup: QWidget, align_right=False):
    """Place a popup window just under widget, kept on-screen."""
    popup.adjustSize()
    g = widget.mapToGlobal(QPoint(0, widget.height()))
    scr = QGuiApplication.screenAt(g) or QGuiApplication.primaryScreen()
    a = scr.availableGeometry()
    x = g.x() - (popup.width() - widget.width() if align_right else 0)
    y = g.y()
    if x + popup.width() > a.right():
        x = a.right() - popup.width()
    if y + popup.height() > a.bottom():
        y = widget.mapToGlobal(QPoint(0, 0)).y() - popup.height()
    popup.move(max(a.left(), x), max(a.top(), y))


class RMenu(QMenu):
    """QMenu with the ribbon look and optional section headers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(T.MENU_QSS)
        self.setFont(T.ui_font())
        self.setAttribute(Qt.WA_TranslucentBackground, False)

    def add_header(self, text):
        lab = QLabel(text)
        lab.setFont(T.ui_font(bold=True))
        lab.setStyleSheet("QLabel{background:#dde7ee;color:#1e395b;padding:4px 8px;"
                          "border-bottom:1px solid #c5c5c5;}")
        wa = QWidgetAction(self)
        wa.setDefaultWidget(lab)
        wa.setEnabled(False)
        self.addAction(wa)
        return wa

    def add_item(self, text, icon=None, slot=None, enabled=True, shortcut=None, checked=None):
        act = QAction(text, self)
        if checked is not None:
            act.setIcon(icons.qicon("check" if checked else "blank"))
        elif icon:
            act.setIcon(icons.qicon(icon))
        if shortcut:
            act.setShortcut(shortcut)
            act.setShortcutVisibleInContextMenu(True)
        act.setEnabled(enabled)
        if slot:
            act.triggered.connect(lambda _=False, s=slot: s())
        self.addAction(act)
        return act


class RButton(QWidget):
    """Ribbon button.

    kind: 'large' | 'small' | 'icon'
    split: large button whose lower half opens a menu separately
    dropdown: the whole button opens a menu
    """
    clicked = Signal()

    def __init__(self, text="", icon=None, kind="large", split=False, dropdown=False,
                 checkable=False, tip=None, parent=None, icon_size=None):
        super().__init__(parent)
        self.text = text
        self.icon_name = icon
        self.kind = kind
        self.split = split
        self.dropdown = dropdown
        self.checkable = checkable
        self._checked = False
        self._hover = None       # None | 'main' | 'menu'
        self._down = None
        self._menu_open = False
        self.menu_factory = None
        self.icon_size = icon_size or (32 if kind == "large" else 16)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover, True)
        self.setFont(T.ui_font())
        if tip:
            self.setToolTip(tip)
        self.setFixedSize(self.sizeHint())

    # -- public -----------------------------------------------------------
    def setChecked(self, on):
        on = bool(on)
        if on != self._checked:
            self._checked = on
            self.update()

    def isChecked(self):
        return self._checked

    def set_icon(self, name):
        self.icon_name = name
        self.update()

    def set_text(self, text):
        self.text = text
        self.setFixedSize(self.sizeHint())
        self.update()

    def set_menu(self, factory):
        """factory() -> QMenu or popup QWidget (must emit `closed` if custom)."""
        self.menu_factory = factory

    # -- geometry ---------------------------------------------------------
    def sizeHint(self):
        fm = QFontMetrics(self.font())
        if self.kind == "large":
            lines = self.text.split("\n")
            w = max(fm.horizontalAdvance(l) for l in lines) if self.text else 0
            if (self.split or self.dropdown) and len(lines) > 1:
                w = max(w, fm.horizontalAdvance(lines[-1]) + 12)
            return QSize(max(42, w + 10), T.CONTENT_H)
        if self.kind == "small":
            w = 3 + (16 + 3 if self.icon_name else 2) + fm.horizontalAdvance(self.text) + 5
            if self.dropdown or self.split:
                w += 9
            return QSize(w, T.ROW_H)
        return QSize(T.ROW_H + (9 if self.dropdown else 0), T.ROW_H)

    def _menu_rect(self):
        if self.kind == "large" and self.split:
            return QRect(0, 37, self.width(), self.height() - 37)
        return self.rect()

    def _part(self, pos):
        if not self.rect().contains(pos):
            return None
        if self.split:
            return "menu" if self._menu_rect().contains(pos) else "main"
        return "menu" if self.dropdown else "main"

    # -- events -----------------------------------------------------------
    def enterEvent(self, e):
        self._hover = self._part(self.mapFromGlobal(QCursor.pos()))
        self.update()

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    def mouseMoveEvent(self, e):
        part = self._part(e.position().toPoint())
        if part != self._hover:
            self._hover = part
            self.update()

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton or not self.isEnabled():
            return
        part = self._part(e.position().toPoint())
        self._down = part
        self.update()
        if part == "menu" and self.menu_factory:
            self._open_menu()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        part = self._part(e.position().toPoint())
        was = self._down
        self._down = None
        self.update()
        if was == "main" and part == "main" and self.isEnabled():
            self.clicked.emit()

    def changeEvent(self, e):
        if e.type() == QEvent.EnabledChange:
            self._hover = None
            self._down = None
            self.update()
        super().changeEvent(e)

    def _open_menu(self):
        m = self.menu_factory()
        if m is None:
            self._down = None
            self.update()
            return
        self._menu_open = True
        self.update()
        if isinstance(m, QMenu):
            m.exec(self.mapToGlobal(QPoint(0, self.height())))
            self._menu_closed()
        else:
            m.closed.connect(self._menu_closed)
            popup_at(self, m)
            m.show()

    def _menu_closed(self):
        self._menu_open = False
        self._down = None
        self._hover = self._part(self.mapFromGlobal(QCursor.pos()))
        self.update()

    # -- painting ---------------------------------------------------------
    def _paint_frame(self, p):
        r = self.rect()
        if not self.isEnabled():
            return
        hover = self._hover is not None
        if self.split:
            mr = self._menu_rect()
            top = QRect(0, 0, r.width(), mr.top())
            if self._menu_open:
                T.draw_hot(p, r, "hover")
                T.draw_hot(p, mr, "down")
            elif self._checked:
                T.draw_hot(p, r, "checked_hover" if hover else "checked")
                if hover:
                    p.setPen(QPen(T.DOWN_BORDER, 1))
                    p.drawLine(1, mr.top(), r.width() - 2, mr.top())
            elif self._down == "main":
                T.draw_hot(p, r, "hover")
                T.draw_hot(p, top.adjusted(0, 0, 0, 1), "down")
            elif hover:
                T.draw_hot(p, r, "hover")
                other = mr if self._hover == "main" else top
                p.fillRect(other.adjusted(1, 1, -1, -1), QColor(255, 255, 255, 120))
                p.setPen(QPen(T.HOT_BORDER, 1))
                p.drawLine(1, mr.top(), r.width() - 2, mr.top())
            return
        if self._menu_open or (self._down and hover):
            T.draw_hot(p, r, "down")
        elif self._checked:
            T.draw_hot(p, r, "checked_hover" if hover else "checked")
        elif hover:
            T.draw_hot(p, r, "hover")

    def paintEvent(self, e):
        p = QPainter(self)
        self._paint_frame(p)
        en = self.isEnabled()
        p.setFont(self.font())
        p.setPen(T.TEXT_BLACK if en else T.TEXT_DISABLED)
        fm = QFontMetrics(self.font())
        w = self.width()
        arrow = self.split or self.dropdown
        acol = T.TEXT_BLACK if en else T.TEXT_DISABLED
        if self.kind == "large":
            if self.icon_name:
                s = self.icon_size
                p.drawPixmap((w - s) // 2, 3 + (32 - s) // 2, icons.pixmap(self.icon_name, s, en))
            lines = self.text.split("\n")
            if len(lines) == 1:
                p.drawText(QRect(0, 37, w, 14), Qt.AlignHCenter | Qt.AlignVCenter, lines[0])
                if arrow:
                    T.draw_arrow(p, w // 2, 58, acol)
            else:
                p.drawText(QRect(0, 37, w, 14), Qt.AlignHCenter | Qt.AlignVCenter, lines[0])
                tw = fm.horizontalAdvance(lines[1])
                total = tw + (9 if arrow else 0)
                x = (w - total) // 2
                p.drawText(QRect(x, 50, tw + 2, 14), Qt.AlignLeft | Qt.AlignVCenter, lines[1])
                if arrow:
                    T.draw_arrow(p, x + tw + 6, 58, acol)
        elif self.kind == "small":
            x = 3
            if self.icon_name:
                p.drawPixmap(x, 3, icons.pixmap(self.icon_name, 16, en))
                x += 19
            else:
                x += 2
            p.drawText(QRect(x, 0, w - x, self.height()), Qt.AlignLeft | Qt.AlignVCenter, self.text)
            if arrow:
                T.draw_arrow(p, w - 7, self.height() // 2 + 1, acol)
        else:
            if self.icon_name:
                p.drawPixmap(3, 3, icons.pixmap(self.icon_name, 16, en))
            elif self.text:
                p.drawText(QRect(0, 0, T.ROW_H, self.height()), Qt.AlignCenter, self.text)
            if self.dropdown:
                T.draw_arrow(p, w - 6, self.height() // 2 + 1, acol)
        p.end()


class ColorButton(RButton):
    """'Color 1' / 'Color 2' toggle with a swatch."""

    def __init__(self, text, swatch, tip=None, parent=None):
        self.color = QColor(0, 0, 0)
        self.swatch = swatch
        super().__init__(text, None, "large", checkable=True, tip=tip, parent=parent)

    def sizeHint(self):
        return QSize(44, T.CONTENT_H)

    def set_color(self, c):
        self.color = QColor(c)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        self._paint_frame(p)
        s = self.swatch
        x = (self.width() - s) // 2
        y = 3 + (32 - s) // 2
        p.setPen(QPen(QColor(160, 160, 160), 1))
        p.setBrush(QColor(255, 255, 255))
        p.drawRect(x, y, s - 1, s - 1)
        p.fillRect(x + 2, y + 2, s - 4, s - 4, self.color)
        p.setFont(self.font())
        p.setPen(T.TEXT_BLACK if self.isEnabled() else T.TEXT_DISABLED)
        lines = self.text.split("\n")
        p.drawText(QRect(0, 37, self.width(), 14), Qt.AlignCenter, lines[0])
        if len(lines) > 1:
            p.drawText(QRect(0, 50, self.width(), 14), Qt.AlignCenter, lines[1])
        p.end()


class Palette(QWidget):
    """10 x 3 colour swatches (two rows of defaults + one row of custom slots)."""
    picked = Signal(QColor, int)   # colour, mouse button (1 left / 2 right)

    CELL = 22
    DEFAULTS = [
        (0, 0, 0), (127, 127, 127), (136, 0, 21), (237, 28, 36), (255, 127, 39),
        (255, 242, 0), (34, 177, 76), (0, 162, 232), (63, 72, 204), (163, 73, 164),
        (255, 255, 255), (195, 195, 195), (185, 122, 87), (255, 174, 201), (255, 201, 14),
        (239, 228, 176), (181, 230, 29), (153, 217, 234), (112, 146, 190), (200, 191, 231),
    ]
    NAMES = ["Black", "Gray-50%", "Dark red", "Red", "Orange", "Yellow", "Green", "Turquoise",
             "Indigo", "Purple", "White", "Gray-25%", "Brown", "Rose", "Gold", "Light yellow",
             "Lime", "Light turquoise", "Blue-gray", "Lavender"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.custom = [None] * 10
        self._next_custom = 0
        self._hover = -1
        self.setMouseTracking(True)
        self.setFixedSize(10 * self.CELL, 3 * self.CELL)

    def add_custom(self, color):
        c = QColor(color)
        for existing in self.custom:
            if existing is not None and existing.rgb() == c.rgb():
                return
        self.custom[self._next_custom] = c
        self._next_custom = (self._next_custom + 1) % 10
        self.update()

    def _color_at(self, idx):
        if idx < 0:
            return None
        if idx < 20:
            return QColor(*self.DEFAULTS[idx])
        return self.custom[idx - 20]

    def _index(self, pos):
        c, r = pos.x() // self.CELL, pos.y() // self.CELL
        if 0 <= c < 10 and 0 <= r < 3:
            return r * 10 + c
        return -1

    def mouseMoveEvent(self, e):
        i = self._index(e.position().toPoint())
        if i != self._hover:
            self._hover = i
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def mousePressEvent(self, e):
        col = self._color_at(self._index(e.position().toPoint()))
        if col is not None and e.button() in (Qt.LeftButton, Qt.RightButton):
            self.picked.emit(col, 1 if e.button() == Qt.LeftButton else 2)

    def event(self, e):
        if e.type() == QEvent.ToolTip:
            i = self._index(e.pos())
            if 0 <= i < 20:
                QToolTip.showText(e.globalPos(), self.NAMES[i], self)
            else:
                QToolTip.hideText()
            return True
        return super().event(e)

    def paintEvent(self, e):
        p = QPainter(self)
        for i in range(30):
            x, y = (i % 10) * self.CELL, (i // 10) * self.CELL
            col = self._color_at(i)
            hot = i == self._hover and col is not None
            p.setPen(QPen(T.HOT_BORDER if hot else QColor(160, 160, 160), 1))
            p.setBrush(QColor(255, 255, 255))
            p.drawRect(x + 1, y + 1, self.CELL - 4, self.CELL - 4)
            inner = QRect(x + 3, y + 3, self.CELL - 7, self.CELL - 7)
            if col is not None:
                p.fillRect(inner, col)
            else:
                g = QLinearGradient(0, inner.top(), 0, inner.bottom())
                g.setColorAt(0, QColor(255, 255, 255))
                g.setColorAt(1, QColor(228, 233, 241))
                p.fillRect(inner, QBrush(g))
        p.end()


class RGroup(QWidget):
    """A labelled ribbon group; children are placed with add()."""

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.title = title
        self._right = 0
        self.pad = 4
        self.setFont(T.ui_font())

    def add(self, w: QWidget, x, y):
        w.setParent(self)
        w.move(self.pad + x, T.CONTENT_TOP + y)
        w.show()
        self._right = max(self._right, x + w.width())
        self.finish()
        return w

    def finish(self):
        fm = QFontMetrics(self.font())
        width = max(self._right, fm.horizontalAdvance(self.title) + 6) + 2 * self.pad + 2
        self.setFixedSize(width, T.PANEL_H - 2)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setFont(self.font())
        p.setPen(T.GROUP_LABEL)
        p.drawText(QRect(0, T.LABEL_TOP, self.width() - 2, 16), Qt.AlignCenter, self.title)
        x = self.width() - 2
        p.setPen(QPen(T.GROUP_SEP_DARK, 1))
        p.drawLine(x, 4, x, T.PANEL_H - 7)
        p.setPen(QPen(T.GROUP_SEP_LIGHT, 1))
        p.drawLine(x + 1, 4, x + 1, T.PANEL_H - 7)
        p.end()


class GroupPopup(QWidget):
    """Shows a collapsed group's contents under its stand-in button."""
    closed = Signal()

    def __init__(self, group, page):
        super().__init__(page.window(), Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.group = group
        self.page = page
        self.setFixedSize(group.width() + 4, T.PANEL_H + 2)
        group.setParent(self)
        group.move(2, 1)
        group.show()
        self._buttons = [b for b in group.findChildren(RButton) if not (b.dropdown or b.split)]
        for b in self._buttons:
            b.clicked.connect(self.close)
        self._galleries = group.findChildren(ShapeGallery)
        for gal in self._galleries:
            gal.picked.connect(self._picked)

    def _picked(self, _sid):
        self.close()

    def hideEvent(self, e):
        for b in self._buttons:
            try:
                b.clicked.disconnect(self.close)
            except (RuntimeError, TypeError):
                pass
        for gal in self._galleries:
            try:
                gal.picked.disconnect(self._picked)
            except (RuntimeError, TypeError):
                pass
        self._buttons = []
        self._galleries = []
        self.group.hide()
        self.group.setParent(self.page)
        self.closed.emit()
        super().hideEvent(e)
        QTimer.singleShot(0, self.deleteLater)

    def paintEvent(self, e):
        p = QPainter(self)
        r = self.rect()
        p.fillRect(r, T.panel_brush(r))
        p.setPen(QPen(T.MENU_BORDER, 1))
        p.drawRect(0, 0, r.width() - 1, r.height() - 1)
        p.end()


class RPage(QWidget):
    """One tab's panel: a row of groups on the gradient background.

    When the window is too narrow, groups collapse one by one into a single
    drop-down button, in the order given to set_collapse_order().
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.groups = []
        self._order = []
        self._stubs = {}
        self._seps = []
        self.setFixedHeight(T.PANEL_H)

    def add_group(self, g: RGroup, stub_icon=None, stub_text=None):
        g.setParent(self)
        self.groups.append(g)
        if stub_icon:
            stub = RButton(stub_text or g.title, stub_icon, "large", dropdown=True, parent=self)
            stub.hide()
            stub.set_menu(lambda g=g: GroupPopup(g, self))
            self._stubs[g] = stub
        self.relayout()
        return g

    def set_collapse_order(self, groups):
        self._order = [g for g in groups if g in self._stubs]
        self.relayout()

    def natural_width(self):
        return sum(g.width() for g in self.groups) + 4

    def relayout(self):
        avail = self.width()
        collapsed = set()
        for g in self._order:
            total = 4 + sum((self._stubs[x].width() + 10) if x in collapsed else x.width() for x in self.groups)
            if total <= avail:
                break
            collapsed.add(g)
        x = 2
        self._seps = []
        for g in self.groups:
            stub = self._stubs.get(g)
            if g in collapsed:
                if g.parent() is self:
                    g.hide()
                stub.move(x + 4, T.CONTENT_TOP)
                stub.show()
                x += stub.width() + 10
                self._seps.append(x - 2)
            else:
                if stub is not None:
                    stub.hide()
                if g.parent() is self:
                    g.move(x, 0)
                    g.show()
                x += g.width()
        self.update()

    def resizeEvent(self, e):
        self.relayout()

    def paintEvent(self, e):
        p = QPainter(self)
        r = self.rect()
        p.fillRect(r, T.panel_brush(r))
        p.setPen(QPen(T.PANEL_BORDER, 1))
        p.drawLine(0, r.height() - 2, r.width(), r.height() - 2)
        p.setPen(QPen(T.PANEL_SHADOW, 1))
        p.drawLine(0, r.height() - 1, r.width(), r.height() - 1)
        for x in self._seps:
            p.setPen(QPen(T.GROUP_SEP_DARK, 1))
            p.drawLine(x, 4, x, T.PANEL_H - 7)
            p.setPen(QPen(T.GROUP_SEP_LIGHT, 1))
            p.drawLine(x + 1, 4, x + 1, T.PANEL_H - 7)
        p.end()


class RTabBar(QWidget):
    """The strip with the application button, the tabs and the help button."""
    tabSelected = Signal(int)
    tabDoubleClicked = Signal(int)
    appButtonPressed = Signal()
    helpClicked = Signal()
    minimizeClicked = Signal()

    APP_W = 56

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tabs = []        # dicts: text, visible, contextual
        self.current = 0
        self._hover = None    # ('tab', i) | ('app',) | ('help',) | ('min',)
        self.app_open = False
        self.minimized = False
        self.setMouseTracking(True)
        self.setFixedHeight(T.TAB_H)
        self.setFont(T.ui_font())

    def add_tab(self, text, contextual=False, visible=True):
        self.tabs.append({"text": text, "visible": visible, "contextual": contextual})
        self.update()
        return len(self.tabs) - 1

    def set_tab_visible(self, i, on):
        self.tabs[i]["visible"] = on
        self.update()

    def set_current(self, i):
        self.current = i
        self.update()

    def app_rect(self):
        return QRect(2, 1, self.APP_W, T.TAB_H - 1)

    def tab_rects(self):
        fm = QFontMetrics(self.font())
        x = 2 + self.APP_W + 3
        out = []
        for t in self.tabs:
            if not t["visible"]:
                out.append(QRect())
                continue
            w = fm.horizontalAdvance(t["text"]) + 26
            out.append(QRect(x, 1, w, T.TAB_H - 1))
            x += w + 2
        return out

    def help_rect(self):
        return QRect(self.width() - 24, 3, 18, 18)

    def min_rect(self):
        return QRect(self.width() - 46, 3, 18, 18)

    def _hit(self, pos):
        if self.app_rect().contains(pos):
            return ("app",)
        if self.help_rect().contains(pos):
            return ("help",)
        if self.min_rect().contains(pos):
            return ("min",)
        for i, r in enumerate(self.tab_rects()):
            if r.contains(pos):
                return ("tab", i)
        return None

    def mouseMoveEvent(self, e):
        h = self._hit(e.position().toPoint())
        if h != self._hover:
            self._hover = h
            self.update()

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        h = self._hit(e.position().toPoint())
        if not h:
            return
        if h[0] == "app":
            self.appButtonPressed.emit()
        elif h[0] == "help":
            self.helpClicked.emit()
        elif h[0] == "min":
            self.minimizeClicked.emit()
        else:
            self.tabSelected.emit(h[1])

    def mouseDoubleClickEvent(self, e):
        h = self._hit(e.position().toPoint())
        if h and h[0] == "tab":
            self.tabDoubleClicked.emit(h[1])

    def event(self, e):
        if e.type() == QEvent.ToolTip:
            h = self._hit(e.pos())
            text = {"app": "<b>Paint</b><div style='margin-top:4px'>Click here to open, save, or print "
                           "and to see everything else you can do with your picture.</div>",
                    "help": "<b>Help (F1)</b>",
                    "min": "<b>Minimize the Ribbon (Ctrl+F1)</b><div style='margin-top:4px'>Show only the tab "
                           "names on the Ribbon.</div>"}.get(h[0]) if h else None
            if text:
                QToolTip.showText(e.globalPos(), text, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(e)

    def paintEvent(self, e):
        p = QPainter(self)
        r = self.rect()
        p.fillRect(r, T.TABSTRIP_BG)
        show_sel = not self.minimized
        # bottom line
        p.setPen(QPen(T.PANEL_BORDER, 1))
        p.drawLine(0, r.height() - 1, r.width(), r.height() - 1)
        # application button
        ar = QRectF(self.app_rect()).adjusted(0.5, 0.5, -0.5, 0)
        p.setRenderHint(QPainter.Antialiasing, True)
        path = QPainterPath()
        path.moveTo(ar.left(), ar.bottom())
        path.lineTo(ar.left(), ar.top() + 3)
        path.quadTo(ar.left(), ar.top(), ar.left() + 3, ar.top())
        path.lineTo(ar.right() - 3, ar.top())
        path.quadTo(ar.right(), ar.top(), ar.right(), ar.top() + 3)
        path.lineTo(ar.right(), ar.bottom())
        g = QLinearGradient(0, ar.top(), 0, ar.bottom())
        hot = self._hover == ("app",) or self.app_open
        g.setColorAt(0, QColor(96, 160, 240) if hot else T.APP_BTN_TOP)
        g.setColorAt(0.5, QColor(52, 116, 210) if hot else QColor(41, 103, 196))
        g.setColorAt(1, QColor(30, 86, 176) if hot else T.APP_BTN_BOTTOM)
        p.setPen(QPen(T.APP_BTN_BORDER, 1))
        p.setBrush(QBrush(g))
        p.drawPath(path)
        p.setPen(QPen(QColor(255, 255, 255, 70), 1))
        p.setBrush(Qt.NoBrush)
        p.drawLine(ar.left() + 3, ar.top() + 1, ar.right() - 3, ar.top() + 1)
        p.setRenderHint(QPainter.Antialiasing, False)
        # glyph: small white sheet with lines + arrow
        gx, gy = int(ar.left()) + 15, int(ar.top()) + 6
        p.fillRect(gx, gy, 14, 11, QColor(255, 255, 255))
        p.fillRect(gx + 1, gy + 1, 12, 2, QColor(41, 103, 196))
        for i in range(3):
            p.fillRect(gx + 2, gy + 4 + i * 2, 10, 1, QColor(120, 160, 220))
        T.draw_arrow(p, gx + 22, gy + 6, QColor(255, 255, 255))
        # tabs
        p.setFont(self.font())
        for i, (t, tr) in enumerate(zip(self.tabs, self.tab_rects())):
            if not t["visible"]:
                continue
            sel = i == self.current and show_sel
            hov = self._hover == ("tab", i)
            rr = QRectF(tr).adjusted(0.5, 0.5, -0.5, 0)
            if sel or hov or t["contextual"]:
                path = QPainterPath()
                path.moveTo(rr.left(), rr.bottom() + (1 if sel else 0))
                path.lineTo(rr.left(), rr.top() + 3)
                path.quadTo(rr.left(), rr.top(), rr.left() + 3, rr.top())
                path.lineTo(rr.right() - 3, rr.top())
                path.quadTo(rr.right(), rr.top(), rr.right(), rr.top() + 3)
                path.lineTo(rr.right(), rr.bottom() + (1 if sel else 0))
                p.setRenderHint(QPainter.Antialiasing, True)
                g = QLinearGradient(0, rr.top(), 0, rr.bottom())
                if sel:
                    g.setColorAt(0, QColor(255, 255, 255))
                    g.setColorAt(1, T.PANEL_TOP)
                    p.setPen(QPen(T.PANEL_BORDER, 1))
                elif hov:
                    g.setColorAt(0, QColor(255, 255, 255, 235))
                    g.setColorAt(1, QColor(255, 247, 220, 200))
                    p.setPen(QPen(QColor(244, 214, 128), 1))
                else:
                    g.setColorAt(0, QColor(255, 244, 205))
                    g.setColorAt(1, QColor(255, 250, 232, 120))
                    p.setPen(QPen(QColor(232, 204, 130), 1))
                p.setBrush(QBrush(g))
                p.drawPath(path)
                p.setRenderHint(QPainter.Antialiasing, False)
                if sel:
                    p.setPen(QPen(T.PANEL_TOP, 1))
                    p.drawLine(tr.left() + 1, r.height() - 1, tr.right() - 1, r.height() - 1)
            p.setPen(T.TEXT)
            p.drawText(tr.adjusted(0, 0, 0, -1), Qt.AlignCenter, t["text"])
        # minimise caret and help
        mr = self.min_rect()
        if self._hover == ("min",):
            T.draw_hot(p, mr, "hover")
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(QColor(70, 90, 120), 1.6))
        cx, cy = mr.center().x() + 0.5, mr.center().y() + 0.5
        if self.minimized:
            p.drawPolyline([QPoint(int(cx - 3), int(cy - 1)), QPoint(int(cx), int(cy + 2)), QPoint(int(cx + 3), int(cy - 1))])
        else:
            p.drawPolyline([QPoint(int(cx - 3), int(cy + 1)), QPoint(int(cx), int(cy - 2)), QPoint(int(cx + 3), int(cy + 1))])
        p.setRenderHint(QPainter.Antialiasing, False)
        hr = self.help_rect()
        if self._hover == ("help",):
            T.draw_hot(p, hr, "hover")
        p.drawPixmap(hr.left() + 1, hr.top() + 1, icons.pixmap("help"))
        p.end()


class Ribbon(QWidget):
    """Tab strip + the current page."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tabbar = RTabBar(self)
        self.pages = []
        self.minimized = False
        self.tabbar.tabSelected.connect(self._on_tab)
        self.tabbar.tabDoubleClicked.connect(lambda i: self.set_minimized(not self.minimized))
        self.tabbar.minimizeClicked.connect(lambda: self.set_minimized(not self.minimized))
        self._relayout()

    def add_page(self, text, page: RPage, contextual=False, visible=True):
        i = self.tabbar.add_tab(text, contextual, visible)
        page.setParent(self)
        self.pages.append(page)
        page.setVisible(i == self.tabbar.current and not self.minimized)
        self._relayout()
        return i

    def _on_tab(self, i):
        if self.minimized:
            self.set_minimized(False)
        self.set_current(i)

    def set_current(self, i):
        self.tabbar.set_current(i)
        for j, pg in enumerate(self.pages):
            pg.setVisible(j == i and not self.minimized)
        self._relayout()

    def current(self):
        return self.tabbar.current

    def set_tab_visible(self, i, on):
        self.tabbar.set_tab_visible(i, on)
        if not on and self.tabbar.current == i:
            self.set_current(0)

    def set_minimized(self, on):
        self.minimized = on
        self.tabbar.minimized = on
        self.set_current(self.tabbar.current)
        self.tabbar.update()

    def _relayout(self):
        h = T.TAB_H + (0 if self.minimized else T.PANEL_H)
        self.setFixedHeight(h)
        self.tabbar.setGeometry(0, 0, self.width(), T.TAB_H)
        for pg in self.pages:
            pg.setGeometry(0, T.TAB_H, self.width(), T.PANEL_H)

    def resizeEvent(self, e):
        self._relayout()

    def minimumSizeHint(self):
        return QSize(300, self.height())


# ---------------------------------------------------------------- popups --
class Popup(QWidget):
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setMouseTracking(True)
        self.setFont(T.ui_font())
        self.setAttribute(Qt.WA_DeleteOnClose, True)

    def hideEvent(self, e):
        self.closed.emit()
        super().hideEvent(e)
        QTimer.singleShot(0, self.deleteLater)

    def _bg(self, p):
        p.fillRect(self.rect(), T.MENU_BG)
        p.setPen(QPen(T.MENU_BORDER, 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)


class GridPopup(Popup):
    """Grid of cells with pixmaps; used for the brush and shape galleries."""
    picked = Signal(str)

    def __init__(self, items, cols, cell, current=None, parent=None, pad=3):
        """items: list of (id, label, pixmap)."""
        super().__init__(parent)
        self.items = items
        self.cols = cols
        self.cell = cell
        self.pad = pad
        self.current = current
        self._hover = -1
        rows = (len(items) + cols - 1) // cols
        self.setFixedSize(cols * cell + 2 * pad + 2, rows * cell + 2 * pad + 2)

    def _index(self, pos):
        x, y = pos.x() - self.pad - 1, pos.y() - self.pad - 1
        if x < 0 or y < 0:
            return -1
        c, r = x // self.cell, y // self.cell
        i = r * self.cols + c
        return i if c < self.cols and 0 <= i < len(self.items) else -1

    def _rect(self, i):
        return QRect(self.pad + 1 + (i % self.cols) * self.cell, self.pad + 1 + (i // self.cols) * self.cell,
                     self.cell, self.cell)

    def mouseMoveEvent(self, e):
        i = self._index(e.position().toPoint())
        if i != self._hover:
            self._hover = i
            self.update()

    def mouseReleaseEvent(self, e):
        i = self._index(e.position().toPoint())
        if i >= 0:
            self.picked.emit(self.items[i][0])
            self.close()
        elif not self.rect().contains(e.position().toPoint()):
            self.close()

    def event(self, e):
        if e.type() == QEvent.ToolTip:
            i = self._index(e.pos())
            if i >= 0:
                QToolTip.showText(e.globalPos(), self.items[i][1], self)
            else:
                QToolTip.hideText()
            return True
        return super().event(e)

    def paintEvent(self, e):
        p = QPainter(self)
        self._bg(p)
        for i, (iid, label, pm) in enumerate(self.items):
            r = self._rect(i)
            if iid == self.current:
                T.draw_hot(p, r, "checked_hover" if i == self._hover else "checked")
            elif i == self._hover:
                T.draw_hot(p, r, "hover")
            p.drawPixmap(r.left() + (r.width() - pm.width()) // 2, r.top() + (r.height() - pm.height()) // 2, pm)
        p.end()


class SizePopup(Popup):
    """Four line thicknesses."""
    picked = Signal(int)

    def __init__(self, sizes, current, parent=None):
        super().__init__(parent)
        self.sizes = sizes
        self.current = current
        self._hover = -1
        self.rows = []
        y = 3
        for s in sizes:
            h = max(26, min(s, 28) + 14)
            self.rows.append(QRect(3, y, 146, h))
            y += h
        self.setFixedSize(152, y + 3)

    def _index(self, pos):
        for i, r in enumerate(self.rows):
            if r.contains(pos):
                return i
        return -1

    def mouseMoveEvent(self, e):
        i = self._index(e.position().toPoint())
        if i != self._hover:
            self._hover = i
            self.update()

    def mouseReleaseEvent(self, e):
        i = self._index(e.position().toPoint())
        if i >= 0:
            self.picked.emit(self.sizes[i])
            self.close()
        elif not self.rect().contains(e.position().toPoint()):
            self.close()

    def event(self, e):
        if e.type() == QEvent.ToolTip:
            i = self._index(e.pos())
            if i >= 0:
                QToolTip.showText(e.globalPos(), f"{self.sizes[i]}px", self)
            return True
        return super().event(e)

    def paintEvent(self, e):
        p = QPainter(self)
        self._bg(p)
        for i, (s, r) in enumerate(zip(self.sizes, self.rows)):
            if s == self.current:
                T.draw_hot(p, r, "checked_hover" if i == self._hover else "checked")
            elif i == self._hover:
                T.draw_hot(p, r, "hover")
            t = min(s, 28)
            p.fillRect(r.left() + 10, r.center().y() - t // 2 + (0 if t % 2 else 0), r.width() - 20, t, QColor(0, 0, 0))
        p.end()


class ShapeGallery(QWidget):
    """In-ribbon shape gallery: 7 x 3 visible cells plus scroll/expand buttons."""
    picked = Signal(str)

    COLS, ROWS, CELL = 7, 3, 20

    def __init__(self, shapes, parent=None):
        super().__init__(parent)
        self.shapes = shapes            # list of (id, label)
        self.current = None
        self.row0 = 0
        self._hover = None              # ('cell', i) | ('up',) | ('down',) | ('more',)
        self._more_open = False
        self.setMouseTracking(True)
        self.setFixedSize(self.COLS * self.CELL + 2 + 15, self.ROWS * self.CELL + 2)

    @property
    def total_rows(self):
        return (len(self.shapes) + self.COLS - 1) // self.COLS

    def set_current(self, sid):
        self.current = sid
        if sid is not None:
            ids = [s[0] for s in self.shapes]
            if sid in ids:
                row = ids.index(sid) // self.COLS
                if row < self.row0:
                    self.row0 = row
                elif row >= self.row0 + self.ROWS:
                    self.row0 = row - self.ROWS + 1
        self.update()

    def _btn_rects(self):
        x = self.COLS * self.CELL + 1
        h = self.height()
        a = h // 3
        return {"up": QRect(x, 0, 15, a), "down": QRect(x, a, 15, a), "more": QRect(x, 2 * a, 15, h - 2 * a)}

    def _hit(self, pos):
        for k, r in self._btn_rects().items():
            if r.contains(pos):
                return (k,)
        x, y = pos.x() - 1, pos.y() - 1
        if 0 <= x < self.COLS * self.CELL and 0 <= y < self.ROWS * self.CELL:
            i = (self.row0 + y // self.CELL) * self.COLS + x // self.CELL
            if i < len(self.shapes):
                return ("cell", i)
        return None

    def mouseMoveEvent(self, e):
        h = self._hit(e.position().toPoint())
        if h != self._hover:
            self._hover = h
            self.update()

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    def wheelEvent(self, e):
        d = -1 if e.angleDelta().y() > 0 else 1
        self.row0 = max(0, min(self.total_rows - self.ROWS, self.row0 + d))
        self.update()

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton or not self.isEnabled():
            return
        h = self._hit(e.position().toPoint())
        if not h:
            return
        if h[0] == "cell":
            self.picked.emit(self.shapes[h[1]][0])
        elif h[0] == "up":
            self.row0 = max(0, self.row0 - 1)
        elif h[0] == "down":
            self.row0 = min(max(0, self.total_rows - self.ROWS), self.row0 + 1)
        elif h[0] == "more":
            items = [(sid, lab, icons.shape_glyph(sid)) for sid, lab in self.shapes]
            pop = GridPopup(items, self.COLS, 22, self.current, self)
            pop.picked.connect(self.picked)
            self._more_open = True
            pop.closed.connect(self._more_closed)
            pop.adjustSize()
            g = self.mapToGlobal(QPoint(0, 0))
            pop.move(g)
            pop.show()
        self.update()

    def _more_closed(self):
        self._more_open = False
        self.update()

    def event(self, e):
        if e.type() == QEvent.ToolTip:
            h = self._hit(e.pos())
            if h and h[0] == "cell":
                QToolTip.showText(e.globalPos(), f"<b>{self.shapes[h[1]][1]}</b>", self)
            else:
                QToolTip.hideText()
            return True
        if e.type() == QEvent.EnabledChange:
            self.update()
        return super().event(e)

    def paintEvent(self, e):
        p = QPainter(self)
        en = self.isEnabled()
        gw = self.COLS * self.CELL + 1
        p.setPen(QPen(QColor(185, 201, 218), 1))
        p.setBrush(QColor(255, 255, 255) if en else QColor(246, 248, 251))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)
        for r in range(self.ROWS):
            for c in range(self.COLS):
                i = (self.row0 + r) * self.COLS + c
                if i >= len(self.shapes):
                    continue
                sid = self.shapes[i][0]
                cr = QRect(1 + c * self.CELL, 1 + r * self.CELL, self.CELL, self.CELL)
                hov = self._hover == ("cell", i) and en
                if sid == self.current and en:
                    T.draw_hot(p, cr, "checked_hover" if hov else "checked")
                elif hov:
                    T.draw_hot(p, cr, "hover")
                pm = icons.shape_glyph(sid, 16, "#34465e" if en else "#a9b2bd")
                p.drawPixmap(cr.left() + 2, cr.top() + 2, pm)
        # scroll buttons
        rects = self._btn_rects()
        for k, br in rects.items():
            g = QLinearGradient(0, br.top(), 0, br.bottom())
            g.setColorAt(0, QColor(250, 252, 254))
            g.setColorAt(1, QColor(222, 231, 243))
            p.fillRect(br.adjusted(0, 1, -1, 0), QBrush(g))
            p.setPen(QPen(QColor(185, 201, 218), 1))
            p.drawRect(br.adjusted(0, 0, -1, 0 if k == "more" else 0).adjusted(0, 0, 0, -1 if k == "more" else 0))
            if en and (self._hover == (k,) or (k == "more" and self._more_open)):
                T.draw_hot(p, br.adjusted(0, 0, 0, 0), "down" if (k == "more" and self._more_open) else "hover", 0)
            can = en and ((k == "up" and self.row0 > 0) or
                          (k == "down" and self.row0 < self.total_rows - self.ROWS) or k == "more")
            col = QColor(60, 80, 110) if can else QColor(175, 185, 198)
            cx, cy = br.center().x(), br.center().y()
            if k == "up":
                for i in range(3):
                    p.fillRect(cx - i, cy - 1 + i, 1 + 2 * i, 1, col)
            elif k == "down":
                T.draw_arrow(p, cx, cy, col)
            else:
                p.fillRect(cx - 2, cy - 3, 5, 1, col)
                T.draw_arrow(p, cx, cy + 1, col)
        p.end()
