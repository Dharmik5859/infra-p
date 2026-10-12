// Every labelled plan set: what the estimator shaded vs what the pipeline measured.

const sign = (v) => (v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(1)}%`);
const pct = (v, d = 0) => (v == null ? '—' : `${Number(v).toFixed(d)}%`);
const area = (v) => Math.round(v).toLocaleString();

function tone(err) {
  if (err == null) return '';
  const a = Math.abs(err);
  return a <= 5 ? 'g-green' : a <= 15 ? 'g-blue' : a <= 30 ? 'g-yellow' : 'g-red';
}

export default function LabelledTable({ files, unlabelled }) {
  if (!files?.length) return null;
  return (
    <section className="card">
      <div className="card-h">
        <div>
          <span className="eyebrow">{files.length} labelled plan sets</span>
          <h3>Plan set by plan set</h3>
        </div>
      </div>
      <p className="muted table-intro">
        <b>Total</b> compares the cut + fill area summed over every section the estimator shaded; <b>fill</b> and
        <b> cut</b> compare each on its own. <b>Within 25%</b> counts individual sections. <b>Shading found</b> is the share
        of the estimator&apos;s shading that lies inside a section the pipeline located.
      </p>
      <div className="table-wrap tall">
        <table className="plan-table">
          <thead>
            <tr>
              <th>Plan set</th><th>Labelled sections</th><th>Total</th>
              <th>Fill ft² (ours / estimator)</th><th>Cut ft² (ours / estimator)</th>
              <th>Within 10%</th><th>Within 25%</th><th>Typical difference</th><th>Shading found</th>
            </tr>
          </thead>
          <tbody>
            {files.map((f) => (
              <tr key={f.file}>
                <td>
                  <b>{f.file.replace(/\.pdf$/i, '')}</b>
                  <span className={`tag kind-tag ${f.kind === 'staged' ? 'warn' : 'neutral'}`}>{f.kind === 'staged' ? 'staged' : 'mainline'}</span>
                </td>
                <td className="num">{f.sections}{f.sections_found ? <small className="muted"> of {f.sections_found}</small> : null}</td>
                <td className="num"><span className={`acc-pill ${tone(f.total_error_pct)}`}>{sign(f.total_error_pct)}</span></td>
                <td className="num">{area(f.fill_ft2)} / {area(f.label_fill_ft2)} <small className="muted">{sign(f.fill_error_pct)}</small></td>
                <td className="num">{area(f.cut_ft2)} / {area(f.label_cut_ft2)} <small className="muted">{sign(f.cut_error_pct)}</small></td>
                <td className="num">{pct(f.within_10pct)}</td>
                <td className="num">{pct(f.within_25pct)}</td>
                <td className="num">{pct(f.median_error_pct, 1)}</td>
                <td className="num">{pct(f.label_found_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {unlabelled?.length > 0 && (
        <p className="muted table-intro">
          Also run, but carrying no estimator labels, so not scored: {unlabelled.map((u) => u.replace(/\.pdf$/i, '')).join(', ')}.
        </p>
      )}
    </section>
  );
}
