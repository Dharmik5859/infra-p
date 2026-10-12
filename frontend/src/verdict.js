// Turns a measured error rate into a grade and a plain-English verdict.
//
// "Accuracy" of a quantity is 100 % minus the size of its total error against
// the reference (a 3.4 % shortfall on cut = 96.6 % cut accuracy). The grade
// takes the worse of fill and cut totals, plus how many individual sections
// land within 10 % -- totals can look good while sections scatter.

export const GRADES = [
  { id: 'excellent', label: 'Excellent', tone: 'green', maxTotal: 5, minWithin10: 75,
    meaning: 'Totals within 5 % and at least 3 in 4 sections within 10 %. Ready for estimating; spot-check flagged sections.' },
  { id: 'good', label: 'Good', tone: 'blue', maxTotal: 10, minWithin10: 60,
    meaning: 'Totals within 10 %. Suitable for estimating after reviewing the flagged sections.' },
  { id: 'fair', label: 'Fair', tone: 'yellow', maxTotal: 20, minWithin10: 0,
    meaning: 'Totals within 20 %. Useful for budgeting; review the section overlays before bidding.' },
  { id: 'review', label: 'Needs review', tone: 'red', maxTotal: Infinity, minWithin10: 0,
    meaning: 'Larger differences. Use the audit overlays to check each section.' },
];

export const accuracy = (errPct) => (errPct == null ? null : Math.max(0, 100 - Math.abs(errPct)));

export function grade(m) {
  const worst = Math.max(Math.abs(m.fill_error_pct ?? 100), Math.abs(m.cut_error_pct ?? 100));
  const w10 = m.within_10pct ?? 0;
  return GRADES.find((g) => worst <= g.maxTotal && w10 >= g.minWithin10) || GRADES[GRADES.length - 1];
}

const pct = (v) => `${Math.abs(v).toFixed(1)} %`;
const dir = (v) => (v > 0 ? 'over' : 'under');

export function sentence(m) {
  const parts = [];
  if (m.fill_error_pct != null && m.cut_error_pct != null) {
    parts.push(`Total fill came out ${pct(m.fill_error_pct)} ${dir(m.fill_error_pct)} and total cut `
      + `${pct(m.cut_error_pct)} ${dir(m.cut_error_pct)} the estimators' labels.`);
  }
  if (m.within_10pct != null) {
    parts.push(`${Math.round(m.within_10pct)} % of individual sections are within 10 %`
      + (m.median_error_pct != null ? ` (typical section error ${m.median_error_pct.toFixed(1)} %).` : '.'));
  }
  return parts.join(' ');
}
