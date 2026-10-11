import { useEffect, useState } from 'react';
import { ft2 } from '../format';

/**
 * A square-feet input that lets the user type freely ("12.", "") and only
 * reports a value once it is a valid non-negative number.
 */
export function AreaInput({ value, onChange, label, tone }) {
  const [text, setText] = useState(String(value));
  const [focused, setFocused] = useState(false);
  // follow outside changes (reset, discard, switching section) while not typing
  useEffect(() => { if (!focused) setText(String(value)); }, [value, focused]);
  const n = Number(text);
  const invalid = text.trim() === '' || !Number.isFinite(n) || n < 0;
  return (
    <input
      className={`area-input ${tone || ''} ${invalid ? 'invalid' : ''}`}
      type="number" inputMode="decimal" min="0" step="0.1"
      value={text} aria-label={label} aria-invalid={invalid}
      onFocus={() => setFocused(true)}
      onBlur={() => { setFocused(false); if (invalid) setText(String(value)); }}
      onChange={(e) => {
        setText(e.target.value);
        const v = Number(e.target.value);
        if (e.target.value.trim() !== '' && Number.isFinite(v) && v >= 0) onChange(Math.round(v * 100) / 100);
      }}
      onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur(); }}
    />
  );
}

/** Every section of the road with editable fill and cut areas. */
export default function AreaEditor({ sections, selectedId, onSelect, onEdit, onReset, surfaceLabel }) {
  if (sections.length === 0) return <div className="empty">No sections on this road.</div>;
  return (
    <>
      <div className="editor-hint muted">
        Type over any area to correct it (square feet, measured to {surfaceLabel.toLowerCase()}). The chart, volumes and
        totals update as you type; press <b>Save changes</b> to keep them.
      </div>
      <div className="table-wrap">
        <table className="edit-table">
          <thead>
            <tr>
              <th>Station</th><th>Page</th>
              <th>Fill (ft²)</th><th>Measured</th>
              <th>Cut (ft²)</th><th>Measured</th>
              <th>Net (ft²)</th><th />
            </tr>
          </thead>
          <tbody>
            {sections.map((s) => (
              <tr key={s.id} className={`${s.id === selectedId ? 'sel-row' : ''} ${s.edited ? 'edited-row' : ''}`}
                onClick={(e) => { if (!e.target.closest('input, button')) onSelect(s.id); }}>
                <td className="mono">{s.station || '—'}</td>
                <td className="num">{s.page}</td>
                <td><AreaInput value={s.fill_ft2} tone="fill" label={`Fill at ${s.station || `page ${s.page}`}`}
                  onChange={(v) => onEdit(s.id, { fill_ft2: v, cut_ft2: s.cut_ft2 })} /></td>
                <td className="num muted">{ft2(s.measured.fill_ft2)}</td>
                <td><AreaInput value={s.cut_ft2} tone="cut" label={`Cut at ${s.station || `page ${s.page}`}`}
                  onChange={(v) => onEdit(s.id, { fill_ft2: s.fill_ft2, cut_ft2: v })} /></td>
                <td className="num muted">{ft2(s.measured.cut_ft2)}</td>
                <td className="num">{ft2(s.net_ft2)}</td>
                <td>
                  <div className="row-actions">
                    {s.zero && <span className="tag neutral" title={s.zero.text}>no earthwork</span>}
                    {s.dirty && <span className="tag warn">unsaved</span>}
                    {s.edited && !s.dirty && <span className="tag edited">edited</span>}
                    {s.edited && <button className="btn ghost small" onClick={() => onReset(s.id)}>Reset</button>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
