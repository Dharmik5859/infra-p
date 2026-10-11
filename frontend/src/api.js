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

/**
 * Upload a plan set. Uses XMLHttpRequest rather than fetch so big scans can
 * report upload progress: onProgress(sentBytes, totalBytes).
 */
export function createJob(file, onProgress) {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append('file', file);
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${BASE}/api/jobs`);
    xhr.responseType = 'text';
    if (onProgress) xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded, e.total); };
    xhr.onerror = () => reject(new Error('The upload was interrupted. Check the connection and try again.'));
    xhr.onload = () => {
      let body = null;
      try { body = JSON.parse(xhr.responseText); } catch { /* an HTML error page from a proxy */ }
      if (xhr.status >= 200 && xhr.status < 300 && body) return resolve(body);
      if (body && body.detail) return reject(new Error(body.detail));
      if (xhr.status === 413) {
        // the backend's own 413 carries a JSON detail; this one came from a
        // web server or hosting platform in front of it
        return reject(new Error('The file was rejected as too large by the web server in front of the app '
          + '(HTTP 413), before it reached the backend. Raise its upload limit, e.g. client_max_body_size in nginx.'));
      }
      reject(new Error(`Upload failed (HTTP ${xhr.status}).`));
    };
    xhr.send(form);
  });
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
