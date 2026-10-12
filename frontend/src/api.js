// All endpoints are relative: Vite proxies /api in development and the
// backend serves this app itself in production.
const BASE = import.meta.env.VITE_API_BASE || '';

async function json(res) {
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new Error((body && body.detail) || `Request failed (${res.status})`);
  return body;
}

export async function health() {
  return json(await fetch(`${BASE}/api/health`));
}

export async function getAccuracy() {
  return json(await fetch(`${BASE}/api/accuracy`));
}

// One XMLHttpRequest (fetch cannot report upload progress). Resolves with
// {status, body}; rejects only when the connection fails.
function send(method, url, payload, headers, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url);
    Object.entries(headers || {}).forEach(([k, v]) => xhr.setRequestHeader(k, v));
    if (onProgress) xhr.upload.onprogress = (e) => onProgress(e.loaded);
    xhr.onerror = () => reject(new Error('network'));
    xhr.onload = () => {
      let body = null;
      try { body = JSON.parse(xhr.responseText); } catch { /* an HTML error page from a proxy */ }
      resolve({ status: xhr.status, body });
    };
    xhr.send(payload);
  });
}

function failure(res, what) {
  if (res.body && res.body.detail) return new Error(res.body.detail);
  if (res.status === 413) {
    return new Error('A web server or proxy in front of the app rejected the upload as too large (HTTP 413).');
  }
  return new Error(`${what} failed (HTTP ${res.status}).`);
}

const MIN_CHUNK = 256 * 1024;

/**
 * Upload a plan set in chunks, so request-size limits of anything in front of
 * the app (nginx, dev tunnels such as Codespaces, hosting platforms) never
 * see the whole file at once. A chunk refused as too large is retried at half
 * the size; a dropped connection is retried a few times.
 * onProgress(sentBytes, totalBytes).
 */
export async function createJob(file, onProgress) {
  const json = { 'Content-Type': 'application/json' };
  const start = await send('POST', `${BASE}/api/uploads`, JSON.stringify({ filename: file.name, size: file.size }), json);
  if (start.status !== 200) throw failure(start, 'Upload');
  const { upload_id: id } = start.body;
  let chunk = start.body.chunk_size;
  let offset = 0;
  let index = 0;
  let retries = 0;
  while (offset < file.size) {
    const piece = file.slice(offset, offset + chunk);
    let res;
    try {
      res = await send('PUT', `${BASE}/api/uploads/${id}/${index}`, piece, { 'Content-Type': 'application/octet-stream' },
        (sent) => onProgress && onProgress(offset + sent, file.size));
    } catch {
      if (++retries > 4) throw new Error('The upload was interrupted. Check the connection and try again.');
      await new Promise((r) => setTimeout(r, 1000 * 2 ** retries));
      continue;
    }
    if (res.status === 413 && chunk > MIN_CHUNK && !(res.body && res.body.detail && !/chunk/i.test(res.body.detail))) {
      chunk = Math.max(MIN_CHUNK, Math.floor(chunk / 2));     // a proxy with a small body limit: send smaller pieces
      continue;
    }
    if (res.status !== 200) throw failure(res, 'Upload');
    offset += piece.size;
    index += 1;
    retries = 0;
    if (onProgress) onProgress(offset, file.size);
  }
  const done = await send('POST', `${BASE}/api/uploads/${id}/complete`, null);
  if (done.status !== 200) throw failure(done, 'Upload');
  return done.body;
}

export async function getJob(id) {
  return json(await fetch(`${BASE}/api/jobs/${id}`));
}

/** Save hand-edited areas for one surface. `edits` maps section id ->
 * {fill_ft2, cut_ft2}, or null to go back to the measured areas.
 * Returns the updated result (volumes recomputed by the server). */
export async function saveEdits(jobId, surface, edits) {
  return json(await fetch(`${BASE}/api/jobs/${jobId}/edits`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ surface, edits }),
  }));
}

const profiles = new Map();

/** A section's traced lines in its image's pixels (cached: they never change). */
export function getProfile(path) {
  if (!profiles.has(path)) {
    const p = fetch(assetUrl(path)).then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    });
    p.catch(() => profiles.delete(path));
    profiles.set(path, p);
  }
  return profiles.get(path);
}

/** Feet-to-pixel calibration per sheet, and the cut / fill shapes, for a finished job. */
export async function getCalibration(jobId) {
  return json(await fetch(`${BASE}/api/jobs/${jobId}/calibration`));
}

/** A sheet's measured sections, in the sheet image's coordinates (cached). */
export const getSheet = (jobId, page) => getProfile(`/api/jobs/${jobId}/pages/${page}.json`);

export function assetUrl(path) {
  return `${BASE}${path}`;
}

export function volumesCsvUrl(jobId, excludedRoadIds, surface) {
  const q = excludedRoadIds.map((id) => `exclude=${encodeURIComponent(id)}`);
  if (surface) q.push(`surface=${encodeURIComponent(surface)}`);
  return `${BASE}/api/jobs/${jobId}/volumes.csv${q.length ? `?${q.join('&')}` : ''}`;
}

export function annotatedPdfUrl(jobId, excludedRoadIds, surface) {
  const q = excludedRoadIds.map((id) => `exclude=${encodeURIComponent(id)}`);
  if (surface) q.push(`surface=${encodeURIComponent(surface)}`);
  return `${BASE}/api/jobs/${jobId}/annotated.pdf${q.length ? `?${q.join('&')}` : ''}`;
}

export function sectionsCsvUrl(jobId) {
  return `${BASE}/api/jobs/${jobId}/sections.csv`;
}
