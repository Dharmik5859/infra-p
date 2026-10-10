"""
Low-level raster tracing primitives: grid stripping, glyph removal,
dash/solid separation, and tracing a surface through noisy, dashed,
gapped ink.

These operate on a binary ink mask at the pipeline's CANONICAL resolution
(see surfaces.CANON_PPF) -- every pixel constant below was tuned there,
so callers resample first instead of rescaling each threshold.

Applied to both surfaces:
    candidates()        per-column ink midpoints
    best_path()         max-scoring DP chain through those candidates
    snap_top()          (design only) recentre on the topmost stroke
    refine_gaps()       recall pass: look for missed dashes inside big gaps
    despike()/densify() outlier rejection + dense per-column array
    trim_buried_tail()  drop false "cut" caused by buried services
"""
from __future__ import annotations

import cv2
import numpy as np
from scipy.ndimage import median_filter


def runs1d(a: np.ndarray, tol: int = 3) -> list[tuple[int, int]]:
    """Group a sorted index array into (start, end) runs, merging gaps <= tol."""
    if len(a) == 0:
        return []
    out, s, p = [], a[0], a[0]
    for v in a[1:]:
        if v - p > tol:
            out.append((int(s), int(p)))
            s = v
        p = v
    out.append((int(s), int(p)))
    return out


def dilate1d(v: np.ndarray, k: int) -> np.ndarray:
    """Binary dilation of a 1-D boolean vector by k samples each way."""
    out = v.copy()
    for s in range(1, k + 1):
        out[:-s] |= v[s:]
        out[s:] |= v[:-s]
    return out


def _erase_slivers(line: np.ndarray, min_len: int) -> None:
    """Zero, in place, every run of ink at least `min_len` long."""
    idx = np.where(line)[0]
    for a, b in runs1d(idx, tol=1):
        if b - a + 1 >= min_len:
            line[a:b + 1] = 0


def strip_grid(ink: np.ndarray, V, H_, bridge: int = 5, sliver: int = 0) -> np.ndarray:
    """Delete the lattice, then SURGICALLY repair the curves it was crossing.

    Only the grid line's own band is erased (frame detection measures it to
    the pixel, antialiased edge rows included). Erasing a wider margin would
    also wipe out any drawn line running along the grid at a shallow angle --
    a 2 % pavement surface near a round elevation loses ~15 ft that way.

    Zeroing a band also punches a hole through every curve that CROSSES it,
    so each band is re-bridged where ink exists on both sides within
    +-`bridge` px: continuity is restored without restoring the grid."""
    m = ink.copy()
    for s, e in V:
        m[:, max(0, s):e + 1] = 0
    for s, e in H_:
        m[max(0, s):e + 1, :] = 0
    if sliver:
        # a skewed, uneven or heavier-than-detected grid line leaves long
        # straight slivers beside its band; data lines only cross there
        # briefly, so long runs are grid
        reach = 4
        for s, e in H_:
            for r in list(range(s - reach, s)) + list(range(e + 1, e + 1 + reach)):
                if 0 <= r < m.shape[0]:
                    _erase_slivers(m[r], sliver)
        for s, e in V:
            for c in list(range(s - reach, s)) + list(range(e + 1, e + 1 + reach)):
                if 0 <= c < m.shape[1]:
                    col = m[:, c].copy()
                    _erase_slivers(col, sliver)
                    m[:, c] = col
    for s, e in V:
        a, b = s - 1, e + 1
        if a < 0 or b >= m.shape[1]:
            continue
        both = dilate1d(m[:, a].astype(bool), bridge) & dilate1d(m[:, b].astype(bool), bridge)
        m[:, a + 1:b] |= both[:, None].astype(np.uint8)
    for s, e in H_:
        a, b = s - 1, e + 1
        if a < 0 or b >= m.shape[0]:
            continue
        both = dilate1d(m[a, :].astype(bool), bridge) & dilate1d(m[b, :].astype(bool), bridge)
        m[a + 1:b, :] |= both[None, :].astype(np.uint8)
    return m


