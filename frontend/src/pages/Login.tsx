import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import LogoStage from '../components/LogoStage';

export default function Login() {
  const [email, setEmail] = useState('admin@fty.local');
  const [password, setPassword] = useState('admin123');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nav = useNavigate();

  const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') || '';
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await fetch(`${API_BASE}/api/v1/auth/seed-admin`, { method: 'POST' });
      const form = new URLSearchParams({ username: email, password });
      const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: form,
      });
      if (!res.ok) throw new Error('Invalid email or password');
      const data = await res.json();
      localStorage.setItem('fty_token', data.access_token);
      nav('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-scene">
      <LogoStage>
        <form className="login-glass" onSubmit={submit}>
          <div className="login-brand">
            <div>
              <b>FTY HelpDesk</b>
              <div className="g-sub" style={{ margin: 0 }}>Customer Experience Platform</div>
            </div>
          </div>
          <h2>Welcome back</h2>
          <p className="g-sub">Support that moves at the speed of youth.</p>
          {error && <div className="g-error">⚠ {error}</div>}
          <label className="g-label" htmlFor="login-email">Email</label>
          <input
            id="login-email" className="g-input" value={email}
            onChange={e => setEmail(e.target.value)} autoComplete="username"
          />
          <div style={{ height: 12 }} />
          <label className="g-label" htmlFor="login-password">Password</label>
          <input
            id="login-password" className="g-input" type="password" value={password}
            onChange={e => setPassword(e.target.value)} autoComplete="current-password"
          />
          <button className="g-btn" disabled={busy}>
            {busy ? 'Authenticating…' : 'Log in →'}
          </button>
          <p className="g-hint">First run? The default admin (<b>admin@fty.local / admin123</b>) is auto-created on login. Workers sign in here too with the email + password your admin created in Settings → Teams & Workers — they only ever see customers assigned to them.</p>
        </form>
        <p className="fty-foot">FREE THE YOUTH · SUPPORT WORKSPACE</p>
      </LogoStage>
    </div>
  );
}
