import { cy } from '../format';

export default function RoadList({ roads, included, activeId, onSelect, onToggle }) {
  return (
    <section className="panel">
      <div className="panel-h"><h3>Roads</h3><span className="spacer" /><span className="tag neutral num">{roads.length}</span></div>
      {roads.length === 0 && <div className="empty">No cross-sections were found in this PDF.</div>}
      <div className="road-list">
        {roads.map((r) => {
          const on = included.has(r.id);
          return (
            <div key={r.id} role="button" tabIndex={0}
              className={`road ${r.id === activeId ? 'active' : ''} ${on ? '' : 'excluded'}`}
              onClick={() => onSelect(r.id)}
              onKeyDown={(e) => { if (e.key === 'Enter') onSelect(r.id); }}>
              <div className="road-top">
                <b className="road-name clamp-2" title={r.label}>{r.label}</b>
                {r.repeat_of && <span className="tag warn" title={r.flags.join('\n')}>repeat</span>}
                <label className="toggle" onClick={(e) => e.stopPropagation()}>
                  <input type="checkbox" checked={on} onChange={() => onToggle(r.id)} aria-label={`Count ${r.label} in the totals`} />
                  count
                </label>
              </div>
              <div className="road-range"><span className="mono">{r.station_from} → {r.station_to}</span><span className="tag neutral">{r.sections.length} sect.</span></div>
              <div className="road-nums num">
                <span className="tag cut">{cy(r.cut_cy)} cut</span>
                <span className="tag fill">{cy(r.fill_cy)} fill</span>
                <span className="muted">cy</span>
              </div>
              {r.sides && (
                <div className="road-lr num">
                  <span>L <i className="cut-text">{cy(r.sides.left.cut_cy)}</i> / <i className="fill-text">{cy(r.sides.left.fill_cy)}</i></span>
                  <span>R <i className="cut-text">{cy(r.sides.right.cut_cy)}</i> / <i className="fill-text">{cy(r.sides.right.fill_cy)}</i></span>
                  <span className="muted">cut / fill cy</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
