"""Object selection: click a character or object to select all of it, without the background.

Classic image processing, in the spirit of "Select Subject"/Object Selection tools and GIMP's
Foreground Select, tuned for drawings (outlines, flat colours) but also coping with gradients:

1. Background model: the colours along the picture's edges, grouped into a few clusters
   (see-through pixels count as one more colour, so transparent layers work).
2. Background growth: starting from the edges, the background spreads through pixels that look like
   background - close to a background colour, or smooth and fairly close (gradients such as a sky) -
   and never across an outline (a strong local edge).
3. Object: everything that is not background and is connected to the clicked pixel, so enclosed
   details (eyes, a white shirt, the gap inside a letter O) come along. Clicking the background
   selects every object.
4. Soft edge: anti-aliased rim pixels get a partial opacity, estimated by projecting each pixel onto
   the line between the nearby background colour and the nearby object colour, and the
   background's tint is removed from them ("decontaminate colours"), so a moved or copied object
   carries no fringe of the old background.
"""
import numpy as np

BG_NEAR = 26.0          # this close (RGBA distance, 0-510) to a background colour: background
STEP = 14.0             # neighbours differing by at most this much (per channel) are one smooth area
REACH = 22.0            # background may spread this far beyond the spread of an edge colour
MIN_SPECK = 12          # isolated object pieces smaller than this are noise when selecting everything
RIM = 2                 # rim width (pixels) given soft opacity


def _channels(a):
    """(h, w, 4) float32 of premultiplied A, R, G, B."""
    return np.stack([(a >> 24) & 0xFF, (a >> 16) & 0xFF, (a >> 8) & 0xFF, a & 0xFF], axis=-1).astype(np.float32)


def _runs(row):
    d = np.diff(np.concatenate(([0], row.view(np.int8), [0])))
    return np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1


def grow(mask, seeds, diagonal=False):
    """Pixels of `mask` connected (4-, or 8- with diagonal) to any pixel of `seeds`."""
    h, w = mask.shape
    runs = [_runs(mask[y]) for y in range(h)]
    seen = [np.zeros(len(r[0]), dtype=bool) for r in runs]
    stack = []
    for y in range(h):
        s, e = runs[y]
        if not len(s):
            continue
        srow = seeds[y] & mask[y]
        if not srow.any():
            continue
        cs = np.concatenate(([0], np.cumsum(srow)))
        hit = cs[e + 1] - cs[s] > 0
        for j in np.flatnonzero(hit):
            seen[y][j] = True
            stack.append((y, j))
    pad = 1 if diagonal else 0
    while stack:
        y, j = stack.pop()
        l, r = int(runs[y][0][j]) - pad, int(runs[y][1][j]) + pad
        for ny in (y - 1, y + 1):
            if ny < 0 or ny >= h:
                continue
            ns, ne = runs[ny]
            if not len(ns):
                continue
            j0 = int(np.searchsorted(ne, l, side="left"))
            j1 = int(np.searchsorted(ns, r, side="right")) - 1
            nseen = seen[ny]
            for k in range(j0, j1 + 1):
                if not nseen[k]:
                    nseen[k] = True
                    stack.append((ny, k))
    out = np.zeros((h, w), dtype=bool)
    for y in range(h):
        s, e = runs[y]
        for j in np.flatnonzero(seen[y]):
            out[y, s[j]:e[j] + 1] = True
    return out


def _border(h, w):
    b = np.zeros((h, w), dtype=bool)
    b[0, :] = b[-1, :] = b[:, 0] = b[:, -1] = True
    return b