def denoise(roi: np.ndarray) -> tuple[np.ndarray, int]:
    """Drop annotation glyphs, traffic arrows and survey specks. Discriminator is
    BOX FILL RATIO: a digit fills ~0.3-0.6 of its bounding box, a 2 px line
    through the same box fills < 0.15. Builds one keep/drop table indexed by
    component label and applies it in a single vectorized pass."""
    n, lab, st, _ = cv2.connectedComponentsWithStats(roi, 8)
    drop = np.zeros(n, dtype=bool)
    dropped = 0
    for k in range(1, n):
        x, y, w, h, a = st[k]
        f = a / (w * h)
        # glyph-sized and dense | a solid symbol (filled arrow, north arrow) --
        # compact, never a long flat box like a pavement section | a speck
        if (8 <= w <= 70 and 10 <= h <= 55 and f >= 0.30) \
           or (a > 700 and f >= 0.35 and max(w, h) <= 4 * min(w, h)) \
           or (a <= 12 and w <= 7 and h <= 7):
            drop[k] = True
            dropped += 1
    keep = np.where(drop[lab], 0, roi).astype(roi.dtype)
    return keep, dropped


def split_dash_solid(mask: np.ndarray):
    """Existing ground is DASHED, the proposed template is SOLID. Estimate the
    dash length from the component-width distribution and cut at 3x the median,
    so the threshold adapts to scan resolution instead of being hard-coded.

    A short component only counts as a ground DASH when it is shaped like a
    piece of line: thin, elongated and not steep. Glyph fragments of labels
    ("0.80% MATCH EXIST", rotated elevation callouts) are compact or upright
    and would otherwise pull the ground trace up into the annotation text.

    Returns (dash, solid, threshold, typical dash width)."""
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask, 8)
    ws = st[1:, cv2.CC_STAT_WIDTH] if n > 1 else np.array([])
    dash_w = float(np.median(ws)) if len(ws) else 12.0
    thr = max(40.0, 3.0 * dash_w)
    is_solid = np.zeros(n, dtype=bool)
    is_dash = np.zeros(n, dtype=bool)
    if n > 1:
        hs = st[1:, cv2.CC_STAT_HEIGHT]
        is_solid[1:] = np.maximum(ws, hs) >= thr
        for k in np.where(~is_solid[1:])[0] + 1:
            w, h, area = st[k, cv2.CC_STAT_WIDTH], st[k, cv2.CC_STAT_HEIGHT], st[k, cv2.CC_STAT_AREA]
            length = float(np.hypot(w, h))
            thickness = area / max(length, 1.0)
            is_dash[k] = (length >= 6 and thickness <= 7.0 and length / max(thickness, 1.0) >= 1.8
                          and h <= 1.6 * w + 3)
    is_dash &= _collinear_support(lab, st, is_dash)
    solid = np.where(is_solid[lab], mask, 0).astype(mask.dtype)
    dash = np.where(is_dash[lab], mask, 0).astype(mask.dtype)
    return dash, solid, thr, dash_w


def _collinear_support(lab: np.ndarray, st: np.ndarray, is_dash: np.ndarray,
                       reach: float = 24.0, max_turn_deg: float = 25.0) -> np.ndarray:
    """A dash of a dashed line is continued by another dash: one whose end
    lies within `reach` px, roughly along the same direction. Strokes of
    label text -- a rotated "1", the bar of a "7", a hyphen -- are short
    lines too, but their neighbours sit beside them, not in line with them."""
    ids = np.where(is_dash)[0]
    keep = np.zeros(len(is_dash), bool)
    if len(ids) < 2:
        return keep
    cen, dirs, half = [], [], []
    for k in ids:
        x, y, w, h = st[k, :4]
        ys, xs = np.nonzero(lab[y:y + h, x:x + w] == k)
        pts = np.stack([xs + x, ys + y], 1).astype(float)
        c = pts.mean(0)
        if len(pts) > 2:
            ev, evec = np.linalg.eigh(np.cov((pts - c).T))
            d = evec[:, 1]
        else:
            d = np.array([1.0, 0.0])
        if d[0] < 0:
            d = -d
        cen.append(c)
        dirs.append(d)
        half.append(max(1.0, float(np.abs((pts - c) @ d).max())))
    cen, dirs, half = np.array(cen), np.array(dirs), np.array(half)
    cos_turn = np.cos(np.radians(max_turn_deg))
    for i in range(len(ids)):
        v = cen - cen[i]
        dist = np.hypot(v[:, 0], v[:, 1])
        gap = dist - half - half[i]                       # end-to-end distance
        ok = (gap <= reach) & (dist > 0)
        if not ok.any():
            continue
        u = v[ok] / dist[ok][:, None]
        along = np.abs(u @ dirs[i]) >= cos_turn           # neighbour lies in line
        parallel = np.abs(dirs[ok] @ dirs[i]) >= cos_turn  # and points the same way
        if (along & parallel).any():
            keep[ids[i]] = True
    return keep


