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

export async function createJob(file) {
  const form = new FormData();
  form.append('file', file);
  return json(await fetch(`${BASE}/api/jobs`, { method: 'POST', body: form }));
}

export async function getJob(id) {
  return json(await fetch(`${BASE}/api/jobs/${id}`));
}

export function assetUrl(path) {
  return `${BASE}${path}`;
}

export function volumesCsvUrl(jobId, excludedRoadIds, surface) {
  const q = excludedRoadIds.map((id) => `exclude=${encodeURIComponent(id)}`);
  if (surface) q.push(`surface=${encodeURIComponent(surface)}`);
  return `${BASE}/api/jobs/${jobId}/volumes.csv${q.length ? `?${q.join('&')}` : ''}`;
}

export function sectionsCsvUrl(jobId) {
  return `${BASE}/api/jobs/${jobId}/sections.csv`;
}
