import { useEffect, useMemo, useRef, useState } from 'react';
import { assetUrl } from '../api';
import { ft2 } from '../format';
import { AreaInput } from './AreaEditor';
import { CENTRE_NOTE, currentSides, polygonSides, removalSides } from '../sides';
import { Centreline, Shading, fitView, isRemoval, polygonFt2, shareInside, unplacedText, useProfile } from './SectionPicture';
import SideTable from './SideTable';
import { InfoTip } from './Ui';

const MARK_LABEL = { fill: 'Added fill', cut: 'Added cut', remove_fill: 'Removed fill', remove_cut: 'Removed cut' };
const r2 = (v) => Math.round(Math.max(0, v) * 100) / 100;

/**
 * Edit one cross-section in a large view. Type the fill / cut areas, or
 * outline an area on the drawing point by point and mark it Fill or Cut;
 * the shading follows every change. Reset goes back to what was measured,
 * Save stores the areas (and the outlined shapes) on the server.
 */
export default function EditSectionModal({ section: s, surface, onClose, onSave }) {
  const prof = useProfile(s.profile);
  const ppf = s.overlay_px_per_ft;
  const measured = s.measured;
  const [fill, setFill] = useState(s.fill_ft2);
  const [cut, setCut] = useState(s.cut_ft2);
  const [marks, setMarks] = useState(() => (s.marks || []).map((m) => ({ ...m })));
  const [pending, setPending] = useState([]);     // points of the outline being drawn
  const [closed, setClosed] = useState(false);    // the outline has been finished
  const [notice, setNotice] = useState(null);
  const [hover, setHover] = useState(null);       // cursor, image pixels
  const [selected, setSelected] = useState(-1);   // an outlined area picked to change or remove
  const [view, setView] = useState(null);        // visible part of the image {x, y, w, h}, image pixels
  const [box, setBox] = useState(null);          // canvas size on screen
  const canvas = useRef(null);
  const drag = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  // inputs are remounted when an action (Fill, Cut, Reset) sets their value
  const [rev, setRev] = useState(0);
  const svg = useRef(null);

  const pendingFt2 = pending.length >= 3 && ppf ? polygonFt2(pending, ppf) : 0;
  const cx = s.centreline?.x ?? (prof ? prof.size[0] / 2 : 0);
  const sides = currentSides(s.sides_measured?.[surface], measured, { fill_ft2: fill, cut_ft2: cut }, marks);
  const clearSelection = () => { setPending([]); setClosed(false); };
  const markedFill = marks.filter((m) => m.kind === 'fill').reduce((n, m) => n + m.ft2, 0);
  const markedCut = marks.filter((m) => m.kind === 'cut').reduce((n, m) => n + m.ft2, 0);
  const changed = Math.abs(fill - s.fill_ft2) > 0.005 || Math.abs(cut - s.cut_ft2) > 0.005
    || JSON.stringify(marks) !== JSON.stringify(s.marks || []);
  const note = unplacedText(fill, cut, measured, marks);

  // -------------------------------------------------------------- actions
  function mark(kind) {
    setNotice(null);
    if (pending.length >= 3) {
      const pts = pending.map(([x, y]) => [Math.round(x * 10) / 10, Math.round(y * 10) / 10]);
      if (kind === 'fill' || kind === 'cut') {
        const ft = r2(polygonFt2(pts, ppf));        // the stored (rounded) points, as the server measures them
        setMarks((m) => [...m, { kind, pts, ft2: ft, sides: polygonSides(pts, cx, ppf) }]);
        if (kind === 'fill') setFill((v) => r2(v + ft)); else setCut((v) => r2(v + ft));
      } else {
        // take away the traced fill/cut that lies inside the outline
        const base = kind === 'remove_fill' ? 'fill' : 'cut';
        const already = marks.filter((m) => m.kind === kind).reduce((n, m) => n + m.ft2, 0);
        const inside = shareInside(prof, surface, base, pending, cx);
        const ft = r2(Math.min(measured[`${base}_ft2`] * inside.share, measured[`${base}_ft2`] - already));
        if (ft < 0.05) {
          setNotice(`There is no measured ${base} inside this selection to remove.`);
          return;
        }
        setMarks((m) => [...m, { kind, pts, ft2: ft, sides: removalSides(ft, inside) }]);
        if (base === 'fill') setFill((v) => r2(v - ft)); else setCut((v) => r2(v - ft));
      }
      clearSelection();
    } else if (selected >= 0 && !isRemoval(marks[selected]) && marks[selected].kind !== kind && (kind === 'fill' || kind === 'cut')) {
      // switch an outlined area between fill and cut
      const m = marks[selected];
      setMarks((ms) => ms.map((x, i) => (i === selected ? { ...x, kind } : x)));
      if (kind === 'fill') { setFill((v) => r2(v + m.ft2)); setCut((v) => r2(v - m.ft2)); } else { setCut((v) => r2(v + m.ft2)); setFill((v) => r2(v - m.ft2)); }
    }
    setRev((n) => n + 1);
  }

  function removeMark(i) {
    const m = marks[i];
    setMarks((ms) => ms.filter((_, j) => j !== i));
    // undoing an outline gives back what it added or took away
    const sign = isRemoval(m) ? 1 : -1;
    if (m.kind.endsWith('fill')) setFill((v) => r2(v + sign * m.ft2)); else setCut((v) => r2(v + sign * m.ft2));
    setSelected(-1);
    setRev((n) => n + 1);
  }

  function reset() {
    setFill(measured.fill_ft2);
    setCut(measured.cut_ft2);
    setMarks([]);
    clearSelection();
    setNotice(null);
    setSelected(-1);
    setRev((n) => n + 1);
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await onSave({ fill_ft2: r2(fill), cut_ft2: r2(cut) },
        marks.map(({ kind, pts, ft2: ft }) => (isRemoval({ kind }) ? { kind, pts, ft2: ft } : { kind, pts })));
      onClose();
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }

  // ------------------------------------------------------------- drawing
  // image pixels under the pointer, kept on the drawing (the server keeps
  // outlines to the image the same way, so both measure the same shape)
  function rawPoint(e) {
    const m = svg.current?.getScreenCTM();
    if (!m) return null;
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(m.inverse());
    return [p.x, p.y];
  }
  function toImage(e) {
    const p = rawPoint(e);
    return p && prof ? [Math.min(Math.max(p[0], 0), prof.size[0]), Math.min(Math.max(p[1], 0), prof.size[1])] : null;
  }

  const nearFirst = (p) => pending.length >= 3 && p && Math.hypot(p[0] - pending[0][0], p[1] - pending[0][1]) < 10 * upp;

  function onCanvasClick(e) {
    if (suppressClick.current) { suppressClick.current = false; return; }
    const p = toImage(e);
    if (!p || !prof || !ppf || closed) return;
    setSelected(-1);
    setNotice(null);
    // clicking the first point again finishes the outline
    if (nearFirst(p)) { setClosed(true); return; }
    setPending((pts) => [...pts, p]);
  }

  // a double-click finishes the outline at the point clicked
  function onCanvasDoubleClick() {
    setPending((pts) => {
      const out = pts.filter((q, i) => i === 0 || Math.hypot(q[0] - pts[i - 1][0], q[1] - pts[i - 1][1]) > 3 * upp);
      if (out.length >= 3) setClosed(true);
      return out;
    });
  }

  useEffect(() => {
    function onKey(e) {
      if (e.target.closest('input, textarea, select')) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        if (pending.length) clearSelection(); else if (selected >= 0) setSelected(-1); else if (!busy) onClose();
      } else if (e.key === 'Enter' && pending.length >= 3) {
        e.preventDefault();
        setClosed(true);
      } else if (e.key === 'Backspace' && pending.length) {
        e.preventDefault();
        setClosed(false);
        setPending((pts) => pts.slice(0, -1));
      } else if ((e.key === 'Delete' || e.key === 'Backspace') && selected >= 0) {
        e.preventDefault();
        removeMark(selected);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  // keep the page behind from scrolling while the dialog is open
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, []);

  // canvas size, and the starting view once both it and the lines are known
  useEffect(() => {
    const el = canvas.current;
    const ro = new ResizeObserver(() => setBox({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const fit = useMemo(() => (prof && box ? fitView(prof, surface, s.marks || [], ppf, box, s.centreline?.x) : null), [prof, box, surface, s.marks, ppf, s.centreline?.x]);
  useEffect(() => { if (fit && !view) setView(fit); }, [fit, view]);

  function zoomAt(f, cx, cy) {
    setView((v) => {
      if (!v || !prof) return v;
      const w = Math.min(Math.max(v.w * f, 20), prof.size[0] * 2);
      const k = w / v.w;
      return { x: cx - (cx - v.x) * k, y: cy - (cy - v.y) * k, w, h: v.h * k };
    });
  }
  const zoomCentre = (f) => view && zoomAt(f, view.x + view.w / 2, view.y + view.h / 2);

  // wheel zooms at the cursor (non-passive, so the dialog doesn't scroll)
  useEffect(() => {
    const el = canvas.current;
    function onWheel(e) {
      if (!svg.current) return;
      e.preventDefault();
      const p = rawPoint(e);
      if (p) zoomAt(Math.exp(e.deltaY * 0.0015), p[0], p[1]);
    }
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  });

  // drag pans; a press that doesn't move is a click (adds a point)
  function onPointerDown(e) {
    if (e.button !== 0 || !view) return;
    drag.current = { x: e.clientX, y: e.clientY, view, moved: false };
  }
  function onPointerMove(e) {
    setHover(toImage(e));
    const d = drag.current;
    if (!d || !box) return;
    const dx = e.clientX - d.x, dy = e.clientY - d.y;
    if (!d.moved && Math.hypot(dx, dy) < 5) return;
    d.moved = true;
    const upp = Math.max(d.view.w / box.w, d.view.h / box.h);
    setView({ ...d.view, x: d.view.x - dx * upp, y: d.view.y - dy * upp });
  }
  function onPointerUp() {
    const d = drag.current;
    drag.current = null;
    if (d?.moved) suppressClick.current = true;
  }
  const suppressClick = useRef(false);

  // image pixels per screen pixel, to keep handles a constant size on screen
  const upp = view && box ? Math.max(view.w / box.w, view.h / box.h) : 1;
  const zoomPct = view && prof ? Math.round((fit ? fit.w / view.w : 1) * 100) : 100;
  const canMark = pending.length >= 3 || (selected >= 0 && !isRemoval(marks[selected]));

  return (
    <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}>
      <div className="modal edit-modal" role="dialog" aria-modal="true" aria-labelledby="edit-title">
        <div className="modal-h">
          <div>
            <span className="eyebrow">Edit cross-section · page {s.page}</span>
            <h3 id="edit-title"><span className="mono">{s.station || 'no station'}</span></h3>
          </div>
          <span className="spacer" />
          <div className="zoom" role="group" aria-label="Zoom">
            <button className="btn icon-btn" onClick={() => zoomCentre(1.4)} aria-label="Zoom out">−</button>
            <span className="num">{zoomPct}%</span>
            <button className="btn icon-btn" onClick={() => zoomCentre(1 / 1.4)} aria-label="Zoom in">+</button>
            <button className="btn small" onClick={() => setView(fit)} disabled={!fit}>Fit</button>
          </div>
          <button className="btn icon-btn" onClick={onClose} disabled={busy} aria-label="Close">×</button>
        </div>

        <div className="edit-body">
          <div className="edit-canvas" ref={canvas}>
            {prof && view ? (
              <svg ref={svg} className={`edit-svg ${drag.current?.moved ? 'panning' : 'drawing'}`}
                viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
                onClick={onCanvasClick} onDoubleClick={onCanvasDoubleClick} onPointerDown={onPointerDown} onPointerMove={onPointerMove}
                onPointerUp={onPointerUp} onPointerLeave={() => { setHover(null); onPointerUp(); }}>
                <image href={assetUrl(s.overlay)} x="0" y="0" width={prof.size[0]} height={prof.size[1]} preserveAspectRatio="none" />
                <Shading prof={prof} surface={surface} fill={fill} cut={cut} measured={measured} marks={marks}
                  selected={selected} onMarkClick={pending.length ? undefined : (i) => setSelected(i)} />
                <Centreline x={s.centreline?.x} height={prof.size[1]} scale={upp} />
                {pending.length > 0 && (
                  <g className={`outline ${closed ? 'closed' : ''}`}>
                    {pending.length >= 3 && <polygon points={pending.map((p) => p.join(',')).join(' ')} />}
                    {!closed && <polyline points={[...pending, ...(hover ? [nearFirst(hover) ? pending[0] : hover] : [])].map((p) => p.join(',')).join(' ')} />}
                    {pending.map(([x, y], i) => (
                      <circle key={i} cx={x} cy={y} r={(i === 0 && !closed && nearFirst(hover) ? 9 : 5) * upp}
                        className={i === 0 ? `first ${!closed && nearFirst(hover) ? 'snap' : ''}` : ''} />
                    ))}
                  </g>
                )}
              </svg>
            ) : <div className="empty">Loading the drawing…</div>}
            <div className="canvas-hint">
              {pending.length >= 3 && !closed ? 'Click the first point, double-click or press Enter to finish the selection'
                : 'Click to add points · drag to move · scroll to zoom'}
            </div>
          </div>

          <aside className="edit-side">
            <div className="edit-fields">
              <label className="stat edit-stat"><span>Fill ft²</span>
                <AreaInput key={`f${rev}`} value={fill} tone="fill" label="Fill area, square feet" onChange={setFill} /></label>
              <label className="stat edit-stat"><span>Cut ft²</span>
                <AreaInput key={`c${rev}`} value={cut} tone="cut" label="Cut area, square feet" onChange={setCut} /></label>
            </div>
            <div className="chips" aria-label="Measured from the drawing">
              <span className="tag neutral num" title="Fill measured from the drawing">measured fill {ft2(measured.fill_ft2)}</span>
              <span className="tag neutral num" title="Cut measured from the drawing">cut {ft2(measured.cut_ft2)}</span>
              <span className={`tag num ${fill - cut >= 0 ? 'fill' : 'cut'}`} title="Net with the areas above">net {ft2(fill - cut)} ft²</span>
            </div>
            <SideTable sides={sides} note={CENTRE_NOTE[s.centreline?.source]} compact />
            {(fill < markedFill - 0.05 || cut < markedCut - 0.05) && (
              <div className="pic-note warn-text">Lower than the areas outlined below; remove an outline to go lower.</div>
            )}

            <div className="edit-tool">
              <h4 className="h-tip">Select an area
                <InfoTip label="How to select an area">Click points around an area on the drawing. Finish by clicking the first
                  point again (or double-click / Enter), then choose what to do with it: count it as fill or cut, or remove
                  measured fill or cut inside it.</InfoTip></h4>
              <p className="muted small-text">
                {pending.length === 0 && selected < 0 && 'Click around an area; close it on the first point.'}
                {pending.length > 0 && pending.length < 3 && `${pending.length} point${pending.length > 1 ? 's' : ''} — keep clicking around the area.`}
                {pending.length >= 3 && !closed && <>Selected <b>{ft2(pendingFt2)} ft²</b>. Keep adding points, or click the first point to finish.</>}
                {pending.length >= 3 && closed && <>Selection finished: <b>{ft2(pendingFt2)} ft²</b>. Choose an action below.</>}
                {pending.length === 0 && selected >= 0 && (isRemoval(marks[selected])
                  ? `Removed area selected (${ft2(marks[selected].ft2)} ft²). Undo it in the list below.`
                  : `Outlined ${marks[selected].kind} area selected (${ft2(marks[selected].ft2)} ft²). Fill or Cut switches it.`)}
              </p>
              <div className="edit-buttons">
                <button className="btn fill-btn" onClick={() => mark('fill')} disabled={!canMark} title="Count the selection as fill">Fill</button>
                <button className="btn cut-btn" onClick={() => mark('cut')} disabled={!canMark} title="Count the selection as cut">Cut</button>
              </div>
              <div className="edit-buttons">
                <button className="btn remove-btn fill" onClick={() => mark('remove_fill')} disabled={pending.length < 3}
                  title="Take away the measured fill inside the selection">Remove fill</button>
                <button className="btn remove-btn cut" onClick={() => mark('remove_cut')} disabled={pending.length < 3}
                  title="Take away the measured cut inside the selection">Remove cut</button>
              </div>
              <div className="edit-buttons">
                <button className="btn" onClick={reset} title="Back to the areas measured from the drawing">Reset</button>
              </div>
              {notice && <div className="pic-note warn-text">{notice}</div>}
              {pending.length > 0 && (
                <div className="edit-buttons">
                  <button className="btn ghost small" onClick={() => { setClosed(false); setPending((p) => p.slice(0, -1)); }}>Undo point</button>
                  <button className="btn ghost small" onClick={clearSelection}>Clear selection</button>
                </div>
              )}
            </div>

            {marks.length > 0 && (
              <div className="mark-list">
                <h4>Your changes</h4>
                {marks.map((m, i) => (
                  <div key={i} className={`mark-row ${i === selected ? 'on' : ''}`}>
                    <button className="mark-pick" onClick={() => { clearSelection(); setSelected(i); }}>
                      <i className={m.kind} /> {MARK_LABEL[m.kind]} · <span className="num">{ft2(m.ft2)} ft²</span>
                    </button>
                    <button className="btn ghost small" onClick={() => removeMark(i)} aria-label={`Undo ${MARK_LABEL[m.kind].toLowerCase()}`}>Undo</button>
                  </div>
                ))}
              </div>
            )}
            {note && <div className="pic-note">{note}</div>}
            {!ppf && <div className="pic-note warn-text">This section has no image scale; outlining is unavailable.</div>}
          </aside>
        </div>

        <div className="modal-f">
          {error && <span className="warn-text">Could not save: {error}</span>}
          <span className="spacer" />
          <button className="btn" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="btn primary" onClick={save} disabled={busy || !changed}>{busy ? 'Saving…' : 'Save'}</button>
        </div>
      </div>
    </div>
  );
}
