// Left / right of the centreline, the same rules as the server
// (backend/gdot_earthwork/sides.py), so edits show their split before saving.

const SIDES = ['left', 'right'];
const r2 = (v) => Math.round(v * 100) / 100 + 0;

function clip(poly, x, keepLeft) {
  const inside = (p) => (keepLeft ? p[0] <= x : p[0] >= x);
  const cross = (a, b) => [x, a[1] + ((x - a[0]) / (b[0] - a[0])) * (b[1] - a[1])];
  const out = [];
  poly.forEach((cur, i) => {
    const prev = poly[(i - 1 + poly.length) % poly.length];
    if (inside(cur)) {
      if (!inside(prev)) out.push(cross(prev, cur));
      out.push(cur);
    } else if (inside(prev)) out.push(cross(prev, cur));
  });
  return out;
}

function area(poly) {
  let a = 0;
  for (let i = 0; i < poly.length; i++) {
    const [x1, y1] = poly[i], [x2, y2] = poly[(i + 1) % poly.length];
    a += x1 * y2 - x2 * y1;
  }
  return poly.length > 2 ? Math.abs(a) / 2 : 0;
}

/** An outlined area's ft² left and right of the centreline (image x = cx). */
export function polygonSides(pts, cx, pxPerFt) {
  const k = pxPerFt * pxPerFt;
  return { left: r2(area(clip(pts, cx, true)) / k), right: r2(area(clip(pts, cx, false)) / k) };
}

/** How removed traced area divides between the sides, column by column. */
export function removalSides(ft2, shares) {
  return { left: r2(ft2 * shares.left), right: r2(ft2 - r2(ft2 * shares.left)) };
}

/**
 * Left / right fill and cut for the areas in use: traced zones stretched by
 * the same factor on both sides, minus what was removed on each side, plus
 * outlined areas on the side they lie. `unplaced` is area typed where no
 * zone of that kind was traced, which belongs to neither side.
 */
export function currentSides(measured, measuredTotal, area, marks = []) {
  if (!measured) return null;
  const out = { left: {}, right: {}, unplaced: {} };
  for (const kind of ['fill', 'cut']) {
    const key = `${kind}_ft2`;
    const added = marks.filter((m) => m.kind === kind);
    const removed = marks.filter((m) => m.kind === `remove_${kind}`);
    const base = Math.max(0, area[key] - added.reduce((n, m) => n + m.ft2, 0));
    const left = measuredTotal[key] - removed.reduce((n, m) => n + m.ft2, 0);
    const k = measuredTotal[key] > 0 ? (left > 0.005 ? base / left : 0) : null;
    out.unplaced[key] = k === null ? r2(base) : 0;
    for (const side of SIDES) {
      const traced = measured[side][key] - removed.reduce((n, m) => n + (m.sides?.[side] || 0), 0);
      out[side][key] = r2(Math.max(0, traced) * (k ?? 0) + added.reduce((n, m) => n + (m.sides?.[side] || 0), 0));
    }
  }
  return out;
}

export const CENTRE_NOTE = {
  neighbour: 'Centreline taken from the neighbouring section (this section’s offset axis could not be read).',
  assumed: 'Centreline assumed at the middle of the grid (the offset axis could not be read).',
};
