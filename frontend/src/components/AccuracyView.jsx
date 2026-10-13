import Headline from './Headline';
import LabelledTable from './LabelledTable';
import { IconInfo } from './Icons';

const sign = (v) => (v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(1)}%`);
const pct = (v, d = 0) => (v == null ? '—' : `${Number(v).toFixed(d)}%`);

function GroupCard({ g }) {
  return (
    <section className="card group-card">
      <span className="eyebrow">{g.files} plan sets · {g.sections} sections</span>
      <h3>{g.title}</h3>
      <div className="big num">{pct(100 - Math.abs(g.total_error_pct), 1)}</div>
      <div className="muted">overall accuracy ({sign(g.total_error_pct)})</div>
      <dl>
        <div><dt>Fill</dt><dd className="num fill-text">{sign(g.fill_error_pct)}</dd></div>
        <div><dt>Cut</dt><dd className="num cut-text">{sign(g.cut_error_pct)}</dd></div>
        <div><dt>Within 25%</dt><dd className="num">{pct(g.within_25pct)}</dd></div>
      </dl>
    </section>
  );
}

export default function AccuracyView({ report }) {
  if (report === undefined) return <div className="page"><div className="card skeleton">Loading accuracy…</div></div>;
  if (report === null || !report.groups) {
    return <div className="page"><div className="card note"><IconInfo />No accuracy report has been generated on this server.</div></div>;
  }
  return (
    <div className="page">
      <section className="hero">
        <div>
          <h2>Accuracy</h2>
          <p className="muted">Compared with estimators' hand-labelled cut and fill · {report.generated}</p>
        </div>
      </section>
      <Headline report={report} />

      <div className="group-grid">
        {report.groups.map((g) => <GroupCard key={g.id} g={g} />)}
      </div>

      <LabelledTable files={report.files} unlabelled={report.unlabelled} />

      <details className="card prose">
        <summary>How it was measured</summary>
        <p><b>Labels.</b> Estimators shaded cut (red) and fill (green) by hand on each scan. That shading is the only reference.</p>
        <p><b>Comparison.</b> The pipeline reads the untouched scan, and each section it finds is scored against the shading inside it.</p>
        <p><b>Accuracy</b> is 100% minus the cut + fill area difference. <b>Within 10% / 25%</b> counts sections under that difference; sections under 10 ft² are left out.</p>
        <p><b>Staged sheets</b> shade only one stage's work while the pipeline measures the whole section, so they differ by design. Small plan sets swing widely, and the 19-series has no labels.</p>
      </details>
    </div>
  );
}
