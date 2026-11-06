"""Picture model: pixels, undo history, flood fill and file formats."""
import os
import struct
import time
import numpy as np
from PySide6.QtCore import QObject, Signal, Qt, QSize, QRect
from PySide6.QtGui import QImage, QColor, QPainter, QImageReader, QImageWriter

MAX_UNDO = 50
UNDO_BYTES = 600 * 1024 * 1024

VGA16 = [0x000000, 0x800000, 0x008000, 0x808000, 0x000080, 0x800080, 0x008080, 0x808080,
         0xC0C0C0, 0xFF0000, 0x00FF00, 0xFFFF00, 0x0000FF, 0xFF00FF, 0x00FFFF, 0xFFFFFF]

# (key, filter label, extensions)
FORMATS = [
    ("bmp1", "Monochrome Bitmap (*.bmp *.dib)", ["bmp", "dib"]),
    ("bmp4", "16 Color Bitmap (*.bmp *.dib)", ["bmp", "dib"]),
    ("bmp8", "256 Color Bitmap (*.bmp *.dib)", ["bmp", "dib"]),
    ("bmp24", "24-bit Bitmap (*.bmp *.dib)", ["bmp", "dib"]),
    ("jpeg", "JPEG (*.jpg *.jpeg *.jpe *.jfif)", ["jpg", "jpeg", "jpe", "jfif"]),
    ("gif", "GIF (*.gif)", ["gif"]),
    ("tiff", "TIFF (*.tif *.tiff)", ["tif", "tiff"]),
    ("png", "PNG (*.png)", ["png"]),
]
FORMAT_BY_KEY = {k: (label, exts) for k, label, exts in FORMATS}
OPEN_FILTER = ("All Picture Files (*.bmp *.dib *.jpg *.jpeg *.jpe *.jfif *.gif *.tif *.tiff *.png *.ico *.webp);;"
               "Bitmap Files (*.bmp *.dib);;JPEG (*.jpg *.jpeg *.jpe *.jfif);;GIF (*.gif);;"
               "TIFF (*.tif *.tiff);;PNG (*.png);;ICO (*.ico);;All Files (*)")
LOSSY = {"bmp1", "bmp4", "bmp8", "gif"}


def format_for_path(path, default="png"):
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext in ("bmp", "dib"):
        return "bmp24"
    for key, _label, exts in FORMATS:
        if ext in exts:
            return key
    return default