def _clusters(colors, k_max=8, merge=24.0):
    """A few representative colours of an (n, 4) array: greedy, then refined by a few k-means steps."""
    if len(colors) > 4000:
        colors = colors[np.linspace(0, len(colors) - 1, 4000).astype(int)]
    centers = []
    rest = colors
    for _ in range(k_max):
        if not len(rest):
            break
        # the most common colour left (by coarse bins) seeds the next cluster
        q = (rest // 16).astype(np.int64)
        key = ((q[:, 0] * 16 + q[:, 1]) * 16 + q[:, 2]) * 16 + q[:, 3]
        vals, counts = np.unique(key, return_counts=True)
        if counts.max() < max(3, 0.02 * len(colors)):
            break
        pick = rest[key == vals[counts.argmax()]].mean(axis=0)
        centers.append(pick)
        d = np.sqrt(((rest - pick) ** 2).sum(axis=1))
        rest = rest[d > merge * 1.5]
    if not centers:
        centers = [colors.mean(axis=0)]
    c = np.array(centers, dtype=np.float32)
    for _ in range(4):
        d = ((colors[:, None, :] - c[None, :, :]) ** 2).sum(axis=2)
        lab = d.argmin(axis=1)
        for i in range(len(c)):
            sel = colors[lab == i]
            if len(sel):
                c[i] = sel.mean(axis=0)
    return c


def _bytes(a):
    """Zero-copy (h, w, 4) uint8 view of a uint32 ARGB array, channels in memory order B, G, R, A."""
    return np.ascontiguousarray(a).view(np.uint8).reshape(a.shape[0], a.shape[1], 4)


def _absdiff_max(x, y):
    """Largest per-channel difference of two (..., 4) uint8 arrays, without widening them."""
    return (np.maximum(x, y) - np.minimum(x, y)).max(axis=-1)


def noise_level(b):
    """Typical colour difference between horizontal neighbours (median of a sample): about 0 for
    drawings, a few steps for photos."""
    h, w = b.shape[:2]
    if w < 2:
        return 0.0
    rows = b[:: max(1, h // 200)]
    d = _absdiff_max(rows[:, 1:], rows[:, :-1])
    return float(np.median(d))


def _box_blur(b, r):
    """(2r+1)^2 box blur of a (h, w, 4) uint8 array, via running sums."""
    x = b.astype(np.int32)
    k = 2 * r + 1
    for axis in (0, 1):
        pad = [(0, 0)] * 3
        pad[axis] = (r + 1, r)
        cs = np.cumsum(np.pad(x, pad, mode="edge"), axis=axis)
        hi = [slice(None)] * 3
        lo = [slice(None)] * 3
        n = x.shape[axis]
        hi[axis] = slice(k, k + n)
        lo[axis] = slice(0, n)
        x = cs[tuple(hi)] - cs[tuple(lo)]
    return np.clip((x + (k * k) // 2) // (k * k), 0, 255).astype(np.uint8)


def _border_loop(a):
    """Edge pixels in order around the picture (top, right, bottom, left)."""
    h, w = a.shape
    if h == 1 or w == 1:
        return a.reshape(-1)
    return np.concatenate((a[0, :], a[1:, -1], a[-1, -2::-1], a[-2:0:-1, 0]))


def edge_colours(a):
    """(n, 4) float array of the background colours along the picture's edges. Only long stretches
    of the edge count, so a character cut off by the edge does not teach its colour as background."""
    loop = _border_loop(a)
    ch = _channels(loop.reshape(1, -1))[0]
    n = len(ch)
    step = np.abs(np.diff(np.concatenate((ch, ch[:1])), axis=0)).max(axis=1)   # i -> i+1 (wraps)
    cut = np.flatnonzero(step > 2 * STEP)
    keep = np.zeros(n, dtype=bool)
    if not len(cut):
        keep[:] = True
    else:
        min_len = max(16, int(0.05 * n))
        for k in range(len(cut)):
            s0 = cut[k] + 1
            s1 = cut[(k + 1) % len(cut)]
            length = (s1 - s0) % n + 1
            if length >= min_len:
                idx = (s0 + np.arange(length)) % n
                keep[idx] = True
    if not keep.any():
        keep[:] = True
    pts = ch[keep]
    centers = _clusters(pts)
    # how far the edge colours of each group spread (gradients spread a lot, flat colours not)
    dist = np.sqrt(((pts[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2))
    lab = dist.argmin(axis=1)
    radii = np.array([np.percentile(dist[lab == i, i], 95) if (lab == i).any() else 0.0
                      for i in range(len(centers))], dtype=np.float32)
    return centers, radii


def background(a):
    """Bool mask of the background of a uint32 premultiplied-ARGB picture, grown in from its edges.

    The background spreads between two neighbouring pixels when their colours differ by only a
    small step (gradients, noise), or when both look like background (close to an edge colour, or on
    an edge between two background colours, like a horizon). An outline next to the background is a
    big jump to a colour that is not background, so it stops the growth."""
    h, w = a.shape
    b = _bytes(a)
    noise = noise_level(b)
    if noise >= 2:
        # photos: decide on a lightly smoothed copy so texture (grass, fabric, grain) does not
        # break the background into fragments; clean drawings are left exact
        b = _box_blur(b, 2 if noise >= 6 else 1)
    small = STEP + 2.5 * noise
    centers, radii = edge_colours(a)                # rows of A, R, G, B
    # per edge colour: squared distance by per-channel lookup tables
    v = np.arange(256, dtype=np.int32)
    near = np.zeros((h, w), dtype=bool)
    reach = np.zeros((h, w), dtype=bool)
    for k, rad in zip(centers, radii):
        ka, kr, kg, kb = (int(round(float(x))) for x in k)
        dd = ((v - kb) ** 2)[b[..., 0]] + ((v - kg) ** 2)[b[..., 1]] + ((v - kr) ** 2)[b[..., 2]] \
            + ((v - ka) ** 2)[b[..., 3]]
        near |= dd <= int(BG_NEAR ** 2)
        reach |= dd <= int((rad + REACH) ** 2)
    reach |= near
    bgish = near
    right = ((_absdiff_max(b[:, 1:], b[:, :-1]) <= small) & reach[:, 1:] & reach[:, :-1]) \
        | (bgish[:, 1:] & bgish[:, :-1])
    down = ((_absdiff_max(b[1:], b[:-1]) <= small) & reach[1:] & reach[:-1]) | (bgish[1:] & bgish[:-1])
    # A pixel that is a blend of the background-like colours on its two sides (the soft edge of a
    # horizon or a cloud) is a transition between backgrounds: the background may cross it. An
    # outline is never a blend of what is on its two sides, so it still stops the growth.
    bridge = _blends(b, reach) & ~reach
    if bridge.any():
        ok = reach | bridge
        right |= ((bridge[:, 1:] | bridge[:, :-1]) & ok[:, 1:] & ok[:, :-1])
        down |= ((bridge[1:] | bridge[:-1]) & ok[1:] & ok[:-1])
    seeds = _border(h, w) & bgish
    if not seeds.any():
        return np.zeros((h, w), dtype=bool)
    return grow_edges(right, down, seeds)


def _blends(b, bg):
    """Pixels whose colour lies (nearly) on the line between their two opposite neighbours (at 1 or
    2 pixels), both of them in `bg` (background-like)."""
    h, w = bg.shape
    out = np.zeros((h, w), dtype=bool)
    for axis in (0, 1):
        n = h if axis == 0 else w
        for k in (1, 2):
            if n <= 2 * k:
                continue
            if axis == 0:
                both = bg[:-2 * k] & bg[2 * k:] & ~bg[k:-k]
                ys, xs = np.nonzero(both)
                p0, p1, q = b[ys, xs], b[ys + 2 * k, xs], b[ys + k, xs]
                ty, tx = ys + k, xs
            else:
                both = bg[:, :-2 * k] & bg[:, 2 * k:] & ~bg[:, k:-k]
                ys, xs = np.nonzero(both)
                p0, p1, q = b[ys, xs], b[ys, xs + 2 * k], b[ys, xs + k]
                ty, tx = ys, xs + k
            if not len(ys):
                continue
            p0, p1, q = p0.astype(np.float32), p1.astype(np.float32), q.astype(np.float32)
            v = p1 - p0
            L2 = (v ** 2).sum(axis=1)
            ok = L2 > (2 * STEP) ** 2            # the two sides really differ
            with np.errstate(invalid="ignore", divide="ignore"):
                t = np.clip(np.nan_to_num(((q - p0) * v).sum(axis=1) / L2), 0, 1)
            resid = np.sqrt(((p0 + t[:, None] * v - q) ** 2).sum(axis=1))
            ok &= resid <= 0.12 * np.sqrt(L2) + 8
            out[ty[ok], tx[ok]] = True
    return out


def grow_edges(right, down, seeds):
    """Pixels connected to `seeds` through allowed links: right[y, x] links (y, x)-(y, x+1),
    down[y, x] links (y, x)-(y+1, x)."""
    h, w = seeds.shape
    # rows split into runs wherever the horizontal link is not allowed
    starts, ends = [], []
    for y in range(h):
        brk = np.flatnonzero(~right[y]) if w > 1 else np.array([], dtype=np.int64)
        s = np.concatenate(([0], brk + 1))
        e = np.concatenate((brk, [w - 1]))
        starts.append(s)
        ends.append(e)
    seen = [np.zeros(len(s), dtype=bool) for s in starts]
    stack = []
    for y in range(h):
        srow = seeds[y]
        if not srow.any():
            continue
        cs = np.concatenate(([0], np.cumsum(srow)))
        hit = cs[ends[y] + 1] - cs[starts[y]] > 0
        for j in np.flatnonzero(hit):
            seen[y][j] = True
            stack.append((y, j))
    while stack:
        y, j = stack.pop()
        l, r = int(starts[y][j]), int(ends[y][j])
        for ny, link_row in ((y - 1, y - 1), (y + 1, y)):
            if ny < 0 or ny >= h:
                continue
            links = down[link_row]
            ns, ne, nseen = starts[ny], ends[ny], seen[ny]
            j0 = int(np.searchsorted(ne, l, side="left"))
            j1 = int(np.searchsorted(ns, r, side="right")) - 1
            for k in range(j0, j1 + 1):
                if nseen[k]:
                    continue
                lo, hi = max(l, int(ns[k])), min(r, int(ne[k]))
                if links[lo:hi + 1].any():
                    nseen[k] = True
                    stack.append((ny, k))
    out = np.zeros((h, w), dtype=bool)
    for y in range(h):
        for j in np.flatnonzero(seen[y]):
            out[y, starts[y][j]:ends[y][j] + 1] = True
    return out


def select_object(a, x, y, bg=None):
    """(mask, alpha) for the object at (x, y): mask is a bool array of its pixels, alpha a float32
    array (1 inside, partial on the soft rim, 0 elsewhere). Clicking the background selects every
    object. Returns (None, None) if there is no object."""
    h, w = a.shape
    if bg is None:
        bg = background(a)
    objects = ~bg
    if not objects.any():
        return None, None
    if bg[y, x]:
        mask = objects
        # drop specks of noise: pieces smaller than MIN_SPECK pixels
        if MIN_SPECK > 1:
            mask = _drop_specks(mask)
    else:
        if noise_level(_bytes(a)) >= 2:
            objects = _close(objects, 2)            # photos: join fragments split by texture
            objects &= ~(bg & ~_dilate(~bg, 1))     # but never take deep background
        seed = np.zeros((h, w), dtype=bool)
        seed[y, x] = True
        mask = grow(objects, seed, diagonal=True)
    if not mask.any():
        return None, None
    alpha = soft_alpha(a, mask, bg)
    return mask, alpha


def _dilate(m, r):
    out = m.copy()
    for _ in range(r):
        g = out.copy()
        g[1:] |= out[:-1]
        g[:-1] |= out[1:]
        g[:, 1:] |= out[:, :-1]
        g[:, :-1] |= out[:, 1:]
        out = g
    return out


def _close(m, r):
    """Morphological closing: fill gaps narrower than about 2r pixels."""
    return ~_dilate(~_dilate(m, r), r)


def _drop_specks(mask):
    h, w = mask.shape
    out = mask.copy()
    runs = [_runs(mask[y]) for y in range(h)]
    # cheap test: a run that is short and has no run touching it above or below is a speck
    for y in range(h):
        s, e = runs[y]
        for j in range(len(s)):
            if e[j] - s[j] + 1 >= MIN_SPECK:
                continue
            lonely = True
            for ny in (y - 1, y + 1):
                if 0 <= ny < h and mask[ny, max(0, s[j] - 1):e[j] + 2].any():
                    lonely = False
                    break
            if lonely:
                out[y, s[j]:e[j] + 1] = False
    return out


def _shift(arr, dy, dx, fill):
    h, w = arr.shape[:2]
    out = np.full_like(arr, fill)
    ys, ye = max(dy, 0), h + min(dy, 0)
    xs, xe = max(dx, 0), w + min(dx, 0)
    out[ys - dy:ye - dy, xs - dx:xe - dx] = arr[ys:ye, xs:xe]
    return out


def soft_alpha(a, mask, bg):
    """Opacity of each selected pixel: 1 inside, partial on the anti-aliased rim next to the
    background."""
    h, w = mask.shape
    alpha = mask.astype(np.float32)
    # rim: selected pixels within RIM of a background pixel
    near_bg = bg.copy()
    for _ in range(RIM):
        g = near_bg.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            g |= _shift(near_bg, dy, dx, False)
        near_bg = g
    rim = mask & near_bg
    ys, xs = np.nonzero(rim)
    if not len(ys):
        return alpha
    q = _channels(a[ys, xs])
    # local background colour (mean of background pixels around) and object colour (the selected
    # pixel around that is furthest from that background colour)
    r = RIM + 2
    bsum = np.zeros_like(q)
    bcnt = np.zeros(len(ys), dtype=np.float32)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            yy, xx = np.clip(ys + dy, 0, h - 1), np.clip(xs + dx, 0, w - 1)
            b = bg[yy, xx]
            bsum[b] += _channels(a[yy[b], xx[b]])
            bcnt[b] += 1
    has_b = bcnt > 0
    B = np.where(has_b[:, None], bsum / np.maximum(bcnt, 1)[:, None], q)
    best = np.full(len(ys), -1.0, dtype=np.float32)
    F = q.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            yy, xx = np.clip(ys + dy, 0, h - 1), np.clip(xs + dx, 0, w - 1)
            m = mask[yy, xx]
            cc = _channels(a[yy, xx])
            dist = ((cc - B) ** 2).sum(axis=1)
            better = m & (dist > best)
            best = np.where(better, dist, best)
            F = np.where(better[:, None], cc, F)
    v = F - B
    L2 = (v ** 2).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        t = ((q - B) * v).sum(axis=1) / L2
    t = np.where((L2 > 30.0 ** 2) & has_b, np.clip(np.nan_to_num(t, nan=1.0), 0.0, 1.0), 1.0)
    alpha[ys, xs] = t.astype(np.float32)
    return alpha


def cutout(a, mask, alpha, bg_color=None):
    """Premultiplied ARGB uint32 array of the selected pixels with soft edges; rim colours have the
    background's tint removed. a, mask, alpha cover the same area."""
    c = _channels(a)
    out = np.zeros(a.shape, dtype=np.uint32)
    inside = mask & (alpha >= 0.999)
    out[inside] = a[inside]
    rim = mask & (alpha < 0.999) & (alpha > 0.02)
    if rim.any():
        ys, xs = np.nonzero(rim)
        h, w = a.shape
        q = c[ys, xs]
        al = alpha[ys, xs][:, None]
        # background colour around each rim pixel (unselected neighbours), else bg_color
        bsum = np.zeros_like(q)
        bcnt = np.zeros(len(ys), dtype=np.float32)
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                yy, xx = np.clip(ys + dy, 0, h - 1), np.clip(xs + dx, 0, w - 1)
                b = ~mask[yy, xx]
                bsum[b] += c[yy[b], xx[b]]
                bcnt[b] += 1
        B = bsum / np.maximum(bcnt, 1)[:, None]
        if bg_color is not None:
            B[bcnt == 0] = bg_color
        # premultiplied: observed q = al * F + (1 - al) * B, so the object's own share is
        # q - (1 - al) * B (alpha channel included)
        fg = np.clip(q - (1.0 - al) * B, 0.0, 255.0)
        fg[:, 1:] = np.minimum(fg[:, 1:], fg[:, :1])        # valid premultiplied colour
        fg = np.rint(fg).astype(np.uint32)
        out[ys, xs] = (fg[:, 0] << 24) | (fg[:, 1] << 16) | (fg[:, 2] << 8) | fg[:, 3]
    return out
