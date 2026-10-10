import { useRef, useState } from 'react';

const FORMATS = [
  { title: 'Scanned strips', body: '19-series: one cross-section per page' },
  { title: 'Scanned sheets', body: '23-series: several sections per sheet' },
  { title: 'CAD-exported PDF', body: 'Vector sheets, measured from the linework' },
];

export default function UploadView({ server, onFile, busy, error }) {
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
    onFile(f);
  }

  const status = server == null ? 'Checking the processing server…'
    : server.unreachable ? 'Processing server is not reachable'
    : server.ok ? `Processing server ready · v${server.version}`
    : 'Server is missing OCR (tesseract) — scanned sheets cannot be read';

  return (
    <main className="center-page">
      <div className="upload-card">
        <h1>Cut &amp; fill from cross-sections</h1>
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
          <span className="muted">or click to browse · cover, plan and profile sheets are skipped on their own</span>
        </div>

        <div className="formats">
          {FORMATS.map((f) => (
            <div className="format" key={f.title}><b>{f.title}</b><span>{f.body}</span></div>
          ))}
        </div>

        <div className="server">
          <span className={`dot ${server == null ? '' : server.ok ? 'ok' : 'bad'}`} />
          {status}
        </div>
        {(localError || error) && <div className="error-box" role="alert">{localError || error}</div>}
      </div>
    </main>
  );
}
