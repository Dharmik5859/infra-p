import { cy, signed } from '../format';
import { GRADES, accuracy, grade, sentence } from '../verdict';
import { IconAccuracy, IconArrow, IconCheck, IconInfo, IconUpload } from './Icons';
import Headline from './Headline';

/** Ring gauge: value 0-100 drawn as an arc in the given colour token. */
export function Gauge({ value, tone, label, sub }) {
  const r = 34, c = 2 * Math.PI * r;
  const v = value == null ? 0 : Math.min(100, Math.max(0, value));
  return (
    <div className="gauge">
      <svg viewBox="0 0 84 84" width="84" height="84" role="img" aria-label={`${label}: ${value == null ? 'not measured' : `${v.toFixed(1)} %`}`}>
        <circle cx="42" cy="42" r={r} className="gauge-track" />
        <circle cx="42" cy="42" r={r} className="gauge-arc" stroke={`var(--${tone})`}
          strokeDasharray={`${(v / 100) * c} ${c}`} transform="rotate(-90 42 42)" />
        <text x="42" y="46" textAnchor="middle" className="gauge-num">{value == null ? '—' : `${v >= 99.95 ? 100 : v.toFixed(1)}`}</text>
      </svg>
      <div className="gauge-label">
        <b>{label}</b>
        <span>{sub}</span>
      </div>
    </div>
  );
}

const signedPct = (v) => (v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(1)} %`);

export function VerdictPill({ g }) {
  return <span className={`pill verdict t-${g.tone}`}><IconCheck width={16} height={16} />{g.label}</span>;
}

export function VerdictCard({ f }) {
  const m = f.metrics;
  const g = grade(m);
  const errText = (e) => (e == null ? '' : `${e > 0 ? '+' : e < 0 ? '−' : ''}${Math.abs(e).toFixed(1)} % vs reference`);
  return (
    <article className={`card verdict-card edge-${g.tone}`}>
      <header className="vc-head">
        <div>
          <span className="eyebrow">{f.format}</span>
          <h2>{f.title}</h2>
        </div>
        <VerdictPill g={g} />
      </header>

      <div className="gauges">
        <Gauge value={accuracy(m.total_fill_error_pct)} tone="green" label="Fill accuracy" sub={errText(m.total_fill_error_pct)} />
        <Gauge value={accuracy(m.total_cut_error_pct)} tone="red" label="Cut accuracy" sub={errText(m.total_cut_error_pct)} />
      </div>

      <p className="vc-verdict">{sentence(m)}</p>

      <dl className="vc-stats">
        <div><dt>Sections checked</dt><dd className="num">{m.sections}</dd></div>
        <div><dt>Within 10 %</dt><dd className="num">{m.within_10pct == null ? '—' : `${Math.round(m.within_10pct)} %`}</dd></div>
        <div><dt>Typical error</dt><dd className="num">{m.median_error_pct == null ? '—' : `${m.median_error_pct.toFixed(1)} %`}</dd></div>
        <div><dt>9 in 10 sections within</dt><dd className="num">{m.p90_error_pct == null ? '—' : `${m.p90_error_pct.toFixed(0)} %`}</dd></div>
      </dl>
      <footer className="vc-ref">
        <IconInfo width={16} height={16} />
        <span>
          Checked against: {f.reference}.
          {f.second && (
            <> Against {f.second.reference}: total fill {signedPct(f.second.metrics.total_fill_error_pct)},
              total cut {signedPct(f.second.metrics.total_cut_error_pct)} — estimators measure by their own
              conventions, so this is a looser check.</>
          )}
        </span>
      </footer>
    </article>
  );
}

function LatestTakeoff({ job, onOpen, onNew }) {
  if (!job) {
    return (
      <section className="card cta">
        <div className="cta-icon"><IconUpload /></div>
        <div>
          <h3>Run a takeoff</h3>
          <p className="muted">Upload a 19-series, 23-series or CAD-exported cross-section PDF. Cover, plan and profile sheets are skipped automatically.</p>
        </div>
        <button className="btn primary" onClick={onNew}>Upload plan set</button>
      </section>
    );
  }
  if (!job.result) {
    const { done = 0, total = 0 } = job.progress || {};
    return (
      <section className="card cta">
        <div className="cta-icon spin"><IconUpload /></div>
        <div>
          <h3>Processing {job.filename}</h3>
          <p className="muted">{total ? `${done} of ${total} pages read` : 'Starting…'}</p>
        </div>
        <button className="btn" onClick={onOpen}>View progress</button>
      </section>
    );
  }
  const { roads, summary } = job.result;
  const counted = roads.filter((r) => !r.repeat_of);
  const surf = summary.design_surface;
  const fill = counted.reduce((a, r) => a + r.volumes[surf].fill_cy, 0);
  const cut = counted.reduce((a, r) => a + r.volumes[surf].cut_cy, 0);
  const net = fill - cut;
  return (
    <section className="card latest">
      <div className="card-h">
        <div>
          <span className="eyebrow">Latest takeoff</span>
          <h3>{job.filename}</h3>
        </div>
        <button className="btn" onClick={onOpen}>Open results <IconArrow width={18} height={18} /></button>
      </div>
      <div className="stat-tiles">
        <div className="tile t-red"><span>Cut</span><b className="num">{cy(cut)}</b><small>cubic yards</small></div>
        <div className="tile t-green"><span>Fill</span><b className="num">{cy(fill)}</b><small>cubic yards</small></div>
        <div className="tile t-blue"><span>Net</span><b className="num">{signed(net)}</b><small>{net >= 0 ? 'import needed' : 'surplus to export'}</small></div>
        <div className="tile t-yellow"><span>Sections</span><b className="num">{summary.sections}</b><small>{counted.length} road{counted.length === 1 ? '' : 's'} · {summary.cross_section_pages} sheets</small></div>
      </div>
    </section>
  );
}

export default function Dashboard({ report, job, onOpen, onNew, onAccuracy }) {
  return (
    <div className="page">
      <section className="hero">
        <div>
          <span className="eyebrow">Automated earthwork takeoff</span>
          <h2>Cut &amp; fill from cross-section plan sets, measured and verified</h2>
          <p className="muted">
            Every result below was measured end to end and checked against an independent reference:
            the exact CAD drawing of the same sheets.
          </p>
        </div>
        <button className="btn" onClick={onAccuracy}><IconAccuracy width={18} height={18} />Full accuracy report</button>
      </section>

      {report && <Headline report={report} compact />}

      {report === undefined && <div className="card skeleton" aria-busy="true">Loading accuracy…</div>}
      {report === null && (
        <div className="card note"><IconInfo />No accuracy report on this server yet. Run <code>python -m tools.accuracy_report</code> to create one.</div>
      )}
      {report && (
        <div className="verdict-grid">
          {report.formats.map((f) => <VerdictCard key={f.id} f={f} />)}
        </div>
      )}

      <LatestTakeoff job={job} onOpen={onOpen} onNew={onNew} />

      <section className="card scale">
        <h3>What the verdicts mean</h3>
        <ul>
          {GRADES.map((g) => (
            <li key={g.id}><span className={`pill verdict t-${g.tone}`}>{g.label}</span><span className="muted">{g.meaning}</span></li>
          ))}
        </ul>
      </section>
    </div>
  );
}
