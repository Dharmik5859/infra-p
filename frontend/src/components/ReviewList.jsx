import { ConfidenceBadge } from './Confidence';

export default function ReviewList({ items, onSelect }) {
  if (items.length === 0) {
    return <div className="empty">Nothing flagged: every station was read, every section traced cleanly and scored 85% or more.</div>;
  }
  return (
    <div className="table-wrap">
      {[...items].sort((a, b) => (a.confidence?.score ?? 100) - (b.confidence?.score ?? 100)).map((s) => (
        <div key={s.id} className="review-item" role="button" tabIndex={0}
          onClick={() => onSelect(s.id)} onKeyDown={(e) => { if (e.key === 'Enter') onSelect(s.id); }}>
          <span className="where mono">{s.station || 'no station'}</span>
          <span className="muted">page {s.page}</span>
          <ConfidenceBadge confidence={s.confidence} />
          {s.confidence && !s.confidence.passed && <span className="what alert-what">{s.confidence.alerts?.[0]?.message}</span>}
          {s.label_source === 'inferred' && <span className="what">Station was not read cleanly; inferred from the sequence.</span>}
          {s.warnings.filter((w) => !w.startsWith('station')).map((w, i) => <span className="what" key={i}>{w}</span>)}
        </div>
      ))}
    </div>
  );
}
