import { useEffect, useMemo, useRef, useState } from 'react';
import { compareJob, getComparison, listComparisons } from '../api';
import { cy, ft2 } from '../format';
import { IconFile, IconUpload } from './Icons';

const pctText = (p) => (p == null ? '—' : `${p > 0 ? '+' : ''}${p.toFixed(1)}%`);
const tone = (d, ref) => {
  const tol = Math.max(5, 0.1 * Math.abs(ref));
  if (Math.abs(d) <= tol) return 'ok';
  return Math.abs(d) <= Math.max(5, 0.25 * Math.abs(ref)) ? 'near' : 'off';
};

function Diff({ v, unit = '' }) {
  if (!v) return <td className="num muted">—</td>;
  return (
    <td className={`num cmp-cell ${tone(v.diff, v.reference)}`} title={`ours ${v.ours}${unit} · provided ${v.reference}${unit} · ${pctText(v.pct)}`}>
      <span>{ft2(v.ours)}</span><small>{ft2(v.reference)}</small>
    </td>
  );
}

function Kpi({ label, v, unit, fmt = ft2 }) {
  return (
    <div className="kpi">
      <div className="label">{label}</div>
      <div className="value num">{fmt(v.ours)}<small>{unit}</small></div>
      <div className="sub">provided {fmt(v.reference)} {unit} · <b className={tone(v.diff, v.reference) === 'ok' ? 'fill-text' : 'cut-text'}>{pctText(v.pct)}</b></div>
    </div>
  );
}

/**
 * Our takeoff against results provided for the same plan set (the SR 5
 * connector comparison ships with the app); any open takeoff can be compared
 * with a results spreadsheet too.
 */
