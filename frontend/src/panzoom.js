import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Zoom and pan an SVG by its viewBox: the wheel zooms at the cursor, a drag
 * pans, and a press that does not move stays a click (`wasDrag()` tells the
 * click handler to ignore the press that ended a drag).
 *
 * `boxRef` is the element the SVG fills; `limit` the content size [w, h].
 */
export function usePanZoom(svgRef, boxRef, limit) {
  const [view, setView] = useState(null);       // {x, y, w, h} in content units
  const [box, setBox] = useState(null);         // on-screen size of the box
  const drag = useRef(null);
  const dragged = useRef(false);

  useEffect(() => {
    const el = boxRef.current;
    if (!el) return undefined;
    const ro = new ResizeObserver(() => setBox({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    return () => ro.disconnect();
  }, [boxRef]);

  const toPoint = useCallback((e) => {
    const m = svgRef.current?.getScreenCTM();
    if (!m) return null;
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(m.inverse());
    return [p.x, p.y];
  }, [svgRef]);

  const zoomAt = useCallback((f, cx, cy) => {
    setView((v) => {
      if (!v) return v;
      const maxW = limit ? Math.max(limit[0], limit[1]) * 2 : Infinity;
      const w = Math.min(Math.max(v.w * f, 4), maxW);
      const k = w / v.w;
      return { x: cx - (cx - v.x) * k, y: cy - (cy - v.y) * k, w, h: v.h * k };
    });
  }, [limit]);

  // the wheel zooms the view, not the page (needs a non-passive listener)
  useEffect(() => {
    const el = boxRef.current;
    if (!el) return undefined;
    const onWheel = (e) => {
      const p = toPoint(e);
      if (!p) return;
      e.preventDefault();
      zoomAt(Math.exp(e.deltaY * 0.0015), p[0], p[1]);
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [boxRef, toPoint, zoomAt]);

  /** Show a content rectangle, padded, filling the box's shape. */
  const fit = useCallback((r, pad = 0.06) => {
    if (!r || !box) return;
    let w = r.w * (1 + 2 * pad), h = r.h * (1 + 2 * pad);
    const aspect = box.w / Math.max(1, box.h);
    if (w / h > aspect) h = w / aspect; else w = h * aspect;
    setView({ x: r.x + r.w / 2 - w / 2, y: r.y + r.h / 2 - h / 2, w, h });
  }, [box]);

  const upp = view && box ? Math.max(view.w / box.w, view.h / box.h) : 1;   // content units per screen pixel

  const handlers = {
    onPointerDown: (e) => {
      if (e.button !== 0 || !view) return;
      drag.current = { x: e.clientX, y: e.clientY, view, moved: false };
      dragged.current = false;
    },
    onPointerMove: (e) => {
      const d = drag.current;
      if (!d || !box) return;
      const dx = e.clientX - d.x, dy = e.clientY - d.y;
      if (!d.moved && Math.hypot(dx, dy) < 5) return;
      d.moved = true;
      const k = Math.max(d.view.w / box.w, d.view.h / box.h);
      setView({ ...d.view, x: d.view.x - dx * k, y: d.view.y - dy * k });
    },
    onPointerUp: () => {
      if (drag.current?.moved) dragged.current = true;
      drag.current = null;
    },
    onPointerLeave: () => { drag.current = null; },
  };

  const wasDrag = () => {
    const was = dragged.current;
    dragged.current = false;
    return was;
  };

  return { view, setView, box, upp, fit, zoomAt, toPoint, handlers, wasDrag, panning: Boolean(drag.current?.moved) };
}
