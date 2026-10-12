// Accuracy at a glance, measured ONLY against estimators' labelled takeoffs
// (backend/accuracy.json, built by tools.accuracy_report). Nothing here is
// hard-coded.

const fmtPct = (v, digits = 1) => `${Number(v).toFixed(digits).replace(/\.0$/, '')}%`;
const acc = (err) => 100 - Math.abs(err);

export default function Headline({ report, compact = false }) {
  const main = report?.groups?.find((g) => g.id === 'mainline');
  const all = report?.overall;
  if (!main || !all) return null;
  const tiles = [
    {
      tone: 'green', value: fmtPct(acc(main.total_error_pct)), meter: acc(main.total_error_pct),
      label: 'Cut + fill total vs the estimator',
      sub: `Mainline sheets: ${main.sections} labelled sections in ${main.files} plan sets (fill ${fmtPct(acc(main.fill_error_pct))}, cut ${fmtPct(acc(main.cut_error_pct))})`,
    },
    {
      tone: 'yellow', value: fmtPct(main.within_25pct, 0), meter: main.within_25pct,
      label: 'Sections within 25% of the estimator',
      sub: `${fmtPct(main.within_10pct, 0)} within 10% · typical section difference ${fmtPct(main.median_error_pct)}`,
    },
    {
      tone: 'blue', value: fmtPct(all.label_found_pct, 0), meter: all.label_found_pct,
      label: "Of the estimators' shading found",
      sub: 'Labelled area that falls inside a cross-section the pipeline located',
    },
    {
      tone: 'red', value: fmtPct(acc(all.total_error_pct)), meter: acc(all.total_error_pct),
      label: 'All labelled sheets, staged included',
      sub: `${all.sections} sections in ${all.files} plan sets; staged sheets shade only one stage's work`,
    },
  ];
  return (
    <section className={`headline ${compact ? 'compact' : ''}`} aria-label="Accuracy at a glance">
      <div className="headline-tiles">
        {tiles.map((t) => (
          <div key={t.label} className={`hl-tile t-${t.tone}`}>
            <div className="hl-value num">{t.value}</div>
            <div className="hl-meter" aria-hidden="true"><i style={{ width: `${Math.max(0, Math.min(100, t.meter))}%` }} /></div>
            <div className="hl-label">{t.label}</div>
            <div className="hl-sub">{t.sub}</div>
          </div>
        ))}
      </div>
      {!compact && (
        <p className="headline-basis">
          Measured only against labelled data: the cut (red) and fill (green) that estimators shaded by hand on
          {` ${all.files}`} scanned plan sets. The pipeline read the scan underneath, untouched, and every section the
          estimator shaded was compared. Per-section shares leave out sections under 10 ft², where a few square feet
          would swing the percentage.
        </p>
      )}
    </section>
  );
}