def candidates(mask: np.ndarray, max_run: int = 30) -> list[list[float]]:
    """Per column, the mid-point of every vertical ink run = a curve observation."""
    out = []
    for x in range(mask.shape[1]):
        col = np.where(mask[:, x])[0]
        c = []
        for s, e in runs1d(col, tol=2):
            if e - s + 1 <= max_run:
                c.append((s + e) / 2.0)
            else:
                c += [float(s), float(e)]
        out.append(c)
    return out


def best_path(cands, reward=3.0, win=260, slope=0.6, slack=8.0, gap_pen=0.04,
              weights=None) -> dict[int, float]:
    """Max-scoring chain through the candidate points (Viterbi over a DAG).

    A greedy left-to-right tracker breaks at the first long dash gap and then
    coasts away from the curve. Scoring globally -- +reward per point used,
    -|dy| for roughness, -gap_pen per skipped column -- recovers the whole
    surface including the stretch hidden behind the proposed template.

    Vectorized over the sliding window: the original was a pure-Python
    `for i: for j in range(start, i)` double loop, which is fine for a
    handful of candidate points but scales very badly on a wide, ink-dense
    real drawing with thousands of them -- confirmed as the dominant cost
    of the whole per-region pipeline on real GDOT plan sets (~5s/region,
    the large majority of total processing time). This computes the same
    scores with numpy array ops over each window instead of a Python-level
    inner loop. Tie-breaking matches exactly: np.argmax returns the FIRST
    occurrence of the max value for a tie, same as the original's strict
    `s > score[i]` comparison while iterating j in increasing order.

    `weights` (parallel to `cands`) scales the reward of individual points,
    so weaker evidence can be offered to the tracer without outranking
    strong evidence."""
    if weights is None:
        weights = [[1.0] * len(c) for c in cands]
    pts = [(x, y, w) for x, (c, cw) in enumerate(zip(cands, weights)) for y, w in zip(c, cw)]
    if not pts:
        return {}
    n = len(pts)
    xs = np.array([p[0] for p in pts], dtype=float)
    ys = np.array([p[1] for p in pts], dtype=float)
    rw = reward * np.array([p[2] for p in pts], dtype=float)
    score = rw.copy()
    prev = np.full(n, -1)
    start = 0
    for i in range(n):
        xi, yi = xs[i], ys[i]
        while xs[start] < xi - win:
            start += 1
        if start >= i:
            continue
        wx = xs[start:i]
        wy = ys[start:i]
        dx = xi - wx
        dy = np.abs(yi - wy)
        valid = (dx > 0) & (dy <= slope * dx + slack)
        if not valid.any():
            continue
        s = score[start:i] + rw[i] - dy - gap_pen * (dx - 1)
        s = np.where(valid, s, -np.inf)
        j_local = int(np.argmax(s))
        if s[j_local] > score[i]:
            score[i] = s[j_local]
            prev[i] = start + j_local
    k = int(np.argmax(score))
    path = []
    while k >= 0:
        path.append(k)
        k = prev[k]
    return {int(xs[i]): float(ys[i]) for i in reversed(path)}


def snap_top(mask: np.ndarray, chain: dict[int, float], rad: int = 9) -> dict[int, float]:
    """The template is drawn as a thin box (surface + pavement structure), so the
    finished surface is the TOPMOST stroke -- and we want that stroke's CENTRE.
    Taking its upper edge biases the whole surface up by half a stroke width,
    which shows up directly as a fill/cut error."""
    out = {}
    for x, y in chain.items():
        lo, hi = max(0, int(y) - rad), min(mask.shape[0], int(y) + rad + 1)
        w = np.where(mask[lo:hi, x])[0]
        if len(w) == 0:
            out[x] = y
            continue
        a, b = runs1d(w, tol=1)[0]
        out[x] = float(lo + (a + b) / 2.0)
    return out


