import { useEffect, useMemo, useRef, useState } from 'react';
import { ft2, stationLabel } from '../format';

const H = 280;
const M = { top: 16, right: 64, bottom: 30, left: 56 };

function niceStep(range, target) {
  const raw = range / Math.max(1, target);
  const mag = 10 ** Math.floor(Math.log10(raw || 1));
  const n = raw / mag;
  return (n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10) * mag;
}

/**
 * Cross-section areas along the road (fill up, cut down) with the mass
 * curve -- cumulative cut minus fill volume -- on the right axis. Click a bar
 * to open that section.
 */
export default function ProfileChart({ sections, selectedId, onSelect }) {
  const box = useRef(null);
  const [width, setWidth] = useState(900);
  const [hover, setHover] = useState(null);


  const pts = sections.filter((s) => s.station_ft != null);
  const geo = useMemo(() => {
    if (pts.length === 0) return null;
    const x0 = Math.min(...pts.map((s) => s.station_ft));
    const x1 = Math.max(...pts.map((s) => s.station_ft));
    const span = Math.max(x1 - x0, 1);
    const maxFill = Math.max(1, ...pts.map((s) => s.fill_ft2));
    const maxCut = Math.max(1, ...pts.map((s) => s.cut_ft2));
    // mass curve: cumulative (cut - fill) by average end area, in cubic yards
    let acc = 0;
    const mass = pts.map((s, i) => {
      if (i > 0) {
        const p = pts[i - 1];
        const L = s.station_ft - p.station_ft;
        acc += (((p.cut_ft2 + s.cut_ft2) - (p.fill_ft2 + s.fill_ft2)) / 2) * L / 27;
      }
      return acc;
    });
    const mMin = Math.min(0, ...mass), mMax = Math.max(0, ...mass);
    return { x0, span, maxFill, maxCut, mass, mMin, mMax };
  }, [pts]);

  // follow the container's width so the chart redraws crisply on resize
  const hasChart = geo !== null;
  useEffect(() => {
    const el = box.current;
    if (!el) return undefined;
    const update = () => setWidth((w) => (Math.abs(el.clientWidth - w) > 2 ? el.clientWidth : w));
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [hasChart]);

  if (!geo) return <div className="empty">No stationed sections on this road.</div>;

  const W = Math.max(320, width);
  const pw = W - M.left - M.right, ph = H - M.top - M.bottom;
  const zeroY = M.top + ph * (geo.maxFill / (geo.maxFill + geo.maxCut));
  const ay = (ph) / (geo.maxFill + geo.maxCut);           // px per ft^2
  const sx = (ft) => M.left + ((ft - geo.x0) / geo.span) * pw;
  const mRange = geo.mMax - geo.mMin || 1;
  const my = (v) => M.top + ((geo.mMax - v) / mRange) * ph;
  const minGap = pts.length > 1 ? Math.min(...pts.slice(1).map((s, i) => sx(s.station_ft) - sx(pts[i].station_ft))) : pw;
  const bw = Math.max(2, Math.min(22, minGap * 0.7));

  const xStep = niceStep(geo.span, Math.max(3, Math.floor(pw / 110)));
  const xTicks = [];
  for (let t = Math.ceil(geo.x0 / xStep) * xStep; t <= geo.x0 + geo.span + 1e-6; t += xStep) xTicks.push(t);
  const aStep = niceStep(geo.maxFill + geo.maxCut, 5);
  const aTicks = [];
  for (let t = -Math.floor(geo.maxCut / aStep) * aStep; t <= geo.maxFill; t += aStep) aTicks.push(t);
  const mStep = niceStep(mRange, 4);
  const mTicks = [];
  for (let t = Math.ceil(geo.mMin / mStep) * mStep; t <= geo.mMax + 1e-6; t += mStep) mTicks.push(t);

  const massPath = pts.map((s, i) => `${i ? 'L' : 'M'}${sx(s.station_ft).toFixed(1)},${my(geo.mass[i]).toFixed(1)}`).join('');
  const hov = hover != null ? pts[hover] : null;

  return (
    <div ref={box} className="chart-wrap" style={{ position: 'relative' }}>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label="Cross-section fill and cut areas along the road, with the mass curve">
        {aTicks.map((t) => (
          <g key={`a${t}`}>
            <line className="grid" x1={M.left} x2={M.left + pw} y1={zeroY - t * ay} y2={zeroY - t * ay} />
            <text x={M.left - 8} y={zeroY - t * ay + 4} textAnchor="end">{Math.abs(t)}</text>
          </g>
        ))}
        {mTicks.map((t) => (
          <text key={`m${t}`} x={M.left + pw + 8} y={my(t) + 4} style={{ fill: 'var(--mass)' }}>{Math.round(t).toLocaleString()}</text>
        ))}
        {xTicks.map((t) => (
          <text key={`x${t}`} x={sx(t)} y={H - 10} textAnchor="middle">{stationLabel(t)}</text>
        ))}
        <text x={14} y={M.top + 8} transform={`rotate(-90 14 ${M.top + 8})`} textAnchor="end">ft²  fill ↑  cut ↓</text>

        {pts.map((s, i) => {
          const x = sx(s.station_ft);
          return (
            <g key={s.id}>
              {s.id === selectedId && <rect className="sel" x={x - bw / 2 - 3} y={M.top} width={bw + 6} height={ph} rx="3" />}
              <rect className="bar-fill" x={x - bw / 2} y={zeroY - s.fill_ft2 * ay} width={bw} height={s.fill_ft2 * ay} rx="1.5" />
              <rect className="bar-cut" x={x - bw / 2} y={zeroY} width={bw} height={s.cut_ft2 * ay} rx="1.5" />
              {s.edited && <circle className={`edit-dot ${s.dirty ? 'dirty' : ''}`} cx={x} cy={M.top + 5} r="3.5" />}
              <rect className="bar-hit" x={x - Math.max(bw, 8) / 2} y={M.top} width={Math.max(bw, 8)} height={ph}
                onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onClick={() => onSelect(s.id)} />
            </g>
          );
        })}
        <line className="axis" x1={M.left} x2={M.left + pw} y1={zeroY} y2={zeroY} />
        <path className="mass" d={massPath} />
      </svg>
      {hov && (
        <div style={{
          position: 'absolute', left: Math.min(W - 190, Math.max(0, sx(hov.station_ft) + 12)), top: 12,
          background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 8, padding: '8px 10px',
          boxShadow: 'var(--shadow)', fontSize: 12.5, pointerEvents: 'none', minWidth: 170,
        }}>
          <b className="mono">{hov.station}</b> <span className="muted">page {hov.page}</span>
          <div className="num fill-text">fill {ft2(hov.fill_ft2)} ft²</div>
          <div className="num cut-text">cut {ft2(hov.cut_ft2)} ft²</div>
          {hov.edited && (
            <div className="muted" style={{ marginTop: 4 }}>
              {hov.dirty ? 'unsaved edit' : 'edited'} · measured {ft2(hov.measured.fill_ft2)} / {ft2(hov.measured.cut_ft2)}
            </div>
          )}
        </div>
      )}
      <div className="legend">
        <span><i style={{ background: 'var(--fill)' }} />fill area</span>
        <span><i style={{ background: 'var(--cut)' }} />cut area</span>
        <span><i style={{ background: 'var(--mass)', height: 2, verticalAlign: 3 }} />mass curve (cumulative cut − fill, cy)</span>
        {sections.some((s) => s.edited) && <span><i style={{ background: 'var(--yellow)', borderRadius: '50%' }} />edited by hand</span>}
      </div>
    </div>
  );
}
