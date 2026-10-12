import { IconAccuracy, IconDashboard, IconResults, IconRuler, IconUpload, Logo } from './Icons';

const ITEMS = [
  { id: 'dashboard', label: 'Dashboard', Icon: IconDashboard },
  { id: 'new', label: 'New takeoff', Icon: IconUpload },
  { id: 'results', label: 'Results', Icon: IconResults },
  { id: 'calibration', label: 'Calibration', Icon: IconRuler },
  { id: 'accuracy', label: 'Accuracy', Icon: IconAccuracy },
];

export default function Sidebar({ view, job, onNavigate }) {
  const running = job && (job.status === 'queued' || job.status === 'running');
  const { done = 0, total = 0 } = job?.progress || {};
  return (
    <aside className="sidebar" aria-label="Main navigation">
      <div className="side-brand">
        <Logo />
        <div>
          <b>Earthwork</b>
          <span>Cut &amp; fill takeoff</span>
        </div>
      </div>
      <nav className="side-nav">
        {ITEMS.map(({ id, label, Icon }) => (
          <a key={id} href={id === 'results' && job ? `#/results/${job.job_id}` : `#/${id}`}
            className={`side-link ${view === id ? 'active' : ''}`} aria-current={view === id ? 'page' : undefined}
            onClick={(e) => { e.preventDefault(); onNavigate(id, id === 'results' ? job?.job_id : undefined); }}>
            <Icon />
            <span>{label}</span>
            {id === 'results' && running && <span className="side-badge">{total ? `${Math.round((done / total) * 100)}%` : '…'}</span>}
          </a>
        ))}
      </nav>
      {job && (
        <div className="side-job" title={job.filename}>
          <span className="side-job-label">{running ? 'Processing' : 'Open takeoff'}</span>
          <span className="side-job-name">{job.filename}</span>
          {running && (
            <div className="mini-bar"><div style={{ width: `${total ? (done / total) * 100 : 8}%` }} /></div>
          )}
        </div>
      )}
      <div className="side-foot">
        <span className="dot-row"><i className="g-blue" /><i className="g-red" /><i className="g-yellow" /><i className="g-green" /></span>
        Average-end-area method
      </div>
    </aside>
  );
}
