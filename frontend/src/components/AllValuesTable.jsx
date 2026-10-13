import { useEffect, useMemo, useRef, useState } from 'react';
import { ft2 } from '../format';
import { IconClose } from './Icons';
import { ConfidenceBadge } from './Confidence';

const COLS = [
  ['station', 'Station'], ['page', 'Sheet'], ['fill', 'Fill'], ['cut', 'Cut'], ['net', 'Net'],
  ['lf', 'Left fill'], ['lc', 'Left cut'], ['rf', 'Right fill'], ['rc', 'Right cut'], ['conf', 'Confidence'],
];

const value = (s, key) => ({
  station: s.station_ft ?? Infinity, page: s.page, fill: s.fill_ft2, cut: s.cut_ft2, net: s.net_ft2,
  lf: s.sides?.left.fill_ft2, lc: s.sides?.left.cut_ft2, rf: s.sides?.right.fill_ft2, rc: s.sides?.right.cut_ft2,
  conf: s.confidence?.score ?? -1,
}[key]);

/**
 * Every section's cut and fill (and its split left / right of the
 * centreline) in one table. Picking a row selects that section: the sheet
 * view moves to its page and zooms onto it.
 */
export default function AllValuesTable({ sections, roads, selectedId, onSelect, onClose }) {
  const [sort, setSort] = useState({ key: null, dir: 1 });
  const [query, setQuery] = useState('');
  const sel = useRef(null);
  const roadLabel = useMemo(() => Object.fromEntries(roads.map((r) => [r.id, r.label])), [roads]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    let out = sections.filter((s) => !q || (s.station || '').toLowerCase().includes(q) || String(s.page) === q);
    if (sort.key) out = [...out].sort((a, b) => (value(a, sort.key) - value(b, sort.key)) * sort.dir);
    return out;
  }, [sections, sort, query]);

  const totals = useMemo(() => rows.reduce((t, s) => ({
    fill: t.fill + s.fill_ft2, cut: t.cut + s.cut_ft2,
    lf: t.lf + (s.sides?.left.fill_ft2 || 0), lc: t.lc + (s.sides?.left.cut_ft2 || 0),
    rf: t.rf + (s.sides?.right.fill_ft2 || 0), rc: t.rc + (s.sides?.right.cut_ft2 || 0),
  }), { fill: 0, cut: 0, lf: 0, lc: 0, rf: 0, rc: 0 }), [rows]);

  useEffect(() => { sel.current?.scrollIntoView({ block: 'nearest' }); }, [selectedId]);

  return (
    <div className="values-drawer" role="dialog" aria-label="All cut and fill values">
      <div className="values-head">
        <div>
          <span className="eyebrow">{rows.length} of {sections.length} sections · ft²</span>
          <h3>All cut &amp; fill values</h3>
        </div>
        <span className="spacer" />
        <input className="values-search" type="search" placeholder="Find station or sheet" value={query}
          onChange={(e) => setQuery(e.target.value)} aria-label="Find a station or sheet" />
        <button className="btn icon-btn" onClick={onClose} aria-label="Close the table"><IconClose width={18} height={18} /></button>
      </div>
      <div className="values-scroll">
        <table className="values-table">
          <thead>
            <tr>
              {COLS.map(([k, label]) => (
                <th key={k} className={k === 'station' ? '' : 'num'} aria-sort={sort.key === k ? (sort.dir > 0 ? 'ascending' : 'descending') : 'none'}>
                  <button onClick={() => setSort((s) => (s.key === k ? { key: k, dir: -s.dir } : { key: k, dir: 1 }))}>
                    {label}{sort.key === k ? (sort.dir > 0 ? ' ↑' : ' ↓') : ''}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.id} ref={s.id === selectedId ? sel : null} className={`${s.id === selectedId ? 'sel-row' : ''} ${s.edited ? 'edited-row' : ''}`}
                onClick={() => onSelect(s.id)} tabIndex={0} onKeyDown={(e) => { if (e.key === 'Enter') onSelect(s.id); }}>
                <td className="mono">
                  {s.station || '—'}
                  {roads.length > 1 && s.road && <small className="muted"> {roadLabel[s.road]}</small>}
                  {s.edited && <span className="tag edited">edited</span>}
                </td>
                <td className="num">{s.page}</td>
                <td className="num fill-text">{ft2(s.fill_ft2)}</td>
                <td className="num cut-text">{ft2(s.cut_ft2)}</td>
                <td className="num">{ft2(s.net_ft2)}</td>
                <td className="num fill-text">{s.sides ? ft2(s.sides.left.fill_ft2) : '—'}</td>
                <td className="num cut-text">{s.sides ? ft2(s.sides.left.cut_ft2) : '—'}</td>
                <td className="num fill-text">{s.sides ? ft2(s.sides.right.fill_ft2) : '—'}</td>
                <td className="num cut-text">{s.sides ? ft2(s.sides.right.cut_ft2) : '—'}</td>
                <td className="num"><ConfidenceBadge confidence={s.confidence} compact /></td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th>Total</th><td />
              <td className="num fill-text">{ft2(totals.fill)}</td>
              <td className="num cut-text">{ft2(totals.cut)}</td>
              <td className="num">{ft2(totals.fill - totals.cut)}</td>
              <td className="num fill-text">{ft2(totals.lf)}</td>
              <td className="num cut-text">{ft2(totals.lc)}</td>
              <td className="num fill-text">{ft2(totals.rf)}</td>
              <td className="num cut-text">{ft2(totals.rc)}</td>
              <td className="num muted">{rows.filter((s) => s.confidence && !s.confidence.passed).length} alerts</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
