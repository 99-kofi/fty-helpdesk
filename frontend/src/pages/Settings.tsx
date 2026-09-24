import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import type { Agent, Team } from '../api/client';
import { ChannelIcon, ErrorBanner, SkeletonList, useToast } from '../components/ui';

type ChannelStatus = { channel: string; connected: boolean; has_token: boolean; oauth_ready?: boolean };
const OAUTH_CHANNELS = ['instagram', 'facebook'];

const OAUTH_ERRORS: Record<string, string> = {
  app_secret_missing: 'META_APP_SECRET is missing on the backend — add it to backend/.env and restart.',
  token_exchange_failed: 'Meta rejected the login code — check the App Secret, redirect URI whitelist, and restart the backend after .env changes.',
  long_lived_failed: 'Meta refused the long-lived token — the app may be in Development mode; add yourself as a test user or go Live.',
  page_lookup_failed: 'Could not read your Pages — re-connect and grant all requested permissions.',
  no_linked_instagram: 'No Page with a linked Instagram business account — make the IG account Business/Creator, link it in Page Settings → Linked accounts, then reconnect and grant all permissions.',
  no_pages_returned: 'Meta returned zero Pages — log in with an account listed under App Roles, grant every permission, and keep testing in Dev mode.',
  no_pages: 'Meta returned no usable Pages — log in with an account that manages a Facebook Page.',
  exchange_failed: 'Unexpected error during connect — see the backend console log.',
};

const HELP: Record<string, string> = {
  instagram: 'Click Connect — you will log in with Meta, authorize FTY, and we store the page token encrypted.',
  whatsapp: 'WhatsApp Cloud API. Token: permanent system-user token. Config JSON: {"phone_number_id": "..."}.',
  facebook: 'Click Connect — Meta Login with Messenger permissions, token stored encrypted.',
  email: 'Inbound: point SendGrid/Mailgun inbound-parse at the email webhook. Outbound: SMTP_* in backend .env.',
  web: 'Website widget. Embed widget.js on your site — no token needed.',
};

