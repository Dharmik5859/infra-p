import { ft2 } from '../format';

/** Fill and cut left and right of the centreline, with the totals. */
export default function SideTable({ sides, note, compact = false }) {
  if (!sides) return null;
  const tot = (k) => sides.left[k] + sides.right[k] + (sides.unplaced?.[k] || 0);
  const unplaced = (sides.unplaced?.fill_ft2 || 0) + (sides.unplaced?.cut_ft2 || 0) > 0.005;
  return (
    <div className={`side-table ${compact ? 'compact' : ''}`}>
      <table aria-label="Fill and cut left and right of the centreline">
        <thead>
          <tr><th /><th>Left</th><th>Right</th><th>Total</th></tr>
        </thead>
        <tbody>
          <tr className="fill-row">
            <th>Fill ft²</th>
            <td className="num">{ft2(sides.left.fill_ft2)}</td>
            <td className="num">{ft2(sides.right.fill_ft2)}</td>
            <td className="num">{ft2(tot('fill_ft2'))}</td>
          </tr>
          <tr className="cut-row">
            <th>Cut ft²</th>
            <td className="num">{ft2(sides.left.cut_ft2)}</td>
            <td className="num">{ft2(sides.right.cut_ft2)}</td>
            <td className="num">{ft2(tot('cut_ft2'))}</td>
          </tr>
        </tbody>
      </table>
      {unplaced && (
        <div className="side-note warn-text">
          {ft2((sides.unplaced.fill_ft2 || 0) + (sides.unplaced.cut_ft2 || 0))} ft² was typed in where nothing is traced, so
          it is on neither side; outline it on the drawing to place it.
        </div>
      )}
      {note && <div className="side-note muted">{note}</div>}
    </div>
  );
}
