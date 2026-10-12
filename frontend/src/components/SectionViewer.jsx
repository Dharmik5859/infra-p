import { SOURCE_TEXT, ft2 } from '../format';
import SectionPicture from './SectionPicture';
import SideTable from './SideTable';
import { CENTRE_NOTE } from '../sides';

export default function SectionViewer({ section: s, surface, position, count, onPrev, onNext, onOpenEdit, onReset }) {
  const sourceTag = s.label_source === 'inferred' ? 'warn' : 'neutral';
  return (
    <section className="panel">
      <div className="panel-h">
        <h3>Cross-section</h3>
        <span className="muted">{position >= 0 ? `${position + 1} of ${count}` : ''}</span>
        <span className="spacer" />
        <span className="muted" style={{ fontSize: 12 }}><span className="kbd">←</span> <span className="kbd">→</span></span>
        <button className="btn icon-btn" onClick={onPrev} disabled={!onPrev} aria-label="Previous section">‹</button>
        <button className="btn icon-btn" onClick={onNext} disabled={!onNext} aria-label="Next section">›</button>
      </div>
      <div className="viewer-body">
        <div className="viewer-meta">
          <span className="station mono">{s.station || 'no station'}</span>
          <span className={`tag ${sourceTag}`}>{SOURCE_TEXT[s.label_source] || 'station not read'}</span>
          <span className="tag neutral">page {s.page}</span>
          <span className="tag info">{s.method === 'vector' ? 'traced from CAD linework' : 'traced from scan'}</span>
          <span className="spacer" style={{ flex: 1 }} />
          <div className="stat"><span>Fill</span><b className="num fill-text">{ft2(s.fill_ft2)} ft²</b></div>
          <div className="stat"><span>Cut</span><b className="num cut-text">{ft2(s.cut_ft2)} ft²</b></div>
          <div className="stat"><span>Net</span><b className="num">{ft2(s.net_ft2)} ft²</b></div>
          <button className="btn primary" onClick={onOpenEdit}>Edit</button>
        </div>
        <SideTable sides={s.sides} note={CENTRE_NOTE[s.centreline?.source]} compact />
        {s.zero && (
          <div className="zero-note" role="note">
            <b>No earthwork here: {s.zero.short.toLowerCase()}.</b> {s.zero.text} If the drawing does show work at this
            station, press Edit to enter or outline it.
          </div>
        )}
        {s.edited && (
          <div className="edit-note">
            <span className={`tag ${s.dirty ? 'warn' : 'edited'}`}>{s.dirty ? 'unsaved edit' : 'edited'}</span>
            <span className="muted">Measured from the drawing: fill {ft2(s.measured.fill_ft2)} ft², cut {ft2(s.measured.cut_ft2)} ft²</span>
            <button className="btn ghost small" onClick={onReset}>Reset to measured</button>
          </div>
        )}
        {s.overlay ? (
          <SectionPicture section={s} surface={surface}
            alt={`Cross-section ${s.station || ''} on page ${s.page}: existing ground in blue, finished grade in black, subgrade in yellow, fill shaded green, cut shaded red`} />
        ) : <div className="empty">No overlay image for this section.</div>}
        <div className="legend" style={{ padding: 0 }}>
          <span><i style={{ background: '#1a73e8' }} />existing ground</span>
          <span><i style={{ background: '#1e1e1e' }} />finished grade</span>
          <span><i style={{ background: '#f9ab00' }} />subgrade (under pavement)</span>
          <span><i style={{ background: 'var(--fill)' }} />fill</span>
          <span><i style={{ background: 'var(--cut)' }} />cut</span>
        </div>
        {s.warnings.length > 0 && (
          <div className="warnings">{s.warnings.map((w, i) => <div className="warning" key={i}>{w}</div>)}</div>
        )}
      </div>
    </section>
  );
}
