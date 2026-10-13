import { VerdictCard } from './Dashboard';
import Headline from './Headline';
import LabelledTable from './LabelledTable';
import { IconAlert, IconCheck, IconInfo } from './Icons';
import { Disclosure, InfoTip, Meter } from './Ui';

const sign = (v) => (v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(1)}%`);
const pct = (v, d = 0) => (v == null ? '—' : `${Number(v).toFixed(d)}%`);

function GroupCard({ g }) {
  return (
    <section className="card group-card">
      <div className="group-top">
        <h3>{g.title}</h3>
        {g.note && <InfoTip label={`About ${g.title}`}>{g.note}</InfoTip>}
      </div>
      <div className="chips">
        <span className="tag neutral">{g.files} plan sets</span>
        <span className="tag neutral">{g.sections} sections</span>
      </div>
      <div className="group-big">
        <div className="big num">{pct(100 - Math.abs(g.total_error_pct), 1)}</div>
        <span className="muted small-text" title="Cut + fill total vs the estimator">total · {sign(g.total_error_pct)}</span>
      </div>
      <Meter value={100 - Math.abs(g.total_error_pct)} tone="green" />
      <dl>
        <div><dt>Fill</dt><dd className="num fill-text">{sign(g.fill_error_pct)}</dd></div>
        <div><dt>Cut</dt><dd className="num cut-text">{sign(g.cut_error_pct)}</dd></div>
        <div><dt>Within 25%</dt><dd className="num">{pct(g.within_25pct)}</dd></div>
        <div><dt>Typical diff.</dt><dd className="num">{pct(g.median_error_pct, 1)}</dd></div>
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
          <span className="eyebrow">Labelled data only · {report.generated}</span>
          <h2>How close are we to the estimators?</h2>
          <div className="chips">
            <span className="tag cut">cut = red shading</span>
            <span className="tag fill">fill = green shading</span>
            <InfoTip label="What the reference is">
              Estimators shaded cut red and fill green by hand on scanned plan sets. Those labels are the only
              reference used on this page: the pipeline read each scan untouched and every labelled section was compared.
            </InfoTip>
          </div>
        </div>
      </section>
      <Headline report={report} />

      <div className="group-grid">
        {report.groups.map((g) => <GroupCard key={g.id} g={g} />)}
      </div>

      <div className="verdict-grid">
        {report.formats.map((f) => <VerdictCard key={f.id} f={f} />)}
      </div>

      <LabelledTable files={report.files} unlabelled={report.unlabelled} />

      <div className="disclosure-grid">
        <Disclosure title="How it was measured" icon={IconCheck} className="prose">
          <p><b>The labels.</b> On each scan the estimator&apos;s shading sits on its own transparent layer. Its area is
            measured shape by shape (the bright fill plus half of each shape&apos;s outline, which is drawn on the
            shape&apos;s edge); orange and brown notes are not counted. Tested on shapes of known size in the
            estimators&apos; colours, this is within 1% (a few % on slivers about 1 ft thick).</p>
          <p><b>The comparison.</b> The pipeline runs on the scan underneath without seeing the shading. For every
            section it finds, the estimator&apos;s shading inside that section is the answer it is scored against.
            Shading outside every found section counts against <i>shading found</i>.</p>
          <p><b>Total</b> is 100% minus the difference in cut + fill area summed over the labelled sections.
            <b> Within 10% / 25%</b> count sections whose fill + cut difference is within that share of the
            estimator&apos;s; sections under 10 ft² are left out of those shares.</p>
        </Disclosure>
        <Disclosure title="What the differences mean" icon={IconAlert} meta="4 notes" className="prose">
          <ul>
            <li><b>Staged sheets</b> show the same cross-sections as the mainline set, but the estimator shades only
              that stage&apos;s work. The pipeline measures the whole section and does not yet separate stages, so these
              differ by design (at the same 77 River Side stations the pipeline measured nearly the same area on the
              Stage 3 and mainline sheets, while the Stage 3 shading was under a third of the mainline&apos;s).</li>
            <li>Estimators follow their own conventions, such as how far under the pavement cut is counted; part of
              any per-section difference is convention, not error.</li>
            <li>Small plan sets with little earthwork (Florence, Hamilton) have totals of a few hundred ft², so their
              percentages swing widely.</li>
            <li>The 19-series has no labelled copy in the data, so it is not scored here.</li>
          </ul>
        </Disclosure>
      </div>
    </div>
  );
}
