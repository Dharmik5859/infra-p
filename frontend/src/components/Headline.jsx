// Accuracy at a glance: the headline figures for a non-specialist audience,
// each with its plain definition underneath. Everything comes from the
// measured report (backend/accuracy.json); nothing here is hard-coded.

const fmtPct = (v, digits = 1) => `${Number(v).toFixed(digits).replace(/\.0$/, '')}%`;

export default function Headline({ report, compact = false }) {
  const h = report?.headline;
  if (!h) return null;
  const sc = report.scale;
  const found = (100 * h.sections_found_and_stationed) / h.sections_checked;
  const tiles = [
    {
      tone: 'blue', value: fmtPct(found, 0),
      label: 'Sections found with the right station',
      sub: `${h.sections_found_and_stationed} of ${h.sections_checked} sections located and matched to the drawing's station`,
    },
    {
      tone: 'green', value: fmtPct(100 - Math.abs(h.volume_error_pct)),
      label: 'Earthwork volume accuracy',
      sub: `Total cut + fill vs the exact drawing (fill ${fmtPct(100 - Math.abs(h.fill_error_pct))}, cut ${fmtPct(100 - Math.abs(h.cut_error_pct))})`,
    },
    {
      tone: 'yellow', value: fmtPct(h.within_25pct, 0),
      label: 'Sections within 25%',
      sub: `${fmtPct(h.within_10pct, 0)} within 10% · typical section error ${fmtPct(h.median_error_pct)}`,
    },
    sc ? {
      tone: 'red', value: sc.sections.toLocaleString(),
      label: 'Sections measured automatically',
      sub: `${sc.plan_sets_processed} plan sets · ${sc.pages.toLocaleString()} pages · no manual input`,
    } : null,
  ].filter(Boolean);

  return (
    <section className={`headline ${compact ? 'compact' : ''}`} aria-label="Accuracy at a glance">
      <div className="headline-tiles">
        {tiles.map((t) => (
          <div key={t.label} className={`hl-tile t-${t.tone}`}>
            <div className="hl-value num">{t.value}</div>
            <div className="hl-label">{t.label}</div>
            <div className="hl-sub">{t.sub}</div>
          </div>
        ))}
      </div>
      {!compact && (
        <p className="headline-basis">
          Measured on {h.sections_checked} cross-sections from {h.plan_sets?.length || 'several'} scanned plan sets
          (the 19-series, the 23-series layout and others), each compared with the exact CAD drawing of the same
          sheet. Sections that could not be matched to the drawing by station count against the first figure.
          Per-section shares leave out sections under 10 ft², where a few square feet would swing the percentage.
        </p>
      )}
    </section>
  );
}