def snap_bottom(mask: np.ndarray, chain: dict[int, float], rad: int) -> dict[int, float]:
    """Subgrade under a traced finished-grade line: the LOWEST template stroke
    within `rad` px below it -- the bottom of the pavement box (or curb)
    where there is one, the line itself where there isn't (shoulders, side
    slopes, ditches are drawn as a single line). A stroke that runs on past
    `rad` -- a guardrail post, a wall face -- is not pavement and ends the
    search."""
    out = {}
    H = mask.shape[0]
    for x, y in chain.items():
        y0 = int(round(y))
        lo, hi = max(0, y0 - 2), min(H, y0 + rad + 1)
        col = np.where(mask[lo:hi, x])[0]
        best = y
        for a, b in runs1d(col + lo, tol=1):
            if b < y0 - 2:
                continue
            if b >= hi - 1:            # runs on beyond reach
                break
            best = (a + b) / 2.0
        out[x] = float(best)
    return out


def despike(y: np.ndarray, win: int, thresh_px: float) -> tuple[np.ndarray, int]:
    """Reject outliers only -- do NOT smooth. Leader lines, witness ticks and
    dimension arrows that survived the glyph filter show up as isolated jumps;
    genuine break-points (ditch invert, catch point, shoulder hinge) must come
    through untouched, so flagged samples are replaced by interpolation from
    their good neighbours rather than by a filtered value."""
    ok = ~np.isnan(y)
    idx = np.where(ok)[0]
    if len(idx) < win:
        return y, 0
    v = y[idx].copy()
    bad = np.abs(v - median_filter(v, size=win, mode="nearest")) > thresh_px
    if bad.any() and (~bad).sum() >= 2:
        v[bad] = np.interp(idx[bad], idx[~bad], v[~bad])
    out = y.copy()
    out[idx] = v
    return out, int(bad.sum())


def trim_buried_tail(x: np.ndarray, gpx: np.ndarray, dpx: np.ndarray, ppf: float,
                      run_ft: float, depth_ft: float, end_ft: float = 1.0):
    """Temporary pipes and other buried services run on past the template's toe.
    They read as a LONG, DEEP run of 'proposed below existing' that reaches the
    end of the chain and STOPS THERE, still inside the ground. A graded cut
    can be just as long and deep, but its back slope climbs out and ends on
    the ground at the catch point -- so a run is only trimmed when the chain
    ends more than `end_ft` below existing ground."""
    ov = ~np.isnan(gpx) & ~np.isnan(dpx)
    if ov.sum() < 10:
        return dpx, []
    c = np.where(ov)[0]
    xx = x[c]
    d = (gpx[c] - dpx[c]) / ppf
    sign = np.sign(np.where(np.abs(d) < 0.10, 0, d))
    runs, i = [], 0
    while i < len(d):
        if sign[i] < 0:
            j = i
            while j < len(d) and sign[j] <= 0:
                j += 1
            runs.append((i, j - 1, xx[j - 1] - xx[i], float(-d[i:j].min())))
            i = j
        else:
            i += 1
    out = dpx.copy()
    killed = []
    for a, b, L, dep in runs:
        if L < run_ft or dep < depth_ft:
            continue
        if xx[-1] - xx[b] <= 2.0 and -d[-1] > end_ft:
            out[c[a]:] = np.nan
            killed.append(dict(side="right", x_from=round(float(xx[a]), 2),
                                x_to=round(float(xx[-1]), 2),
                                run_ft=round(float(L), 1), depth_ft=round(dep, 2)))
        elif xx[a] - xx[0] <= 2.0 and -d[0] > end_ft:
            out[:c[b] + 1] = np.nan
            killed.append(dict(side="left", x_from=round(float(xx[0]), 2),
                                x_to=round(float(xx[b]), 2),
                                run_ft=round(float(L), 1), depth_ft=round(dep, 2)))
    return out, killed


