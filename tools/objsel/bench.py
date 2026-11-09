"""Randomized benchmark for object selection.

Every scene is generated from a seed: a random background (flat, gradient, two-tone with a horizon,
stripes, polka dots, checks, paper texture, photo-like noise, vignette, dark, transparent) and 1-4
random objects (cartoon figures, blobs, stars, rings, sketchy outlines with gaps, flat art without
outlines), sometimes overlapping or cut off by the picture's edge, sometimes saved as JPEG.

The exact answer comes from drawing each object again on its own: an object is its filled silhouette
(enclosed details and holes included, as the tool defines it), and objects that touch or overlap
count as one.

    python bench.py [N] [first_seed]       # prints per-category scores and the worst scenes
"""
import os
import sys
import time
import math
import random
import tempfile
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QPointF, QRectF  # noqa: E402
from PySide6.QtGui import (QGuiApplication, QImage, QColor, QPainter, QPainterPath, QPen, QBrush,  # noqa: E402
                           QLinearGradient, QRadialGradient, QPolygonF)

app = QGuiApplication.instance() or QGuiApplication([])

from opendraw7.document import const_pixels  # noqa: E402
from opendraw7 import objectselect as O  # noqa: E402

BACKGROUNDS = ["flat", "gradient", "horizon", "stripes", "dots", "checks", "paper", "photo_noise",
               "vignette", "dark", "transparent"]
OBJECTS = ["figure", "blob", "star", "ring", "sketch", "flat_art"]


def rcolor(rng, lo=0, hi=255):
    return QColor(rng.randint(lo, hi), rng.randint(lo, hi), rng.randint(lo, hi))


def far_color(rng, avoid, min_dist=110):
    """A random colour at least min_dist (RGB distance) from every colour in avoid."""
    for _ in range(200):
        c = rcolor(rng)
        if all(math.dist((c.red(), c.green(), c.blue()), (a.red(), a.green(), a.blue())) >= min_dist for a in avoid):
            return c
    return QColor(0, 0, 0)


