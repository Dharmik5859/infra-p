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

function needsReview(s) {
  return s.label_source === 'inferred' || s.warnings.length > 0 || !s.station;
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
            <a className="btn primary" href={annotatedPdfUrl(result.job_id, excluded, surface)}>Plan set PDF with takeoff</a>
            <span className="export-note">Your original PDF, every page unchanged, with cut/fill shading and areas drawn on each
              section and a volume summary at the end.</span>
            <a className="btn" href={volumesCsvUrl(result.job_id, excluded, surface)}>Volumes by road (CSV)</a>
            <a className="btn" href={sectionsCsvUrl(result.job_id)}>Areas by section (CSV)</a>
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
          <span className="muted">Earthwork measured to</span>
          <div className="segmented" role="radiogroup" aria-label="Proposed surface used for earthwork">
            {summary.surfaces.map((sf) => (
              <button key={sf} role="radio" aria-checked={surface === sf}
                className={surface === sf ? 'on' : ''} onClick={() => setSurface(sf)}>
                {SURFACE_LABEL[sf] || sf}
              </button>
            ))}
          </div>
          <span className="muted hint">
            {surface === 'subgrade'
              ? 'bottom of the pavement structure — standard earthwork practice'
              : 'top of pavement — includes the pavement layer in fill'}
          </span>
          <span className="spacer" />
          <a className="btn" href={annotatedPdfUrl(result.job_id, excluded, surface)}
            title="Your original PDF with cut/fill and areas drawn on every section">Download PDF</a>
        </div>
        <div className="kpis">
          <div className="kpi">
            <div className="label">Cut</div>
            <div className="value num cut-text">{cy(totals.cut)}<small>cy</small></div>
            <div className="sub lr">left {cy(totals.side.left.cut)} · right {cy(totals.side.right.cut)} cy</div>
            <div className="balance" aria-hidden="true">
              <div className="c" style={{ width: `${(totals.cut / balanceTotal) * 100}%` }} />
              <div className="f" style={{ width: `${(totals.fill / balanceTotal) * 100}%` }} />
            </div>
          </div>
          <div className="kpi">
            <div className="label">Fill</div>
            <div className="value num fill-text">{cy(totals.fill)}<small>cy</small></div>
            <div className="sub lr">left {cy(totals.side.left.fill)} · right {cy(totals.side.right.fill)} cy</div>
            <div className="sub">{included.size} of {roads.length} road{roads.length === 1 ? '' : 's'} counted</div>
          </div>
          <div className="kpi">
            <div className="label">Net</div>
            <div className={`value num ${totals.net >= 0 ? 'fill-text' : 'cut-text'}`}>{signed(totals.net)}<small>cy</small></div>
            <div className="sub">{totals.net >= 0 ? 'import (fill exceeds cut)' : 'export (cut exceeds fill)'}</div>
          </div>
          <div className="kpi">
            <div className="label">Cross-sections</div>
            <div className="value num">{summary.sections}</div>
            <div className="sub">
              {summary.cross_section_pages} of {summary.pages} pages · {review.length} to review
              {zeroCount > 0 && <> · {zeroCount} with no earthwork</>}
              {editedCount > 0 && <> · <span className="edited-text">{editedCount} edited</span></>}
            </div>
          </div>
        </div>

        {result.warnings.length > 0 && (
          <div className="warnings">{result.warnings.map((w, i) => <div className="warning" key={i}>{w}</div>)}</div>
        )}

        {road && (
          <section className="panel">
            <div className="panel-h">
              <h3>{road.label} profile</h3>
              <span className="muted">{road.station_from} → {road.station_to}</span>
              <span className="spacer" />
              <span className="num cut-text">{cy(road.cut_cy)} cy cut</span>
              <span className="num fill-text">{cy(road.fill_cy)} cy fill</span>
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
