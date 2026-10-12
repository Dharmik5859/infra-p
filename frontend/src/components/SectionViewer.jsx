import { SOURCE_TEXT, ft2 } from '../format';
import SectionPicture from './SectionPicture';
import SideTable from './SideTable';
import { CENTRE_NOTE } from '../sides';

export default function SectionViewer({ section: s, surface, position, count, onPrev, onNext, onOpenEdit, onReset }) {
  const sourceTag = s.label_source === 'inferred' ? 'warn' : 'neutral';
  return (
    <section className="panel viewer">
      <div className="viewer-head">
        <div className="viewer-title">
          <span className="eyebrow">Cross-section {position >= 0 ? `${position + 1} of ${count}` : ''}</span>
          <div className="viewer-station">
            <span className="station mono">{s.station || 'no station'}</span>
            <span className={`tag ${sourceTag}`}>{SOURCE_TEXT[s.label_source] || 'station not read'}</span>
            <span className="tag neutral">page {s.page}</span>
            <span className="tag info">{s.method === 'vector' ? 'CAD linework' : 'scan'}</span>
          </div>
        </div>
        <span className="spacer" />
        <div className="stepper" role="group" aria-label="Step through sections">
          <button className="btn icon-btn" onClick={onPrev} disabled={!onPrev} aria-label="Previous section" title="Previous (←)">‹</button>
          <button className="btn icon-btn" onClick={onNext} disabled={!onNext} aria-label="Next section" title="Next (→)">›</button>
        </div>
        <button className="btn primary" onClick={onOpenEdit}>Edit section</button>
      </div>

      <div className="viewer-grid">
        <div className="viewer-main">
          {s.overlay ? (
            <SectionPicture section={s} surface={surface}
              alt={`Cross-section ${s.station || ''} on page ${s.page}: existing ground in blue, finished grade in black, subgrade in yellow, fill shaded green, cut shaded red`} />
          ) : <div className="empty">No overlay image for this section.</div>}
          <div className="legend">
            <span><i style={{ background: '#1a73e8' }} />existing ground</span>
            <span><i style={{ background: '#1e1e1e' }} />finished grade</span>
            <span><i style={{ background: '#f9ab00' }} />subgrade (under pavement)</span>
            <span><i style={{ background: 'var(--fill)' }} />fill</span>
            <span><i style={{ background: 'var(--cut)' }} />cut</span>
          </div>
        </div>

        <aside className="viewer-areas" aria-label="Areas of this section">
          <div className="area-totals">
            <div className="area-total fill"><span>Fill</span><b className="num">{ft2(s.fill_ft2)}</b><small>ft²</small></div>
            <div className="area-total cut"><span>Cut</span><b className="num">{ft2(s.cut_ft2)}</b><small>ft²</small></div>
            <div className="area-total net"><span>Net</span><b className="num">{s.net_ft2 > 0 ? '+' : ''}{ft2(s.net_ft2)}</b><small>ft²</small></div>
          </div>
          <SideTable sides={s.sides} note={CENTRE_NOTE[s.centreline?.source]} compact />
          {s.edited && (
            <div className="edit-note">
              <span className={`tag ${s.dirty ? 'warn' : 'edited'}`}>{s.dirty ? 'unsaved edit' : 'edited'}</span>
              <span className="muted">measured fill {ft2(s.measured.fill_ft2)}, cut {ft2(s.measured.cut_ft2)} ft²</span>
              <button className="btn ghost small" onClick={onReset}>Reset</button>
            </div>
          )}
        </aside>
      </div>

      {(s.zero || s.warnings.length > 0) && (
        <div className="viewer-foot">
          {s.zero && (
            <div className="zero-note" role="note">
              <b>No earthwork here: {s.zero.short.toLowerCase()}.</b> {s.zero.text} If the drawing does show work at this
              station, press Edit section to enter or outline it.
            </div>
          )}
          {s.warnings.length > 0 && (
            <div className="warnings">{s.warnings.map((w, i) => <div className="warning" key={i}>{w}</div>)}</div>
          )}
        </div>
      )}
    </section>
  );
}
