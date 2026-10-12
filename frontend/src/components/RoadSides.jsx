import { cy, ft2 } from '../format';

/**
 * A road's earthwork left and right of the centreline: volumes (cy, by
 * average end area, side by side) and the cross-section areas they come
 * from (ft², summed over the road's sections).
 */
export default function RoadSides({ road }) {
  if (!road?.sides) return null;
  const { sides, area } = road;
  const rows = [['fill', 'Fill'], ['cut', 'Cut']];
  return (
    <div className="road-sides">
      <table aria-label={`${road.label}: fill and cut left and right of the centreline`}>
        <thead>
          <tr>
            <th rowSpan={2} />
            <th colSpan={3} className="grp">Volume (cy)</th>
            <th colSpan={3} className="grp">Section area (ft², summed)</th>
          </tr>
          <tr>
            <th>← Left</th><th>Right →</th><th>Total</th>
            <th>← Left</th><th>Right →</th><th>Total</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([k, label]) => (
            <tr key={k} className={`${k}-row`}>
              <th>{label}</th>
              <td className="num">{cy(sides.left[`${k}_cy`])}</td>
              <td className="num">{cy(sides.right[`${k}_cy`])}</td>
              <td className="num tot">{cy(road[`${k}_cy`])}</td>
              <td className="num">{ft2(area.left[k])}</td>
              <td className="num">{ft2(area.right[k])}</td>
              <td className="num tot">{ft2(area[k])}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
