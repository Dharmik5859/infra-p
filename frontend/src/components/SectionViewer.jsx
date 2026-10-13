import { useState } from 'react';
import { SOURCE_TEXT, ft2 } from '../format';
import AllValuesTable from './AllValuesTable';
import { IconSection, IconSheet, IconTable } from './Icons';
import SectionPicture from './SectionPicture';
import SheetView from './SheetView';
import SideTable from './SideTable';
import { CENTRE_NOTE } from '../sides';
import { ConfidenceBadge, ConfidencePanel } from './Confidence';

const SCALE_SOURCE = { labels: 'read off the axis labels', label_widths: 'from the axis labels', ocr: 'read off the scan',
  assumed: 'assumed (labels not read)' };

function scaleText(sc) {
  if (!sc) return null;
  const same = sc.ftPerSquareX === sc.ftPerSquareY;
  return same ? `${sc.ftPerSquareX} ft grid` : `${sc.ftPerSquareX} ft × ${sc.ftPerSquareY} ft grid`;
}

export default function SectionViewer({ jobId, section: s, sections, roads, surface, position, count, onPrev, onNext,
  onSelect, onOpenEdit, onReset }) {
  const sourceTag = s.label_source === 'inferred' ? 'warn' : 'neutral';
  // the whole PDF sheet with every section marked, or this section close up
  const [mode, setMode] = useState('sheet');
  const [table, setTable] = useState(false);
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
            {s.scale && (
              <span className={`tag ${s.scale.verticalDiffers ? 'warn' : 'neutral'}`}
                title={`Horizontal: ${s.scale.ftPerSquareX} ft per square, ${SCALE_SOURCE[s.scale.sourceX] || s.scale.sourceX}\nVertical: ${s.scale.ftPerSquareY} ft per square, ${SCALE_SOURCE[s.scale.sourceY] || s.scale.sourceY}\n${s.scale.pixelsPerFootX.toFixed(2)} × ${s.scale.pixelsPerFootY.toFixed(2)} page px per ft`}>
                {scaleText(s.scale)}
              </span>
            )}
            <ConfidenceBadge confidence={s.confidence} />
          </div>
        </div>
        <span className="spacer" />
        <div className="viewer-tools">
        <div className="segmented" role="radiogroup" aria-label="View">
          <button role="radio" aria-checked={mode === 'sheet'} className={mode === 'sheet' ? 'on' : ''} onClick={() => setMode('sheet')}>
            <IconSheet width={16} height={16} />Sheet</button>
          <button role="radio" aria-checked={mode === 'section'} className={mode === 'section' ? 'on' : ''} onClick={() => setMode('section')}>
            <IconSection width={16} height={16} />Section</button>
        </div>
        <button className={`btn ${table ? 'tonal' : ''}`} onClick={() => setTable((t) => !t)} aria-pressed={table}
          title="All cut and fill values"><IconTable width={18} height={18} />All values</button>
        <div className="stepper" role="group" aria-label="Step through sections">
          <button className="btn icon-btn" onClick={onPrev} disabled={!onPrev} aria-label="Previous section" title="Previous (←)">‹</button>
          <button className="btn icon-btn" onClick={onNext} disabled={!onNext} aria-label="Next section" title="Next (→)">›</button>
        </div>
        <button className="btn primary" onClick={onOpenEdit}>Edit section</button>
        </div>
      </div>

      <div className={`viewer-grid ${mode === 'sheet' ? 'sheet-mode' : ''}`}>
        <div className="viewer-main">
          {mode === 'sheet' ? (
            <SheetView jobId={jobId} section={s} sections={sections} surface={surface} onSelect={onSelect} />
          ) : s.overlay ? (
            <SectionPicture section={s} surface={surface}
              alt={`Cross-section ${s.station || ''} on page ${s.page}: existing ground in blue, finished grade in black, subgrade in yellow, fill shaded green, cut shaded red`} />
          ) : <div className="empty">No overlay image for this section.</div>}
          {mode === 'sheet' ? (
            <div className="legend">
              <span><i style={{ background: 'var(--fill)' }} />fill</span>
              <span><i style={{ background: 'var(--cut)' }} />cut</span>
              <span><i className="legend-frame" />measured section (click to select)</span>
              <span><i className="legend-frame sel" />selected section</span>
            </div>
          ) : (
          <div className="legend">
            <span><i style={{ background: '#1a73e8' }} />existing ground</span>
            <span><i style={{ background: '#1e1e1e' }} />finished grade</span>
            <span><i style={{ background: '#f9ab00' }} />subgrade (under pavement)</span>
            <span><i style={{ background: 'var(--fill)' }} />fill</span>
            <span><i style={{ background: 'var(--cut)' }} />cut</span>
          </div>
          )}
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

      {table && (
        <AllValuesTable sections={sections} roads={roads} selectedId={s.id} onSelect={onSelect} onClose={() => setTable(false)} />
      )}

      {(s.zero || s.warnings.length > 0 || (s.confidence && !s.confidence.passed)) && (
        <div className="viewer-foot">
          {s.confidence && !s.confidence.passed && <ConfidencePanel confidence={s.confidence} />}
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
