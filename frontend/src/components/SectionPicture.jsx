import { useEffect, useMemo, useState } from 'react';
import { assetUrl, getProfile } from '../api';
import { ft2 } from '../format';

/**
 * Fill and cut zones between the existing ground and the proposed surface,
 * from the traced lines (overlay pixels). Each point keeps its depth d
 * (ground row minus surface row: + = fill), so a zone can be drawn at any
 * scale of that depth -- the same column-wise rule the areas are measured by.
 */
function zones(prof, surface) {
  const { x, ground: g } = prof;
  const t = prof[surface] || prof.finished;
  const out = [];
  let cur = null;
  const close = () => { if (cur && cur.pts.length > 1) out.push(cur); cur = null; };
  for (let i = 0; i < x.length; i++) {
    if (g[i] == null || t[i] == null) { close(); continue; }
    const d = g[i] - t[i];
    const kind = d > 0.05 ? 'fill' : d < -0.05 ? 'cut' : null;
    if (cur && kind !== cur.kind) {
      // where the lines cross, end this zone (and start the next) on the crossing
      const j = i - 1;
      if (g[j] != null && t[j] != null) {
        const dj = g[j] - t[j];
        const u = dj / (dj - d);
        const xc = x[j] + u * (x[i] - x[j]), gc = g[j] + u * (g[i] - g[j]);
        cur.pts.push([xc, gc, 0]);
        close();
        if (kind) cur = { kind, pts: [[xc, gc, 0]] };
      } else close();
    }
    if (kind) {
      if (!cur) cur = { kind, pts: [] };
      cur.pts.push([x[i], g[i], d]);
    }
  }
  close();
  return out;
}

const pt = (x, y) => `${x.toFixed(1)},${y.toFixed(1)}`;

/**
 * The section drawing with fill and cut shaded on top. The shading follows
 * the areas in use -- measured, or typed in by the user -- by stretching each
 * traced zone's depth in proportion, so the shaded area always matches the
 * numbers next to it.
 */
export default function SectionPicture({ section: s, surface, alt }) {
  const [prof, setProf] = useState(null);
  useEffect(() => {
    let live = true;
    setProf(null);
    if (s.profile) getProfile(s.profile).then((p) => { if (live) setProf(p); }).catch(() => {});
    return () => { live = false; };
  }, [s.profile]);

  const zs = useMemo(() => (prof ? zones(prof, surface) : []), [prof, surface]);
  const m = s.measured || { fill_ft2: s.fill_ft2, cut_ft2: s.cut_ft2 };
  const k = {
    fill: m.fill_ft2 > 0 ? s.fill_ft2 / m.fill_ft2 : 1,
    cut: m.cut_ft2 > 0 ? s.cut_ft2 / m.cut_ft2 : 1,
  };
  // areas typed in where the drawing has no zone of that kind to stretch
  const unplaced = [
    s.fill_ft2 > 0 && !(m.fill_ft2 > 0) && `fill ${ft2(s.fill_ft2)} ft²`,
    s.cut_ft2 > 0 && !(m.cut_ft2 > 0) && `cut ${ft2(s.cut_ft2)} ft²`,
  ].filter(Boolean);

  return (
    <div className="viewer-img">
      <div className="pic-areas">
        <span className="chip fill">Fill {ft2(s.fill_ft2)} ft²</span>
        <span className="chip cut">Cut {ft2(s.cut_ft2)} ft²</span>
        {s.edited && <span className={`chip ${s.dirty ? 'warn' : 'edited'}`}>{s.dirty ? 'unsaved edit' : 'edited'}</span>}
      </div>
      <div className="pic">
        <img src={assetUrl(s.overlay)} alt={alt} />
        {prof && (
          <svg className="pic-shade" viewBox={`0 0 ${prof.size[0]} ${prof.size[1]}`} preserveAspectRatio="none" aria-hidden="true">
            {zs.map((z, i) => {
              const top = z.pts.map(([x, g, d]) => [x, g - d * k[z.kind]]);
              const poly = [...top.map(([x, y]) => pt(x, y)), ...z.pts.slice().reverse().map(([x, g]) => pt(x, g))].join(' ');
              return (
                <g key={i} className={`zone ${z.kind}`}>
                  <polygon points={poly} />
                  {s.edited && k[z.kind] !== 1 && <polyline points={top.map(([x, y]) => pt(x, y)).join(' ')} />}
                </g>
              );
            })}
          </svg>
        )}
      </div>
      {unplaced.length > 0 && (
        <div className="pic-note">
          Typed in: {unplaced.join(' and ')}. The drawing has no such zone at this station to shade, so it is counted
          but not drawn.
        </div>
      )}
    </div>
  );
}
