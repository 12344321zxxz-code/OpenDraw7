"""Key tips: press and release Alt (or press F10) to show letters on the ribbon; type them instead
of clicking. The first level covers the quick access toolbar, the Paint menu and the tabs; choosing a
tab shows the tips of its controls. Esc goes back a level, Alt or a mouse click hides them."""
from PySide6.QtCore import Qt, QObject, QEvent, QRect, QPoint, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QLinearGradient, QBrush, QFontMetrics
from PySide6.QtWidgets import QWidget, QApplication

from . import theme as T

GROUP_KEYS = {"Clipboard": "ZC", "Image": "ZI", "Tools": "ZT", "Shapes": "ZS", "Colors": "ZL",
              "Font": "ZF", "Background": "ZB"}


class Tip:
    __slots__ = ("keys", "rect", "action", "enabled", "cx")

    def __init__(self, keys, rect, action, enabled=True, cx=None):
        self.keys, self.rect, self.action, self.enabled = keys, rect, action, enabled
        self.cx = rect.center().x() if cx is None else cx     # where the badge is centred


class Overlay(QWidget):
    """Draws the tips over the window; lets every mouse event through."""

    def __init__(self, win):
        super().__init__(win)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFont(T.ui_font(11))
        self.tips = []
        self.prefix = ""
        self.hide()

    def badge(self, tip):
        fm = QFontMetrics(self.font())
        w = max(16, fm.horizontalAdvance(tip.keys) + 8)
        h = 16
        r = tip.rect
        return QRect(tip.cx - w // 2, r.bottom() - h // 2 + 1, w, h)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setFont(self.font())
        for tip in self.tips:
            if not tip.keys.startswith(self.prefix):
                continue
            b = self.badge(tip)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 40))
            p.drawRoundedRect(b.translated(1, 1), 2, 2)
            g = QLinearGradient(0, b.top(), 0, b.bottom())
            g.setColorAt(0, QColor(255, 255, 255))
            g.setColorAt(1, QColor(228, 229, 240))
            p.setBrush(QBrush(g))
            p.setPen(QPen(QColor(118, 118, 118), 1))
            p.drawRoundedRect(b.adjusted(0, 0, -1, -1), 2, 2)
            p.setPen(QColor(60, 60, 60) if tip.enabled else QColor(160, 160, 160))
            p.drawText(b, Qt.AlignCenter, tip.keys)
        p.end()


