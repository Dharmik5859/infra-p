import { useDeferredValue, useEffect, useMemo, useState } from 'react';
import { IconChevron, IconCopy, IconDownload, IconSearch } from './Icons';

/**
 * JSON, pretty-printed with syntax colours. Arrays of plain numbers (shape
 * points) stay on one line so a long response still reads as a list of
 * objects.
 */
function pretty(value, indent = 0) {
  const pad = '  '.repeat(indent);
  if (Array.isArray(value)) {
    if (value.length === 0) return '[]';
    if (value.every((v) => typeof v === 'number')) return `[${value.join(', ')}]`;
    return `[\n${value.map((v) => `${pad}  ${pretty(v, indent + 1)}`).join(',\n')}\n${pad}]`;
  }
  if (value && typeof value === 'object') {
    const keys = Object.keys(value);
    if (keys.length === 0) return '{}';
    return `{\n${keys.map((k) => `${pad}  ${JSON.stringify(k)}: ${pretty(value[k], indent + 1)}`).join(',\n')}\n${pad}}`;
  }
  return JSON.stringify(value);
}

const TOKEN = /("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|(\/\/[^\n]*)/g;

function highlight(text) {
  const out = [];
  let last = 0;
  let k = 0;
  for (const m of text.matchAll(TOKEN)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    if (m[1]) {
      out.push(<span key={k++} className={m[2] ? 'j-key' : 'j-str'}>{m[1]}</span>);
      if (m[2]) out.push(m[2]);
    } else if (m[3]) out.push(<span key={k++} className="j-lit">{m[3]}</span>);
    else if (m[4]) out.push(<span key={k++} className="j-num">{m[4]}</span>);
    else if (m[5]) out.push(<span key={k++} className="j-com">{m[5]}</span>);
    last = m.index + m[0].length;
  }
  out.push(text.slice(last));
  return out;
}

export default function JsonView({ value, note }) {
  const text = useMemo(() => pretty(value) + (note ? `\n// ${note}` : ''), [value, note]);
  const lines = useMemo(() => text.split('\n').length, [text]);
  const body = useMemo(() => highlight(text), [text]);
  return (
    <div className="json-view">
      <div className="json-gutter" aria-hidden="true">
        {Array.from({ length: lines }, (_, i) => <span key={i}>{i + 1}</span>)}
      </div>
      <pre className="json-code" tabIndex={0} aria-label="JSON response">{body}</pre>
    </div>
  );
}

export { pretty };

/* ---------------------------------------------------------------- tree explorer
 * The same JSON as a tree: every object and array folds, long arrays are
 * paged, and a search keeps only the branches whose keys or values match
 * (shape point lists are matched by key only, or every number would hit). */
const PAGE = 50;
const isNumList = (v) => Array.isArray(v) && v.length > 0 && v.every((x) => typeof x === 'number');
const isBranch = (v) => v !== null && typeof v === 'object';
const childPath = (path, key) => `${path}/${String(key).replace(/~/g, '~0').replace(/\//g, '~1')}`;

function scan(value, query) {
  const needle = query.toLowerCase();
  const keep = new Set();
  const hits = new Set();
  const walk = (v, path, key) => {
    let hit = key != null && String(key).toLowerCase().includes(needle);
    let inside = false;
    if (isNumList(v)) { /* by key only */ } else if (Array.isArray(v)) {
      v.forEach((c, i) => { if (walk(c, childPath(path, i), null)) inside = true; });
    } else if (isBranch(v)) {
      Object.keys(v).forEach((k) => { if (walk(v[k], childPath(path, k), k)) inside = true; });
    } else if (!hit) hit = String(v).toLowerCase().includes(needle);
    if (hit) hits.add(path);
    if (hit || inside) keep.add(path);
    return hit || inside;
  };
  walk(value, '', null);
  return { keep, hits };
}

function Marked({ text, query }) {
  if (!query) return text;
  const lower = text.toLowerCase();
  const q = query.toLowerCase();
  const out = [];
  let at = 0;
  for (let i = lower.indexOf(q); i !== -1; i = lower.indexOf(q, at)) {
    if (i > at) out.push(text.slice(at, i));
    out.push(<mark key={i}>{text.slice(i, i + q.length)}</mark>);
    at = i + q.length;
  }
  out.push(text.slice(at));
  return out;
}

function Leaf({ value, query }) {
  const cls = typeof value === 'string' ? 'j-str' : typeof value === 'number' ? 'j-num' : 'j-lit';
  return <span className={cls}><Marked text={JSON.stringify(value)} query={query} /></span>;
}

function Node({ name, value, path, depth, ctx, filtered, comma }) {
  const { query, overrides, setOverride, limits, setLimit } = ctx;
  const key = name == null ? null : typeof name === 'number'
    ? <span className="jt-index">{name}: </span>
    : <><span className="j-key"><Marked text={JSON.stringify(name)} query={query} /></span>: </>;
  const tail = comma ? ',' : '';

  if (!isBranch(value)) {
    return <div className="jt-row" style={{ '--d': depth }}><span className="jt-pad" />{key}<Leaf value={value} query={query} />{tail}</div>;
  }

  const isArr = Array.isArray(value);
  const keys = isArr ? value.map((_, i) => i) : Object.keys(value);
  const [l, r] = isArr ? ['[', ']'] : ['{', '}'];
  if (keys.length === 0) {
    return <div className="jt-row" style={{ '--d': depth }}><span className="jt-pad" />{key}{l}{r}{tail}</div>;
  }
  const nums = isNumList(value);
  const forced = filtered && query && ctx.keep.has(path) && !ctx.hits.has(path);
  const auto = forced || (depth < ctx.depth && !(nums && value.length > 16) && !(isArr && value.length > 200 && depth > 0));
  const open = overrides.has(path) ? overrides.get(path) : auto;
  const toggle = () => setOverride(path, !open);
  const label = name == null ? 'the response' : String(name);
  const summary = nums ? `${value.length} numbers` : isArr ? `${value.length} item${value.length === 1 ? '' : 's'}`
    : `${keys.length} key${keys.length === 1 ? '' : 's'}`;

  const head = (
    <div className="jt-row" style={{ '--d': depth }}>
      <button type="button" className="jt-toggle" aria-expanded={open} onClick={toggle}
        aria-label={`${open ? 'Collapse' : 'Expand'} ${label}`}><IconChevron width={14} height={14} /></button>
      {key}
      {open ? l : (
        <button type="button" className="jt-summary" onClick={toggle} tabIndex={-1}>
          {l}<span>{summary}</span>{r}
        </button>
      )}
      {!open && tail}
      {open && nums && <span className="jt-nums j-num">{value.join(', ')}</span>}
      {open && nums && <>{r}{tail}</>}
    </div>
  );
  if (!open || nums) return head;

  const childFiltered = filtered && query && !ctx.hits.has(path);
  let shown = keys.filter((k) => !childFiltered || ctx.keep.has(childPath(path, k)));
  const total = shown.length;
  const limit = limits.get(path) || PAGE;
  shown = shown.slice(0, limit);
  return (
    <>
      {head}
      {shown.map((k, i) => (
        <Node key={k} name={k} value={value[k]} path={childPath(path, k)} depth={depth + 1} ctx={ctx}
          filtered={childFiltered} comma={i < shown.length - 1 || total > limit} />
      ))}
      {total > limit && (
        <div className="jt-row" style={{ '--d': depth + 1 }}>
          <span className="jt-pad" />
          <button type="button" className="jt-more" onClick={() => setLimit(path, limit + PAGE * 4)}>
            Show {Math.min(PAGE * 4, total - limit)} more of {total - limit} hidden
          </button>
        </div>
      )}
      {childFiltered && total < keys.length && (
        <div className="jt-row jt-hidden" style={{ '--d': depth + 1 }}><span className="jt-pad" />
          {keys.length - total} not matching</div>
      )}
      <div className="jt-row" style={{ '--d': depth }}><span className="jt-pad" />{r}{tail}</div>
    </>
  );
}

/**
 * A JSON response to explore: fold / unfold, search, copy and download.
 * `fileName` names the download; `label` names the region for assistive tech.
 */
export function JsonTree({ value, fileName = 'response.json', label = 'JSON response' }) {
  const [search, setSearch] = useState('');
  const query = useDeferredValue(search.trim());
  const [depth, setDepth] = useState(2);
  const [overrides, setOverrides] = useState(() => new Map());
  const [limits, setLimits] = useState(() => new Map());
  const [copied, setCopied] = useState(false);

  useEffect(() => { setOverrides(new Map()); setLimits(new Map()); }, [value, query]);

  const text = useMemo(() => JSON.stringify(value, null, 2), [value]);
  const found = useMemo(() => (query ? scan(value, query) : null), [value, query]);
  const ctx = {
    query, depth, overrides, limits, keep: found?.keep, hits: found?.hits,
    setOverride: (p, v) => setOverrides((m) => new Map(m).set(p, v)),
    setLimit: (p, v) => setLimits((m) => new Map(m).set(p, v)),
  };

  function copy() {
    const done = () => { setCopied(true); setTimeout(() => setCopied(false), 1500); };
    if (navigator.clipboard?.writeText) navigator.clipboard.writeText(text).then(done, () => {});
  }
  function download() {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], { type: 'application/json' }));
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 0);
  }
  const all = (d) => { setDepth(d); setOverrides(new Map()); };
  const kb = text.length / 1024;

  return (
    <div className="jt">
      <div className="jt-bar">
        <label className="jt-search">
          <IconSearch width={16} height={16} />
          <span className="sr-only">Filter keys and values</span>
          <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Filter keys and values" />
        </label>
        <span className="jt-count muted" aria-live="polite">
          {found ? `${found.hits.size} match${found.hits.size === 1 ? '' : 'es'}` : `${kb < 1024 ? `${kb.toFixed(1)} KB` : `${(kb / 1024).toFixed(1)} MB`}`}
        </span>
        <span className="spacer" />
        <button type="button" className="btn small" onClick={() => all(8)}>Expand</button>
        <button type="button" className="btn small" onClick={() => all(1)}>Collapse</button>
        <button type="button" className="btn small" onClick={copy}><IconCopy width={16} height={16} />{copied ? 'Copied' : 'Copy'}</button>
        <button type="button" className="btn small" onClick={download}><IconDownload width={16} height={16} />.json</button>
      </div>
      <div className="jt-body" role="region" aria-label={label} tabIndex={0}>
        {found && found.hits.size === 0
          ? <div className="jt-row jt-hidden"><span className="jt-pad" />Nothing matches &ldquo;{query}&rdquo;.</div>
          : <Node name={null} value={value} path="" depth={0} ctx={ctx} filtered={Boolean(found)} />}
      </div>
    </div>
  );
}
