import { cy } from '../format';

export default function RoadList({ roads, included, activeId, onSelect, onToggle }) {
  return (
    <section className="panel">
      <div className="panel-h"><h3>Roads</h3><span className="spacer" /><span className="muted">{roads.length}</span></div>
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
                <b>{r.label}</b>
                {r.repeat_of && <span className="tag warn" title={r.flags.join('\n')}>repeat</span>}
                <label className="toggle" onClick={(e) => e.stopPropagation()}>
                  <input type="checkbox" checked={on} onChange={() => onToggle(r.id)} />
                  count
                </label>
              </div>
              <div className="road-range mono">{r.station_from} → {r.station_to} · {r.sections.length} sections</div>
              <div className="road-nums num">
                <span className="cut-text">{cy(r.cut_cy)} cut</span>
                <span className="fill-text">{cy(r.fill_cy)} fill</span>
                <span className="muted">cy</span>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
