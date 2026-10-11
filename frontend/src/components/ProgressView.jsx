import { useEffect, useState } from 'react';

export default function ProgressView({ job }) {
  const [start] = useState(() => Date.now());
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, []);
  const { done, total } = job.progress || { done: 0, total: 0 };
  const pct = total ? Math.round((done / total) * 100) : 0;
  const secs = Math.round((now - start) / 1000);

  return (
    <div className="page narrow">
      <div className="card progress-card" aria-live="polite">
        <h2>Reading {job.filename}</h2>
        <div className="muted">
          {job.status === 'queued'
            ? 'Waiting for another plan set to finish…'
            : total ? `${done} of ${total} pages · ${pct}%` : 'Starting…'} · {secs}s
        </div>
        <div className={`bar ${total ? '' : 'indeterminate'}`}>
          <div style={{ width: `${pct}%` }} />
        </div>
        <ul className="steps">
          <li>Finding cross-section frames on every page</li>
          <li>Reading station labels (PDF text, or OCR on scans)</li>
          <li>Tracing existing ground and proposed design</li>
          <li>Measuring cut / fill and grouping stations into roads</li>
        </ul>
      </div>
    </div>
  );
}
