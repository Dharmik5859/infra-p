// Average-end-area volumes, the same formula the server uses
// (backend/gdot_earthwork/volume.py), so unsaved edits preview exactly:
//   V = (A1 + A2) / 2 * L   [ft³ -> yd³]

const r1 = (v) => Math.round(v * 10) / 10 + 0;
const r2 = (v) => Math.round(v * 100) / 100 + 0;

/** Recompute a road's volumes from its sections' current areas.
 * `serverVolumes` supplies the per-segment warnings (they depend only on
 * station spacing, which edits never change). */
export function roadVolumes(sections, serverVolumes) {
  const ordered = sections.filter((s) => s.station_ft != null).sort((a, b) => a.station_ft - b.station_ft);
  const warn = new Map((serverVolumes?.segments || []).map((g) => [`${g.from}|${g.to}`, g.warning]));
  let fill = 0, cut = 0;
  // the same average end areas, side by side of the centreline
  const side = { left: { fill: 0, cut: 0 }, right: { fill: 0, cut: 0 } };
  const segments = [];
  for (let i = 1; i < ordered.length; i++) {
    const a = ordered[i - 1], b = ordered[i];
    const L = b.station_ft - a.station_ft;
    // segments rounded to 0.01 cy and summed, exactly as the server does
    const f = r2(((a.fill_ft2 + b.fill_ft2) / 2) * L / 27);
    const c = r2(((a.cut_ft2 + b.cut_ft2) / 2) * L / 27);
    fill += f; cut += c;
    const sides = a.sides && b.sides ? {} : null;
    if (sides) {
      for (const sd of ['left', 'right']) {
        const sf = r2(((a.sides[sd].fill_ft2 + b.sides[sd].fill_ft2) / 2) * L / 27);
        const sc = r2(((a.sides[sd].cut_ft2 + b.sides[sd].cut_ft2) / 2) * L / 27);
        side[sd].fill += sf; side[sd].cut += sc;
        sides[sd] = { fill_cy: r1(sf), cut_cy: r1(sc) };
      }
    }
    segments.push({
      from: a.station, to: b.station, length_ft: Math.round(L * 100) / 100,
      fill_cy: r1(f), cut_cy: r1(c), net_cy: r1(f - c), sides,
      warning: warn.get(`${a.station}|${b.station}`) || null,
      edited: a.edited || b.edited,
    });
  }
  // cross-section areas summed over the road's stationed sections (ft²)
  const area = { fill: 0, cut: 0, left: { fill: 0, cut: 0 }, right: { fill: 0, cut: 0 } };
  for (const s of ordered) {
    area.fill += s.fill_ft2; area.cut += s.cut_ft2;
    for (const sd of ['left', 'right']) {
      area[sd].fill += s.sides?.[sd].fill_ft2 || 0;
      area[sd].cut += s.sides?.[sd].cut_ft2 || 0;
    }
  }
  const hasSides = ordered.length > 0 && ordered.every((s) => s.sides);
  return {
    fill_cy: r1(fill), cut_cy: r1(cut), net_cy: r1(fill - cut), segments,
    sides: hasSides ? {
      left: { fill_cy: r1(side.left.fill), cut_cy: r1(side.left.cut) },
      right: { fill_cy: r1(side.right.fill), cut_cy: r1(side.right.cut) },
    } : null,
    area,
  };
}
