const nf1 = new Intl.NumberFormat(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const nf0 = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });

export const cy = (v) => nf0.format(Math.round(v));
export const ft2 = (v) => nf1.format(v);
export const signed = (v) => (v > 0 ? '+' : v < 0 ? '−' : '') + nf0.format(Math.abs(Math.round(v)));

export function stationLabel(ft) {
  if (ft == null) return '—';
  const whole = Math.floor(ft / 100);
  const rest = ft - whole * 100;
  return `${whole}+${rest.toFixed(rest % 1 ? 2 : 0).padStart(rest % 1 ? 5 : 2, '0')}`;
}

export const SOURCE_TEXT = {
  text: 'from PDF text',
  ocr: 'read by OCR',
  inferred: 'inferred from sequence',
};