# ---- backgrounds ---------------------------------------------------------------------------
def paint_background(img, kind, rng):
    w, h = img.width(), img.height()
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    used = []
    if kind == "transparent":
        p.end()
        img.fill(0)
        return used
    if kind in ("flat", "paper", "photo_noise"):
        c = rcolor(rng, 150, 255)
        p.fillRect(0, 0, w, h, c)
        used.append(c)
    elif kind == "dark":
        c = rcolor(rng, 0, 60)
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, c)
        c2 = QColor(min(255, c.red() + 25), min(255, c.green() + 25), min(255, c.blue() + 40))
        g.setColorAt(1, c2)
        p.fillRect(0, 0, w, h, QBrush(g))
        used += [c, c2]
    elif kind == "gradient":
        ang = rng.uniform(0, math.pi)
        g = QLinearGradient(w / 2 - math.cos(ang) * w / 2, h / 2 - math.sin(ang) * h / 2,
                            w / 2 + math.cos(ang) * w / 2, h / 2 + math.sin(ang) * h / 2)
        for t in (0, 1):
            c = rcolor(rng, 60, 255)
            g.setColorAt(t, c)
            used.append(c)
        p.fillRect(0, 0, w, h, QBrush(g))
    elif kind == "horizon":
        y = int(h * rng.uniform(0.45, 0.75))
        top = QLinearGradient(0, 0, 0, y)
        c1, c2 = rcolor(rng, 60, 200), rcolor(rng, 150, 255)
        top.setColorAt(0, c1)
        top.setColorAt(1, c2)
        p.fillRect(0, 0, w, y, QBrush(top))
        c3 = rcolor(rng, 30, 160)
        p.fillRect(0, y, w, h - y, c3)
        used += [c1, c2, c3]
    elif kind == "stripes":
        c1, c2 = rcolor(rng, 120, 255), rcolor(rng, 120, 255)
        p.fillRect(0, 0, w, h, c1)
        sw = rng.randint(6, 30)
        p.setPen(Qt.NoPen)
        p.setBrush(c2)
        vertical = rng.random() < 0.5
        for k in range(0, (w if vertical else h), 2 * sw):
            p.drawRect(QRectF(k, 0, sw, h) if vertical else QRectF(0, k, w, sw))
        used += [c1, c2]
    elif kind == "dots":
        c1, c2 = rcolor(rng, 150, 255), rcolor(rng, 80, 255)
        p.fillRect(0, 0, w, h, c1)
        step, r = rng.randint(14, 30), rng.uniform(2, 5)
        p.setPen(Qt.NoPen)
        p.setBrush(c2)
        for y in range(step // 2, h, step):
            for x in range(step // 2 + (y // step % 2) * step // 2, w, step):
                p.drawEllipse(QPointF(x, y), r, r)
        used += [c1, c2]
    elif kind == "checks":
        c1, c2 = rcolor(rng, 150, 255), rcolor(rng, 150, 255)
        s = rng.randint(8, 24)
        for y in range(0, h, s):
            for x in range(0, w, s):
                p.fillRect(x, y, s, s, c1 if (x // s + y // s) % 2 == 0 else c2)
        used += [c1, c2]
    elif kind == "vignette":
        c1, c2 = rcolor(rng, 180, 255), rcolor(rng, 40, 140)
        g = QRadialGradient(w / 2, h / 2, max(w, h) * 0.75)
        g.setColorAt(0, c1)
        g.setColorAt(1, c2)
        p.fillRect(0, 0, w, h, QBrush(g))
        used += [c1, c2]
    p.end()
    if kind in ("paper", "photo_noise"):
        a = const_pixels(img).astype(np.int32)
        sigma = 5 if kind == "paper" else 12
        nrng = np.random.default_rng(rng.randint(0, 2 ** 31))
        noise = nrng.normal(0, sigma, (h, w, 3))
        if kind == "photo_noise":                     # soft, blotchy rather than per-pixel
            k = 3
            noise = np.cumsum(np.cumsum(noise, 0), 1)
            noise = (noise[k:, k:] - noise[:-k, k:] - noise[k:, :-k] + noise[:-k, :-k]) / k
            noise = np.pad(noise, ((k, 0), (k, 0), (0, 0)), mode="edge")
        ch = [(a >> 16) & 255, (a >> 8) & 255, a & 255]
        out = [np.clip(ch[i] + noise[..., i], 0, 255).astype(np.uint32) for i in range(3)]
        from opendraw7.document import pixels
        pixels(img)[:] = 0xFF000000 | (out[0] << 16) | (out[1] << 8) | out[2]
    return used


# ---- objects -----------------------------------------------------------------------------
def blob_path(rng, cx, cy, r):
    n = rng.randint(6, 11)
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        rr = r * rng.uniform(0.65, 1.15)
        pts.append(QPointF(cx + rr * math.cos(a), cy + rr * math.sin(a)))
    path = QPainterPath(pts[0])
    for i in range(n):
        p0, p1 = pts[i], pts[(i + 1) % n]
        mid = QPointF((p0.x() + p1.x()) / 2, (p0.y() + p1.y()) / 2)
        path.quadTo(p0, mid) if i else path.moveTo(mid)
    path.closeSubpath()
    return path


def star_path(cx, cy, r, n=5):
    pts = []
    for i in range(2 * n):
        a = -math.pi / 2 + i * math.pi / n
        rr = r if i % 2 == 0 else r * 0.45
        pts.append(QPointF(cx + rr * math.cos(a), cy + rr * math.sin(a)))
    path = QPainterPath()
    path.addPolygon(QPolygonF(pts))
    path.closeSubpath()
    return path


def draw_object(p, obj, truth=False):
    """Draw obj (a dict from make_object); with truth, draw its filled silhouette in white."""
    kind, cx, cy, r = obj["kind"], obj["cx"], obj["cy"], obj["r"]
    W = QColor(255, 255, 255)
    fill, line, lw = obj["fill"], obj["line"], obj["lw"]
    if kind == "figure":
        s = r / 60.0
        if truth:
            p.setPen(QPen(W, 3 * s, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(W)
        for (x0, y0, x1, y1) in ((-12, 55, -18, 95), (12, 55, 18, 95), (-25, 15, -55, 40), (25, 15, 55, 40)):
            p.setPen(QPen(W if truth else line, 11 * s, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(cx + x0 * s, cy + y0 * s), QPointF(cx + x1 * s, cy + y1 * s))
            p.setPen(QPen(W if truth else obj["skin"], 6 * s, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(cx + x0 * s, cy + y0 * s), QPointF(cx + x1 * s, cy + y1 * s))
        p.setPen(QPen(W if truth else line, 3 * s))
        p.setBrush(W if truth else fill)
        p.drawRoundedRect(QRectF(cx - 28 * s, cy - 5 * s, 56 * s, 65 * s), 14 * s, 14 * s)
        p.setBrush(W if truth else obj["skin"])
        p.drawEllipse(QRectF(cx - 32 * s, cy - 70 * s, 64 * s, 64 * s))
        if not truth:
            for ex in (-12, 12):
                p.setPen(QPen(line, 2 * s))
                p.setBrush(obj["eye"])
                p.drawEllipse(QRectF(cx + (ex - 7) * s, cy - 52 * s, 14 * s, 16 * s))
                p.setPen(Qt.NoPen)
                p.setBrush(line)
                p.drawEllipse(QRectF(cx + (ex - 3) * s, cy - 46 * s, 6 * s, 7 * s))
        return
    if kind in ("blob", "flat_art", "sketch"):
        path = blob_path(random.Random(obj["shape_seed"]), cx, cy, r)
    elif kind == "star":
        path = star_path(cx, cy, r, obj["points"])
    elif kind == "ring":
        path = QPainterPath()
        path.addEllipse(QPointF(cx, cy), r, r)
    if truth:
        p.setPen(QPen(W, lw) if lw else Qt.NoPen)
        p.setBrush(W)
        p.drawPath(path)
        return
    if kind == "ring":
        # a thick coloured ring with a hole showing a different colour (part of the object)
        p.setPen(QPen(line, lw))
        p.setBrush(fill)
        p.drawPath(path)
        inner = QPainterPath()
        inner.addEllipse(QPointF(cx, cy), r * 0.45, r * 0.45)
        p.setBrush(obj["eye"])
        p.drawPath(inner)
        return
    if kind == "sketch":
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawPath(path)
        pen = QPen(line, lw)
        pen.setDashPattern([7, 1.2])                 # a sketchy outline with small gaps
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        return
    p.setPen(QPen(line, lw) if lw else Qt.NoPen)
    p.setBrush(fill)
    p.drawPath(path)
    if kind == "blob" and obj.get("detail"):
        p.setPen(QPen(line, max(1, lw * 0.6)))
        p.setBrush(obj["eye"])
        p.drawEllipse(QPointF(cx - r * 0.25, cy - r * 0.15), r * 0.14, r * 0.14)
        p.drawEllipse(QPointF(cx + r * 0.25, cy - r * 0.15), r * 0.14, r * 0.14)


def make_object(rng, kind, w, h, bg_colors, cut_off=False):
    r = rng.uniform(35, min(w, h) * 0.22)
    if cut_off:
        side = rng.choice("lrtb")
        cx = {"l": r * 0.3, "r": w - r * 0.3}.get(side, rng.uniform(r, w - r))
        cy = {"t": r * 0.3, "b": h - r * 0.3}.get(side, rng.uniform(r, h - r))
    else:
        cx, cy = rng.uniform(r + 15, w - r - 15), rng.uniform(r * 1.25 + 15, h - r * 1.6 - 15)
    fill = far_color(rng, bg_colors, 90 if kind == "flat_art" else 70)
    line = QColor(0, 0, 0) if rng.random() < 0.7 else QColor(rng.randint(0, 80), rng.randint(0, 80), rng.randint(0, 80))
    lw = 0 if kind == "flat_art" else rng.choice([1.5, 2.5, 3, 4, 6])
    return {"kind": kind, "cx": cx, "cy": cy, "r": r, "fill": fill, "line": line, "lw": lw,
            "skin": far_color(rng, bg_colors, 60), "eye": QColor(255, 255, 255) if rng.random() < .6 else rcolor(rng),
            "shape_seed": rng.randint(0, 10 ** 9), "points": rng.randint(4, 7), "detail": rng.random() < 0.5}


# ---- a scene -----------------------------------------------------------------------------------
def make_scene(seed):
    rng = random.Random(seed)
    w, h = rng.randint(300, 900), rng.randint(250, 700)
    bkind = BACKGROUNDS[seed % len(BACKGROUNDS)]
    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied if bkind == "transparent" else QImage.Format_RGB32)
    bg_colors = paint_background(img, bkind, rng)
    n = rng.randint(1, 4)
    objs = [make_object(rng, rng.choice(OBJECTS), w, h, bg_colors, cut_off=rng.random() < 0.2) for _ in range(n)]
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    for o in objs:
        draw_object(p, o)
    p.end()
    cover = []
    for o in objs:
        t = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
        t.fill(0)
        q = QPainter(t)
        q.setRenderHint(QPainter.Antialiasing, True)
        draw_object(q, o, truth=True)
        q.end()
        cover.append((const_pixels(t) >> 24).astype(np.float32) / 255.0)
    jpeg = bkind not in ("transparent",) and rng.random() < 0.25
    if jpeg:
        path = os.path.join(tempfile.gettempdir(), f"bench_{seed}.jpg")
        img.save(path, "JPG", rng.choice([60, 75, 90]))
        img = QImage(path).convertToFormat(QImage.Format_RGB32)
    a = const_pixels(img.convertToFormat(QImage.Format_ARGB32_Premultiplied)).copy()
    return {"seed": seed, "a": a, "bkind": bkind, "objs": objs, "cover": cover, "jpeg": jpeg, "img": img, "rng": rng}


def groups(cover):
    """Objects that touch or overlap form one group: list of (object indices, coverage 0..1)."""
    n = len(cover)
    solid = [c > 0.5 for c in cover]
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(n):
        di = O._dilate(solid[i], 1)
        for j in range(i + 1, n):
            if (di & solid[j]).any():
                parent[find(i)] = find(j)
    out = {}
    for i in range(n):
        out.setdefault(find(i), []).append(i)
    res = []
    for idx in out.values():
        cov = np.maximum.reduce([cover[i] for i in idx])
        res.append((idx, cov))
    return res


def score_scene(sc):
    a, rng = sc["a"], sc["rng"]
    t0 = time.time()
    bg = O.background(a)
    results = []
    gs = groups(sc["cover"])
    for idx, cov in gs:
        # click somewhere well inside this group and not inside any other object
        others = np.zeros_like(cov)
        for j, c in enumerate(sc["cover"]):
            if j not in idx:
                others = np.maximum(others, c)
        inside = (cov > 0.99) & (others < 0.01)
        ys, xs = np.nonzero(inside)
        if not len(ys):
            continue
        k = rng.randrange(len(ys))
        mask, alpha = O.select_object(a, int(xs[k]), int(ys[k]), bg)
        truth = cov > 0.5
        if mask is None:
            iou, soft = 0.0, 0.0
        else:
            iou = (mask & truth).sum() / max(1, (mask | truth).sum())
            sel = np.where(mask, alpha, 0)
            soft = np.minimum(sel, cov).sum() / max(1e-6, np.maximum(sel, cov).sum())
        results.append({"kinds": [sc["objs"][i]["kind"] for i in idx], "iou": float(iou), "soft": float(soft)})
    # clicking the background: every object
    allc = np.maximum.reduce(sc["cover"])
    ys, xs = np.nonzero(allc < 0.01)
    k = rng.randrange(len(ys))
    mask, alpha = O.select_object(a, int(xs[k]), int(ys[k]), bg)
    truth = allc > 0.5
    all_iou = 0.0 if mask is None else float((mask & truth).sum() / max(1, (mask | truth).sum()))
    return results, all_iou, time.time() - t0


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 330
    first = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    by_bg, by_obj, worst, all_bg = {}, {}, [], {}
    times = []
    dump = []
    for seed in range(first, first + n):
        sc = make_scene(seed)
        res, all_iou, t = score_scene(sc)
        times.append(t)
        all_bg.setdefault(sc["bkind"], []).append(all_iou)
        for r in res:
            by_bg.setdefault(sc["bkind"] + (" jpeg" if sc["jpeg"] else ""), []).append(r["soft"])
            for kd in set(r["kinds"]):
                by_obj.setdefault(kd, []).append(r["soft"])
            worst.append((r["soft"], seed, sc["bkind"], r["kinds"]))
            dump.append((seed, tuple(r["kinds"]), round(r["soft"], 4)))
    every = [s for v in by_bg.values() for s in v]
    print(f"{n} scenes, {len(every)} object clicks: mean soft IoU {np.mean(every):.4f}, "
          f"median {np.median(every):.4f}, below 0.9: {np.mean(np.array(every) < 0.9) * 100:.1f}%, "
          f"below 0.5: {np.mean(np.array(every) < 0.5) * 100:.1f}%; mean {np.mean(times):.2f}s per scene")
    print("by background:")
    for k in sorted(by_bg):
        v = np.array(by_bg[k])
        print(f"  {k:18s} n={len(v):3d} mean {v.mean():.3f}  <0.9 {np.mean(v < 0.9) * 100:5.1f}%")
    print("by object:")
    for k in sorted(by_obj):
        v = np.array(by_obj[k])
        print(f"  {k:18s} n={len(v):3d} mean {v.mean():.3f}  <0.9 {np.mean(v < 0.9) * 100:5.1f}%")
    print("background click (all objects): " + ", ".join(f"{k} {np.mean(v):.3f}" for k, v in sorted(all_bg.items())))
    if os.environ.get("BENCH_DUMP"):
        import json
        json.dump(dump, open(os.environ["BENCH_DUMP"], "w"))
    worst.sort()
    print("worst:", ", ".join(f"seed {s} {b} {k} {q:.2f}" for q, s, b, k in worst[:12]))


if __name__ == "__main__":
    main()
