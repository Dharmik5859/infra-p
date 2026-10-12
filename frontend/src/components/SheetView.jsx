import { useEffect, useMemo, useRef, useState } from 'react';
import { assetUrl, getSheet } from '../api';
import { ft2 } from '../format';
import { usePanZoom } from '../panzoom';
import { isRemoval, zoneScale } from './SectionPicture';

const sub = (a, b) => [a[0] - b[0], a[1] - b[1]];
const add = (a, b) => [a[0] + b[0], a[1] + b[1]];
const pts = (list) => list.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');

/** A section's frame on the sheet: its four corners and bounding box. */
function frameOf(g) {
  const [tl, tr, bl] = g.frame;
  const br = add(tr, sub(bl, tl));
  const corners = [tl, tr, br, bl];
  const xs = corners.map((p) => p[0]), ys = corners.map((p) => p[1]);
  const x = Math.min(...xs), y = Math.min(...ys);
  return { corners, box: { x, y, w: Math.max(...xs) - x, h: Math.max(...ys) - y } };
}

/** Section-image pixel -> sheet point, through the image's placed corners. */
function imageToSheet(g) {
  if (!g.canvas || !g.image_size) return null;
  const [o, a, b] = g.canvas;
  const [w, h] = g.image_size;
  return ([x, y]) => [o[0] + (a[0] - o[0]) * x / w + (b[0] - o[0]) * y / h, o[1] + (a[1] - o[1]) * x / w + (b[1] - o[1]) * y / h];
}

/**
 * Fill / cut zones of one section on the sheet: runs where the proposed
 * surface is above (fill) or below (cut) the ground, measured along the
 * frame's "up", each stretched by k so the shading matches the areas in use
 * (the same rule as the section picture and the PDF export).
 */
function sheetZones(g, surface, k) {
  const ground = g.ground, top = g[surface] || g.finished;
  const [tl, , bl] = g.frame;
  const v = sub(tl, bl), len = Math.hypot(v[0], v[1]) || 1;
  const up = [v[0] / len, v[1] / len];
  const out = [];
  let run = [], sign = 0;
  const flush = () => {
    if (run.length >= 2 && k[sign > 0 ? 'fill' : 'cut'] > 0) {
      const kk = k[sign > 0 ? 'fill' : 'cut'];
      const upper = run.map((i) => add(ground[i], [(top[i][0] - ground[i][0]) * kk, (top[i][1] - ground[i][1]) * kk]));
      out.push({ kind: sign > 0 ? 'fill' : 'cut', points: [...upper, ...run.slice().reverse().map((i) => ground[i])] });
    }
  };
  for (let i = 0; i < ground.length; i++) {
    let s = 0;
    if (ground[i] && top[i]) {
      const d = (top[i][0] - ground[i][0]) * up[0] + (top[i][1] - ground[i][1]) * up[1];
      s = d > 0.02 ? 1 : d < -0.02 ? -1 : 0;
    }
    if (s !== sign) {
      flush();
      run = run.length && s ? [run[run.length - 1]] : [];
      sign = s;
    }
    if (s) run.push(i);
  }
  flush();
  return out;
}

function SectionOnSheet({ g, sec, surface, selected, upp, onPick }) {
  const toSheet = useMemo(() => imageToSheet(g), [g]);
  const k = zoneScale(sec.measured, sec.fill_ft2, sec.cut_ft2, sec.marks || []);
  const zones = useMemo(() => sheetZones(g, surface, k), [g, surface, k.fill, k.cut]); // eslint-disable-line react-hooks/exhaustive-deps
  const { corners } = useMemo(() => frameOf(g), [g]);
  const marks = (sec.marks || []).filter(() => toSheet);
  const removals = marks.filter(isRemoval);
  const maskId = `sheet-rm-${g.id}`;
  const fs = 12 * upp;
  const [tl] = corners;
  return (
    <g className={`on-sheet ${selected ? 'selected' : ''}`}>
      {removals.length > 0 && (
        <defs>
          <mask id={maskId} maskUnits="userSpaceOnUse" x="-1e5" y="-1e5" width="2e5" height="2e5">
            <rect x="-1e5" y="-1e5" width="2e5" height="2e5" fill="#fff" />
            {removals.map((m, i) => <polygon key={i} points={pts(m.pts.map(toSheet))} fill="#000" />)}
          </mask>
        </defs>
      )}
      <g mask={removals.length ? `url(#${maskId})` : undefined}>
        {zones.map((z, i) => <polygon key={i} className={`zone ${z.kind}`} points={pts(z.points)} />)}
      </g>
      {marks.filter((m) => !isRemoval(m)).map((m, i) => (
        <polygon key={`m${i}`} className={`zone mark ${m.kind}`} points={pts(m.pts.map(toSheet))} />
      ))}
      <polygon className="frame-hit" points={pts(corners)} onClick={() => onPick(g.id)}>
        <title>{`${sec.station || 'no station'} — fill ${ft2(sec.fill_ft2)} ft², cut ${ft2(sec.cut_ft2)} ft²`}</title>
      </polygon>
      <text className="sheet-label" x={tl[0] + 6 * upp} y={tl[1] + fs * 1.4} style={{ fontSize: fs, strokeWidth: fs * 0.3 }}>
        <tspan className="st">{sec.station || 'no station'}</tspan>
        <tspan className="f" dx={fs * 0.6}>F {ft2(sec.fill_ft2)}</tspan>
        <tspan className="c" dx={fs * 0.5}>C {ft2(sec.cut_ft2)}</tspan>
      </text>
    </g>
  );
}