def pixels(img: QImage):
    """Writable (h, w) uint32 view of a 32-bit image (detaches the image)."""
    h, w = img.height(), img.width()
    return np.frombuffer(img.bits(), dtype=np.uint32).reshape(h, img.bytesPerLine() // 4)[:, :w]


def const_pixels(img: QImage):
    h, w = img.height(), img.width()
    return np.frombuffer(img.constBits(), dtype=np.uint32).reshape(h, img.bytesPerLine() // 4)[:, :w]


ALPHA_FMT = QImage.Format_ARGB32_Premultiplied


def has_transparency(img: QImage) -> bool:
    """True if any pixel of img is not fully opaque."""
    if not img.hasAlphaChannel():
        return False
    a = const_pixels(img.convertToFormat(ALPHA_FMT))
    return bool((a < np.uint32(0xFF000000)).any())


def flatten(img: QImage, bg=QColor(255, 255, 255)) -> QImage:
    """Any image -> opaque RGB32, compositing transparency over bg."""
    if img.format() == QImage.Format_RGB32:
        return img
    out = QImage(img.size(), QImage.Format_RGB32)
    out.fill(bg)
    p = QPainter(out)
    p.drawImage(0, 0, img)
    p.end()
    return out


def flood_region(a, x: int, y: int, tolerance: int = 0):
    """Mask of the 4-connected area around (x, y) whose colour (alpha included) is within
    `tolerance` per channel of the colour at (x, y). `a` is an (h, w) uint32 ARGB array."""
    h, w = a.shape
    target = int(a[y, x])
    tch = [(target >> sh) & 0xFF for sh in (24, 16, 8, 0)]
    runs = {}

    def same(row):
        if tolerance == 0:
            return row == np.uint32(target)
        m = None
        for sh, tv in zip((24, 16, 8, 0), tch):
            ok = np.abs(((row >> sh) & 0xFF).astype(np.int16) - tv) <= tolerance
            m = ok if m is None else (m & ok)
        return m

    def row_runs(ry):
        r = runs.get(ry)
        if r is None:
            m = same(a[ry])
            d = np.diff(np.concatenate(([0], m.view(np.int8), [0])))
            starts = np.flatnonzero(d == 1)
            ends = np.flatnonzero(d == -1) - 1
            r = (starts, ends, np.zeros(len(starts), dtype=bool))
            runs[ry] = r
        return r

    starts, ends, seen = row_runs(y)
    i = int(np.searchsorted(starts, x, side="right")) - 1
    seen[i] = True
    stack = [(y, i)]
    while stack:
        ry, ri = stack.pop()
        s, e, _ = runs[ry]
        l, r = int(s[ri]), int(e[ri])
        for ny in (ry - 1, ry + 1):
            if ny < 0 or ny >= h:
                continue
            ns, ne, nseen = row_runs(ny)
            if not len(ns):
                continue
            j0 = int(np.searchsorted(ne, l, side="left"))
            j1 = int(np.searchsorted(ns, r, side="right")) - 1
            for j in range(j0, j1 + 1):
                if not nseen[j]:
                    nseen[j] = True
                    stack.append((ny, j))
    mask = np.zeros((h, w), dtype=bool)
    for ry, (s, e, seen) in runs.items():
        row = mask[ry]
        for j in np.flatnonzero(seen):
            row[int(s[j]):int(e[j]) + 1] = True
    return mask


def flood_fill(img: QImage, x: int, y: int, color: QColor) -> bool:
    """4-connected fill of the area of the clicked colour around (x, y), anti-aliased rim included.

    Colours within FILL_TOLERANCE count as the clicked one, so specks left by rounding on soft
    edges do not survive the next fill."""
    if not (0 <= x < img.width() and 0 <= y < img.height()):
        return False
    new = np.uint32(0xFF000000 | (color.rgb() & 0xFFFFFF))
    a = pixels(img)
    target = a[y, x]
    if target == new:
        return False
    mask = flood_region(a, x, y, FILL_TOLERANCE)
    _fill_soft_edge(a, mask, target, new)
    a[mask] = new
    return True


FILL_TOLERANCE = 3  # per-channel difference still treated as the clicked colour
SNAP = 6            # rim pixels this close to the fill colour become exactly the fill colour
NEAR = 12           # rim pixels this close to the clicked colour are taken over whole
EDGE_REACH = 4      # how far past the filled area anti-aliased edge pixels are looked for
EDGE_SEARCH = 3     # radius of the window searched for the edge's solid colour


def _rgb(v):
    """(..., 4) float array of the premultiplied A, R, G, B channels."""
    v = np.asarray(v, dtype=np.uint32)
    return np.stack([(v >> 24) & 0xFF, (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF],
                    axis=-1).astype(np.float32)


def _fill_soft_edge(a, mask, target, new):
    """Recolour the anti-aliased rim around a filled area.

    Smoothed brush strokes and shape outlines leave pixels that are a blend of the old background
    and the stroke colour. An exact-colour fill stops at them and leaves a pale ring. For each such
    pixel the share of background in it is estimated (by projecting it onto the line between the
    background colour and the nearby solid stroke colour) and exactly that share is swapped for the
    fill colour, so the edge stays smooth and no ring is left. Only pixels next to the fill are
    looked at, so the cost follows the length of the border, not the size of the area.
    """
    h, w = mask.shape
    # pixels just outside the fill: 8-neighbours of filled pixels that are not filled
    edge = np.zeros_like(mask)
    edge[1:, :] |= mask[:-1, :]
    edge[:-1, :] |= mask[1:, :]
    edge[:, 1:] |= mask[:, :-1]
    edge[:, :-1] |= mask[:, 1:]
    edge[1:, 1:] |= mask[:-1, :-1]
    edge[1:, :-1] |= mask[:-1, 1:]
    edge[:-1, 1:] |= mask[1:, :-1]
    edge[:-1, :-1] |= mask[1:, 1:]
    edge &= ~mask
    ey, ex = np.nonzero(edge)
    if not len(ey):
        return
    # every pixel within EDGE_REACH of the fill lies within EDGE_REACH - 1 of an edge pixel
    r = EDGE_REACH - 1
    offs = [(dy, dx) for dy in range(-r, r + 1) for dx in range(-r, r + 1)]
    py = np.concatenate([ey + dy for dy, dx in offs])
    px = np.concatenate([ex + dx for dy, dx in offs])
    keep = (py >= 0) & (py < h) & (px >= 0) & (px < w)
    flat = np.unique(py[keep].astype(np.int64) * w + px[keep])
    py, px = flat // w, flat % w
    keep = ~mask[py, px]
    py, px = py[keep], px[keep]
    if not len(py):
        return

    t = _rgb(target)
    c = _rgb(a[py, px])
    # the solid stroke colour: the colour furthest from the background in the neighbourhood
    best_d = np.full(len(py), -1.0, dtype=np.float32)
    best_c = np.zeros_like(c)
    R = EDGE_SEARCH
    for dy in range(-R, R + 1):
        for dx in range(-R, R + 1):
            qy, qx = py + dy, px + dx
            valid = (qy >= 0) & (qy < h) & (qx >= 0) & (qx < w)
            qc = _rgb(a[np.clip(qy, 0, h - 1), np.clip(qx, 0, w - 1)])
            qd = np.where(valid, ((qc - t) ** 2).sum(axis=-1), -1.0)
            better = qd > best_d
            best_d = np.where(better, qd, best_d)
            best_c = np.where(better[:, None], qc, best_c)

    v = t - best_c                                  # stroke -> background
    L2 = (v ** 2).sum(axis=-1)
    q = c - best_c
    with np.errstate(invalid="ignore", divide="ignore"):
        share = (q * v).sum(axis=-1) / L2           # share of background in the pixel
        resid = np.sqrt(np.maximum((q ** 2).sum(axis=-1) - share ** 2 * L2, 0.0))
    share = np.clip(np.nan_to_num(share), 0.0, 1.0).astype(np.float32)
    L = np.sqrt(L2)
    cand = (L2 >= 24.0 ** 2) & (share > 0.02) & (resid <= 0.12 * L + 6.0)
    # specks only slightly off the clicked colour (overlapping soft strokes, rounding) go whole
    near_t = (np.abs(c - t) <= NEAR).all(axis=-1)
    share = np.where(near_t, 1.0, share).astype(np.float32)
    cand |= near_t

    # grow outwards from the fill one ring at a time, only through pixels that get steadily
    # further from the background, so the rim of a stroke is taken but nothing beyond the stroke
    keys = py * w + px                              # sorted, so neighbours are found by bisection
    level = np.full(len(py), -1.0, dtype=np.float32)
    ok = np.zeros(len(py), dtype=bool)
    nbrs = [(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx]
    for _ in range(EDGE_REACH):
        reach = np.full(len(py), -1.0, dtype=np.float32)
        for dy, dx in nbrs:
            qy, qx = py + dy, px + dx
            valid = (qy >= 0) & (qy < h) & (qx >= 0) & (qx < w)
            qy, qx = np.clip(qy, 0, h - 1), np.clip(qx, 0, w - 1)
            lv = np.where(mask[qy, qx], 1.0, -1.0).astype(np.float32)
            key = qy * w + qx
            pos = np.clip(np.searchsorted(keys, key), 0, len(keys) - 1)
            lv = np.where(keys[pos] == key, np.maximum(lv, level[pos]), lv)
            reach = np.maximum(reach, np.where(valid, lv, -1.0))
        step = cand & ~ok & (reach > 0) & (share <= reach + 0.06)
        if not step.any():
            break
        ok |= step
        level = np.where(step, share, level)
    if not ok.any():
        return
    out = c[ok] + share[ok, None] * (_rgb(new) - t)
    out = np.clip(np.rint(out), 0, 255).astype(np.int32)
    out[:, 1:] = np.minimum(out[:, 1:], out[:, :1])     # stay valid premultiplied ARGB
    nc = _rgb(new).astype(np.int32)
    near_new = (np.abs(out - nc) <= SNAP).all(axis=-1)
    out[near_new] = nc
    out = out.astype(np.uint32)
    a[py[ok], px[ok]] = (out[:, 0] << 24) | (out[:, 1] << 16) | (out[:, 2] << 8) | out[:, 3]


# ------------------------------------------------------------ BMP writing --
def _bmp_bytes(img: QImage, bpp: int) -> bytes:
    w, h = img.width(), img.height()
    palette = b""
    if bpp == 1:
        m = img.convertToFormat(QImage.Format_Mono, Qt.MonoOnly | Qt.ThresholdDither | Qt.AvoidDither)
        table = m.colorTable()
        bpl = m.bytesPerLine()
        rows = np.frombuffer(m.constBits(), np.uint8).reshape(h, bpl)
        data = rows[::-1].tobytes()
        palette = b"".join(struct.pack("<BBBB", c & 255, (c >> 8) & 255, (c >> 16) & 255, 0) for c in table[:2])
        ncol = 2
    elif bpp == 4:
        table = [0xFF000000 | c for c in VGA16]
        m = img.convertToFormat(QImage.Format_Indexed8, table, Qt.ThresholdDither | Qt.AvoidDither)
        bpl = m.bytesPerLine()
        idx = np.frombuffer(m.constBits(), np.uint8).reshape(h, bpl)[:, :w]
        if w % 2:
            idx = np.concatenate([idx, np.zeros((h, 1), np.uint8)], axis=1)
        packed = ((idx[:, 0::2] << 4) | (idx[:, 1::2] & 15)).astype(np.uint8)
        pad = (-packed.shape[1]) % 4
        if pad:
            packed = np.concatenate([packed, np.zeros((h, pad), np.uint8)], axis=1)
        data = packed[::-1].tobytes()
        palette = b"".join(struct.pack("<BBBB", c & 255, (c >> 8) & 255, (c >> 16) & 255, 0) for c in VGA16)
        ncol = 16
    elif bpp == 8:
        m = img.convertToFormat(QImage.Format_Indexed8, Qt.ThresholdDither | Qt.AvoidDither)
        table = list(m.colorTable())
        table += [0] * (256 - len(table))
        bpl = m.bytesPerLine()
        rows = np.frombuffer(m.constBits(), np.uint8).reshape(h, bpl)
        data = rows[::-1].tobytes()
        palette = b"".join(struct.pack("<BBBB", c & 255, (c >> 8) & 255, (c >> 16) & 255, 0) for c in table[:256])
        ncol = 256
    else:
        m = img.convertToFormat(QImage.Format_BGR888)
        bpl = m.bytesPerLine()
        rows = np.frombuffer(m.constBits(), np.uint8).reshape(h, bpl)
        data = rows[::-1].tobytes()
        ncol = 0
    offset = 14 + 40 + len(palette)
    header = struct.pack("<2sIHHI", b"BM", offset + len(data), 0, 0, offset)
    info = struct.pack("<IiiHHIIiiII", 40, w, h, 1, bpp, 0, len(data), 3780, 3780, ncol, ncol)
    return header + info + palette + data


# ------------------------------------------------------------ GIF writing --
def _lzw(data: bytes, min_code=8) -> bytes:
    clear = 1 << min_code
    eoi = clear + 1
    out = bytearray()
    buf = 0
    nbits = 0
    code_size = min_code + 1
    next_code = eoi + 1
    table = {}

    def emit(code):
        nonlocal buf, nbits
        buf |= code << nbits
        nbits += code_size
        while nbits >= 8:
            out.append(buf & 255)
            buf >>= 8
            nbits -= 8

    emit(clear)
    if not data:
        emit(eoi)
    else:
        prefix = data[0]
        get = table.get
        for c in data[1:]:
            key = (prefix << 8) | c
            code = get(key)
            if code is not None:
                prefix = code
                continue
            emit(prefix)
            if next_code < 4096:
                table[key] = next_code
                if next_code == (1 << code_size):
                    code_size += 1
                next_code += 1
            else:
                emit(clear)
                table = {}
                get = table.get
                code_size = min_code + 1
                next_code = eoi + 1
            prefix = c
        emit(prefix)
        emit(eoi)
    if nbits:
        out.append(buf & 255)
    return bytes(out)


def _gif_indexed(img: QImage):
    """(index array h x w, colour table of 256, transparent index or None) for a GIF."""
    w, h = img.width(), img.height()
    clear = None
    if img.hasAlphaChannel():
        a = const_pixels(img.convertToFormat(ALPHA_FMT))
        clear = (a >> 24) < 128
        if not clear.any():
            clear = None
    if clear is None:
        m = img.convertToFormat(QImage.Format_Indexed8, Qt.ThresholdDither | Qt.AvoidDither)
        table = list(m.colorTable())
        idx = np.frombuffer(m.constBits(), np.uint8).reshape(h, m.bytesPerLine())[:, :w].copy()
        return idx, table + [0] * (256 - len(table)), None
    # 255 colours for the picture, index 255 for see-through pixels
    solid = flatten(img)
    m = solid.convertToFormat(QImage.Format_Indexed8, Qt.ThresholdDither | Qt.AvoidDither)
    table = list(m.colorTable())
    idx = np.frombuffer(m.constBits(), np.uint8).reshape(h, m.bytesPerLine())[:, :w].copy()
    if len(table) > 255:
        m = solid.convertToFormat(QImage.Format_Indexed8, table[:255], Qt.ThresholdDither | Qt.AvoidDither)
        table = list(m.colorTable())
        idx = np.frombuffer(m.constBits(), np.uint8).reshape(h, m.bytesPerLine())[:, :w].copy()
    table = table + [0] * (256 - len(table))
    idx[clear] = 255
    return idx, table, 255


def _gif_bytes(img: QImage) -> bytes:
    w, h = img.width(), img.height()
    idx_arr, table, clear = _gif_indexed(img)
    idx = idx_arr.tobytes()
    out = bytearray(b"GIF89a")
    out += struct.pack("<HHBBB", w, h, 0xF7, 0, 0)
    for c in table[:256]:
        out += bytes(((c >> 16) & 255, (c >> 8) & 255, c & 255))
    if clear is not None:
        out += b"\x21\xF9\x04" + struct.pack("<BHB", 0x01, 0, clear) + b"\x00"
    out += b"\x2C" + struct.pack("<HHHHB", 0, 0, w, h, 0)
    out.append(8)
    comp = _lzw(idx, 8)
    for i in range(0, len(comp), 255):
        chunk = comp[i:i + 255]
        out.append(len(chunk))
        out += chunk
    out += b"\x00\x3B"
    return bytes(out)


def reduce_colors(img: QImage, fmt: str) -> QImage:
    """What the picture looks like after a round trip through a lossy format."""
    if fmt != "gif":
        img = flatten(img)
    if fmt == "bmp1":
        m = img.convertToFormat(QImage.Format_Mono, Qt.MonoOnly | Qt.ThresholdDither | Qt.AvoidDither)
    elif fmt == "bmp4":
        m = img.convertToFormat(QImage.Format_Indexed8, [0xFF000000 | c for c in VGA16],
                                Qt.ThresholdDither | Qt.AvoidDither)
    elif fmt == "gif" and has_transparency(img):
        idx, table, clear = _gif_indexed(img)
        lut = np.array([0xFF000000 | (c & 0xFFFFFF) for c in table], dtype=np.uint32)
        lut[clear] = 0
        out = QImage(img.width(), img.height(), ALPHA_FMT)
        pixels(out)[:] = lut[idx]
        return out
    elif fmt in ("bmp8", "gif"):
        m = img.convertToFormat(QImage.Format_Indexed8, Qt.ThresholdDither | Qt.AvoidDither)
    else:
        return img
    return m.convertToFormat(QImage.Format_RGB32)


def save_image(img: QImage, path: str, fmt: str) -> None:
    """Write img to path in the given format key; raises OSError on failure."""
    if fmt in ("bmp1", "bmp4", "bmp8", "bmp24", "jpeg"):
        img = flatten(img)          # these formats cannot keep see-through areas
    if fmt in ("bmp1", "bmp4", "bmp8", "bmp24"):
        data = _bmp_bytes(img, {"bmp1": 1, "bmp4": 4, "bmp8": 8, "bmp24": 24}[fmt])
        with open(path, "wb") as f:
            f.write(data)
        return
    if fmt == "gif":
        with open(path, "wb") as f:
            f.write(_gif_bytes(img))
        return
    qfmt = {"jpeg": "jpeg", "tiff": "tiff", "png": "png"}[fmt]
    w = QImageWriter(path, qfmt.encode())
    if fmt == "jpeg":
        w.setQuality(92)
    elif fmt == "tiff":
        w.setCompression(1)        # LZW
    if fmt == "png":
        out = img
    elif img.hasAlphaChannel():
        out = img.convertToFormat(QImage.Format_ARGB32)
    else:
        out = img.convertToFormat(QImage.Format_RGB888)
    out.setDotsPerMeterX(3780)
    out.setDotsPerMeterY(3780)
    if not w.write(out):
        raise OSError(w.errorString())


def load_image(path: str) -> QImage:
    r = QImageReader(path)
    r.setAutoTransform(True)
    r.setDecideFormatFromContent(True)
    img = r.read()
    if img.isNull():
        raise OSError(r.errorString() or "This is not a valid bitmap file, or its format is not currently supported.")
    if has_transparency(img):
        return img.convertToFormat(ALPHA_FMT)
    return flatten(img.convertToFormat(ALPHA_FMT) if img.hasAlphaChannel() else img.convertToFormat(QImage.Format_RGB32))


class Document(QObject):
    changed = Signal()         # pixels changed
    sizeChanged = Signal()
    historyChanged = Signal()
    fileChanged = Signal()

    def __init__(self, w=800, h=600, parent=None):
        super().__init__(parent)
        self.image = QImage(w, h, QImage.Format_RGB32)
        self.image.fill(QColor(255, 255, 255))
        self.undo_stack = []
        self.redo_stack = []
        self.path = None
        self.fmt = "png"
        self.modified = False
        self.file_size = None
        self.saved_at = None

    # -- basic info --------------------------------------------------------
    def width(self):
        return self.image.width()

    def height(self):
        return self.image.height()

    def size(self):
        return self.image.size()

    def rect(self):
        return self.image.rect()

    def title(self):
        return os.path.basename(self.path) if self.path else "Untitled"

    @property
    def transparent(self):
        """The picture has a see-through background (erasing and deleting clear to transparent)."""
        return self.image.format() == ALPHA_FMT

    def conform(self, img: QImage, bg=QColor(255, 255, 255)) -> QImage:
        """img in the picture's pixel format: kept see-through if the picture is, else flattened."""
        if self.transparent:
            return img if img.format() == ALPHA_FMT else img.convertToFormat(ALPHA_FMT)
        return flatten(img, bg)

    def blank(self, w, h, bg: QColor) -> QImage:
        """A new empty image in the picture's format: transparent, or filled with bg."""
        img = QImage(w, h, ALPHA_FMT if self.transparent else QImage.Format_RGB32)
        img.fill(0 if self.transparent else bg)
        return img

    def set_transparent(self, on: bool, bg=QColor(255, 255, 255)):
        """Switch the see-through background on or off (undoable)."""
        if bool(on) == self.transparent:
            return
        self.push_undo()
        old = self.image.size()
        self.image = self.image.convertToFormat(ALPHA_FMT) if on else flatten(self.image, bg)
        self._emit(old)

    # -- history -----------------------------------------------------------
    def push_undo(self):
        self.undo_stack.append(QImage(self.image))
        self._trim()
        self.redo_stack.clear()
        self.modified = True
        self.historyChanged.emit()

    def _trim(self):
        while len(self.undo_stack) > MAX_UNDO:
            self.undo_stack.pop(0)
        total = sum(i.sizeInBytes() for i in self.undo_stack)
        while total > UNDO_BYTES and len(self.undo_stack) > 3:
            total -= self.undo_stack.pop(0).sizeInBytes()

    def drop_last_undo(self):
        """Abandon the operation started by the last push_undo()."""
        if self.undo_stack:
            old = self.image.size()
            self.image = self.undo_stack.pop()
            self.historyChanged.emit()
            self._emit(old)

    def can_undo(self):
        return bool(self.undo_stack)

    def can_redo(self):
        return bool(self.redo_stack)

    def undo(self):
        if not self.undo_stack:
            return
        old = self.image.size()
        self.redo_stack.append(QImage(self.image))
        self.image = self.undo_stack.pop()
        self.modified = True
        self.historyChanged.emit()
        self._emit(old)

    def redo(self):
        if not self.redo_stack:
            return
        old = self.image.size()
        self.undo_stack.append(QImage(self.image))
        self.image = self.redo_stack.pop()
        self.modified = True
        self.historyChanged.emit()
        self._emit(old)

    def _emit(self, old_size=None):
        if old_size is not None and old_size != self.image.size():
            self.sizeChanged.emit()
        self.changed.emit()

    def set_image(self, img: QImage, bg=QColor(255, 255, 255)):
        """Replace pixels (caller has already pushed undo), keeping the picture's format."""
        old = self.image.size()
        self.image = self.conform(img, bg)
        self._emit(old)

    def resize_canvas(self, w, h, bg: QColor):
        w, h = max(1, int(w)), max(1, int(h))
        if w == self.width() and h == self.height():
            return
        self.push_undo()
        img = self.blank(w, h, bg)
        p = QPainter(img)
        p.drawImage(0, 0, self.image)
        p.end()
        self.set_image(img)

    # -- files -------------------------------------------------------------
    def new(self, w, h):
        self.image = QImage(w, h, QImage.Format_RGB32)
        self.image.fill(QColor(255, 255, 255))
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.path = None
        self.fmt = "png"
        self.modified = False
        self.file_size = None
        self.saved_at = None
        self.historyChanged.emit()
        self.sizeChanged.emit()
        self.changed.emit()
        self.fileChanged.emit()

    def load(self, path):
        img = load_image(path)
        self.image = img
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.path = os.path.abspath(path)
        self.fmt = format_for_path(path)
        self.modified = False
        self._stat()
        self.historyChanged.emit()
        self.sizeChanged.emit()
        self.changed.emit()
        self.fileChanged.emit()

    def restore(self, img: QImage, path, fmt):
        """Bring back a picture from a recovery copy: unsaved, tied to its original file if any."""
        self.image = img.convertToFormat(ALPHA_FMT) if has_transparency(img) else flatten(img)
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.path = os.path.abspath(path) if path else None
        self.fmt = fmt if fmt in FORMAT_BY_KEY else "png"
        self.modified = True
        self.file_size = None
        self.saved_at = None
        if self.path and os.path.exists(self.path):
            self._stat()
        self.historyChanged.emit()
        self.sizeChanged.emit()
        self.changed.emit()
        self.fileChanged.emit()

    def save(self, path, fmt):
        save_image(self.image, path, fmt)
        if fmt in LOSSY:
            reduced = reduce_colors(self.image, fmt)
            self.image = reduced
            self.changed.emit()
        self.path = os.path.abspath(path)
        self.fmt = fmt
        self.modified = False
        self._stat()
        self.fileChanged.emit()

    def _stat(self):
        try:
            st = os.stat(self.path)
            self.file_size = st.st_size
            self.saved_at = st.st_mtime
        except OSError:
            self.file_size = None
            self.saved_at = time.time()
