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
      label: 'Overall accuracy', sub: `cut + fill vs estimator · ${main.sections} sections`,
    },
    {
      tone: 'yellow', value: fmtPct(main.within_25pct, 0), meter: main.within_25pct,
      label: 'Sections within 25%', sub: `${fmtPct(main.within_10pct, 0)} within 10%`,
    },
    {
      tone: 'blue', value: fmtPct(all.label_found_pct, 0), meter: all.label_found_pct,
      label: 'Shading found', sub: "of the estimators' labelled area",
    },
  ].slice(0, compact ? 2 : 3);
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
    </section>
  );
}