export default function ComparisonView({ openJob }) {
  const [list, setList] = useState(null);
  const [name, setName] = useState(null);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState('all');
  const input = useRef(null);

  useEffect(() => {
    listComparisons().then((l) => { setList(l); if (l.length) setName(l[0].name); }).catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (!name) return;
    setReport(null);
    getComparison(name).then(setReport).catch((e) => setError(e.message));
  }, [name]);

  async function upload(files) {
    const f = files?.[0];
    if (!f || !openJob) return;
    setBusy(true); setError(null);
    try {
      setReport(await compareJob(openJob.job_id, f));
      setName(null);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  const rows = useMemo(() => {
    if (!report) return [];
    return report.rows.filter((r) => {
      if (filter === 'all') return true;
      if (filter === 'missing') return r.status !== 'matched';
      if (r.status !== 'matched') return false;
      return ['total_cut', 'total_fill'].some((k) => tone(r.areas[k].diff, r.areas[k].reference) === 'off');
    });
  }, [report, filter]);

  const s = report?.summary;
  return (
    <div className="page cmp-page">
      <section className="card cmp-head">
        <div>
          <span className="eyebrow">Comparison with provided results</span>
          <h2>{report?.title || 'Comparison'}</h2>
          {report && (
            <p className="muted">
              {report.planSet} vs {report.referenceFile}
              {report.generated && <> · run {report.generated}</>} · areas to {report.surface}
              {report.referenceAreaUnit === 'yd2' && <> · provided areas converted from yd² (× 9)</>}
            </p>
          )}
        </div>
        <span className="spacer" />
        {list && list.length > 1 && (
          <select value={name || ''} onChange={(e) => setName(e.target.value)} aria-label="Stored comparison">
            {list.map((c) => <option key={c.name} value={c.name}>{c.title || c.name}</option>)}
          </select>
        )}
        {list && list.length === 1 && name === null && (
          <button className="btn small" onClick={() => setName(list[0].name)}>Back to {list[0].title}</button>
        )}
        <input ref={input} type="file" hidden accept=".xlsx,.csv" onChange={(e) => upload(e.target.files)} />
        <button className="btn" disabled={!openJob || busy} onClick={() => input.current?.click()}
          title={openJob ? `Compare ${openJob.filename} with a results spreadsheet` : 'Open a takeoff first'}>
          <IconUpload width={16} height={16} />{busy ? 'Comparing…' : 'Compare open takeoff with a file'}
        </button>
      </section>

      {error && <div className="warning">{error}</div>}
      {!report && !error && <div className="empty">{list && !list.length ? 'No stored comparisons yet.' : 'Loading…'}</div>}

      {report && (
        <>
          <div className="kpis">
            <Kpi label="Cut area, matched stations" v={s.areaCutFt2} unit="ft²" />
            <Kpi label="Fill area, matched stations" v={s.areaFillFt2} unit="ft²" />
            <Kpi label="Cut volume" v={s.volumeCutCy} unit="cy" fmt={cy} />
            <Kpi label="Fill volume" v={s.volumeFillCy} unit="cy" fmt={cy} />
            <div className="kpi">
              <div className="label">Stations</div>
              <div className="value num">{s.matched}<small>/ {s.referenceStations}</small></div>
              <div className="sub">
                within 10%: <b>{s.sectionsWithin10Pct}</b> · within 25%: <b>{s.sectionsWithin25Pct}</b>
                {s.areaWeightedErrorPct != null && <> · area error {s.areaWeightedErrorPct}%</>}
              </div>
            </div>
          </div>

          {report.notes?.length > 0 && (
            <section className="card cmp-findings">
              <span className="eyebrow">What the differences come from</span>
              <ul>{report.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
            </section>
          )}

          {(s.missing.length > 0 || s.extraSections.length > 0) && (
            <div className="cmp-notes">
              {s.missing.length > 0 && <div><b>Provided but not found in our takeoff:</b> <span className="mono">{s.missing.join(', ')}</span></div>}
              {s.extraSections.length > 0 && <div><b>In our takeoff, not in the provided results:</b> <span className="mono">{s.extraSections.join(', ')}</span></div>}
            </div>
          )}

          <section className="card">
            <div className="json-head"><div><span className="eyebrow">By street and stage</span><h3>Volumes (average end area)</h3></div></div>
            <div className="table-wrap">
              <table className="values-table cmp-table">
                <thead><tr><th>Street</th><th>Stage</th><th className="num">Stations</th>
                  <th className="num">Left cut</th><th className="num">Left fill</th><th className="num">Right cut</th><th className="num">Right fill</th>
                  <th className="num">Cut</th><th className="num">Fill</th></tr></thead>
                <tbody>
                  {report.groups.map((g) => (
                    <tr key={`${g.street}-${g.stage}`}>
                      <td>{g.street}</td><td>{g.stage}</td><td className="num">{g.matched}/{g.stations}</td>
                      <Diff v={g.volumes.left_cut} unit=" cy" /><Diff v={g.volumes.left_fill} unit=" cy" />
                      <Diff v={g.volumes.right_cut} unit=" cy" /><Diff v={g.volumes.right_fill} unit=" cy" />
                      <Diff v={g.volumes.cut} unit=" cy" /><Diff v={g.volumes.fill} unit=" cy" />
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted small-note">Each cell: ours on top, provided below. Green within 10 %, amber within 25 %, red beyond.</p>
          </section>

          <section className="card">
            <div className="json-head">
              <div><span className="eyebrow">Section by section · ft²</span><h3>Areas left and right of the centreline</h3></div>
              <span className="spacer" />
              <div className="segmented small" role="radiogroup" aria-label="Rows">
                {[['all', 'All'], ['off', 'Over 25% off'], ['missing', 'Not found']].map(([k, label]) => (
                  <button key={k} role="radio" aria-checked={filter === k} className={filter === k ? 'on' : ''} onClick={() => setFilter(k)}>{label}</button>
                ))}
              </div>
            </div>
            <div className="table-wrap cmp-scroll">
              <table className="values-table cmp-table">
                <thead><tr><th>Station</th><th>Street · stage</th><th className="num">Sheet</th><th className="num">Conf.</th>
                  <th className="num">Left cut</th><th className="num">Left fill</th><th className="num">Right cut</th><th className="num">Right fill</th>
                  <th className="num">Total cut</th><th className="num">Total fill</th></tr></thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i} className={r.status !== 'matched' ? 'missing-row' : ''}>
                      <td className="mono">{r.station}</td>
                      <td className="muted">{r.street} · {r.stage}</td>
                      <td className="num">{r.page ?? '—'}</td>
                      <td className="num">{r.confidence != null ? `${r.confidence}%` : '—'}</td>
                      {r.status === 'matched' ? (
                        ['left_cut', 'left_fill', 'right_cut', 'right_fill', 'total_cut', 'total_fill'].map((k) => <Diff key={k} v={r.areas[k]} unit=" ft²" />)
                      ) : (
                        <td colSpan={6} className="muted">not found in our takeoff (provided: left cut {ft2(r.reference.left.cut_ft2)}, right cut {ft2(r.reference.right.cut_ft2)}, left fill {ft2(r.reference.left.fill_ft2)}, right fill {ft2(r.reference.right.fill_ft2)})</td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {report.ourRoads && (
            <p className="muted small-note"><IconFile width={14} height={14} /> Our takeoff found {report.sections} sections
              {report.lowConfidence != null && <> ({report.lowConfidence} below 85% confidence)</>}, on {report.ourRoads.length} road{report.ourRoads.length === 1 ? '' : 's'}.</p>
          )}
        </>
      )}
    </div>
  );
}
