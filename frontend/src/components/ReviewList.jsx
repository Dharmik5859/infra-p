import { ConfidenceBadge } from './Confidence';
import { IconCheck } from './Icons';

export default function ReviewList({ items, onSelect }) {
  if (items.length === 0) {
    return (
      <div className="empty all-clear" title="Every station was read, every section traced cleanly and scored 85% or more.">
        <IconCheck width={18} height={18} /><b>All clear</b><span className="muted">every section ≥ 85%</span>
      </div>
    );
  }
  return (
    <div className="table-wrap">
      {[...items].sort((a, b) => (a.confidence?.score ?? 100) - (b.confidence?.score ?? 100)).map((s) => {
        const reasons = [];
        if (s.confidence && !s.confidence.passed && s.confidence.alerts?.[0]?.message) reasons.push(['bad', s.confidence.alerts[0].message]);
        if (s.label_source === 'inferred') reasons.push(['warn', 'Station inferred from the sequence']);
        s.warnings.filter((w) => !w.startsWith('station')).forEach((w) => reasons.push(['warn', w]));
        return (
          <div key={s.id} className="review-item" role="button" tabIndex={0}
            onClick={() => onSelect(s.id)} onKeyDown={(e) => { if (e.key === 'Enter') onSelect(s.id); }}>
            <span className="where mono">{s.station || 'no station'}</span>
            <span className="review-meta">
              <span className="tag neutral">p. {s.page}</span>
              <ConfidenceBadge confidence={s.confidence} />
            </span>
            {reasons.length > 0 && (
              <span className="what chips">
                {reasons.map(([tone, text], i) => <span key={i} className={`tag ${tone} reason`} title={text}>{text}</span>)}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