def refine_gaps(chain: dict[int, float], full_mask: np.ndarray, ppf: float,
                 min_gap_ft: float, tol_px: float):
    """Inside a long interpolation gap the surface's own dashes usually still
    exist -- they were simply absorbed into a solid component they touch, so the
    dash/solid split never offered them. Re-hunt for ink near the interpolated
    path in the FULL mask and accept it when it is close enough to be the same
    surface. This is a recall pass, not a smoother: it only ever adds points."""
    if len(chain) < 2:
        return chain, 0
    xs = np.array(sorted(chain))
    ys = np.array([chain[x] for x in xs])
    add = {}
    for i in np.where(np.diff(xs) / ppf > min_gap_ft)[0]:
        a, b, ya, yb = xs[i], xs[i + 1], ys[i], ys[i + 1]
        for x in range(a + 1, b):
            yp = ya + (yb - ya) * (x - a) / (b - a)
            col = np.where(full_mask[:, x])[0]
            if not len(col):
                continue
            best = min(((s_ + e) / 2 for s_, e in runs1d(col, tol=2)), key=lambda c: abs(c - yp))
            if abs(best - yp) <= tol_px:
                add[x] = best
    out = dict(chain)
    out.update(add)
    return out, len(add)


def interp_spans(chain: dict[int, float], W: int, ppf: float, warn_ft: float):
    """Boolean per column: True where the surface is only a straight-line guess
    across a gap wider than `warn_ft`. Area computed there is not supported by
    ink and is reported separately rather than quietly folded into the total."""
    m = np.zeros(W, bool)
    if len(chain) < 2:
        return m, 0.0
    xs = np.array(sorted(chain))
    d = np.diff(xs) / ppf
    for i in np.where(d > warn_ft)[0]:
        m[xs[i]:xs[i + 1] + 1] = True
    return m, float(d.max()) if len(d) else 0.0


def densify(chain: dict[int, float], W: int) -> np.ndarray:
    """Chain -> dense per-column array, linearly interpolated, NaN outside."""
    g = np.full(W, np.nan)
    if not chain:
        return g
    xs = np.array(sorted(chain))
    ys = np.array([chain[x] for x in xs])
    grid = np.arange(W)
    m = (grid >= xs[0]) & (grid <= xs[-1])
    g[m] = np.interp(grid[m], xs, ys)
    return g


def split_chain(chain: dict[int, float], max_gap: int) -> list[dict[int, float]]:
    """Break a traced chain wherever consecutive points are more than
    `max_gap` columns apart."""
    if not chain:
        return []
    xs = sorted(chain)
    pieces, cur = [], {xs[0]: chain[xs[0]]}
    for a, b in zip(xs, xs[1:]):
        if b - a > max_gap:
            pieces.append(cur)
            cur = {}
        cur[b] = chain[b]
    pieces.append(cur)
    return pieces


def drop_structures(pieces: list[dict[int, float]], ground: np.ndarray, ppf: float,
                    tie_ft: float = 2.0, min_len_ft: float = 2.0):
    """Keep the pieces of the design line that are earthwork.

    A roadway template always meets existing ground through its side slopes
    (or a wall). A bridge deck, a culvert top or a sign structure is drawn
    with the same solid pen but hangs ABOVE the ground at both of its ends.
    Measuring "fill" under it would count air as embankment, so such pieces
    are dropped and reported. Slivers too short to be a surface are dropped
    silently. Returns (kept pieces, notes)."""
    kept, notes = [], []
    for pc in pieces:
        xs = sorted(pc)
        if (xs[-1] - xs[0]) / ppf < min_len_ft:
            continue
        floating = 0
        for x in (xs[0], xs[-1]):
            g = ground[x] if 0 <= x < len(ground) else np.nan
            if not np.isnan(g) and (g - pc[x]) / ppf > tie_ft:   # design above ground, untied
                floating += 1
        if floating == 2:
            notes.append(dict(x_from=xs[0], x_to=xs[-1]))
            continue
        kept.append(pc)
    return kept, notes


