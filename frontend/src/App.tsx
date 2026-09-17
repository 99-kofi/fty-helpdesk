import { useEffect, useState } from 'react';
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import Inbox from './pages/Inbox';
import Tickets from './pages/Tickets';
import Customers from './pages/Customers';
import Analytics from './pages/Analytics';
import Login from './pages/Login';
import Settings from './pages/Settings';
import Knowledge from './pages/Knowledge';
import Automation from './pages/Automation';
import { api, Agent, isLoggedIn, logout } from './api/client';

type Link = { to: string; label: string; icon: string; end?: boolean; admin?: boolean };

const LINKS: Link[] = [
  { to: '/', label: 'Inbox', icon: '📨', end: true },
  { to: '/tickets', label: 'Tickets', icon: '🎫' },
  { to: '/customers', label: 'Customers', icon: '👥' },
  { to: '/knowledge', label: 'Knowledge', icon: '📚', admin: true },
  { to: '/automation', label: 'Automation', icon: '🤖', admin: true },
  { to: '/analytics', label: 'Analytics', icon: '📊', admin: true },
  { to: '/settings', label: 'Settings', icon: '⚙', admin: true },
];

function Guard({ children }: { children: JSX.Element }) {
  const loc = useLocation();
  if (!isLoggedIn() && loc.pathname !== '/login') return <Navigate to="/login" replace />;
  return children;
}

/** Admin-only pages: dashboards, knowledge, automation, settings. */
function AdminGuard({ children }: { children: JSX.Element }) {
  const [role, setRole] = useState<string | null>(null);
  useEffect(() => {
    api<Agent>('/auth/me').then(me => setRole(me.role)).catch(() => setRole('?'));
  }, []);
  if (role === null) return <div className="muted">Loading…</div>;
  return role === 'admin' ? children : <Navigate to="/" replace />;
}

export default function App() {
  const nav = useNavigate();
  const logged = isLoggedIn();
  const [me, setMe] = useState<Agent | null>(null);

  useEffect(() => {
    if (logged) api<Agent>('/auth/me').then(setMe).catch(() => {});
    else setMe(null);
  }, [logged]);

  // No sidebar before login: the Login page owns the full viewport.
  if (!logged) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  // Admin sees every feature; everyone else sees only their assigned work.
  const isAdmin = me?.role === 'admin';
  const links = LINKS.filter(l => !l.admin || isAdmin);

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="row" style={{ padding: '0 8px 4px' }}>
          <img src="/fty-logo.png" alt="FTY" style={{ width: 34, height: 34, objectFit: 'contain', background: '#fff', borderRadius: 9, padding: 2 }} />
          <h2 style={{ margin: 0 }}>FTY HelpDesk</h2>
        </div>
        <p className="sub">Customer Experience</p>
        {links.map(l => (
          <NavLink key={l.to} to={l.to} end={l.end} className={({ isActive }) => `navlink ${isActive ? 'active' : ''}`}>
            <span>{l.icon}</span> <span>{l.label}</span>
          </NavLink>
        ))}
        <div className="foot">
          {me && (
            <div className="small" style={{ marginBottom: 8, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <b style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{me.name}</b>
              <span className="badge b-normal">{me.role}</span>
            </div>
          )}
          <button className="btn" style={{ width: '100%' }} onClick={() => { logout(); nav('/login'); }}>Log out</button>
        </div>
      </aside>
      <div className="main">
        <div className="content">
          <Routes>
            <Route path="/login" element={<Navigate to="/" replace />} />
            <Route path="/" element={<Guard><Inbox /></Guard>} />
            <Route path="/tickets" element={<Guard><Tickets /></Guard>} />
            <Route path="/customers" element={<Guard><Customers /></Guard>} />
            <Route path="/knowledge" element={<Guard><AdminGuard><Knowledge /></AdminGuard></Guard>} />
            <Route path="/automation" element={<Guard><AdminGuard><Automation /></AdminGuard></Guard>} />
            <Route path="/analytics" element={<Guard><AdminGuard><Analytics /></AdminGuard></Guard>} />
            <Route path="/settings" element={<Guard><AdminGuard><Settings /></AdminGuard></Guard>} />
          </Routes>
        </div>
      </div>
    </div>
  );
}
