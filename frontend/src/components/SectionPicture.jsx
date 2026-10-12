import { useEffect, useMemo, useState } from 'react';
import { assetUrl, getProfile } from '../api';
import { ft2 } from '../format';

/**
 * Fill and cut zones between the existing ground and the proposed surface,
 * from the traced lines (image pixels). Each point keeps its depth d
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

const pt = ([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`;

/** Area of a polygon of image pixels, in ft². */
export function polygonFt2(pts, pxPerFt) {
  let a = 0;
  for (let i = 0; i < pts.length; i++) {
    const [x1, y1] = pts[i], [x2, y2] = pts[(i + 1) % pts.length];
    a += x1 * y2 - x2 * y1;
  }
  return Math.abs(a) / 2 / (pxPerFt * pxPerFt);
}

const markSum = (marks, kind) => marks.filter((m) => m.kind === kind).reduce((n, m) => n + m.ft2, 0);

/** A section's traced lines in its image's pixels, or null while loading. */
export function useProfile(url) {
  const [prof, setProf] = useState(null);
  useEffect(() => {
    let live = true;
    setProf(null);
    if (url) getProfile(url).then((p) => { if (live) setProf(p); }).catch(() => {});
    return () => { live = false; };
  }, [url]);
  return prof;
}

/**
 * Solid fill / cut shading for an SVG laid over the section image. The
 * traced zones carry whatever the outlined areas (marks) don't: each zone's
 * depth is stretched by (area − marked) / measured, so the shaded area always
 * equals the numbers in use.
 */
export function Shading({ prof, surface, fill, cut, measured, marks = [], selected = -1, onMarkClick }) {
  const zs = useMemo(() => (prof ? zones(prof, surface) : []), [prof, surface]);
  const k = {
    fill: measured.fill_ft2 > 0 ? Math.max(0, fill - markSum(marks, 'fill')) / measured.fill_ft2 : 1,
    cut: measured.cut_ft2 > 0 ? Math.max(0, cut - markSum(marks, 'cut')) / measured.cut_ft2 : 1,
  };
  return (
    <>
      {zs.map((z, i) => {
        if (k[z.kind] === 0) return null;
        const top = z.pts.map(([x, g, d]) => [x, g - d * k[z.kind]]);
        return <polygon key={`z${i}`} className={`zone ${z.kind}`}
          points={[...top, ...z.pts.slice().reverse()].map(pt).join(' ')} />;
      })}
      {marks.map((m, i) => (
        <polygon key={`m${i}`} className={`zone mark ${m.kind} ${i === selected ? 'selected' : ''}`}
          points={m.pts.map(pt).join(' ')}
          onClick={onMarkClick ? (e) => { e.stopPropagation(); onMarkClick(i); } : undefined} />
      ))}
    </>
  );
}

/** Fill / cut typed in where nothing on the drawing can be shaded for it. */
export function unplacedText(fill, cut, measured, marks) {
  const out = [];
  if (fill - markSum(marks, 'fill') > 0.05 && !(measured.fill_ft2 > 0)) out.push(`fill ${ft2(fill - markSum(marks, 'fill'))} ft²`);
  if (cut - markSum(marks, 'cut') > 0.05 && !(measured.cut_ft2 > 0)) out.push(`cut ${ft2(cut - markSum(marks, 'cut'))} ft²`);
  return out.length ? `${out.join(' and ')} typed in with no such zone on the drawing to shade: counted, not drawn. Outline it with the area tool to show it.` : null;
}

/** The section drawing with fill and cut shaded from the areas in use. */
export default function SectionPicture({ section: s, surface, alt }) {
  const prof = useProfile(s.profile);
  const measured = s.measured || { fill_ft2: s.fill_ft2, cut_ft2: s.cut_ft2 };
  const note = unplacedText(s.fill_ft2, s.cut_ft2, measured, s.marks || []);
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
            <Shading prof={prof} surface={surface} fill={s.fill_ft2} cut={s.cut_ft2} measured={measured} marks={s.marks || []} />
          </svg>
        )}
      </div>
      {note && <div className="pic-note">{note}</div>}
    </div>
  );
}