def fill_along_gridlines(chain: dict[int, float], grid_rows: list[float], min_gap: int,
                         tol: float = 9.0) -> dict[int, float]:
    """A drawn line running along (or crossing at a shallow angle) a grid
    line is erased together with the grid -- a pavement surface sitting at a
    round elevation such as 660.00 is the common case. When a gap in the
    traced chain starts and ends close to the same grid row, the gap was
    made by grid removal, not by the drawing: bridge it straight."""
    if len(chain) < 2 or not grid_rows:
        return chain
    rows = np.asarray(grid_rows, float)
    xs = sorted(chain)
    out = dict(chain)
    for a, b in zip(xs, xs[1:]):
        if b - a <= min_gap:
            continue
        ya, yb = chain[a], chain[b]
        r = rows[np.argmin(np.abs(rows - (ya + yb) / 2))]
        if abs(ya - r) <= tol and abs(yb - r) <= tol:
            for x in range(a + 1, b):
                out[x] = ya + (yb - ya) * (x - a) / (b - a)
    return out


def template_strokes(solid: np.ndarray, link_px: int, min_px: int) -> np.ndarray:
    """Keep the solid strokes that make up the roadway template.

    The template (pavement, shoulders, side slopes, ditches) is one network
    of strokes that touch or nearly touch. Leader lines, utility callouts and
    label underlines are drawn with the same solid pen but stand apart from
    it, and they are short. Group strokes lying within `link_px` of each
    other and keep only the wide groups: the widest one, plus any other spanning at
    least 30 % of it (a second roadway beyond a median, the far side of a
    structure) and at least `min_px`."""
    if not solid.any():
        return solid
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (link_px, link_px))
    n, lab, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(solid, k), 8)
    if n <= 2:
        return solid
    widths = st[1:, cv2.CC_STAT_WIDTH] - link_px
    cut = max(0.3 * widths.max(), min_px)
    keep = np.zeros(n, bool)
    keep[1:] = widths >= cut
    if not keep.any():
        keep[1 + int(np.argmax(widths))] = True
    return np.where(keep[lab], solid, 0).astype(solid.dtype)


def ground_candidates(dash: np.ndarray, template: np.ndarray, hidden_weight: float):
    """Candidate points for tracing existing ground: its own dashes, plus the
    template's strokes at a fraction of the reward. Dashed ground that slips
    behind the solid template (where the two coincide, e.g. widening onto
    existing pavement) leaves no dashes of its own; following the template
    there beats bridging blind in a straight line, while anywhere real dashes
    exist they win."""
    cd, ct = candidates(dash), candidates(template)
    cands = [a + b for a, b in zip(cd, ct)]
    weights = [[1.0] * len(a) + [hidden_weight] * len(b) for a, b in zip(cd, ct)]
    return cands, weights


def drop_rulers(solid: np.ndarray, min_len: int, max_rise: int = 4) -> np.ndarray:
    """Remove dead-straight horizontal strokes longer than `min_len`: border
    and grid remnants, axis lines, title rules. A drawn surface is never that
    flat for that long (a 2 % cross slope alone rises several pixels over
    40 ft). Tick marks hanging off an axis are ignored when judging flatness
    -- only the horizontal structure is measured -- and removed with it."""
    if not solid.any():
        return solid
    horiz = cv2.morphologyEx(solid, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1)))
    n, lab, st, _ = cv2.connectedComponentsWithStats(horiz, 8)
    ruler = np.zeros(n, bool)
    ruler[1:] = (st[1:, cv2.CC_STAT_WIDTH] >= min_len) & (st[1:, cv2.CC_STAT_HEIGHT] <= max_rise)
    if not ruler.any():
        return solid
    kill = ruler[lab].astype(np.uint8)
    # take the ticks attached to a ruler with it
    kill = cv2.dilate(kill, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    n2, lab2, _, _ = cv2.connectedComponentsWithStats(solid, 8)
    hit = np.unique(lab2[(kill > 0) & (solid > 0)])
    gone = np.zeros(n2, bool)
    gone[hit[hit > 0]] = True
    # only drop whole components that are mostly ruler (keep a template that
    # merely touches an axis line, minus the line itself)
    out = solid.copy()
    for k in np.where(gone)[0]:
        comp = lab2 == k
        if (comp & (kill > 0)).sum() >= 0.5 * comp.sum():
            out[comp] = 0
        else:
            out[comp & (kill > 0)] = 0
    return out
