"""Autosave and crash recovery.

While a picture has unsaved changes, a copy is written every AUTOSAVE_MS to the recovery folder
(one PNG plus a small JSON file per running OpenDraw7, named after its process id). The files are
removed when the picture is saved, replaced or the program closes normally. If OpenDraw7 starts and
finds files left by a process that is no longer running, it offers to bring the picture back.
"""
import json
import os
import threading
import time

from PySide6.QtCore import QObject, QTimer, QStandardPaths
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QMessageBox

AUTOSAVE_MS = int(os.environ.get("OPENDRAW7_AUTOSAVE_MS", 2 * 60 * 1000))   # override for testing


def recovery_dir():
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".local", "share", "OpenDraw7")
    return os.path.join(base, "recovery")


def _alive(pid):
    """True if an OpenDraw7 process with this id is still running."""
    if pid == os.getpid():
        return True
    proc = f"/proc/{pid}"
    if os.path.isdir("/proc"):
        try:
            with open(proc + "/stat", encoding="utf-8", errors="replace") as f:
                state = f.read().rsplit(")", 1)[-1].split()[0]
            if state in ("Z", "X"):          # exited, not yet reaped
                return False
            with open(proc + "/cmdline", "rb") as f:
                cmd = f.read().replace(b"\0", b" ").lower()
            return b"opendraw7" in cmd or b"run.py" in cmd     # else the id was reused
        except (OSError, IndexError):
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def leftovers(folder=None):
    """[(meta dict, png path, json path)] left by OpenDraw7 processes that are gone, newest first."""
    folder = folder or recovery_dir()
    out = []
    try:
        names = os.listdir(folder)
    except OSError:
        return out
    for name in names:
        if not name.endswith(".json"):
            continue
        jpath = os.path.join(folder, name)
        ppath = jpath[:-5] + ".png"
        try:
            with open(jpath, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            continue
        if not os.path.exists(ppath) or _alive(int(meta.get("pid", -1))):
            continue
        out.append((meta, ppath, jpath))
    out.sort(key=lambda t: t[0].get("time", 0), reverse=True)
    return out


def discard(ppath, jpath):
    for p in (ppath, jpath):
        try:
            os.remove(p)
        except OSError:
            pass


class AutoSaver(QObject):
    """Keeps a recovery copy of the window's picture while it has unsaved changes."""

    def __init__(self, win, interval=AUTOSAVE_MS, folder=None):
        super().__init__(win)
        self.win = win
        self.folder = folder or recovery_dir()
        stem = os.path.join(self.folder, f"{os.getpid()}")
        self.png, self.json = stem + ".png", stem + ".json"
        self._dirty = False
        self._thread = None
        win.doc.changed.connect(self._changed)
        win.doc.fileChanged.connect(self._file_changed)
        self.timer = QTimer(self)
        self.timer.setInterval(interval)
        self.timer.timeout.connect(self.save_now)
        self.timer.start()

    def _changed(self):
        self._dirty = True

    def _file_changed(self):
        # saved, opened or new: nothing unsaved any more
        if not self.win.doc.modified:
            self._dirty = False
            self.clear()

    def save_now(self, wait=False):
        """Write the recovery copy if there is something unsaved. Returns True if it wrote."""
        doc = self.win.doc
        if not (self._dirty and doc.modified):
            return False
        if self._thread is not None and self._thread.is_alive():
            return False
        try:
            img = QImage(self.win.canvas.display_image())     # includes a moved selection or new shape
        except Exception:
            img = QImage(doc.image)
        meta = {"pid": os.getpid(), "time": time.time(), "path": doc.path or "", "fmt": doc.fmt,
                "title": doc.title()}
        self._dirty = False
        self._thread = threading.Thread(target=self._write, args=(img, meta), daemon=True)
        self._thread.start()
        if wait:
            self._thread.join()
        return True

    def _write(self, img, meta):
        try:
            os.makedirs(self.folder, exist_ok=True)
            tmp = self.png + ".tmp"
            if not img.save(tmp, "PNG"):
                return
            os.replace(tmp, self.png)
            with open(self.json + ".tmp", "w", encoding="utf-8") as f:
                json.dump(meta, f)
            os.replace(self.json + ".tmp", self.json)
        except OSError:
            pass

    def clear(self):
        if self._thread is not None and self._thread.is_alive():
            self._thread.join()
        discard(self.png, self.json)


def offer_restore(win, folder=None):
    """Ask whether to bring back a picture left by a crashed OpenDraw7. Returns True if restored."""
    found = leftovers(folder)
    if not found:
        return False
    meta, ppath, jpath = found[0]
    when = time.strftime("%x %X", time.localtime(meta.get("time", 0)))
    name = meta.get("title") or "Untitled"
    box = QMessageBox(win)
    box.setWindowTitle("Paint")
    box.setIcon(QMessageBox.Question)
    box.setText(f"Paint closed before \"{name}\" was saved.")
    box.setInformativeText(f"A copy from {when} was kept. Do you want to restore it?")
    restore = box.addButton("Restore", QMessageBox.AcceptRole)
    box.addButton("Discard", QMessageBox.DestructiveRole)
    box.setDefaultButton(restore)
    box.exec()
    if box.clickedButton() is not restore:
        discard(ppath, jpath)
        return False
    img = QImage(ppath)
    if img.isNull():
        discard(ppath, jpath)
        return False
    win.doc.restore(img, meta.get("path") or None, meta.get("fmt") or "png")
    discard(ppath, jpath)
    return True
