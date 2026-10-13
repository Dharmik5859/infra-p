import { useCallback, useEffect, useMemo, useState } from 'react';
import { annotatedPdfUrl, saveEdits, sectionsCsvUrl, volumesCsvUrl } from '../api';
import { cy, signed } from '../format';
import { currentSides } from '../sides';
import { roadVolumes } from '../volumes';
import ProfileChart from './ProfileChart';
import RoadList from './RoadList';
import RoadSides from './RoadSides';
import SectionViewer from './SectionViewer';
import SegmentsTable from './SegmentsTable';
import ReviewList from './ReviewList';
import AreaEditor from './AreaEditor';
import EditSectionModal from './EditSectionModal';
import { IconBalance, IconDownload, IconLayers, IconTrendDown, IconTrendUp } from './Icons';
import { InfoTip, NoteList, StatCard } from './Ui';

function needsReview(s) {
  return s.label_source === 'inferred' || s.warnings.length > 0 || !s.station || (s.confidence && !s.confidence.passed);
}

const SURFACE_LABEL = { subgrade: 'Subgrade', finished: 'Finished grade' };
const ZERO_SHORT = { structure: 'Bridge / structure', no_design: 'No proposed surface drawn', matches_existing: 'Matches existing ground' };
const same = (a, b) => Math.abs(a.fill_ft2 - b.fill_ft2) < 0.005 && Math.abs(a.cut_ft2 - b.cut_ft2) < 0.005;

