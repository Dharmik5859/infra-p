import { useRef, useState } from 'react';

const FORMATS = [
  { title: '19-series', body: 'Scanned strips, one cross-section per page', tone: 'blue' },
  { title: '23-series', body: 'Scanned sheets, several sections per sheet', tone: 'green' },
  { title: 'CAD-exported PDF', body: 'Measured exactly from the drawing linework', tone: 'yellow' },
];

const mb = (bytes) => `${(bytes / 1048576).toLocaleString(undefined, { maximumFractionDigits: bytes < 10485760 ? 1 : 0 })} MB`;

export default function UploadView({ server, onFile, busy, progress, error }) {
  const input = useRef(null);
  const [over, setOver] = useState(false);
  const [localError, setLocalError] = useState(null);

  function pick(files) {
    const f = files && files[0];
    if (!f) return;
    if (!f.name.toLowerCase().endsWith('.pdf')) {
      setLocalError('Please choose a PDF plan set.');
      return;
    }
    setLocalError(null);
    const limit = server?.max_upload_mb;
    if (limit && f.size > limit * 1048576) {
      setLocalError(`This PDF is ${mb(f.size)}, larger than the server's ${limit.toLocaleString()} MB upload limit. `
        + 'Raise MAX_UPLOAD_MB on the backend to process it.');
      return;
    }
    onFile(f);
  }

  const status = server == null ? 'Checking the processing server…'
    : server.unreachable ? 'Processing server is not reachable'
    : server.ok ? `Processing server ready · v${server.version}`
      + (server.max_upload_mb ? ` · PDFs up to ${server.max_upload_mb >= 1024 ? `${server.max_upload_mb / 1024} GB` : `${server.max_upload_mb} MB`}` : '')
    : 'Server is missing OCR (tesseract) — scanned sheets cannot be read';

  return (
    <div className="page narrow">
      <div className="card upload-card">
        <h2>Cut &amp; fill from cross-sections</h2>
        <p className="lede">
          Upload a road plan set. Cross-section sheets are found automatically, each station is read,
          the existing ground and proposed design are traced, and cut/fill volumes are computed per road
          by the average-end-area method.
        </p>

        <div
          className={`dropzone ${over ? 'over' : ''}`}
          role="button"
          tabIndex={0}
          aria-label="Choose a plan set PDF"
          onClick={() => !busy && input.current?.click()}
          onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && !busy) { e.preventDefault(); input.current?.click(); } }}
          onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); if (!busy) pick(e.dataTransfer.files); }}
        >
          <input ref={input} type="file" accept="application/pdf,.pdf" hidden onChange={(e) => pick(e.target.files)} />
          <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 16V4M7 9l5-5 5 5" /><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" />
          </svg>
          <span className="big">{busy ? 'Uploading…' : 'Drop the plan set PDF here'}</span>
          {busy && progress?.total > 0 && (
            <div className="upload-progress" aria-live="polite">
              <div className="bar"><div style={{ width: `${(100 * progress.sent) / progress.total}%` }} /></div>
              <span className="muted num">
                {mb(progress.sent)} of {mb(progress.total)}
                {progress.sent >= progress.total ? ' · reading the PDF…' : ` · ${Math.round((100 * progress.sent) / progress.total)}%`}
              </span>
            </div>
          )}
          {!busy && <span className="muted">or click to browse · cover, plan and profile sheets are skipped on their own</span>}
        </div>

        <div className="formats">
          {FORMATS.map((f) => (
            <div className={`format t-${f.tone}`} key={f.title}><b>{f.title}</b><span>{f.body}</span></div>
          ))}
        </div>

        <div className="deliverables">
          <span className="eyebrow">What you get</span>
          <ul>
            <li><b>Cut &amp; fill volumes</b> per road, by the average-end-area method</li>
            <li><b>Every cross-section</b> traced, with its area and an audit drawing</li>
            <li><b>Your plan set back as a PDF</b>, cut and fill drawn on every section</li>
            <li><b>Review &amp; edit</b> any area; volumes and the PDF follow your edits</li>
          </ul>
        </div>

        <div className="server">
          <span className={`dot ${server == null ? '' : server.ok ? 'ok' : 'bad'}`} />
          {status}
        </div>
        {(localError || error) && <div className="error-box" role="alert">{localError || error}</div>}
      </div>
    </div>
  );
}
