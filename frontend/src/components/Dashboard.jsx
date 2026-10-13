import { annotatedPdfUrl } from '../api';
import { cy, signed } from '../format';
import { GRADES, accuracy, grade, sentence } from '../verdict';
import {
  IconAccuracy, IconArrow, IconBalance, IconChevron, IconCheck, IconDownload, IconInfo, IconLayers, IconTrendDown, IconTrendUp, IconUpload,
} from './Icons';
import Headline from './Headline';
import { InfoTip, StatCard } from './Ui';

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

export function VerdictPill({ g }) {
  return <span className={`pill verdict t-${g.tone}`} title={g.meaning}><IconCheck width={16} height={16} />{g.label}</span>;
}

export function VerdictCard({ f }) {
  const m = f.metrics;
  if (!m) {
    return (
      <article className="card verdict-card edge-neutral">
        <header className="vc-head">
          <div>
            <span className="eyebrow">{f.format}</span>
            <h2>{f.title}</h2>
          </div>
          <span className="pill verdict t-neutral">Not scored</span>
        </header>
        <p className="vc-verdict vc-short">
          <IconInfo width={18} height={18} />
          <span>No labelled copy to score against</span>
          <InfoTip label="Why this series is not scored">
            No estimator-labelled copy of this series is in the data, so there is nothing to score it against. Its
            takeoffs run normally; each section&apos;s picture shows exactly what was measured.
          </InfoTip>
        </p>
      </article>
    );
  }
  const g = grade(m);
  const errText = (e) => (e == null ? '' : `${e > 0 ? '+' : e < 0 ? '−' : ''}${Math.abs(e).toFixed(1)} % vs estimator`);
  return (
    <article className={`card verdict-card edge-${g.tone}`}>
      <header className="vc-head">
        <div>
          <span className="eyebrow">{f.format}</span>
          <h2>{f.title}</h2>
        </div>
        <span className="vc-pill">
          <VerdictPill g={g} />
          <InfoTip label="What this verdict means">
            <b>{g.label}:</b> {g.meaning}<br /><br />{sentence(m)}
          </InfoTip>
        </span>
      </header>

      <div className="gauges">
        <Gauge value={accuracy(m.fill_error_pct)} tone="green" label="Fill accuracy" sub={errText(m.fill_error_pct)} />
        <Gauge value={accuracy(m.cut_error_pct)} tone="red" label="Cut accuracy" sub={errText(m.cut_error_pct)} />
      </div>

      <dl className="vc-stats">
        <div><dt>Labelled sections</dt><dd className="num">{m.sections}</dd></div>
        <div><dt>Within 10 %</dt><dd className="num">{m.within_10pct == null ? '—' : `${Math.round(m.within_10pct)} %`}</dd></div>
        <div><dt>Typical error</dt><dd className="num">{m.median_error_pct == null ? '—' : `${m.median_error_pct.toFixed(1)} %`}</dd></div>
        <div><dt>90% within</dt><dd className="num">{m.p90_error_pct == null ? '—' : `${m.p90_error_pct.toFixed(0)} %`}</dd></div>
      </dl>
      <footer className="vc-ref" title={`Checked against ${f.reference}.`}>
        <IconInfo width={16} height={16} />
        <span className="ellipsis">Checked against {f.reference}</span>
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
          <div className="chips" style={{ marginTop: 6 }}>
            <span className="tag info">19-series</span><span className="tag ok">23-series</span><span className="tag warn">CAD PDF</span>
            <InfoTip label="Which PDFs work">Upload a 19-series, 23-series or CAD-exported cross-section PDF. Cover, plan and profile sheets are skipped automatically.</InfoTip>
          </div>
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
          <h3 className="ellipsis" title={job.filename}>Processing {job.filename}</h3>
          <div className="mini-bar" style={{ maxWidth: 360 }}><div className={total ? '' : 'indet'} style={total ? { width: `${(done / total) * 100}%` } : undefined} /></div>
          <p className="muted num small-text">{total ? `${done} / ${total} pages` : 'Starting…'}</p>
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
          <h3 className="ellipsis" title={job.filename}>{job.filename}</h3>
        </div>
        <div className="card-actions">
          <a className="btn" href={annotatedPdfUrl(job.job_id, roads.filter((r) => r.repeat_of).map((r) => r.id), surf)}><IconDownload width={18} height={18} />PDF</a>
          <button className="btn primary" onClick={onOpen}>Open results <IconArrow width={18} height={18} /></button>
        </div>
      </div>
      <div className="stat-grid">
        <StatCard icon={IconTrendDown} tone="red" label="Cut" value={cy(cut)} unit="cy" />
        <StatCard icon={IconTrendUp} tone="green" label="Fill" value={cy(fill)} unit="cy" />
        <StatCard icon={IconBalance} tone="blue" label="Net" value={signed(net)} unit="cy" className="v-plain">
          <div className="chips"><span className={`tag ${net >= 0 ? 'info' : 'warn'}`}>{net >= 0 ? 'import' : 'export'}</span></div>
        </StatCard>
        <StatCard icon={IconLayers} tone="yellow" label="Sections" value={summary.sections} className="v-plain">
          <div className="chips">
            <span className="tag neutral">{counted.length} road{counted.length === 1 ? '' : 's'}</span>
            <span className="tag neutral">{summary.cross_section_pages} sheets</span>
          </div>
        </StatCard>
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
          <h2>Cut &amp; fill, measured and verified</h2>
          <div className="chips">
            <span className="tag ok"><IconCheck width={14} height={14} />Scored vs estimator labels</span>
            <InfoTip label="How accuracy is measured">
              Accuracy below is measured only against estimators&apos; labelled takeoffs: the cut and fill they shaded
              by hand on the same sheets.
            </InfoTip>
          </div>
        </div>
        <button className="btn" onClick={onAccuracy}><IconAccuracy width={18} height={18} />Accuracy report</button>
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

      <details className="card scale disclosure-card">
        <summary>
          <span className="scale-title">Verdict scale</span>
          <span className="chips">
            {GRADES.map((g) => <span key={g.id} className={`pill verdict t-${g.tone}`} title={g.meaning}>{g.label}</span>)}
          </span>
          <IconChevron className="chev" width={16} height={16} />
        </summary>
        <ul>
          {GRADES.map((g) => (
            <li key={g.id}><span className={`pill verdict t-${g.tone}`}>{g.label}</span><span className="muted">{g.meaning}</span></li>
          ))}
        </ul>
      </details>
    </div>
  );
}