export default function Results({ result, onResult }) {
  const { summary } = result;
  const [surface, setSurface] = useState(summary.design_surface);
  // unsaved hand edits: { surface: { sectionId: {fill_ft2, cut_ft2} } }
  const [drafts, setDrafts] = useState({});
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState(null);       // {ok, text}

  // Flatten the chosen surface onto each section: the area in use (a draft,
  // a saved edit, or the measurement) plus what was measured, so every view
  // below reads plain fill/cut fields.
  const sections = useMemo(() => result.sections.map((s) => {
    const measured = (s.measured || s.areas)[surface];
    const area = drafts[surface]?.[s.id] || s.areas[surface];
    const edited = !same(area, measured);
    // a section with no earthwork says why (bridge, nothing proposed, resurfacing) -- unless the user typed areas in
    const zero = s.zero_reason && !edited && area.fill_ft2 + area.cut_ft2 < 0.5
      ? { short: ZERO_SHORT[s.zero_reason] || 'No earthwork', text: result.zero_reasons?.[s.zero_reason] || '' } : null;
    const marks = s.marks?.[surface] || [];
    return {
      ...s, fill_ft2: area.fill_ft2, cut_ft2: area.cut_ft2, net_ft2: area.fill_ft2 - area.cut_ft2,
      measured, marks, edited: edited || marks.length > 0, dirty: Boolean(drafts[surface]?.[s.id]), zero,
      // left / right of the centreline for the areas in use
      sides: currentSides(s.sides_measured?.[surface], measured, area, marks),
    };
  }), [result.sections, result.zero_reasons, surface, drafts]);

  // volumes are recomputed in the browser from the areas above, so edits
  // show in the chart, tables and totals before they are saved
  const roads = useMemo(() => result.roads.map((r) => ({
    ...r, ...roadVolumes(r.sections.map((i) => sections[i]), r.volumes[surface]),
  })), [result.roads, sections, surface]);

  // Repeated sheet series (same stations drawn again) are excluded by default.
  const [included, setIncluded] = useState(() => new Set(result.roads.filter((r) => !r.repeat_of).map((r) => r.id)));
  const [roadId, setRoadId] = useState(roads[0]?.id ?? null);
  const [sectionId, setSectionId] = useState(roads[0]?.sections[0] ?? sections[0]?.id ?? null);
  const [tab, setTab] = useState('segments');
  const [editing, setEditing] = useState(null);       // section id open in the edit dialog

  const road = roads.find((r) => r.id === roadId) || null;
  const roadSections = useMemo(() => (road ? road.sections.map((i) => sections[i]) : sections), [road, sections]);
  const review = useMemo(() => sections.filter(needsReview), [sections]);
  const editedCount = sections.filter((s) => s.edited).length;
  const zeroCount = sections.filter((s) => s.zero).length;
  const lowCount = sections.filter((s) => s.confidence && !s.confidence.passed).length;
  const dirtyCount = Object.values(drafts).reduce((n, d) => n + Object.keys(d).length, 0);

  const totals = useMemo(() => {
    let fill = 0, cut = 0;
    const side = { left: { fill: 0, cut: 0 }, right: { fill: 0, cut: 0 } };
    for (const r of roads) {
      if (!included.has(r.id)) continue;
      fill += r.fill_cy; cut += r.cut_cy;
      for (const sd of ['left', 'right']) {
        side[sd].fill += r.sides?.[sd].fill_cy || 0;
        side[sd].cut += r.sides?.[sd].cut_cy || 0;
      }
    }
    return { fill, cut, net: fill - cut, side };
  }, [roads, included]);

  // ---------------------------------------------------------------- editing
  const setArea = useCallback((id, area) => {
    setSaveMsg(null);
    setDrafts((prev) => {
      const saved = result.sections[id].areas[surface];
      const mine = { ...(prev[surface] || {}) };
      if (same(area, saved)) delete mine[id];          // back to what the server has: nothing to save
      else mine[id] = area;
      return { ...prev, [surface]: mine };
    });
  }, [result.sections, surface]);

  const resetArea = useCallback((id) => {
    setArea(id, { ...(result.sections[id].measured || result.sections[id].areas)[surface] });
  }, [result.sections, surface, setArea]);

  async function save() {
    setSaving(true);
    setSaveMsg(null);
    try {
      let latest = result;
      for (const [sf, d] of Object.entries(drafts)) {
        const ids = Object.keys(d);
        if (!ids.length) continue;
        const edits = {};
        for (const id of ids) {
          const measured = (result.sections[id].measured || result.sections[id].areas)[sf];
          const marks = result.sections[id].marks?.[sf] || [];
          edits[id] = same(d[id], measured) && !marks.length ? null
            : { ...d[id], marks: marks.map(({ kind, pts }) => ({ kind, pts })) };
        }
        latest = await saveEdits(result.job_id, sf, edits);
      }
      setDrafts({});
      onResult(latest);
      setSaveMsg({ ok: true, text: 'Saved. Volumes, the chart, the PDF and the CSV downloads now use your areas.' });
    } catch (e) {
      setSaveMsg({ ok: false, text: `Could not save: ${e.message}` });
    } finally {
      setSaving(false);
    }
  }

  // the edit dialog saves its section straight away (areas + outlined shapes)
  async function saveSection(id, area, marks) {
    const measured = (result.sections[id].measured || result.sections[id].areas)[surface];
    const latest = await saveEdits(result.job_id, surface,
      { [id]: same(area, measured) && !marks.length ? null : { ...area, marks } });
    setDrafts((prev) => {
      const mine = { ...(prev[surface] || {}) };
      delete mine[id];
      return { ...prev, [surface]: mine };
    });
    onResult(latest);
    setSaveMsg({ ok: true, text: `Saved ${result.sections[id].station || 'the section'}. The picture, chart, totals, PDF and CSV now use these areas.` });
  }

  // don't lose unsaved edits to a closed tab
  useEffect(() => {
    if (!dirtyCount) return undefined;
    const warn = (e) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirtyCount]);

  // ------------------------------------------------------------- navigation
  function selectSection(id) {
    const s = sections[id];
    if (s?.road && s.road !== roadId) setRoadId(s.road);
    setSectionId(id);
  }

  function selectRoad(id) {
    setRoadId(id);
    const r = roads.find((x) => x.id === id);
    if (r && !r.sections.includes(sectionId)) setSectionId(r.sections[0]);
  }

  // ← / → step through the selected road's sections
  useEffect(() => {
    function onKey(e) {
      if (editing != null || e.target.closest('input, textarea, select')) return;
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      const ids = roadSections.map((s) => s.id);
      const i = ids.indexOf(sectionId);
      const j = e.key === 'ArrowLeft' ? i - 1 : i + 1;
      if (j >= 0 && j < ids.length) { e.preventDefault(); setSectionId(ids[j]); }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [roadSections, sectionId, editing]);

  const excluded = roads.filter((r) => !included.has(r.id)).map((r) => r.id);
  const section = sectionId != null ? sections[sectionId] : null;
  const pos = section ? roadSections.findIndex((s) => s.id === section.id) : -1;
  const balanceTotal = totals.fill + totals.cut || 1;

  return (
    <div className="results">
      <div className="side-col">
        <RoadList roads={roads} included={included} activeId={roadId} onSelect={selectRoad}
          onToggle={(id) => setIncluded((prev) => {
            const next = new Set(prev);
            next.has(id) ? next.delete(id) : next.add(id);
            return next;
          })} />
        <section className="panel">
          <div className="panel-h"><h3>Export</h3></div>
          <div className="export-list">
            <div className="export-row">
              <a className="btn primary" href={annotatedPdfUrl(result.job_id, excluded, surface)}><IconDownload width={18} height={18} />Plan set PDF</a>
              <InfoTip label="What the PDF contains">Your original PDF, every page unchanged, with cut/fill shading and areas drawn on each
                section and a volume summary at the end.</InfoTip>
            </div>
            <a className="btn" href={volumesCsvUrl(result.job_id, excluded, surface)}>Volumes by road · CSV</a>
            <a className="btn" href={sectionsCsvUrl(result.job_id)}>Areas by section · CSV</a>
            {dirtyCount > 0 && <span className="export-note warn-text">Save your edits first: downloads use saved areas only.</span>}
          </div>
        </section>
      </div>

      <div className="main-col">
        {(dirtyCount > 0 || saveMsg) && (
          <div className={`save-bar ${dirtyCount ? 'dirty' : saveMsg?.ok ? 'ok' : 'bad'}`} role="status">
            {dirtyCount > 0 ? (
              <>
                <span><b>{dirtyCount} unsaved edit{dirtyCount === 1 ? '' : 's'}</b>
                  <span className="muted"> · the chart, tables and totals already show {dirtyCount === 1 ? 'it' : 'them'}</span></span>
                <span className="spacer" />
                <button className="btn" onClick={() => { setDrafts({}); setSaveMsg(null); }} disabled={saving}>Discard</button>
                <button className="btn primary" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</button>
              </>
            ) : (
              <>
                <span>{saveMsg.text}</span>
                <span className="spacer" />
                <button className="btn ghost" onClick={() => setSaveMsg(null)}>Dismiss</button>
              </>
            )}
          </div>
        )}

        <div className="surface-bar">
          <span className="muted surface-lead">Measured to</span>
          <div className="segmented" role="radiogroup" aria-label="Proposed surface used for earthwork">
            {summary.surfaces.map((sf) => (
              <button key={sf} role="radio" aria-checked={surface === sf}
                className={surface === sf ? 'on' : ''} onClick={() => setSurface(sf)}>
                {SURFACE_LABEL[sf] || sf}
              </button>
            ))}
          </div>
          <InfoTip label="About the surface">
            <b>Subgrade:</b> bottom of the pavement structure — standard earthwork practice.<br />
            <b>Finished grade:</b> top of pavement — includes the pavement layer in fill.
          </InfoTip>
          <span className="spacer" />
          <a className="btn" href={annotatedPdfUrl(result.job_id, excluded, surface)}
            title="Your original PDF with cut/fill and areas drawn on every section"><IconDownload width={18} height={18} />PDF</a>
        </div>
        <div className="stat-grid">
          <StatCard icon={IconTrendDown} tone="red" label="Cut" value={cy(totals.cut)} unit="cy">
            <div className="lr-mini num"><span><i>L</i>{cy(totals.side.left.cut)}</span><span><i>R</i>{cy(totals.side.right.cut)}</span></div>
            <div className="balance" role="img" aria-label={`Cut is ${Math.round((totals.cut / balanceTotal) * 100)}% of cut plus fill`}>
              <div className="c" style={{ width: `${(totals.cut / balanceTotal) * 100}%` }} />
              <div className="f" style={{ width: `${(totals.fill / balanceTotal) * 100}%` }} />
            </div>
          </StatCard>
          <StatCard icon={IconTrendUp} tone="green" label="Fill" value={cy(totals.fill)} unit="cy">
            <div className="lr-mini num"><span><i>L</i>{cy(totals.side.left.fill)}</span><span><i>R</i>{cy(totals.side.right.fill)}</span></div>
            <div className="chips"><span className="tag neutral" title="Roads counted in the totals">{included.size}/{roads.length} road{roads.length === 1 ? '' : 's'} counted</span></div>
          </StatCard>
          <StatCard icon={IconBalance} tone={totals.net >= 0 ? 'green' : 'red'} label="Net" value={signed(totals.net)} unit="cy"
            tip={totals.net >= 0 ? 'Import: fill exceeds cut.' : 'Export: cut exceeds fill.'}>
            <div className="chips"><span className={`tag ${totals.net >= 0 ? 'info' : 'warn'}`}>{totals.net >= 0 ? 'import' : 'export'}</span></div>
          </StatCard>
          <StatCard icon={IconLayers} tone="yellow" label="Sections" value={summary.sections} className="v-plain">
            <div className="chips">
              <span className="tag neutral" title={`${summary.cross_section_pages} of ${summary.pages} pages have cross-sections`}>{summary.cross_section_pages}/{summary.pages} pages</span>
              {review.length > 0 && <span className="tag warn" title="Sections flagged for review">{review.length} to review</span>}
              {lowCount > 0 && <span className="tag bad" title={`Below ${85}% confidence`}>{lowCount} &lt;{85}%</span>}
              {zeroCount > 0 && <span className="tag neutral" title="Sections with no earthwork">{zeroCount} no earthwork</span>}
              {editedCount > 0 && <span className="tag edited">{editedCount} edited</span>}
            </div>
          </StatCard>
        </div>

        {result.warnings.length > 0 && <NoteList items={result.warnings} label="plan-set warning" />}

        {road && (
          <section className="panel">
            <div className="panel-h">
              <div className="profile-title">
                <h3 className="ellipsis" title={road.label}>{road.label}</h3>
                <span className="muted mono small-text">{road.station_from} → {road.station_to}</span>
              </div>
              <span className="spacer" />
              <span className="tag cut num">{cy(road.cut_cy)} cy cut</span>
              <span className="tag fill num">{cy(road.fill_cy)} cy fill</span>
            </div>
            <ProfileChart sections={roadSections} selectedId={sectionId} onSelect={setSectionId} />
            <RoadSides road={road} />
          </section>
        )}

        {section && (
          <SectionViewer jobId={result.job_id} section={section} sections={sections} roads={roads} onSelect={selectSection}
            surface={surface} position={pos} count={roadSections.length}
            onOpenEdit={() => setEditing(section.id)} onReset={() => resetArea(section.id)}
            onPrev={pos > 0 ? () => setSectionId(roadSections[pos - 1].id) : null}
            onNext={pos >= 0 && pos < roadSections.length - 1 ? () => setSectionId(roadSections[pos + 1].id) : null} />
        )}

        <section className="panel">
          <div className="panel-h">
            <div className="tabs" role="tablist">
              <button role="tab" aria-selected={tab === 'segments'} className={`tab ${tab === 'segments' ? 'active' : ''}`} onClick={() => setTab('segments')}>Volumes</button>
              <button role="tab" aria-selected={tab === 'edit'} className={`tab ${tab === 'edit' ? 'active' : ''}`} onClick={() => setTab('edit')}>
                Edit areas {editedCount > 0 && <span className="tag edited" style={{ marginLeft: 6 }}>{editedCount}</span>}
              </button>
              <button role="tab" aria-selected={tab === 'review'} className={`tab ${tab === 'review' ? 'active' : ''}`} onClick={() => setTab('review')}>
                Needs review {review.length > 0 && <span className="tag warn" style={{ marginLeft: 6 }}>{review.length}</span>}
              </button>
            </div>
          </div>
          {tab === 'segments' && <SegmentsTable road={road} sections={sections} onSelect={selectSection} />}
          {tab === 'edit' && (
            <AreaEditor sections={roadSections} selectedId={sectionId} onSelect={setSectionId}
              onEdit={setArea} onReset={resetArea} onOpen={(id) => { setSectionId(id); setEditing(id); }} surfaceLabel={SURFACE_LABEL[surface] || surface} />
          )}
          {tab === 'review' && <ReviewList items={review} onSelect={selectSection} />}
        </section>
        {editing != null && sections[editing] && (
          <EditSectionModal key={`${editing}-${surface}`} section={sections[editing]} surface={surface}
            onClose={() => setEditing(null)} onSave={(area, marks) => saveSection(editing, area, marks)} />
        )}
      </div>
    </div>
  );
}
