"""Dialog boxes: Resize and Skew, Image Properties, About, full-screen and thumbnail views."""
import time
from PySide6.QtCore import Qt, QSize, QRect, Signal
from PySide6.QtGui import QIntValidator, QPainter, QColor, QPixmap, QImage
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QRadioButton,
                               QLabel, QLineEdit, QCheckBox, QPushButton, QDialogButtonBox, QWidget,
                               QMessageBox)

from . import theme as T
from . import icons
from . import __version__, APP_NAME


def _int(edit: QLineEdit, default):
    try:
        return int(edit.text())
    except ValueError:
        return default


class ResizeSkewDialog(QDialog):
    def __init__(self, size: QSize, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Resize and Skew")
        self.base = QSize(size)
        self._busy = False
        lay = QVBoxLayout(self)

        box = QGroupBox("Resize")
        g = QGridLayout(box)
        g.addWidget(QLabel("By:"), 0, 0)
        self.by_pct = QRadioButton("Percentage")
        self.by_px = QRadioButton("Pixels")
        self.by_pct.setChecked(True)
        g.addWidget(self.by_pct, 0, 1)
        g.addWidget(self.by_px, 0, 2)
        self.h_edit = QLineEdit("100")
        self.v_edit = QLineEdit("100")
        for e in (self.h_edit, self.v_edit):
            e.setValidator(QIntValidator(1, 99999, self))
            e.setFixedWidth(70)
        ih = QLabel()
        ih.setPixmap(icons.pixmap("resize"))
        g.addWidget(QLabel("Horizontal:"), 1, 1)
        g.addWidget(self.h_edit, 1, 2)
        g.addWidget(QLabel("Vertical:"), 2, 1)
        g.addWidget(self.v_edit, 2, 2)
        self.keep = QCheckBox("Maintain aspect ratio")
        self.keep.setChecked(True)
        g.addWidget(self.keep, 3, 0, 1, 3)
        lay.addWidget(box)

        box2 = QGroupBox("Skew (Degrees)")
        g2 = QGridLayout(box2)
        self.sh_edit = QLineEdit("0")
        self.sv_edit = QLineEdit("0")
        for e in (self.sh_edit, self.sv_edit):
            e.setValidator(QIntValidator(-89, 89, self))
            e.setFixedWidth(70)
        g2.addWidget(QLabel("Horizontal:"), 0, 1)
        g2.addWidget(self.sh_edit, 0, 2)
        g2.addWidget(QLabel("Vertical:"), 1, 1)
        g2.addWidget(self.sv_edit, 1, 2)
        g2.setColumnMinimumWidth(0, 26)
        lay.addWidget(box2)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        self.by_pct.toggled.connect(self._mode_changed)
        self.h_edit.textEdited.connect(lambda _t: self._linked(self.h_edit, self.v_edit, True))
        self.v_edit.textEdited.connect(lambda _t: self._linked(self.v_edit, self.h_edit, False))
        self.keep.toggled.connect(lambda on: on and self._linked(self.h_edit, self.v_edit, True))
        self.h_edit.selectAll()
        self.h_edit.setFocus()

    def _mode_changed(self, pct):
        if pct:
            self.h_edit.setText("100")
            self.v_edit.setText("100")
        else:
            self.h_edit.setText(str(self.base.width()))
            self.v_edit.setText(str(self.base.height()))

    def _linked(self, src, dst, src_is_h):
        if not self.keep.isChecked():
            return
        v = _int(src, 0)
        if v <= 0:
            return
        if self.by_pct.isChecked():
            dst.setText(str(v))
        elif src_is_h:
            dst.setText(str(max(1, round(v * self.base.height() / self.base.width()))))
        else:
            dst.setText(str(max(1, round(v * self.base.width() / self.base.height()))))

    def values(self):
        """(width, height, skew_h, skew_v) in pixels / degrees."""
        h, v = _int(self.h_edit, 100), _int(self.v_edit, 100)
        if self.by_pct.isChecked():
            h = max(1, min(500, h))
            v = max(1, min(500, v))
            w = max(1, round(self.base.width() * h / 100.0))
            hh = max(1, round(self.base.height() * v / 100.0))
        else:
            w, hh = max(1, h), max(1, v)
        return w, hh, max(-89, min(89, _int(self.sh_edit, 0))), max(-89, min(89, _int(self.sv_edit, 0)))


class PropertiesDialog(QDialog):
    DPI = 96.0

    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image Properties")
        self.doc = doc
        self.px = QSize(doc.size())
        lay = QVBoxLayout(self)

        box = QGroupBox("File Attributes")
        g = QGridLayout(box)
        saved = time.strftime("%x %X", time.localtime(doc.saved_at)) if doc.path and doc.saved_at else "Not Available"
        if doc.file_size is None:
            disk = "Not Available"
        elif doc.file_size < 1024:
            disk = f"{doc.file_size} bytes"
        else:
            disk = f"{doc.file_size / 1024.0:,.1f}KB"
        for row, (k, v) in enumerate((("Last Saved:", saved), ("Size on disk:", disk), ("Resolution:", "96 DPI"))):
            g.addWidget(QLabel(k), row, 0)
            g.addWidget(QLabel(v), row, 1)
        g.setColumnStretch(1, 1)
        lay.addWidget(box)

        row = QHBoxLayout()
        ub = QGroupBox("Units")
        ul = QVBoxLayout(ub)
        self.u_in = QRadioButton("Inches")
        self.u_cm = QRadioButton("Centimeters")
        self.u_px = QRadioButton("Pixels")
        self.u_px.setChecked(True)
        for w in (self.u_in, self.u_cm, self.u_px):
            ul.addWidget(w)
            w.toggled.connect(self._units_changed)
        row.addWidget(ub)
        cb = QGroupBox("Colors")
        cl = QVBoxLayout(cb)
        self.c_bw = QRadioButton("Black and white")
        self.c_col = QRadioButton("Color")
        self.c_col.setChecked(True)
        cl.addWidget(self.c_bw)
        cl.addWidget(self.c_col)
        cl.addStretch(1)
        row.addWidget(cb)
        lay.addLayout(row)

        dims = QHBoxLayout()
        self.w_edit = QLineEdit()
        self.h_edit = QLineEdit()
        for e in (self.w_edit, self.h_edit):
            e.setFixedWidth(70)
        dims.addWidget(QLabel("Width:"))
        dims.addWidget(self.w_edit)
        dims.addWidget(QLabel("Height:"))
        dims.addWidget(self.h_edit)
        default = QPushButton("Default")
        default.clicked.connect(self._default)
        dims.addWidget(default)
        lay.addLayout(dims)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._unit = "px"
        self._show()

    def _factor(self, unit):
        return {"px": 1.0, "in": 1.0 / self.DPI, "cm": 2.54 / self.DPI}[unit]

    def _read(self):
        f = self._factor(self._unit)
        try:
            w = float(self.w_edit.text().replace(",", "."))
            h = float(self.h_edit.text().replace(",", "."))
        except ValueError:
            return
        self.px = QSize(max(1, min(30000, round(w / f))), max(1, min(30000, round(h / f))))

    def _show(self):
        f = self._factor(self._unit)
        if self._unit == "px":
            self.w_edit.setText(str(self.px.width()))
            self.h_edit.setText(str(self.px.height()))
        else:
            self.w_edit.setText(f"{self.px.width() * f:.2f}")
            self.h_edit.setText(f"{self.px.height() * f:.2f}")

    def _units_changed(self, on):
        if not on:
            return
        self._read()
        self._unit = "in" if self.u_in.isChecked() else "cm" if self.u_cm.isChecked() else "px"
        self._show()

    def _default(self):
        self.px = QSize(800, 600)
        self._show()

    def values(self):
        self._read()
        return self.px.width(), self.px.height(), self.c_bw.isChecked()


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(icons.pixmap("app", 64))
        top.addWidget(ic, 0, Qt.AlignTop)
        text = QLabel(
            f"<h3 style='margin:0'>{APP_NAME}</h3>"
            f"<p>Version {__version__}</p>"
            "<p>An open-source paint program for Linux, built to look and work like the "
            "one that shipped with Windows 7.</p>"
            "<p>All code and artwork are original. This project is not affiliated with or "
            "endorsed by Microsoft.</p>"
            "<p>Released under the MIT licence. Built with Qt for Python (PySide6, LGPL).</p>")
        text.setWordWrap(True)
        text.setMinimumWidth(330)
        top.addWidget(text, 1)
        lay.addLayout(top)
        bb = QDialogButtonBox(QDialogButtonBox.Ok)
        bb.accepted.connect(self.accept)
        lay.addWidget(bb)


def ask_save(parent, name):
    """'Do you want to save changes?' -> 'save' | 'discard' | 'cancel'."""
    mb = QMessageBox(parent)
    mb.setWindowTitle("Paint")
    mb.setIcon(QMessageBox.NoIcon)
    mb.setText(f"Do you want to save changes to {name}?")
    save = mb.addButton("Save", QMessageBox.AcceptRole)
    dont = mb.addButton("Don't Save", QMessageBox.DestructiveRole)
    mb.addButton("Cancel", QMessageBox.RejectRole)
    mb.setDefaultButton(save)
    mb.exec()
    hit = mb.clickedButton()
    return "save" if hit is save else "discard" if hit is dont else "cancel"


class FullScreenView(QWidget):
    """The picture on its own, full screen; any click or key leaves."""

    def __init__(self, image: QImage, parent=None):
        super().__init__(parent, Qt.Window | Qt.FramelessWindowHint)
        self.image = QImage(image)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setCursor(Qt.ArrowCursor)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), T.WORKSPACE)
        p.drawImage(0, 0, self.image)
        p.end()

    def mousePressEvent(self, e):
        self.close()

    def keyPressEvent(self, e):
        self.close()


class ThumbnailWindow(QWidget):
    """Small always-on-top view of the whole picture at 100%."""
    closed = Signal()

    def __init__(self, canvas, parent=None):
        super().__init__(parent, Qt.Tool | Qt.WindowStaysOnTopHint)
        self.canvas = canvas
        self.setWindowTitle("Thumbnail")
        self.resize(220, 170)
        canvas.doc.changed.connect(self.update)
        canvas.viewChanged.connect(self.update)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(255, 255, 255))
        img = self.canvas.display_image()
        o = self.canvas.visible_doc_origin()
        p.drawImage(0, 0, img, o.x(), o.y(), self.width(), self.height())
        p.end()

    def closeEvent(self, e):
        self.closed.emit()
        super().closeEvent(e)
