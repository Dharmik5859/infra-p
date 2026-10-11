import { useState } from 'react';

// Accuracy plan set by plan set: every PDF that was run, what was found in
// it, and -- where a reference exists -- how close the takeoff came.

const REF_LABEL = {
  cad: 'CAD drawing of the same sheets',
  estimator: "Estimator's hand takeoff",
};

function tone(acc) {
  if (acc == null) return '';
  if (acc >= 95) return 'g-green';
  if (acc >= 85) return 'g-blue';
  if (acc >= 70) return 'g-yellow';
  return 'g-red';
}

const acc = (err) => (err == null ? null : Math.max(0, 100 - Math.abs(err)));
const fmt = (v, d = 1) => (v == null ? '—' : `${Number(v).toFixed(d).replace(/\.0$/, '')}%`);

function AccCell({ err }) {
  const a = acc(err);
  if (a == null) return <td className="num muted">—</td>;
  return (
    <td className="num">
      <span className={`acc-pill ${tone(a)}`}>{fmt(a)}</span>
      <small className="muted"> {err > 0 ? '+' : err < 0 ? '−' : ''}{Math.abs(err).toFixed(1)}%</small>
    </td>
  );
}

export default function PlanSetTable({ planSets }) {
  const [all, setAll] = useState(false);
  if (!planSets?.length) return null;
  const checked = planSets.filter((p) => p.check);
  const rows = all ? planSets : checked;
  const totalSections = planSets.reduce((n, p) => n + (p.sections || 0), 0);

  return (
    <section className="card">
      <div className="card-h">
        <div>
          <span className="eyebrow">Tested on {planSets.length} PDFs · {totalSections.toLocaleString()} cross-sections</span>
          <h3>Accuracy by plan set</h3>
        </div>
        <div className="segmented" role="radiogroup" aria-label="Which plan sets to show">
          <button role="radio" aria-checked={!all} className={!all ? 'on' : ''} onClick={() => setAll(false)}>
            With a reference ({checked.length})
          </button>
          <button role="radio" aria-checked={all} className={all ? 'on' : ''} onClick={() => setAll(true)}>
            All PDFs ({planSets.length})
          </button>
        </div>
      </div>
      <p className="muted table-intro">
        Every PDF was run through the pipeline untouched. Where the same sheets also exist as a CAD drawing, or carry an
        estimator's takeoff, the result was compared section by section. <b>Volume accuracy</b> is 100% minus the
        difference in total cut + fill; <b>within 25%</b> counts individual sections.
      </p>
      <div className="table-wrap tall">
        <table className="plan-table">
          <thead>
            <tr>
              <th>Plan set</th><th>Pages</th><th>Sections found</th><th>Stations read</th>
              <th>Checked against</th><th>Sections checked</th><th>Volume accuracy</th>
              <th>Fill</th><th>Cut</th><th>Within 25%</th><th>Typical error</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const c = p.check;
              const read = p.sections ? (100 * p.stations_read) / p.sections : null;
              return (
                <tr key={`${p.folder}/${p.file}`}>
                  <td>
                    <b>{p.file.replace(/\.pdf$/i, '')}</b>
                    <div className="row-note">
                      {p.kind}{p.folder ? ` · ${p.folder.replace(/^EARTHWORK\//, '')}` : ''}
                      {p.no_earthwork ? ` · ${p.no_earthwork} with no earthwork` : ''}
                    </div>
                  </td>
                  <td className="num">{p.error ? '—' : p.pages}</td>
                  <td className="num">{p.error ? <span className="g-text-red">failed</span> : p.sections}</td>
                  <td className="num">{read == null ? '—' : `${Math.round(read)}%`}
                    {p.stations_inferred > 0 && <small className="muted"> +{p.stations_inferred} inferred</small>}</td>
                  <td className={c ? '' : 'muted'}>
                    {c ? REF_LABEL[p.reference] : p.kind === 'CAD drawing' ? 'Measured from the drawing itself' : 'No reference available'}
                  </td>
                  <td className="num">{c ? c.sections_checked : '—'}</td>
                  {c ? <AccCell err={c.volume_error_pct} /> : <td className="num muted">—</td>}
                  {c ? <AccCell err={c.fill_error_pct} /> : <td className="num muted">—</td>}
                  {c ? <AccCell err={c.cut_error_pct} /> : <td className="num muted">—</td>}
                  <td className="num">{c ? fmt(c.within_25pct, 0) : '—'}</td>
                  <td className="num">{c ? fmt(c.median_error_pct) : '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="muted table-intro">
        Estimators measure to their own conventions (for example, how far under the pavement cut is counted), so
        comparisons with their takeoffs are looser than those with the CAD drawing. Totals of a few hundred square feet
        swing the percentages widely; check the number of sections next to each figure.
      </p>
    </section>
  );
}
