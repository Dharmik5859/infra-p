// Accuracy at a glance, measured ONLY against estimators' labelled takeoffs
// (backend/accuracy.json, built by tools.accuracy_report). Nothing here is
// hard-coded.

import { IconAccuracy, IconFlag, IconLayers, IconScan } from './Icons';
import { Disclosure, InfoTip } from './Ui';

const fmtPct = (v, digits = 1) => `${Number(v).toFixed(digits).replace(/\.0$/, '')}%`;
const acc = (err) => 100 - Math.abs(err);

export default function Headline({ report, compact = false }) {
  const main = report?.groups?.find((g) => g.id === 'mainline');
  const all = report?.overall;
  if (!main || !all) return null;
  const tiles = [
    {
      tone: 'green', value: fmtPct(acc(main.total_error_pct)), meter: acc(main.total_error_pct),
      label: 'Cut + fill total', Icon: IconAccuracy,
      chips: [['fill', `fill ${fmtPct(acc(main.fill_error_pct))}`], ['cut', `cut ${fmtPct(acc(main.cut_error_pct))}`]],
      tip: `Cut + fill total vs the estimator. Mainline sheets: ${main.sections} labelled sections in ${main.files} plan sets (fill ${fmtPct(acc(main.fill_error_pct))}, cut ${fmtPct(acc(main.cut_error_pct))}).`,
    },
    {
      tone: 'yellow', value: fmtPct(main.within_25pct, 0), meter: main.within_25pct,
      label: 'Sections within 25%', Icon: IconLayers,
      chips: [['neutral', `≤10%: ${fmtPct(main.within_10pct, 0)}`], ['neutral', `typical ${fmtPct(main.median_error_pct)}`]],
      tip: `Sections within 25% of the estimator. ${fmtPct(main.within_10pct, 0)} within 10% · typical section difference ${fmtPct(main.median_error_pct)}.`,
    },
    {
      tone: 'blue', value: fmtPct(all.label_found_pct, 0), meter: all.label_found_pct,
      label: 'Shading found', Icon: IconScan,
      chips: [],
      tip: "Of the estimators' shading found: labelled area that falls inside a cross-section the pipeline located.",
    },
    {
      tone: 'red', value: fmtPct(acc(all.total_error_pct)), meter: acc(all.total_error_pct),
      label: 'All sheets, staged incl.', Icon: IconFlag,
      chips: [['neutral', `${all.sections} sections`], ['neutral', `${all.files} sets`]],
      tip: `All labelled sheets, staged included: ${all.sections} sections in ${all.files} plan sets; staged sheets shade only one stage's work.`,
    },
  ];
  return (
    <section className={`headline ${compact ? 'compact' : ''}`} aria-label="Accuracy at a glance">
      <div className="headline-tiles">
        {tiles.map((t) => (
          <div key={t.label} className={`hl-tile t-${t.tone}`}>
            <div className="hl-top">
              <span className="hl-icon" aria-hidden="true"><t.Icon width={18} height={18} /></span>
              <span className="hl-label">{t.label}</span>
              <InfoTip label={`About ${t.label.toLowerCase()}`}>{t.tip}</InfoTip>
            </div>
            <div className="hl-value num">{t.value}</div>
            <div className="hl-meter" aria-hidden="true"><i style={{ width: `${Math.max(0, Math.min(100, t.meter))}%` }} /></div>
            {t.chips.length > 0 && (
              <div className="chips hl-chips">{t.chips.map(([tone, text]) => <span key={text} className={`tag ${tone}`}>{text}</span>)}</div>
            )}
          </div>
        ))}
      </div>
      {!compact && (
        <Disclosure title="How these are measured" className="headline-basis">
          Measured only against labelled data: the cut (red) and fill (green) that estimators shaded by hand on
          {` ${all.files}`} scanned plan sets. The pipeline read the scan underneath, untouched, and every section the
          estimator shaded was compared. Per-section shares leave out sections under 10 ft², where a few square feet
          would swing the percentage.
        </Disclosure>
      )}
    </section>
  );
}
