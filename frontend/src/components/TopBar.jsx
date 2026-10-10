import { useEffect, useState } from 'react';

function Logo() {
  return (
    <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="currentColor" opacity="0.92" />
      <path d="M4 21 L11 14 L16 17 L22 10 L28 14" fill="none" stroke="var(--surface)" strokeWidth="2.2"
        strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 23.5 L28 23.5" stroke="var(--fill)" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}

function ThemeToggle() {
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem('theme'); } catch { return null; }
  });
  useEffect(() => {
    if (theme) document.documentElement.dataset.theme = theme;
    else delete document.documentElement.dataset.theme;
    try { theme ? localStorage.setItem('theme', theme) : localStorage.removeItem('theme'); } catch { /* private mode */ }
  }, [theme]);
  const dark = theme ? theme === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
  return (
    <button className="btn ghost icon-btn" onClick={() => setTheme(dark ? 'light' : 'dark')}
      title={dark ? 'Switch to light theme' : 'Switch to dark theme'} aria-label="Toggle colour theme">
      {dark ? (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
      ) : (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></svg>
      )}
    </button>
  );
}

export default function TopBar({ job, onNew }) {
  return (
    <header className="topbar">
      <div className="brand"><Logo /> Earthwork Takeoff</div>
      {job && <span className="file" title={job.filename}>{job.filename}</span>}
      <span className="spacer" />
      {onNew && <button className="btn" onClick={onNew}>New plan set</button>}
      <ThemeToggle />
    </header>
  );
}