export default function Settings() {
  const [rows, setRows] = useState<ChannelStatus[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [me, setMe] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [forms, setForms] = useState<Record<string, { token: string; config: string }>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [oauthBusy, setOauthBusy] = useState<string | null>(null);
  const [newTeam, setNewTeam] = useState('');
  const [memberPick, setMemberPick] = useState<Record<number, string>>({});
  const [newUser, setNewUser] = useState({ name: '', email: '', password: '', role: 'agent' });
  const [resetPw, setResetPw] = useState<Record<number, string>>({});
  const [tab, setTab] = useState<'channels' | 'teams' | 'capacity' | 'maintenance'>('channels');
  const [resetting, setResetting] = useState(false);
  const [params, setParams] = useSearchParams();
  const { toast, node } = useToast();

  async function load() {
    try {
      setErr(null);
      const [ch, tm, ag, myself] = await Promise.all([
        api<ChannelStatus[]>('/channels'),
        api<Team[]>('/teams').catch(() => [] as Team[]),
        api<Agent[]>('/agents').catch(() => [] as Agent[]),
        api<Agent>('/auth/me').catch(() => null as unknown as Agent),
      ]);
      setRows(ch);
      setTeams(tm);
      setAgents(ag);
      setMe(myself);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to load settings');
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); }, []);

  // OAuth landing: backend redirects here with ?connected= or ?oauth_error=
  useEffect(() => {
    const ok = params.get('connected');
    const bad = params.get('oauth_error');
    if (ok) toast(`✅ ${ok} connected via Meta Login`);
    if (bad) toast(`OAuth failed: ${OAUTH_ERRORS[bad] ?? bad}`);
    if (ok || bad) {
      params.delete('connected');
      params.delete('oauth_error');
      setParams(params, { replace: true });
      load();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function connectOAuth(channel: string) {
    setOauthBusy(channel);
    try {
      const { url } = await api<{ url: string }>(`/channels/${channel}/oauth/start`);
      window.location.href = url; // → Meta Login
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Could not start Meta Login (META_APP_ID?)');
      setOauthBusy(null);
    }
  }

  async function save(channel: string) {
    const f = forms[channel] ?? { token: '', config: '' };
    setSaving(channel);
    try {
      await api(`/channels/${channel}`, {
        method: 'PUT',
        body: JSON.stringify({ access_token: f.token || null, config: f.config || null }),
      });
      toast(`${channel} connected`);
      setForms(prev => ({ ...prev, [channel]: { token: '', config: '' } }));
      load();
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Save failed (admin/manager only)');
    } finally {
      setSaving(null);
    }
  }

  const origin = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') || (typeof location !== 'undefined' ? location.origin : '');
  const embed = `<script src="${origin}/api/v1/web/widget.js" data-base="${origin}"></script>`;

  async function createTeam() {
    if (!newTeam.trim()) return;
    try {
      await api('/teams', { method: 'POST', body: JSON.stringify({ name: newTeam.trim() }) });
      setNewTeam('');
      toast(`Team ${newTeam.trim()} created`);
      load();
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Create failed (admin/manager only)');
    }
  }

  async function addMember(teamId: number) {
    const uid = memberPick[teamId];
    if (!uid) return;
    await api(`/teams/${teamId}/members`, { method: 'POST', body: JSON.stringify({ user_id: Number(uid) }) });
    toast('Worker added to team');
    load();
  }

  async function removeMember(teamId: number, userId: number) {
    await api(`/teams/${teamId}/members/${userId}`, { method: 'DELETE' });
    load();
  }

  async function patchAgent(id: number, patch: object) {
    try {
      await api(`/agents/${id}`, { method: 'PATCH', body: JSON.stringify(patch) });
      load();
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Update failed');
    }
  }

  const isAdmin = me?.role === 'admin';
  const isManager = me?.role === 'admin' || me?.role === 'manager';

  async function createUser() {
    if (!newUser.name.trim() || !newUser.email.trim() || newUser.password.length < 6) {
      toast('Name, email and a 6+ character password are required');
      return;
    }
    try {
      await api('/users', { method: 'POST', body: JSON.stringify(newUser) });
      toast(`Login created for ${newUser.email} — they sign in on the same Login page`);
      setNewUser({ name: '', email: '', password: '', role: 'agent' });
      load();
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Create failed');
    }
  }

  async function resetPassword(id: number) {
    const pw = (resetPw[id] ?? '').trim();
    if (pw.length < 6) { toast('New password must be 6+ characters'); return; }
    try {
      await api(`/users/${id}`, { method: 'PATCH', body: JSON.stringify({ password: pw }) });
      toast('Password reset');
      setResetPw(p => ({ ...p, [id]: '' }));
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Reset failed');
    }
  }

  async function setUserRole(id: number, role: string) {
    try {
      await api(`/users/${id}`, { method: 'PATCH', body: JSON.stringify({ role }) });
      load();
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Role change failed');
    }
  }

  async function clearInbox() {
    if (!confirm('Clear all inbox data? This will delete all customers, conversations, messages, and tickets for a fresh test. Users, teams, and Knowledge Base are kept. This cannot be undone.')) return;
    if (!confirm('Are you absolutely sure? Type OK to proceed — this will wipe the inbox.')) return;
    setResetting(true);
    try {
      const res = await api<{ ok: boolean; message: string }>('/admin/reset-inbox', { method: 'POST' });
      toast(`✅ ${res.message || 'Inbox cleared — fresh start ready'}`);
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Reset failed (admin only)');
    } finally {
      setResetting(false);
    }
  }

  return (
    <div>
      {node}
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ margin: '0 0 6px' }}>⚙ Settings & Administration</h1>
        <p className="muted small" style={{ margin: 0 }}>Configure inbound channels, manage team workers, and adjust capacity routing.</p>
      </div>

      {/* Structured Navigation Tabs */}
      <div className="settings-tabs">
        <button
          type="button"
          className={`settings-tab ${tab === 'channels' ? 'active' : ''}`}
          onClick={() => setTab('channels')}
        >
          <span>📡</span> Channels & Integrations
        </button>
        <button
          type="button"
          className={`settings-tab ${tab === 'teams' ? 'active' : ''}`}
          onClick={() => setTab('teams')}
        >
          <span>👥</span> Teams & Workers
        </button>
        <button
          type="button"
          className={`settings-tab ${tab === 'capacity' ? 'active' : ''}`}
          onClick={() => setTab('capacity')}
        >
          <span>🟢</span> Availability & Capacity
        </button>
        {isAdmin && (
          <button
            type="button"
            className={`settings-tab ${tab === 'maintenance' ? 'active' : ''}`}
            onClick={() => setTab('maintenance')}
          >
            <span>🧹</span> Maintenance
          </button>
        )}
      </div>

      {err && <ErrorBanner message={err} onRetry={load} />}
      {loading && <SkeletonList />}

      {/* Tab 1: Channels & Webhooks */}
      {!loading && tab === 'channels' && (
        <div>
          <div className="settings-section-header">
            <h2>Connected Communication Channels</h2>
            <p className="muted small">Tokens are encrypted and stored server-side only. Never exposed after saving.</p>
          </div>
          {rows.map(r => (
            <div key={r.channel} className="card" style={{ marginBottom: 14 }}>
              <div className="row">
                <ChannelIcon channel={r.channel} /> <b style={{ textTransform: 'capitalize', fontSize: 16 }}>{r.channel}</b>
                <span className={`badge ${r.connected ? 'b-resolved' : 'b-normal'}`}>{r.connected ? 'connected' : 'not connected'}</span>
                {r.has_token && <span className="badge b-normal">token saved</span>}
              </div>
              <p className="small muted" style={{ margin: '8px 0' }}>{HELP[r.channel]}</p>
              {!isAdmin && <p className="small muted">🔒 Connections are managed by your admin.</p>}
              {isAdmin && OAUTH_CHANNELS.includes(r.channel) && (
                <div className="row" style={{ marginBottom: 8 }}>
                  <button className="btn btn-primary" disabled={oauthBusy === r.channel || r.oauth_ready === false} onClick={() => connectOAuth(r.channel)}>
                    {oauthBusy === r.channel ? 'Opening Meta…' : `🔗 Connect ${r.channel === 'instagram' ? 'Instagram' : 'Facebook'}`}
                  </button>
                  {r.oauth_ready === false ? (
                    <span className="small" style={{ color: '#b45309' }}>⚠ Meta Login unavailable — set META_APP_ID in backend/.env and restart the backend.</span>
                  ) : (
                    <span className="small muted">or paste a token manually below</span>
                  )}
                </div>
              )}
              {isAdmin && r.channel !== 'web' && (
                <div className="row" style={{ marginTop: 8 }}>
                  <input
                    className="input" type="password" placeholder="Access token…" style={{ maxWidth: 320 }}
                    value={forms[r.channel]?.token ?? ''}
                    onChange={e => setForms(p => ({ ...p, [r.channel]: { token: e.target.value, config: p[r.channel]?.config ?? '' } }))}
                  />
                  {(r.channel === 'whatsapp') && (
                    <input
                      className="input" placeholder='Config JSON…' style={{ maxWidth: 280 }}
                      value={forms[r.channel]?.config ?? ''}
                      onChange={e => setForms(p => ({ ...p, [r.channel]: { token: p[r.channel]?.token ?? '', config: e.target.value } }))}
                    />
                  )}
                  <button className="btn btn-primary" disabled={saving === r.channel} onClick={() => save(r.channel)}>
                    {saving === r.channel ? 'Saving…' : 'Connect'}
                  </button>
                </div>
              )}
              <div className="small muted" style={{ marginTop: 10, background: 'rgba(255,255,255,0.02)', padding: '6px 10px', borderRadius: 8 }}>
                {r.channel === 'web' ? (
                  <>Embed: <code>{embed}</code> · <a href={`${origin}/api/v1/web/widget-demo`} target="_blank" rel="noreferrer">live demo</a></>
                ) : r.channel === 'email' ? (
                  <>Inbound webhook: <code>{origin}/webhooks/email</code></>
                ) : (
                  <>Webhook: <code>{origin}/webhooks/{r.channel}</code> (verify with your META_VERIFY_TOKEN)</>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Tab 2: Teams & Workers */}
      {!loading && tab === 'teams' && (
        <div>
          <div className="settings-section-header">
            <h2>Teams & Worker Management</h2>
            <p className="muted small">Organize staff into operational teams. Full and offline/away workers are automatically skipped during message routing.</p>
          </div>

          <div className="settings-two-col">
            {isAdmin && (
              <div className="card">
                <b>＋ Create Worker Login</b>
                <p className="small muted" style={{ margin: '4px 0 12px' }}>Workers sign in on the same login page and see their assigned queue.</p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <div>
                    <label className="small muted" style={{ display: 'block', marginBottom: 4 }}>Full Name</label>
                    <input className="input" placeholder="e.g. Alex Smith" value={newUser.name} onChange={e => setNewUser({ ...newUser, name: e.target.value })} />
                  </div>
                  <div>
                    <label className="small muted" style={{ display: 'block', marginBottom: 4 }}>Email Address</label>
                    <input className="input" placeholder="alex@fty.local" value={newUser.email} onChange={e => setNewUser({ ...newUser, email: e.target.value })} />
                  </div>
                  <div>
                    <label className="small muted" style={{ display: 'block', marginBottom: 4 }}>Password (6+ characters)</label>
                    <input className="input" type="password" placeholder="••••••••" value={newUser.password} onChange={e => setNewUser({ ...newUser, password: e.target.value })} />
                  </div>
                  <div>
                    <label className="small muted" style={{ display: 'block', marginBottom: 4 }}>System Role</label>
                    <select className="select" value={newUser.role} onChange={e => setNewUser({ ...newUser, role: e.target.value })}>
                      <option value="agent">agent (worker)</option>
                      <option value="manager">manager</option>
                      <option value="admin">admin</option>
                    </select>
                  </div>
                  <button className="btn btn-primary" style={{ marginTop: 4 }} onClick={createUser}>Create Worker Login</button>
                </div>
              </div>
            )}

            {isManager && (
              <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
                <b>＋ Create New Team</b>
                <p className="small muted" style={{ margin: '4px 0 12px' }}>Categorize routing queues by department or focus area.</p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: 1 }}>
                  <div>
                    <label className="small muted" style={{ display: 'block', marginBottom: 4 }}>Team Name</label>
                    <input className="input" placeholder="e.g. Sales, Orders, VIP Support…" value={newTeam} onChange={e => setNewTeam(e.target.value)} />
                  </div>
                  <div style={{ marginTop: 'auto' }}>
                    <button className="btn btn-primary" style={{ width: '100%' }} onClick={createTeam}>Create Team</button>
                  </div>
                </div>
              </div>
            )}
          </div>

          <h3 style={{ margin: '24px 0 12px' }}>Active Teams ({teams.length})</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 14 }}>
            {teams.map(t => (
              <div key={t.id} className="card" style={{ margin: 0, display: 'flex', flexDirection: 'column' }}>
                <div className="row" style={{ marginBottom: 10, justifyContent: 'space-between' }}>
                  <b style={{ fontSize: 16 }}>{t.name}</b>
                  <span className="badge b-normal">{t.members.length} member(s)</span>
                </div>
                <div style={{ minHeight: 60, display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 14 }}>
                  {t.members.length === 0 ? (
                    <span className="small muted">No workers assigned to this team yet.</span>
                  ) : t.members.map(m => (
                    <div key={m.user_id} className="row" style={{ background: 'rgba(255,255,255,0.03)', padding: '6px 10px', borderRadius: 8 }}>
                      <span className={`status-dot ${m.availability || 'available'}`} />
                      <span className="grow small">
                        <b>{m.name}</b> <span className="muted">· {m.availability} · {m.active} active</span>
                      </span>
                      {isManager && (
                        <button className="btn" style={{ padding: '2px 8px', fontSize: 12 }} onClick={() => removeMember(t.id, m.user_id)}>Remove</button>
                      )}
                    </div>
                  ))}
                </div>
                {isManager && (
                  <div className="row" style={{ marginTop: 'auto' }}>
                    <select className="select grow" value={memberPick[t.id] ?? ''} onChange={e => setMemberPick(p => ({ ...p, [t.id]: e.target.value }))}>
                      <option value="">＋ Add worker to team…</option>
                      {agents.filter(a => !t.members.some(m => m.user_id === a.id)).map(a => (
                        <option key={a.id} value={a.id}>{a.name}</option>
                      ))}
                    </select>
                    <button className="btn btn-primary" onClick={() => addMember(t.id)} disabled={!memberPick[t.id]}>Add</button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 3: Availability & Capacity */}
      {!loading && tab === 'capacity' && (
        <div>
          <div className="settings-section-header">
            <h2>Availability, Capacity & Access</h2>
            <p className="muted small">Set worker load thresholds, availability statuses, and reset credentials.</p>
          </div>

          {me && (
            <div className="card" style={{ marginBottom: 16 }}>
              <div className="row">
                <span className={`status-dot ${me.availability || 'available'}`} style={{ width: 12, height: 12 }} />
                <div>
                  <b style={{ fontSize: 15 }}>My Personal Status — {me.name}</b>
                  <div className="small muted">Your current real-time routing availability:</div>
                </div>
              </div>
              <div className="row" style={{ marginTop: 12 }}>
                <select className="select" style={{ maxWidth: 240 }} value={me.availability ?? 'available'} onChange={e => patchAgent(me.id, { availability: e.target.value })}>
                  <option value="available">🟢 Available (Accepting chats)</option>
                  <option value="away">🟡 Away (Busy — paused)</option>
                  <option value="offline">🔴 Offline (Done — paused)</option>
                </select>
                <span className="small muted">Setting 🟡 Away or 🔴 Offline pauses auto-assignment to you.</span>
              </div>
            </div>
          )}

          {isAdmin && (
            <div className="card" style={{ marginBottom: 16, borderColor: 'rgba(248,113,113,0.3)', background: 'rgba(248,113,113,0.04)' }}>
              <b>🧹 Maintenance — Fresh Start for Testing</b>
              <p className="small muted" style={{ margin: '4px 0 10px' }}>Clear all inbox test data (customers, conversations, messages, tickets, history) for a clean test. Keeps users, teams, and Knowledge Base. Use before demos.</p>
              <button className="btn" style={{ background: 'rgba(248,113,113,0.9)', borderColor: 'rgba(248,113,113,0.9)', color: '#fff' }} onClick={clearInbox} disabled={resetting}>
                {resetting ? 'Clearing…' : 'Clear Inbox — Fresh Start'}
              </button>
            </div>
          )}
      {/* Tab 4: Maintenance (admin) */}
      {!loading && tab === 'maintenance' && isAdmin && (
        <div>
          <div className="settings-section-header">
            <h2>Maintenance & Testing</h2>
            <p className="muted small">Reset test data and verify system health.</p>
          </div>
          <div className="card" style={{ borderColor: 'rgba(248,113,113,0.35)' }}>
            <b>🧹 Clear Inbox — Fresh Start</b>
            <p className="small muted" style={{ margin: '6px 0 12px' }}>Removes all customers, conversations, messages, tickets, and history for a clean test run. <b>Preserves</b> users, teams, and Knowledge Base. Useful before demos.</p>
            <button className="btn" style={{ background: '#ef4444', borderColor: '#ef4444', color: '#fff' }} onClick={clearInbox} disabled={resetting}>
              {resetting ? 'Clearing…' : 'Clear All Inbox Data'}
            </button>
            <p className="small muted" style={{ marginTop: 8 }}>Local alternative: <code>powershell -NoProfile -ExecutionPolicy Bypass -File scripts/reset-dev.ps1</code></p>
          </div>
        </div>
      )}

          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <table className="table">
              <thead><tr><th>Worker</th><th>Role</th><th>Status</th><th>Max Active Capacity</th>{isAdmin && <th>Reset Password</th>}</tr></thead>
              <tbody>
                {agents.map(a => (
                  <tr key={a.id}>
                    <td>
                      <div className="row">
                        <span className={`status-dot ${a.availability || 'available'}`} />
                        <div>
                          <b>{a.name}</b><br />
                          <span className="muted small">{a.email}</span>
                        </div>
                      </div>
                    </td>
                    <td>
                      {isAdmin ? (
                        <select className="select" value={a.role} onChange={e => setUserRole(a.id, e.target.value)}>
                          <option value="agent">agent</option>
                          <option value="manager">manager</option>
                          <option value="admin">admin</option>
                        </select>
                      ) : (
                        <span className="badge b-normal">{a.role}</span>
                      )}
                    </td>
                    <td>
                      <select className="select" value={a.availability ?? 'available'} disabled={!isManager} onChange={e => patchAgent(a.id, { availability: e.target.value })}>
                        <option value="available">🟢 Available</option>
                        <option value="away">🟡 Away</option>
                        <option value="offline">🔴 Offline</option>
                      </select>
                    </td>
                    <td>
                      <div className="row">
                        <input className="input" type="number" min={1} max={50} style={{ maxWidth: 80 }} defaultValue={a.max_active ?? 10}
                          key={`${a.id}-${a.max_active}`} disabled={!isManager}
                          onBlur={e => patchAgent(a.id, { max_active: Number(e.target.value) })} />
                        <span className="small muted">active chats</span>
                      </div>
                    </td>
                    {isAdmin && (
                      <td>
                        <div className="row">
                          <input className="input" type="password" style={{ maxWidth: 140 }} placeholder="New 6+ password"
                            value={resetPw[a.id] ?? ''} onChange={e => setResetPw(p => ({ ...p, [a.id]: e.target.value }))} />
                          <button className="btn" style={{ padding: '4px 12px' }} onClick={() => resetPassword(a.id)}>Reset</button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {/* Tab 4: Maintenance (admin) */}
      {!loading && tab === 'maintenance' && isAdmin && (
        <div>
          <div className="settings-section-header">
            <h2>Maintenance & Testing</h2>
            <p className="muted small">Reset test data and verify system health.</p>
          </div>
          <div className="card" style={{ borderColor: 'rgba(248,113,113,0.35)' }}>
            <b>🧹 Clear Inbox — Fresh Start</b>
            <p className="small muted" style={{ margin: '6px 0 12px' }}>Removes all customers, conversations, messages, tickets, and history for a clean test run. <b>Preserves</b> users, teams, and Knowledge Base. Useful before demos.</p>
            <button className="btn" style={{ background: '#ef4444', borderColor: '#ef4444', color: '#fff' }} onClick={clearInbox} disabled={resetting}>
              {resetting ? 'Clearing…' : 'Clear All Inbox Data'}
            </button>
            <p className="small muted" style={{ marginTop: 8 }}>Local alternative: <code>powershell -NoProfile -ExecutionPolicy Bypass -File scripts/reset-dev.ps1</code></p>
          </div>
        </div>
      )}
    </div>
  );
}
