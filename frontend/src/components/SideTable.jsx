import { ft2 } from '../format';
import { InfoTip } from './Ui';

/**
 * Fill and cut left and right of the centreline as bars growing out from
 * it, so the split reads at a glance; the numbers sit at each end.
 */
export default function SideTable({ sides, note, compact = false }) {
  if (!sides) return null;
  const rows = [['fill', 'Fill'], ['cut', 'Cut']];
  const max = Math.max(1e-9, ...rows.flatMap(([k]) => [sides.left[`${k}_ft2`], sides.right[`${k}_ft2`]]));
  const unplaced = (sides.unplaced?.fill_ft2 || 0) + (sides.unplaced?.cut_ft2 || 0);
  return (
    <div className={`split ${compact ? 'compact' : ''}`} role="table" aria-label="Fill and cut left and right of the centreline, square feet">
      <div className="split-head" role="row">
        <span role="columnheader" className="split-l">← Left</span>
        <span role="columnheader" className="split-cl">CL</span>
        <span role="columnheader" className="split-r">Right →</span>
        <span role="columnheader" className="split-t">Total</span>
      </div>
      {rows.map(([k, label]) => {
        const l = sides.left[`${k}_ft2`], r = sides.right[`${k}_ft2`];
        return (
          <div key={k} className={`split-row ${k}`} role="row">
            <span className="split-kind" role="rowheader">{label}</span>
            <span className="split-val l num" role="cell">{ft2(l)}</span>
            <span className="split-bar l" aria-hidden="true"><i style={{ width: `${(100 * l) / max}%` }} /></span>
            <span className="split-axis" aria-hidden="true" />
            <span className="split-bar r" aria-hidden="true"><i style={{ width: `${(100 * r) / max}%` }} /></span>
            <span className="split-val r num" role="cell">{ft2(r)}</span>
            <span className="split-val t num" role="cell">{ft2(l + r + (sides.unplaced?.[`${k}_ft2`] || 0))} ft²</span>
          </div>
        );
      })}
      {(unplaced > 0.005 || note) && (
        <div className="split-note chips">
          {unplaced > 0.005 && (
            <span className="tag warn num" title="Typed in where nothing is traced, so it is on neither side; outline it on the drawing to place it.">
              {ft2(unplaced)} ft² unplaced</span>
          )}
          {note && <><span className="tag neutral">centreline estimated</span><InfoTip label="About the centreline">{note}</InfoTip></>}
          {unplaced > 0.005 && <InfoTip label="About unplaced area">{ft2(unplaced)} ft² was typed in where nothing is traced, so it is on neither side; outline it on the drawing to place it.</InfoTip>}
        </div>
      )}
    </div>
  );
}
