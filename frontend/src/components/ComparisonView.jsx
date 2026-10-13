import { useEffect, useMemo, useRef, useState } from 'react';
import { compareJob, getComparison, listComparisons } from '../api';
import { cy, ft2 } from '../format';
import { IconCheck, IconFile, IconFlag, IconLayers, IconTrendDown, IconTrendUp, IconUpload } from './Icons';
import { Disclosure, Meter, StatCard } from './Ui';

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

const TONE_TAG = { ok: 'ok', near: 'warn', off: 'bad' };

function Kpi({ label, v, unit, fmt = ft2, icon, kind }) {
  const t = tone(v.diff, v.reference);
  return (
    <StatCard icon={icon} tone={kind} label={label} value={fmt(v.ours)} unit={unit}>
      <div className="chips">
        <span className={`tag ${TONE_TAG[t]} num`} title="Difference from the provided result">{pctText(v.pct)}</span>
        <span className="muted small-text num" title="Provided result">vs {fmt(v.reference)}</span>
      </div>
    </StatCard>
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
            <div className="chips cmp-meta">
              <span className="tag info" title="Plan set"><IconFile width={14} height={14} />{report.planSet}</span>
              <span className="muted small-text">vs</span>
              <span className="tag neutral" title="Provided results">{report.referenceFile}</span>
              {report.generated && <span className="tag neutral" title="Run">{report.generated}</span>}
              <span className="tag neutral" title="Areas measured to">{report.surface}</span>
              {report.referenceAreaUnit === 'yd2' && <span className="tag warn" title="Provided areas converted from yd² (× 9)">yd² × 9</span>}
            </div>
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
          <IconUpload width={16} height={16} />{busy ? 'Comparing…' : 'Compare with a file'}
        </button>
      </section>

      {error && <div className="warning">{error}</div>}
      {!report && !error && <div className="empty">{list && !list.length ? 'No stored comparisons yet.' : 'Loading…'}</div>}

      {report && (
        <>
          <div className="stat-grid cmp-stats">
            <Kpi label="Cut area" v={s.areaCutFt2} unit="ft²" icon={IconTrendDown} kind="red" />
            <Kpi label="Fill area" v={s.areaFillFt2} unit="ft²" icon={IconTrendUp} kind="green" />
            <Kpi label="Cut volume" v={s.volumeCutCy} unit="cy" fmt={cy} icon={IconTrendDown} kind="red" />
            <Kpi label="Fill volume" v={s.volumeFillCy} unit="cy" fmt={cy} icon={IconTrendUp} kind="green" />
            <StatCard icon={IconLayers} tone="blue" label="Stations" value={s.matched} unit={`/ ${s.referenceStations}`} className="v-plain"
              tip="Matched stations / provided stations. Areas above are over matched stations.">
              <Meter value={(100 * s.sectionsWithin25Pct) / Math.max(1, s.matched)} tone="yellow" label={`${s.sectionsWithin25Pct} of ${s.matched} within 25%`} />
              <div className="chips">
                <span className="tag ok" title="Sections within 10%">≤10%: {s.sectionsWithin10Pct}</span>
                <span className="tag warn" title="Sections within 25%">≤25%: {s.sectionsWithin25Pct}</span>
                {s.areaWeightedErrorPct != null && <span className="tag neutral" title="Area-weighted error">err {s.areaWeightedErrorPct}%</span>}
              </div>
            </StatCard>
          </div>

          {report.notes?.length > 0 && (
            <Disclosure title="What the differences come from" meta={`${report.notes.length} finding${report.notes.length === 1 ? '' : 's'}`} className="cmp-findings">
              <ul>{report.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
            </Disclosure>
          )}

          {(s.missing.length > 0 || s.extraSections.length > 0) && (
            <div className="cmp-gaps">
              {s.missing.length > 0 && (
                <details className="notes">
                  <summary><IconFlag width={16} height={16} /><b className="num">{s.missing.length}</b>
                    <span className="notes-label">not found in ours</span><span className="notes-peek mono">{s.missing.join(', ')}</span></summary>
                  <ul className="mono"><li>Provided but not found in our takeoff: {s.missing.join(', ')}</li></ul>
                </details>
              )}
              {s.extraSections.length > 0 && (
                <details className="notes info">
                  <summary><IconCheck width={16} height={16} /><b className="num">{s.extraSections.length}</b>
                    <span className="notes-label">only in ours</span><span className="notes-peek mono">{s.extraSections.join(', ')}</span></summary>
                  <ul className="mono"><li>In our takeoff, not in the provided results: {s.extraSections.join(', ')}</li></ul>
                </details>
              )}
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
                      <td className="street-cell" title={g.street}>{g.street}</td><td>{g.stage}</td><td className="num">{g.matched}/{g.stations}</td>
                      <Diff v={g.volumes.left_cut} unit=" cy" /><Diff v={g.volumes.left_fill} unit=" cy" />
                      <Diff v={g.volumes.right_cut} unit=" cy" /><Diff v={g.volumes.right_fill} unit=" cy" />
                      <Diff v={g.volumes.cut} unit=" cy" /><Diff v={g.volumes.fill} unit=" cy" />
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="cmp-legend" aria-label="Legend">
              <span className="muted small-text">ours / <small>provided</small></span>
              <span className="tag ok">≤ 10%</span><span className="tag warn">≤ 25%</span><span className="tag bad">&gt; 25%</span>
            </div>
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
                      <td className="muted street-cell" title={`${r.street} · ${r.stage}`}>{r.street} · {r.stage}</td>
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
            <div className="chips small-note">
              <IconFile width={14} height={14} /><span className="muted">Our takeoff</span>
              <span className="tag neutral">{report.sections} sections</span>
              {report.lowConfidence != null && <span className={`tag ${report.lowConfidence ? 'bad' : 'ok'}`}>{report.lowConfidence} below 85%</span>}
              <span className="tag neutral">{report.ourRoads.length} road{report.ourRoads.length === 1 ? '' : 's'}</span>
            </div>
          )}
        </>
      )}
    </div>
  );
}