/**
 * The whole sheet of the original PDF with every measured cross-section on
 * it outlined and its cut / fill shaded. Click a section to select it; when
 * a section is picked elsewhere (chart, table, ← →), the view moves to its
 * sheet and zooms onto it.
 */
export default function SheetView({ jobId, section, sections, surface, onSelect }) {
  const [sheet, setSheet] = useState(null);
  const [error, setError] = useState(null);
  const svg = useRef(null), boxRef = useRef(null);
  const pz = usePanZoom(svg, boxRef, sheet?.size);
  const page = section.page;

  useEffect(() => {
    let live = true;
    setError(null);
    getSheet(jobId, page).then((s) => { if (live) setSheet(s); }).catch((e) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [jobId, page]);

  const here = sheet && sheet.page === page ? sheet : null;
  const geom = here?.sections.find((g) => g.id === section.id);
  const pageFit = here ? { x: 0, y: 0, w: here.size[0], h: here.size[1] } : null;

  // move onto the selected section whenever it (or its sheet) changes
  useEffect(() => {
    if (!here || !pz.box) return;
    if (geom) pz.fit(frameOf(geom).box, 0.08); else pz.fit(pageFit, 0.01);
  }, [here, section.id, pz.box?.w > 0]); // eslint-disable-line react-hooks/exhaustive-deps

  const pages = useMemo(() => [...new Set(sections.map((s) => s.page))].sort((a, b) => a - b), [sections]);
  const pi = pages.indexOf(page);
  const goPage = (p) => {
    const first = sections.filter((s) => s.page === p).sort((a, b) => a.id - b.id)[0];
    if (first) onSelect(first.id);
  };
  const zoomPct = pz.view && pageFit ? Math.round((pageFit.w / pz.view.w) * 100) : 100;
  const v = pz.view;

  return (
    <div className="sheet-card">
      <div className="pic-toolbar">
        <div className="pager" role="group" aria-label="Sheets">
          <button className="btn icon-btn small" onClick={() => goPage(pages[pi - 1])} disabled={pi <= 0} aria-label="Previous sheet">‹</button>
          <span className="num">Sheet {page} <span className="muted">· {pi + 1} of {pages.length} with sections</span></span>
          <button className="btn icon-btn small" onClick={() => goPage(pages[pi + 1])} disabled={pi < 0 || pi >= pages.length - 1} aria-label="Next sheet">›</button>
        </div>
        <span className="spacer" />
        <div className="zoom" role="group" aria-label="Zoom">
          <button className="btn icon-btn small" onClick={() => v && pz.zoomAt(1.4, v.x + v.w / 2, v.y + v.h / 2)} aria-label="Zoom out">−</button>
          <span className="num">{zoomPct}%</span>
          <button className="btn icon-btn small" onClick={() => v && pz.zoomAt(1 / 1.4, v.x + v.w / 2, v.y + v.h / 2)} aria-label="Zoom in">+</button>
        </div>
        <button className="btn small" onClick={() => pz.fit(pageFit, 0.01)} disabled={!pageFit}>Whole sheet</button>
        <button className="btn small" onClick={() => geom && pz.fit(frameOf(geom).box, 0.08)} disabled={!geom}>This section</button>
      </div>
      <div className="sheet-frame" ref={boxRef}>
        {error && <div className="empty">Could not load the sheet: {error}</div>}
        {here && v && (
          <svg ref={svg} className={`sheet-svg ${pz.panning ? 'panning' : ''}`} viewBox={`${v.x} ${v.y} ${v.w} ${v.h}`}
            {...pz.handlers} onClickCapture={(e) => { if (pz.wasDrag()) e.stopPropagation(); }}
            role="img" aria-label={`Sheet ${page} of the plan set with each measured cross-section outlined`}>
            <image href={assetUrl(here.image)} x="0" y="0" width={here.size[0]} height={here.size[1]} preserveAspectRatio="none" />
            {here.sections.map((g) => sections[g.id] && (
              <SectionOnSheet key={g.id} g={g} sec={sections[g.id]} surface={surface} selected={g.id === section.id}
                upp={pz.upp} onPick={onSelect} />
            ))}
          </svg>
        )}
        {!here && !error && <div className="empty">Loading sheet {page}…</div>}
        <div className="canvas-hint">Click a section to select it · drag to move · scroll to zoom</div>
      </div>
    </div>
  );
}
