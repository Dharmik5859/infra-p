import { useEffect, useState } from 'react';
import { IconFile, IconMenu, IconMoon, IconSun, IconUpload } from './Icons';

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
    <button className="icon-round" onClick={() => setTheme(dark ? 'light' : 'dark')}
      title={dark ? 'Switch to light theme' : 'Switch to dark theme'} aria-label="Toggle colour theme">
      {dark ? <IconSun /> : <IconMoon />}
    </button>
  );
}

function ServerPill({ server }) {
  const [cls, text] = server == null ? ['', 'Connecting…']
    : server.unreachable ? ['bad', 'Server offline']
    : server.ok ? ['ok', 'Server ready']
    : ['warn', 'OCR missing'];
  const title = server?.ok === false && !server.unreachable
    ? 'tesseract is not installed on the server, so scanned sheets cannot be read' : undefined;
  return <span className={`pill status ${cls}`} title={title}><i />{text}</span>;
}

export default function NavBar({ title, sub, server, file, onMenu, onNew }) {
  return (
    <header className="navbar">
      <button className="icon-round menu-btn" onClick={onMenu} aria-label="Open navigation"><IconMenu /></button>
      <div className="nav-title">
        <h1>{title}</h1>
        <span>{sub}</span>
      </div>
      {file && <span className="pill file" title={file}><IconFile width={16} height={16} />{file}</span>}
      <span className="spacer" />
      <ServerPill server={server} />
      <ThemeToggle />
      <button className="btn primary nav-new" onClick={onNew}><IconUpload width={18} height={18} />New takeoff</button>
    </header>
  );
}
