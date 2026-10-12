import { useMemo } from 'react';

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
