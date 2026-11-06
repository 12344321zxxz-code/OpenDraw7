"""Picture model: pixels, undo history, flood fill and file formats."""
import os
import struct
import time
import numpy as np
from PySide6.QtCore import QObject, Signal, Qt, QSize, QRect
from PySide6.QtGui import QImage, QColor, QPainter, QImageReader, QImageWriter

MAX_UNDO = 50
UNDO_BYTES = 600 * 1024 * 1024
MAX_SIDE = 25000                  # largest width or height a picture may get from an edit
MAX_PIXELS = 120_000_000          # about 480 MB per copy; undo keeps a few more
TOO_BIG = (f"The picture would be too large. Paint can work with pictures up to {MAX_SIDE:,} pixels "
           f"wide or high and {MAX_PIXELS // 1_000_000} million pixels in all.")


def fits(w, h) -> bool:
    """True if a w x h picture is within the size Paint will make by editing."""
    return 1 <= w <= MAX_SIDE and 1 <= h <= MAX_SIDE and w * h <= MAX_PIXELS

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
    ("ora", "OpenRaster - keeps layers (*.ora)", ["ora"]),
]
FORMAT_BY_KEY = {k: (label, exts) for k, label, exts in FORMATS}
OPEN_FILTER = ("All Picture Files (*.bmp *.dib *.jpg *.jpeg *.jpe *.jfif *.gif *.tif *.tiff *.png *.ico *.webp *.ora);;"
               "Bitmap Files (*.bmp *.dib);;JPEG (*.jpg *.jpeg *.jpe *.jfif);;GIF (*.gif);;"
               "TIFF (*.tif *.tiff);;PNG (*.png);;OpenRaster (*.ora);;ICO (*.ico);;All Files (*)")
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
    if fmt == "ora":
        save_ora([Layer(img)], path)
        return
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
    """One picture from a file; a layered OpenRaster file comes back merged."""
    if format_for_path(path, "") == "ora":
        img = blend_layers(load_ora(path))
        return img if has_transparency(img) else flatten(img)
    if QImageReader.allocationLimit() < 1024:
        QImageReader.setAllocationLimit(1024)     # Qt refuses images over 256 MB by default
    r = QImageReader(path)
    r.setAutoTransform(True)
    r.setDecideFormatFromContent(True)
    img = r.read()
    if img.isNull():
        raise OSError(r.errorString() or "This is not a valid bitmap file, or its format is not currently supported.")
    if has_transparency(img):
        return img.convertToFormat(ALPHA_FMT)
    return flatten(img.convertToFormat(ALPHA_FMT) if img.hasAlphaChannel() else img.convertToFormat(QImage.Format_RGB32))


class Layer:
    """One layer: its pixels, name, visibility and opacity (0..1)."""
    __slots__ = ("image", "name", "visible", "opacity")

    def __init__(self, image: QImage, name="Background", visible=True, opacity=1.0):
        self.image = image
        self.name = name
        self.visible = visible
        self.opacity = opacity

    def copy(self):
        # QImage copies share their pixels until one of them is painted on
        return Layer(QImage(self.image), self.name, self.visible, self.opacity)


class _State:
    """Everything undo restores: every layer and which one is active."""
    __slots__ = ("layers", "active")

    def __init__(self, layers, active):
        self.layers = [ly.copy() for ly in layers]
        self.active = active

    def nbytes(self):
        return sum(ly.image.sizeInBytes() for ly in self.layers)


