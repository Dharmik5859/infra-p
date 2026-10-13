// Every labelled plan set: what the estimator shaded vs what the pipeline measured.

const sign = (v) => (v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(1)}%`);
const pct = (v, d = 0) => (v == null ? '—' : `${Number(v).toFixed(d)}%`);

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
          <h3>By plan set</h3>
        </div>
      </div>
      <div className="table-wrap tall">
        <table className="plan-table">
          <thead>
            <tr>
              <th>Plan set</th><th>Sections</th><th>Total</th><th>Fill</th><th>Cut</th><th>Within 25%</th>
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
                <td className="num">{sign(f.fill_error_pct)}</td>
                <td className="num">{sign(f.cut_error_pct)}</td>
                <td className="num">{pct(f.within_25pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {unlabelled?.length > 0 && (
        <p className="muted table-intro">
          Not scored (no labels): {unlabelled.map((u) => u.replace(/\.pdf$/i, '')).join(', ')}.
        </p>
      )}
    </section>
  );
}
