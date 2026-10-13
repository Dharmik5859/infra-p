/**
 * A section's confidence (0-100, from the server) and its alerts. 85 % and
 * above passes; below that the section carries an alert saying what to check.
 */
export const PASS = 85;

export function level(c) {
  if (!c) return 'none';
  return c.passed ? 'pass' : c.score >= 60 ? 'warn' : 'fail';
}

export function ConfidenceBadge({ confidence: c, compact = false }) {
  if (!c) return null;
  const lv = level(c);
  const title = c.deductions?.length
    ? `Confidence ${c.score}% (pass: ${c.threshold ?? PASS}%)\n${c.deductions.map((d) => `−${d.points}  ${d.note}`).join('\n')}`
    : `Confidence ${c.score}%: nothing had to be guessed`;
  return (
    <span className={`conf-badge ${lv}`} title={title} aria-label={`Confidence ${c.score} percent, ${c.passed ? 'passes' : 'below the pass mark'}`}>
      <i style={{ '--p': `${c.score}%` }} />
      {c.score}%{!compact && <small>{c.passed ? 'pass' : 'alert'}</small>}
    </span>
  );
}

export function ConfidencePanel({ confidence: c }) {
  if (!c) return null;
  const lv = level(c);
  const ded = [...(c.deductions || [])].sort((a, b) => b.points - a.points);
  const max = Math.max(1, ...ded.map((d) => d.points));
  return (
    <div className={`conf-panel ${lv}`} role={c.passed ? 'note' : 'alert'}>
      <div className="conf-head">
        <ConfidenceBadge confidence={c} compact />
        <b className="conf-msg">{c.passed ? 'Confidence passes' : (c.alerts?.[0]?.message || 'Low confidence')}</b>
        <span className="conf-mark" title={`Pass mark ${c.threshold ?? PASS}%`}>
          <span className="conf-meter" aria-hidden="true">
            <i style={{ width: `${c.score}%` }} />
            <b style={{ left: `${c.threshold ?? PASS}%` }} />
          </span>
          <span className="muted num">pass {c.threshold ?? PASS}%</span>
        </span>
      </div>
      {ded.length > 0 && (
        <ul className="conf-list" aria-label="Deductions">
          {ded.map((d, i) => (
            <li key={i}>
              <span className="conf-pts num">−{d.points}</span>
              <span className="conf-bar" aria-hidden="true"><i style={{ width: `${(100 * d.points) / max}%` }} /></span>
              <span className="tag neutral conf-factor">{d.factor}</span>
              <span className="conf-note">{d.note}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