class Document(QObject):
    """The picture: a stack of layers (bottom first). `image` is the active layer's pixels, so every
    tool draws on the active layer. A picture with one layer behaves exactly like a plain picture."""
    changed = Signal()         # pixels changed
    sizeChanged = Signal()
    historyChanged = Signal()
    fileChanged = Signal()
    layersChanged = Signal()   # layers added, removed, reordered, renamed, shown/hidden, or active changed

    def __init__(self, w=800, h=600, parent=None):
        super().__init__(parent)
        img = QImage(w, h, QImage.Format_RGB32)
        img.fill(QColor(255, 255, 255))
        self.layers = [Layer(img)]
        self.active = 0
        self.undo_stack = []
        self.redo_stack = []
        self.path = None
        self.fmt = "png"
        self.modified = False
        self.file_size = None
        self.saved_at = None
        self._layer_no = 1

    # -- the active layer's pixels --------------------------------------------
    @property
    def image(self) -> QImage:
        return self.layers[self.active].image

    @image.setter
    def image(self, img: QImage):
        self.layers[self.active].image = img

    @property
    def layer(self) -> Layer:
        return self.layers[self.active]

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
        """The active layer is see-through: erasing and deleting on it clear to transparent.
        (Always true for layers above the background.)"""
        return self.image.format() == ALPHA_FMT

    @property
    def background_transparent(self):
        """The bottom layer has a see-through background (Image Properties)."""
        return self.layers[0].image.format() == ALPHA_FMT

    def single(self):
        """Only one layer, fully shown: the picture is just that layer."""
        ly = self.layers[0]
        return len(self.layers) == 1 and ly.visible and ly.opacity >= 1.0

    def conform(self, img: QImage, bg=QColor(255, 255, 255)) -> QImage:
        """img in the active layer's pixel format: kept see-through if the layer is, else flattened."""
        return self._conform_to(self.image, img, bg)

    @staticmethod
    def _conform_to(model: QImage, img: QImage, bg):
        if model.format() == ALPHA_FMT:
            return img if img.format() == ALPHA_FMT else img.convertToFormat(ALPHA_FMT)
        return flatten(img, bg)

    def blank(self, w, h, bg: QColor, like: QImage = None) -> QImage:
        """A new empty image in the format of `like` (default: the active layer): transparent,
        or filled with bg."""
        clear = (like if like is not None else self.image).format() == ALPHA_FMT
        img = QImage(w, h, ALPHA_FMT if clear else QImage.Format_RGB32)
        img.fill(0 if clear else bg)
        return img

    def set_transparent(self, on: bool, bg=QColor(255, 255, 255)):
        """Switch the see-through background (bottom layer) on or off (undoable)."""
        if bool(on) == self.background_transparent:
            return
        self.push_undo()
        old = self.size()
        base = self.layers[0]
        base.image = base.image.convertToFormat(ALPHA_FMT) if on else flatten(base.image, bg)
        self._emit(old)

    # -- composite ---------------------------------------------------------------
    def composite(self, active_image: QImage = None, upto=None) -> QImage:
        """The visible layers blended together, bottom first. active_image stands in for the active
        layer (a tool's preview); upto stops before that layer index."""
        layers = self.layers if upto is None else self.layers[:upto]
        if active_image is None and self.single():
            return self.image
        w, h = self.width(), self.height()
        out = QImage(w, h, ALPHA_FMT)
        out.fill(0)
        p = QPainter(out)
        for i, ly in enumerate(layers):
            if not ly.visible or ly.opacity <= 0:
                continue
            p.setOpacity(ly.opacity)
            p.drawImage(0, 0, active_image if (i == self.active and active_image is not None) else ly.image)
        p.end()
        return out

    def flattened(self) -> QImage:
        """What the picture looks like, for saving to a one-layer format, printing or copying."""
        if self.single():
            return self.image
        img = self.composite()
        return img if has_transparency(img) else flatten(img)

    # -- history -----------------------------------------------------------
    def _state(self):
        return _State(self.layers, self.active)

    def _restore(self, st: _State):
        old = self.size()
        self.layers = [ly.copy() for ly in st.layers]
        self.active = min(st.active, len(self.layers) - 1)
        self._emit(old)
        self.layersChanged.emit()

    def push_undo(self):
        self.undo_stack.append(self._state())
        self._trim()
        self.redo_stack.clear()
        self.modified = True
        self.historyChanged.emit()

    def _trim(self):
        while len(self.undo_stack) > MAX_UNDO:
            self.undo_stack.pop(0)
        total = sum(s.nbytes() for s in self.undo_stack)
        while total > UNDO_BYTES and len(self.undo_stack) > 3:
            total -= self.undo_stack.pop(0).nbytes()

    def drop_last_undo(self):
        """Abandon the operation started by the last push_undo()."""
        if self.undo_stack:
            st = self.undo_stack.pop()
            self.historyChanged.emit()
            self._restore(st)

    def can_undo(self):
        return bool(self.undo_stack)

    def can_redo(self):
        return bool(self.redo_stack)

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(self._state())
        st = self.undo_stack.pop()
        self.modified = True
        self.historyChanged.emit()
        self._restore(st)

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(self._state())
        st = self.redo_stack.pop()
        self.modified = True
        self.historyChanged.emit()
        self._restore(st)

    def _emit(self, old_size=None):
        if old_size is not None and old_size != self.size():
            self.sizeChanged.emit()
        self.changed.emit()

    def set_image(self, img: QImage, bg=QColor(255, 255, 255)):
        """Replace the active layer's pixels (caller has already pushed undo), keeping its format.
        If the size changes, the other layers are cropped or grown to match."""
        old = self.size()
        self.image = self.conform(img, bg)
        if self.image.size() != old:
            for i, ly in enumerate(self.layers):
                if i != self.active:
                    ly.image = self._sized(ly.image, self.image.width(), self.image.height(), bg)
        self._emit(old)

    def _sized(self, img, w, h, bg, ox=0, oy=0):
        """img on a w x h canvas of its own format, its top-left at (-ox, -oy)."""
        out = self.blank(w, h, bg, like=img)
        p = QPainter(out)
        p.drawImage(-ox, -oy, img)
        p.end()
        return out

    def resize_canvas(self, w, h, bg: QColor):
        """Make the canvas w x h. Returns False (and changes nothing) if that is too large."""
        w, h = max(1, int(w)), max(1, int(h))
        if w == self.width() and h == self.height():
            return True
        if not fits(w, h):
            return False
        self.push_undo()
        self.grow(w, h, bg)
        return True

    def grow(self, w, h, bg: QColor):
        """Resize every layer's canvas to w x h (no undo step of its own)."""
        old = self.size()
        for ly in self.layers:
            ly.image = self._sized(ly.image, w, h, bg)
        self._emit(old)

    def crop_all(self, rect: QRect, bg: QColor):
        """Cut every layer down to rect (no undo step of its own)."""
        old = self.size()
        for ly in self.layers:
            ly.image = self._sized(ly.image, rect.width(), rect.height(), bg, rect.left(), rect.top())
        self._emit(old)

    def transform_all(self, fn, bg: QColor):
        """Apply fn(QImage) -> QImage to every layer (rotate, flip, resize, skew); one undo step."""
        self.push_undo()
        old = self.size()
        for ly in self.layers:
            ly.image = self._conform_to(ly.image, fn(ly.image), bg)
        self._emit(old)

    # -- layers ------------------------------------------------------------------
    def _new_name(self):
        names = {ly.name for ly in self.layers}
        while True:
            self._layer_no += 1
            name = f"Layer {self._layer_no}"
            if name not in names:
                return name

    def _fix_formats(self):
        """Only the bottom layer may be opaque; anything above it is see-through."""
        for ly in self.layers[1:]:
            if ly.image.format() != ALPHA_FMT:
                ly.image = ly.image.convertToFormat(ALPHA_FMT)

    def _layers_done(self, old=None):
        self._fix_formats()
        self._emit(old or self.size())
        self.layersChanged.emit()

    def set_active(self, i):
        i = max(0, min(len(self.layers) - 1, int(i)))
        if i != self.active:
            self.active = i
            self.layersChanged.emit()

    def add_layer(self):
        """A new see-through layer above the active one, which becomes active."""
        self.push_undo()
        img = QImage(self.width(), self.height(), ALPHA_FMT)
        img.fill(0)
        self.layers.insert(self.active + 1, Layer(img, self._new_name()))
        self.active += 1
        self._layers_done()

    def duplicate_layer(self):
        self.push_undo()
        src = self.layer.copy()
        src.name = f"{self.layer.name} copy"
        self.layers.insert(self.active + 1, src)
        self.active += 1
        self._layers_done()

    def delete_layer(self):
        if len(self.layers) <= 1:
            return False
        self.push_undo()
        del self.layers[self.active]
        self.active = max(0, self.active - 1)
        self._layers_done()
        return True

    def move_layer(self, d):
        j = self.active + d
        if not (0 <= j < len(self.layers)):
            return False
        self.push_undo()
        ls = self.layers
        ls[self.active], ls[j] = ls[j], ls[self.active]
        self.active = j
        self._layers_done()
        return True

    def merge_down(self):
        """Blend the active layer into the one below it."""
        if self.active == 0:
            return False
        self.push_undo()
        top, below = self.layers[self.active], self.layers[self.active - 1]
        if top.visible:
            img = QImage(below.image)
            p = QPainter(img)
            p.setOpacity(top.opacity)
            p.drawImage(0, 0, top.image)
            p.end()
            below.image = img
        del self.layers[self.active]
        self.active -= 1
        self._layers_done()
        return True

    def flatten_layers(self, bg=QColor(255, 255, 255)):
        """Merge every visible layer into one background layer."""
        if len(self.layers) == 1:
            return False
        self.push_undo()
        img = self.composite()
        if not self.background_transparent:
            img = flatten(img, bg)
        self.layers = [Layer(img, self.layers[0].name)]
        self.active = 0
        self._layers_done()
        return True

    def set_layer_props(self, i, name=None, visible=None, opacity=None, undo=True):
        ly = self.layers[i]
        new = (ly.name if name is None else name, ly.visible if visible is None else bool(visible),
               ly.opacity if opacity is None else max(0.0, min(1.0, float(opacity))))
        if new == (ly.name, ly.visible, ly.opacity):
            return
        if undo:
            self.push_undo()
            ly = self.layers[i]
        ly.name, ly.visible, ly.opacity = new
        self.changed.emit()
        self.layersChanged.emit()

    def set_layers(self, layers, active=None):
        """Replace the whole stack (opening a layered file)."""
        old = self.size()
        self.layers = layers
        self.active = len(layers) - 1 if active is None else active
        self._layer_no = len(layers)
        self._layers_done(old)

    # -- files -------------------------------------------------------------
    def _reset(self, layers):
        self.layers = layers
        self.active = len(layers) - 1
        self._layer_no = len(layers)
        self._fix_formats()
        self.undo_stack.clear()
        self.redo_stack.clear()

    def new(self, w, h):
        img = QImage(w, h, QImage.Format_RGB32)
        img.fill(QColor(255, 255, 255))
        self._reset([Layer(img)])
        self.path = None
        self.fmt = "png"
        self.modified = False
        self.file_size = None
        self.saved_at = None
        self.historyChanged.emit()
        self.sizeChanged.emit()
        self.changed.emit()
        self.layersChanged.emit()
        self.fileChanged.emit()

    def load(self, path):
        if format_for_path(path, "") == "ora":
            layers = load_ora(path)
        else:
            layers = [Layer(load_image(path))]
        self._reset(layers)
        self.path = os.path.abspath(path)
        self.fmt = format_for_path(path)
        self.modified = False
        self._stat()
        self.historyChanged.emit()
        self.sizeChanged.emit()
        self.changed.emit()
        self.layersChanged.emit()
        self.fileChanged.emit()

    def restore(self, img, path, fmt):
        """Bring back a picture from a recovery copy: unsaved, tied to its original file if any.
        img is a QImage or a list of Layers."""
        if isinstance(img, list):
            layers = img
        else:
            layers = [Layer(img.convertToFormat(ALPHA_FMT) if has_transparency(img) else flatten(img))]
        self._reset(layers)
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
        self.layersChanged.emit()
        self.fileChanged.emit()

    def save(self, path, fmt):
        if fmt == "ora":
            save_ora(self.layers, path)
        else:
            save_image(self.flattened(), path, fmt)
            if fmt in LOSSY and self.single():
                self.image = reduce_colors(self.image, fmt)
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


