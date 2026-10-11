import { accuracy, grade } from '../verdict';
import { VerdictPill } from './Dashboard';
import { IconInfo } from './Icons';

const signedPct = (v) => (v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(1)} %`);
const pct = (v) => (v == null ? '—' : `${v.toFixed(1)} %`);
const area = (v) => (v == null ? '—' : Math.round(v).toLocaleString());

export default function AccuracyView({ report }) {
  if (report === undefined) return <div className="page"><div className="card skeleton">Loading accuracy…</div></div>;
  if (report === null) {
    return <div className="page"><div className="card note"><IconInfo />No accuracy report has been generated on this server.</div></div>;
  }
  return (
    <div className="page">
      <section className="card">
        <div className="card-h">
          <div>
            <span className="eyebrow">Measured {report.generated}</span>
            <h3>Every evaluation</h3>
          </div>
        </div>
        <div className="table-wrap tall">
          <table className="acc-table">
            <thead>
              <tr>
                <th>Plan set</th><th>Reference</th><th>Verdict</th><th>Sections</th>
                <th>Fill accuracy</th><th>Cut accuracy</th><th>Within 10 %</th><th>Typical error</th>
                <th>Fill ft² (ours / ref)</th><th>Cut ft² (ours / ref)</th>
              </tr>
            </thead>
            <tbody>
              {report.checks.map((c) => {
                const m = c.metrics;
                return (
                  <tr key={c.id}>
                    <td><b>{c.title}</b></td>
                    <td className="muted">{c.reference}</td>
                    <td><VerdictPill g={grade(m)} /></td>
                    <td className="num">{m.sections}</td>
                    <td className="num"><span className="g-text-green">{pct(accuracy(m.total_fill_error_pct))}</span> <small className="muted">{signedPct(m.total_fill_error_pct)}</small></td>
                    <td className="num"><span className="g-text-red">{pct(accuracy(m.total_cut_error_pct))}</span> <small className="muted">{signedPct(m.total_cut_error_pct)}</small></td>
                    <td className="num">{m.within_10pct == null ? '—' : `${Math.round(m.within_10pct)} %`}</td>
                    <td className="num">{pct(m.median_error_pct)}</td>
                    <td className="num">{area(m.total_fill_ft2)} / {area(m.ref_total_fill_ft2)}</td>
                    <td className="num">{area(m.total_cut_ft2)} / {area(m.ref_total_cut_ft2)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <div className="two-col">
        <section className="card prose">
          <h3>How it was measured</h3>
          <p><b>Exact CAD geometry.</b> Some scanned sets also exist as CAD-exported PDFs of the same sheets. The scan is read
            from its pixels only; the CAD twin's linework gives the exact answer, matched station by station.</p>
          <p><b>Estimators' takeoffs.</b> Many scans in the EARTHWORK folder carry an estimator's red/green cut/fill shading on a
            separate layer. The pipeline reads only the drawing underneath; the shading is then measured as the human answer.
            Estimators sometimes follow different conventions (for example, how far below pavement cut is counted), so this is a
            looser reference than CAD geometry.</p>
          <p><b>Accuracy</b> is 100 % minus the difference in total fill (or cut) area across all checked sections.
            <b> Within 10 %</b> counts individual sections whose fill + cut is within 10 % of the reference; very small
            sections (under 10 ft² in total) are left out of that percentage because a few square feet swing it wildly.</p>
        </section>
        <section className="card prose">
          <h3>Known limitations</h3>
          <ul>
            <li>Station labels on scans are read by OCR and decoded across the whole document. Misreads that break the
              sequence are corrected and flagged under <i>Needs review</i>; a wrong but plausible label cannot be detected.</li>
            <li>Lines drawn with the same pen as the proposed template (temporary works, staging, removal lines) can be
              measured as earthwork. The audit overlay of every section shows exactly what was measured.</li>
            <li>Bridge decks and buried pipes are recognised and excluded, and reported on the section.</li>
            <li>A 10 ft major grid is assumed, which holds for every sheet series seen so far.</li>
          </ul>
        </section>
      </div>
    </div>
  );
}