class KeyTips(QObject):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.overlay = Overlay(win)
        self.level = 0              # 0 hidden, 1 tabs, 2 a tab's controls
        self.page = None
        self._armed = False
        QApplication.instance().installEventFilter(self)

    # -- what the tips are ---------------------------------------------------------
    def _wrect(self, w):
        return QRect(w.mapTo(self.win, QPoint(0, 0)), w.size())

    def _visible(self, w):
        return w is not None and w.isVisibleTo(self.win) and w.isVisible()

    def _widget_tip(self, keys, w, action=None):
        if not self._visible(w):
            return None
        r = self._wrect(w)
        cx = r.left() + 11 if getattr(w, "kind", None) == "small" else None    # under the icon
        return Tip(keys, r, action or (lambda: press(w)), w.isEnabled(), cx)

    def level1(self):
        win = self.win
        tips = []
        for keys, b in (("1", win.q_save), ("2", win.q_undo), ("3", win.q_redo)):
            t = self._widget_tip(keys, b)
            if t:
                tips.append(t)
        tb = win.ribbon.tabbar
        off = tb.mapTo(win, QPoint(0, 0))
        tips.append(Tip("F", tb.app_rect().translated(off), win._open_app_menu))
        rects = tb.tab_rects()
        for idx, keys in ((win.home_idx, "H"), (win.view_idx, "V"), (win.text_idx, "X")):
            if tb.tabs[idx]["visible"]:
                tips.append(Tip(keys, rects[idx].translated(off), lambda i=idx: self._open_tab(i)))
        return tips

    def level2(self, idx):
        win = self.win
        c1, c2, edit = win._color_btns[0 if idx == win.home_idx else 1]
        if idx == win.home_idx:
            spec = [("V", win.paste_btn), ("X", win.cut_btn), ("C", win.copy_btn),
                    ("SE", win.select_btn), ("RC", win.crop_btn), ("RE", win.resize_btn), ("RO", win.rotate_btn),
                    ("P", win.tool_btns["pencil"]), ("F", win.tool_btns["fill"]), ("T", win.tool_btns["text"]),
                    ("E", win.tool_btns["eraser"]), ("K", win.tool_btns["picker"]),
                    ("M", win.tool_btns["magnifier"]), ("B", win.brush_btn),
                    ("SH", win.gallery, win.gallery.open_more), ("SO", win.outline_btn), ("SF", win.fill_btn),
                    ("SZ", win.size_btn), ("1", c1), ("2", c2), ("EC", edit)]
        elif idx == win.view_idx:
            spec = [("I", win.zoomin_btn), ("O", win.zoomout_btn), ("M", win.z100_btn), ("W", win.zfit_btn),
                    ("R", win.rulers_chk), ("G", win.grid_chk), ("S", win.status_chk),
                    ("F", win.full_btn), ("T", win.thumb_btn)]
        else:
            spec = [("V", win.t_paste), ("X", win.t_cut), ("C", win.t_copy),
                    ("FF", win.font_combo, lambda: open_combo(win.font_combo)),
                    ("FS", win.size_combo, lambda: open_combo(win.size_combo)),
                    ("1", win.fmt_btns["bold"]), ("2", win.fmt_btns["italic"]), ("3", win.fmt_btns["underline"]),
                    ("4", win.fmt_btns["strike"]), ("BO", win.opaque_btn), ("BT", win.transp_btn),
                    ("C1", c1), ("C2", c2), ("EC", edit)]
        tips = []
        for item in spec:
            t = self._widget_tip(*item)
            if t:
                tips.append(t)
        page = win.ribbon.pages[idx]
        for g, stub in page._stubs.items():
            if self._visible(stub) and g.title in GROUP_KEYS:
                tips.append(Tip(GROUP_KEYS[g.title], self._wrect(stub), lambda s=stub: s._open_menu()))
        return tips

    # -- showing -----------------------------------------------------------------
    def active(self):
        return self.level > 0

    def show(self, level=1, page=None):
        self.level, self.page = level, page
        o = self.overlay
        o.prefix = ""
        o.tips = self.level1() if level == 1 else self.level2(page)
        o.setGeometry(self.win.rect())
        o.raise_()
        o.show()
        o.update()

    def hide(self):
        self.level = 0
        self.overlay.hide()

    def _open_tab(self, idx):
        rb = self.win.ribbon
        if rb.minimized:
            rb.set_minimized(False)
        rb.set_current(idx)
        self.show(2, idx)

    def _key(self, e):
        k = e.key()
        if k in (Qt.Key_Shift, Qt.Key_Control, Qt.Key_Meta, Qt.Key_AltGr, Qt.Key_CapsLock):
            return
        if k == Qt.Key_Escape:
            if self.overlay.prefix:
                self.overlay.prefix = ""
                self.overlay.update()
            elif self.level == 2:
                self.show(1)
            else:
                self.hide()
            return
        if k == Qt.Key_Backspace:
            self.overlay.prefix = self.overlay.prefix[:-1]
            self.overlay.update()
            return
        ch = e.text().upper()
        if not ch or not ch.isprintable() or ch.isspace():
            return
        prefix = self.overlay.prefix + ch
        matches = [t for t in self.overlay.tips if t.keys.startswith(prefix)]
        if not matches:
            QApplication.beep()
            return
        exact = [t for t in matches if t.keys == prefix]
        if exact and len(matches) == 1:
            tip = exact[0]
            if not tip.enabled:
                QApplication.beep()
                self.overlay.prefix = ""
                self.overlay.update()
                return
            if self.level == 1 and tip.keys in ("H", "V", "X"):
                tip.action()            # straight away, so the next letter already sees the tab's tips
                return
            self.hide()
            QTimer.singleShot(0, tip.action)
            return
        self.overlay.prefix = prefix
        self.overlay.update()

    # -- input -------------------------------------------------------------------
    def _ours(self, obj):
        w = obj if isinstance(obj, QWidget) else None
        return w is not None and w.window() is self.win and self.win.isActiveWindow()

    def eventFilter(self, obj, e):
        t = e.type()
        if t in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick, QEvent.Wheel):
            self._armed = False
            if self.active():
                self.hide()
            return False
        if t == QEvent.WindowDeactivate and obj is self.win:
            self._armed = False
            self.hide()
            return False
        if t not in (QEvent.KeyPress, QEvent.KeyRelease, QEvent.ShortcutOverride) or not self._ours(obj):
            return False
        k = e.key()
        if t == QEvent.ShortcutOverride:
            if self.active() or (k == Qt.Key_F10 and not e.modifiers()):
                e.accept()
                return True
            return False
        if t == QEvent.KeyPress:
            if e.isAutoRepeat():
                return self.active()
            if k == Qt.Key_Alt:
                self._armed = not self.active()
                if self.active():
                    self.hide()
                    return True
                return False
            self._armed = False
            if k == Qt.Key_F10 and not e.modifiers():
                self.hide() if self.active() else self.show(1)
                return True
            if self.active():
                self._key(e)
                return True
            return False
        # KeyRelease
        if k == Qt.Key_Alt:
            show = self._armed and not self.active()
            self._armed = False
            if show:
                self.show(1)
                return True
            return False
        return self.active()


def press(w):
    """Do what clicking w would do."""
    from .ribbon import RButton
    if not w.isEnabled():
        return
    if isinstance(w, RButton):
        if w.menu_factory is not None and (w.dropdown or w.split):
            w._open_menu()
        else:
            w.clicked.emit()
        return
    toggle = getattr(w, "on_toggle", None)
    if toggle is not None or hasattr(w, "setChecked") and hasattr(w, "isChecked"):
        w.setChecked(not w.isChecked())
        if toggle:
            toggle(w.isChecked())


def open_combo(combo):
    combo.setFocus(Qt.ShortcutFocusReason)
    combo.showPopup()
