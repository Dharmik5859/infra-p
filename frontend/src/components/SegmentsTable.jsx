import { cy, signed } from '../format';

export default function SegmentsTable({ road, sections, onSelect }) {
  if (!road) return <div className="empty">Select a road.</div>;
  if (road.segments.length === 0) {
    return <div className="empty">This road has a single section, so no volume can be computed between stations.</div>;
  }
  // map a station label back to its section so a row click opens it
  const byLabel = new Map(road.sections.map((i) => [sections[i].station, i]));
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr><th>From</th><th>To</th><th>Length (ft)</th><th>Cut (cy)</th><th>Fill (cy)</th><th>Net (cy)</th>
            <th>Left cut (cy)</th><th>Left fill (cy)</th><th>Right cut (cy)</th><th>Right fill (cy)</th></tr>
        </thead>
        <tbody>
          {road.segments.map((s, i) => (
            <tr key={i} className="seg-row" tabIndex={0}
              onClick={() => byLabel.has(s.to) && onSelect(byLabel.get(s.to))}
              onKeyDown={(e) => { if (e.key === 'Enter' && byLabel.has(s.to)) onSelect(byLabel.get(s.to)); }}
              title={s.warning || ''}>
              <td className="mono">{s.from}</td>
              <td className="mono">{s.to}{s.warning && <span className="tag warn" style={{ marginLeft: 6 }}>!</span>}
                {s.edited && <span className="tag edited" style={{ marginLeft: 6 }} title="uses a hand-edited area">edited</span>}</td>
              <td className="num">{s.length_ft}</td>
              <td className="num cut-text">{cy(s.cut_cy)}</td>
              <td className="num fill-text">{cy(s.fill_cy)}</td>
              <td className="num">{signed(s.net_cy)}</td>
              <td className="num cut-text">{s.sides ? cy(s.sides.left.cut_cy) : '—'}</td>
              <td className="num fill-text">{s.sides ? cy(s.sides.left.fill_cy) : '—'}</td>
              <td className="num cut-text">{s.sides ? cy(s.sides.right.cut_cy) : '—'}</td>
              <td className="num fill-text">{s.sides ? cy(s.sides.right.fill_cy) : '—'}</td>
            </tr>
          ))}
          <tr className="total">
            <td>Total</td><td />
            <td className="num">{Math.round(road.segments.reduce((a, s) => a + s.length_ft, 0))}</td>
            <td className="num cut-text">{cy(road.cut_cy)}</td>
            <td className="num fill-text">{cy(road.fill_cy)}</td>
            <td className="num">{signed(road.net_cy)}</td>
            <td className="num cut-text">{road.sides ? cy(road.sides.left.cut_cy) : '—'}</td>
            <td className="num fill-text">{road.sides ? cy(road.sides.left.fill_cy) : '—'}</td>
            <td className="num cut-text">{road.sides ? cy(road.sides.right.cut_cy) : '—'}</td>
            <td className="num fill-text">{road.sides ? cy(road.sides.right.fill_cy) : '—'}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
