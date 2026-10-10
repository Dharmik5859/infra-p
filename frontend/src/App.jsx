import { useCallback, useEffect, useRef, useState } from 'react';
import { createJob, getJob, health } from './api';
import TopBar from './components/TopBar';
import UploadView from './components/UploadView';
import ProgressView from './components/ProgressView';
import Results from './components/Results';

// The job id lives in the URL hash so a reload (or a shared link, while the
// server still holds the job) reopens the same results.
function jobFromHash() {
  const m = window.location.hash.match(/job=([\w-]+)/);
  return m ? m[1] : null;
}

export default function App() {
  const [server, setServer] = useState(null);       // null = checking
  const [job, setJob] = useState(null);             // latest job status from the API
  const [error, setError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const timer = useRef(null);

  useEffect(() => {
    health().then(setServer).catch(() => setServer({ ok: false, unreachable: true }));
  }, []);

  const poll = useCallback((id) => {
    clearTimeout(timer.current);
    getJob(id)
      .then((j) => {
        setJob(j);
        if (j.status === 'queued' || j.status === 'running') {
          timer.current = setTimeout(() => poll(id), 800);
        } else if (j.status === 'error') {
          setError(j.error || 'Processing failed.');
        }
      })
      .catch((e) => {
        setError(e.message);
        setJob(null);
        window.location.hash = '';
      });
  }, []);

  useEffect(() => {
    const id = jobFromHash();
    if (id) poll(id);
    return () => clearTimeout(timer.current);
  }, [poll]);

  async function upload(file) {
    setError(null);
    setUploading(true);
    try {
      const { job_id } = await createJob(file);
      window.location.hash = `job=${job_id}`;
      setJob({ job_id, filename: file.name, status: 'queued', progress: { done: 0, total: 0 } });
      poll(job_id);
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
    }
  }

  function reset() {
    clearTimeout(timer.current);
    window.location.hash = '';
    setJob(null);
    setError(null);
  }

  const done = job && job.status === 'done' && job.result;
  const running = job && (job.status === 'queued' || job.status === 'running');

  return (
    <>
      <TopBar job={done ? job : null} onNew={job ? reset : null} />
      {done ? (
        <Results result={job.result} />
      ) : running ? (
        <ProgressView job={job} />
      ) : (
        <UploadView server={server} onFile={upload} busy={uploading} error={error} />
      )}
    </>
  );
}
