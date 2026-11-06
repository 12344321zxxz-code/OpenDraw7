"""From scanner or camera: bring a picture in from a scanner (SANE) or a webcam (ffmpeg)."""
import glob
import os
import re
import shutil
import subprocess
import tempfile

from PySide6.QtCore import Qt, QProcess, QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QLabel,
                               QPushButton, QComboBox, QDialogButtonBox, QApplication)

from . import theme as T

INSTALL = {
    "scanimage": "To use a scanner, install the SANE scanner tools, for example:\n\n"
                 "    sudo apt install sane-utils\n\n(Fedora: sudo dnf install sane-backends)",
    "ffmpeg": "To take a picture with a webcam, install ffmpeg, for example:\n\n"
              "    sudo apt install ffmpeg\n\n(Fedora: sudo dnf install ffmpeg)",
}


def _tool_env():
    """Environment for outside programs: without the bundled build's library path."""
    env = dict(os.environ)
    for k in ("LD_LIBRARY_PATH", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
        orig = env.pop(k + "_ORIG", None)      # PyInstaller keeps the user's own value here
        if orig is not None:
            env[k] = orig
        elif k == "LD_LIBRARY_PATH" and getattr(__import__("sys"), "frozen", False):
            env.pop(k, None)
    return env


def find_scanners(timeout=20):
    """[(device name, label)] from `scanimage -L`, or None if scanimage is not installed."""
    if not shutil.which("scanimage"):
        return None
    try:
        out = subprocess.run(["scanimage", "-L"], capture_output=True, text=True, timeout=timeout,
                             env=_tool_env()).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    found = []
    for line in out.splitlines():
        m = re.match(r"device [`'](.+?)' is an? (.+)", line.strip())
        if m:
            found.append((m.group(1), m.group(2).strip()))
    return found


def find_cameras():
    """[(device path, label)] for video capture devices, or None if ffmpeg is not installed."""
    cams = []
    for dev in sorted(glob.glob("/dev/video*"), key=lambda p: int(re.sub(r"\D", "", p) or 0)):
        n = os.path.basename(dev)
        name = n
        try:
            with open(f"/sys/class/video4linux/{n}/name", encoding="utf-8") as f:
                name = f.read().strip() or n
        except OSError:
            pass
        try:
            with open(f"/sys/class/video4linux/{n}/index", encoding="utf-8") as f:
                if f.read().strip() not in ("", "0"):
                    continue        # metadata node of a camera that is already listed
        except OSError:
            pass
        cams.append((dev, name))
    if not shutil.which("ffmpeg"):
        return None if cams else []
    return cams


class AcquireDialog(QDialog):
    """Choose a scanner or camera, then scan or take the picture. result_path holds the image."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose Device")
        self.setFont(T.ui_font())
        self.resize(420, 330)
        self.result_path = None
        self.proc = None
        self.out = os.path.join(tempfile.mkdtemp(prefix="opendraw7-"), "acquired.png")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("What device do you want to use?"))
        self.list = QListWidget(self)
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel("Resolution (scanners):"))
        self.dpi = QComboBox(self)
        self.dpi.addItems(["75", "150", "200", "300", "600"])
        self.dpi.setCurrentText("150")
        row.addWidget(self.dpi)
        row.addWidget(QLabel("DPI"))
        row.addStretch(1)
        lay.addLayout(row)
        self.status = QLabel("", self)
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        bb = QDialogButtonBox(self)
        self.go = QPushButton("OK", self)
        self.go.setDefault(True)
        self.refresh_btn = QPushButton("Refresh", self)
        bb.addButton(self.go, QDialogButtonBox.AcceptRole)
        bb.addButton(self.refresh_btn, QDialogButtonBox.ActionRole)
        bb.addButton(QDialogButtonBox.Cancel)
        bb.rejected.connect(self._cancel)
        self.go.clicked.connect(self._start)
        self.refresh_btn.clicked.connect(self.refresh)
        self.list.itemDoubleClicked.connect(lambda _i: self._start())
        self.list.currentRowChanged.connect(self._selected)
        lay.addWidget(bb)
        self.missing = []
        QTimer.singleShot(0, self.refresh)

    def refresh(self):
        self.list.clear()
        self.status.setText("Looking for scanners and cameras…")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            scanners = find_scanners()
            cams = find_cameras()
        finally:
            QApplication.restoreOverrideCursor()
        self.missing = []
        if scanners is None:
            self.missing.append("scanimage")
        if cams is None:
            self.missing.append("ffmpeg")
        for dev, label in scanners or []:
            it = QListWidgetItem(f"Scanner: {label}")
            it.setData(Qt.UserRole, ("scanner", dev))
            self.list.addItem(it)
        for dev, label in cams or []:
            it = QListWidgetItem(f"Camera: {label}  ({dev})")
            it.setData(Qt.UserRole, ("camera", dev))
            self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)
            self.status.setText("")
        else:
            msg = "No scanner or camera was found. Check that it is connected and switched on, then click Refresh."
            if self.missing:
                msg += "\n\n" + "\n\n".join(INSTALL[m] for m in self.missing)
            self.status.setText(msg)
            self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.go.setEnabled(self.list.count() > 0)

    def _selected(self, row):
        it = self.list.item(row)
        kind = it.data(Qt.UserRole)[0] if it else None
        self.dpi.setEnabled(kind == "scanner")
        self.go.setText("Scan" if kind == "scanner" else "Take picture" if kind == "camera" else "OK")

    def _start(self):
        it = self.list.currentItem()
        if it is None or self.proc is not None:
            return
        kind, dev = it.data(Qt.UserRole)
        if os.path.exists(self.out):
            os.remove(self.out)
        if kind == "scanner":
            prog = "scanimage"
            args = ["--device-name", dev, "--format=png", "--mode", "Color", "--resolution", self.dpi.currentText(),
                    "-o", self.out]
            self.status.setText("Scanning…  This can take a minute.")
        else:
            prog = "ffmpeg"
            # skip the first frames: many webcams start too dark while they adjust
            args = ["-hide_banner", "-loglevel", "error", "-f", "v4l2", "-i", dev,
                    "-vf", "select=gte(n\\,8)", "-frames:v", "1", "-y", self.out]
            self.status.setText("Taking the picture…")
        self.proc = QProcess(self)
        env = self.proc.processEnvironment()
        env.clear()
        for k, v in _tool_env().items():
            env.insert(k, v)
        self.proc.setProcessEnvironment(env)
        self.proc.finished.connect(self._done)
        self.proc.errorOccurred.connect(self._failed)
        self.go.setEnabled(False)
        self.list.setEnabled(False)
        self.proc.start(prog, args)

    def _failed(self, _err):
        if self.proc is not None and self.proc.state() == QProcess.NotRunning:
            self._done(-1, None)

    def _done(self, code, _status):
        proc, self.proc = self.proc, None
        if proc is None:
            return
        err = bytes(proc.readAllStandardError()).decode(errors="replace").strip()
        self.go.setEnabled(True)
        self.list.setEnabled(True)
        if code == 0 and os.path.exists(self.out) and os.path.getsize(self.out) > 0:
            self.result_path = self.out
            self.accept()
            return
        self.status.setText("The device did not send a picture." + (f"\n\n{err[-400:]}" if err else ""))

    def _cancel(self):
        if self.proc is not None:
            self.proc.kill()
            self.proc.waitForFinished(2000)
            self.proc = None
        self.reject()


def acquire(parent):
    """Show the device chooser; returns the path of the acquired picture, or None."""
    dlg = AcquireDialog(parent)
    if dlg.exec() == QDialog.Accepted:
        return dlg.result_path
    return None

