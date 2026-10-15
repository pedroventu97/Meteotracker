"""Pure functions for corridor extraction and passage detection (metric CRS, metres/seconds)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage
import shapely
from shapely.geometry import LineString

OFFS8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


# ---------------------------------------------------------------- density grid
def line_cells(geom, cell: float, step: float = 5.0) -> set:
    out = set()
    for g in getattr(geom, "geoms", [geom]):
        if g.is_empty or g.length == 0:
            continue
        d = np.append(np.arange(0, g.length, step), g.length)
        pts = shapely.line_interpolate_point(g, d)
        xy = shapely.get_coordinates(pts)
        out.update(zip(np.floor(xy[:, 0] / cell).astype(int), np.floor(xy[:, 1] / cell).astype(int)))
    return out


def dilate_cells(cells: set, r: int = 1) -> set:
    out = set()
    for i, j in cells:
        for di in range(-r, r + 1):
            for dj in range(-r, r + 1):
                out.add((i + di, j + dj))
    return out


def count_grid(cell_sets: list[set]):
    """Return (array of distinct-group counts, i0, j0)."""
    cnt: dict = {}
    for s in cell_sets:
        for c in s:
            cnt[c] = cnt.get(c, 0) + 1
    if not cnt:
        return np.zeros((0, 0), int), 0, 0
    ij = np.array(list(cnt.keys()))
    i0, j0 = ij.min(0) - 2
    W, H = ij.max(0) - (i0, j0) + 3
    A = np.zeros((W, H), np.int32)
    A[ij[:, 0] - i0, ij[:, 1] - j0] = list(cnt.values())
    return A, int(i0), int(j0)


# ---------------------------------------------------------------- thinning
def zhang_suen(img: np.ndarray) -> np.ndarray:
    I = np.pad(img.astype(np.uint8), 1)
    while True:
        changed = False
        for step in (0, 1):
            P = I
            p2, p3, p4 = P[:-2, 1:-1], P[:-2, 2:], P[1:-1, 2:]
            p5, p6, p7 = P[2:, 2:], P[2:, 1:-1], P[2:, :-2]
            p8, p9 = P[1:-1, :-2], P[:-2, :-2]
            seq = [p2, p3, p4, p5, p6, p7, p8, p9, p2]
            B = sum(x.astype(int) for x in seq[:8])
            A = sum(((seq[k] == 0) & (seq[k + 1] == 1)).astype(int) for k in range(8))
            c = P[1:-1, 1:-1] == 1
            if step == 0:
                m = c & (B >= 2) & (B <= 6) & (A == 1) & (p2 * p4 * p6 == 0) & (p4 * p6 * p8 == 0)
            else:
                m = c & (B >= 2) & (B <= 6) & (A == 1) & (p2 * p4 * p8 == 0) & (p2 * p6 * p8 == 0)
            if m.any():
                I[1:-1, 1:-1][m] = 0
                changed = True
        if not changed:
            return I[1:-1, 1:-1].astype(bool)


# ---------------------------------------------------------------- skeleton -> strokes
def _deg(S):
    return ndimage.convolve(S.astype(int), np.ones((3, 3), int), mode="constant") - S.astype(int)


def skeleton_edges(S: np.ndarray):
    """Trace skeleton into edges between nodes (junction clusters / endpoints). Returns list of (node_a, node_b, [pixels])."""
    S = S.copy()
    deg = _deg(S) * S
    junc = (deg >= 3) & S
    lab, nj = ndimage.label(junc, structure=np.ones((3, 3)))
    node = np.zeros(S.shape, int)
    node[junc] = lab[junc]
    ends = np.argwhere((deg == 1) & S)
    for k, (i, j) in enumerate(ends):
        node[i, j] = nj + 1 + k
    W, H = S.shape
    visited = np.zeros(S.shape, bool)
    edges = []

    def nbrs(i, j):
        for di, dj in OFFS8:
            a, b = i + di, j + dj
            if 0 <= a < W and 0 <= b < H and S[a, b]:
                yield a, b

    def walk(start, first):
        path = [start, first]
        prev, cur = start, first
        while node[cur] == 0:
            visited[cur] = True
            nxt = [p for p in nbrs(*cur) if p != prev and not (visited[p] and node[p] == 0) and p not in path[-3:]]
            if not nxt:
                break
            # prefer 4-neighbours to avoid stair shortcuts
            nxt.sort(key=lambda p: abs(p[0] - cur[0]) + abs(p[1] - cur[1]))
            prev, cur = cur, nxt[0]
            path.append(cur)
        return path

    for i, j in np.argwhere(node > 0):
        for nb in nbrs(i, j):
            if node[nb] == 0 and not visited[nb]:
                p = walk((i, j), nb)
                edges.append((int(node[i, j]), int(node[p[-1]]) if node[p[-1]] else -1, p))
    # pure loops
    rest = np.argwhere(S & ~visited & (node == 0))
    for i, j in rest:
        if visited[i, j]:
            continue
        nb = [p for p in nbrs(i, j) if not visited[p]]
        if not nb:
            continue
        visited[i, j] = True
        p = walk((i, j), nb[0])
        edges.append((-1, -1, p))
    return edges


def _end_vec(px, at_start, k=4):
    a = np.array(px[0] if at_start else px[-1], float)
    b = np.array(px[min(k, len(px) - 1)] if at_start else px[max(-k - 1, -len(px))], float)
    v = b - a  # pointing inward
    n = np.hypot(*v)
    return v / n if n else v


def merge_strokes(edges, cell: float, spur_m: float = 60.0, max_turn_deg: float = 45.0):
    """Prune short dangling spurs, then join edges through nodes by best continuity (stroke building)."""
    deg: dict = {}
    for a, b, p in edges:
        for n in (a, b):
            if n > 0:
                deg[n] = deg.get(n, 0) + 1
    keep = []
    for a, b, p in edges:
        L = len(p) * cell
        dangling = (deg.get(a, 0) <= 1) or (deg.get(b, 0) <= 1) or a == -1 or b == -1
        junctioned = deg.get(a, 0) >= 3 or deg.get(b, 0) >= 3
        if L < spur_m and dangling and junctioned:
            continue
        keep.append((a, b, p))
    edges = keep
    ends: dict = {}
    for e, (a, b, p) in enumerate(edges):
        if a > 0:
            ends.setdefault(a, []).append((e, 0))
        if b > 0:
            ends.setdefault(b, []).append((e, 1))
    pair = {}
    cos_max = np.cos(np.radians(180 - max_turn_deg))
    for n, lst in ends.items():
        cand = []
        for x in range(len(lst)):
            for y in range(x + 1, len(lst)):
                (e1, s1), (e2, s2) = lst[x], lst[y]
                if e1 == e2:
                    continue
                v1 = _end_vec(edges[e1][2], s1 == 0)
                v2 = _end_vec(edges[e2][2], s2 == 0)
                c = float(np.dot(v1, v2))  # -1 = straight continuation
                if c <= cos_max:
                    cand.append((c, lst[x], lst[y]))
        cand.sort(key=lambda t: t[0])
        used = set()
        for c, u, v in cand:
            if u in used or v in used:
                continue
            pair[u] = v
            pair[v] = u
            used.update([u, v])
    done = set()
    strokes = []

    def oriented(e, start_end):
        p = edges[e][2]
        return p if start_end == 0 else p[::-1]

    order = sorted(range(len(edges)), key=lambda e: ((e, 0) in pair) + ((e, 1) in pair))
    for e0 in order:
        if e0 in done:
            continue
        # go to one free end
        e, s = e0, 0
        seen = {e0}
        while (e, s) in pair:
            e2, s2 = pair[(e, s)]
            if e2 in seen:
                break
            seen.add(e2)
            e, s = e2, 1 - s2
        # now traverse from (e, s) outward to the other side
        pts = []
        cur, cs = e, s
        while True:
            done.add(cur)
            seg = oriented(cur, cs)
            pts.extend(seg if not pts else seg[1:])
            nxt = pair.get((cur, 1 - cs))
            if nxt is None or nxt[0] in done:
                break
            cur, cs = nxt
        strokes.append(pts)
    return strokes


def pixels_to_line(px, i0, j0, cell, simplify_m=8.0):
    xy = [((i + i0 + 0.5) * cell, (j + j0 + 0.5) * cell) for i, j in px]
    if len(xy) < 2:
        return None
    ln = LineString(xy)
    # light smoothing (moving average, 5 px) before simplification
    a = np.array(xy)
    if len(a) >= 5:
        k = np.ones(5) / 5
        sm = np.c_[np.convolve(a[:, 0], k, "same"), np.convolve(a[:, 1], k, "same")]
        sm[:2], sm[-2:] = a[:2], a[-2:]
        ln = LineString(sm)
    return ln.simplify(simplify_m)


# ---------------------------------------------------------------- passages
@dataclass
class PassageParams:
    tol_m: float = 20.0
    min_len_m: float = 250.0
    max_gap_m: float = 40.0
    max_dt_s: float = 120.0
    reversal_m: float = 40.0
    bin_cover_frac: float = 0.5


@dataclass
class Run:
    idx: np.ndarray
    s: np.ndarray
    direction: str = ""
    extent: tuple = field(default_factory=tuple)


def _split_reversals(idx, s, hyst):
    """Split a run where position along corridor reverses by more than hyst metres."""
    out = []
    start = 0
    lo = hi = s[0]
    trend = 0
    for k in range(1, len(s)):
        lo, hi = min(lo, s[k]), max(hi, s[k])
        if trend == 0:
            if s[k] - s[start] > hyst:
                trend = 1
            elif s[start] - s[k] > hyst:
                trend = -1
        elif trend == 1 and hi - s[k] > hyst:
            cut = start + int(np.argmax(s[start:k + 1]))
            out.append((start, cut + 1))
            start, lo, hi, trend = cut, s[cut], s[cut], -1
            lo = min(s[start:k + 1]); hi = s[start]
        elif trend == -1 and s[k] - lo > hyst:
            cut = start + int(np.argmin(s[start:k + 1]))
            out.append((start, cut + 1))
            start, trend = cut, 1
            hi = max(s[start:k + 1]); lo = s[start]
    out.append((start, len(s)))
    return [(idx[a:b], s[a:b]) for a, b in out if b - a >= 2]


def detect_passages(line: LineString, x, y, t, prm: PassageParams):
    """x,y metric coords, t seconds (sorted). Returns list of Run with direction 'along'/'against'."""
    x, y, t = map(np.asarray, (x, y, t))
    if len(x) < 2:
        return []
    pts = shapely.points(x, y)
    d = shapely.distance(line, pts)
    near = np.where(d <= prm.tol_m)[0]
    if len(near) < 2:
        return []
    s_all = shapely.line_locate_point(line, pts[near])
    trk = np.r_[0, np.cumsum(np.hypot(np.diff(x), np.diff(y)))]
    # gap rule: along-corridor gap |ds| <= max_gap_m and time gap <= max_dt_s; brief excursions off the band are bridged
    brk = (np.diff(t[near]) > prm.max_dt_s) | (np.abs(np.diff(s_all)) > prm.max_gap_m)
    cuts = np.r_[0, np.where(brk)[0] + 1, len(near)]
    runs = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        if b - a < 2:
            continue
        for idx, s in _split_reversals(near[a:b], s_all[a:b], prm.reversal_m):
            ext = (float(s.min()), float(s.max()))
            if ext[1] - ext[0] >= prm.min_len_m:
                runs.append(Run(idx=idx, s=s, direction="along" if s[-1] >= s[0] else "against", extent=ext))
    return runs


def bins_covered(extent, line_len, bin_m, frac=0.5):
    nb = max(1, int(np.ceil(line_len / bin_m - 1e-9)))
    out = []
    for k in range(nb):
        b0, b1 = k * bin_m, min((k + 1) * bin_m, line_len)
        ov = min(b1, extent[1]) - max(b0, extent[0])
        if ov > 0 and ov >= frac * (b1 - b0):
            out.append(k)
    return out


def make_bins(line: LineString, bin_m: float):
    L = line.length
    nb = max(1, int(np.ceil(L / bin_m - 1e-9)))
    return [(k, k * bin_m, min((k + 1) * bin_m, L), shapely.ops.substring(line, k * bin_m, min((k + 1) * bin_m, L))) for k in range(nb)]


import shapely.ops  # noqa: E402


def refine_centerline(line: LineString, x, y, search_m: float = 40.0, step_m: float = 10.0, win_m: float = 30.0,
                      min_pts: int = 3, iters: int = 2) -> LineString:
    """Re-centre a raster-derived centerline on the median lateral position of observed track points.

    For stations every step_m, takes points within search_m of the line and within +-win_m along it,
    computes the median signed lateral offset and shifts the station by it (stations without support keep 0 shift,
    offsets are then median-smoothed). Repeated `iters` times with shrinking search radius.
    """
    x = np.asarray(x); y = np.asarray(y)
    for it in range(iters):
        L = line.length
        if L < 2 * step_m:
            return line
        pts = shapely.points(x, y)
        d = shapely.distance(line, pts)
        m = d <= search_m
        if m.sum() < min_pts:
            return line
        P = pts[m]
        s = shapely.line_locate_point(line, P)
        on = shapely.line_interpolate_point(line, s)
        on2 = shapely.line_interpolate_point(line, np.clip(s + 1.0, 0, L))
        on1 = shapely.line_interpolate_point(line, np.clip(s - 1.0, 0, L))
        a = shapely.get_coordinates(on); t = shapely.get_coordinates(on2) - shapely.get_coordinates(on1)
        t /= np.maximum(np.hypot(t[:, 0], t[:, 1]), 1e-9)[:, None]
        nrm = np.c_[-t[:, 1], t[:, 0]]
        off = np.sum((shapely.get_coordinates(P) - a) * nrm, axis=1)
        st = np.append(np.arange(0, L, step_m), L)
        o = np.zeros(len(st))
        for k, sv in enumerate(st):
            w = np.abs(s - sv) <= win_m
            if w.sum() >= min_pts:
                o[k] = np.median(off[w])
        if len(o) >= 5:
            o = ndimage.median_filter(o, size=5, mode="nearest")
        c = shapely.get_coordinates(shapely.line_interpolate_point(line, st))
        c2 = shapely.get_coordinates(shapely.line_interpolate_point(line, np.clip(st + 1, 0, L)))
        c1 = shapely.get_coordinates(shapely.line_interpolate_point(line, np.clip(st - 1, 0, L)))
        tt = c2 - c1; tt /= np.maximum(np.hypot(tt[:, 0], tt[:, 1]), 1e-9)[:, None]
        new = c + o[:, None] * np.c_[-tt[:, 1], tt[:, 0]]
        line = LineString(new).simplify(2.0)
        search_m = max(25.0, search_m * 0.75)
    return line