# ------------------------------------------------------------ OpenRaster --
ORA_MIME = b"image/openraster"


def _png_bytes(img: QImage) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba.data())


def blend_layers(layers) -> QImage:
    """The visible layers (bottom first) blended into one image."""
    base = layers[0]
    if len(layers) == 1 and base.visible and base.opacity >= 1.0:
        return base.image
    out = QImage(base.image.width(), base.image.height(), ALPHA_FMT)
    out.fill(0)
    p = QPainter(out)
    for ly in layers:
        if ly.visible and ly.opacity > 0:
            p.setOpacity(ly.opacity)
            p.drawImage(0, 0, ly.image)
    p.end()
    return out


def save_ora(layers, path, merged=None):
    """Write layers (bottom first) as an OpenRaster file (GIMP, Krita and MyPaint open it).
    Safe to call from a worker thread."""
    import zipfile
    from xml.sax.saxutils import quoteattr
    w, h = layers[0].image.width(), layers[0].image.height()
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("mimetype"), ORA_MIME, compress_type=zipfile.ZIP_STORED)
        entries = []
        for i, ly in enumerate(layers):
            src = f"data/layer{i}.png"
            z.writestr(src, _png_bytes(ly.image))
            entries.append(f'<layer name={quoteattr(ly.name)} src="{src}" x="0" y="0" '
                           f'opacity="{ly.opacity:.3f}" visibility="{"visible" if ly.visible else "hidden"}"/>')
        xml = (f'<?xml version="1.0" encoding="UTF-8"?>\n<image version="0.0.3" w="{w}" h="{h}" '
               f'xres="96" yres="96"><stack>' + "".join(reversed(entries)) + "</stack></image>")
        z.writestr("stack.xml", xml.encode("utf-8"))
        if merged is None:
            merged = blend_layers(layers)
        z.writestr("mergedimage.png", _png_bytes(merged))
        z.writestr("Thumbnails/thumbnail.png",
                   _png_bytes(merged.scaled(256, 256, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
    os.replace(tmp, path)


def load_ora(path):
    """Layers (bottom first) from an OpenRaster file."""
    import zipfile
    import xml.etree.ElementTree as ET
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as ex:
        raise OSError(f"This is not a valid OpenRaster file ({ex}).")
    with z:
        root = ET.fromstring(z.read("stack.xml"))
        w, h = int(root.get("w")), int(root.get("h"))
        out = []

        def walk(stack, ox=0, oy=0):
            for el in stack:                       # top first in the file
                x = ox + int(float(el.get("x", 0) or 0))
                y = oy + int(float(el.get("y", 0) or 0))
                if el.tag == "stack":
                    walk(el, x, y)
                elif el.tag == "layer" and el.get("src"):
                    img = QImage.fromData(z.read(el.get("src")))
                    if img.isNull():
                        continue
                    canvas = QImage(w, h, ALPHA_FMT)
                    canvas.fill(0)
                    p = QPainter(canvas)
                    p.drawImage(x, y, img)
                    p.end()
                    out.append(Layer(canvas, el.get("name") or f"Layer {len(out) + 1}",
                                     el.get("visibility", "visible") != "hidden",
                                     max(0.0, min(1.0, float(el.get("opacity", 1) or 1)))))
        walk(root.find("stack"))
    if not out:
        raise OSError("The OpenRaster file has no layers.")
    out.reverse()                                  # bottom first
    base = out[0]
    if not has_transparency(base.image):
        base.image = flatten(base.image)
    return out
