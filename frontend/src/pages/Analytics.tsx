import { useEffect, useState } from 'react';
import { api, Overview } from '../api/client';
import { ErrorBanner, Spinner, StatCard } from '../components/ui';

function Bars({ data, suffix = '' }: { data: Record<string, number>; suffix?: string }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, n]) => n));
  if (entries.length === 0) return <span className="muted small">No data yet.</span>;
  return (
    <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
      {entries.map(([k, n]) => (
        <div key={k}>
          <div className="row"><span className="small" style={{ width: 140 }}>{k.replace(/_/g, ' ')}</span><b>{n}{suffix}</b></div>
          <div className="bar"><div style={{ width: `${(n / max) * 100}%` }} /></div>
        </div>
      ))}
    </div>
  );
}

export default function Analytics() {
  const [ov, setOv] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api<Overview>('/analytics/overview')
      .then(setOv)
      .catch(e => setErr(e instanceof Error ? e.message : 'Failed to load analytics'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="row"><Spinner /> <span className="muted">Loading analytics…</span></div>;

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>📊 Analytics</h1>
      {err && <ErrorBanner message={err} />}
      {ov && (
        <>
          <div className="stat-grid">
            <StatCard num={ov.totals.open_conversations} label="Open conversations" />
            <StatCard num={ov.totals.unassigned} label="Unassigned" />
            <StatCard num={ov.totals.urgent} label="Urgent open" />
            <StatCard num={ov.avg_first_response_min ?? '—'} label="Avg first response (min)" />
            <StatCard num={ov.avg_resolution_hours ?? '—'} label="Avg resolution (hrs)" />
            <StatCard num={ov.totals.tickets} label="Total tickets" />
          </div>
          <div className="card" style={{ marginBottom: 12 }}>
            <b>Volume — last 14 days</b>
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6, height: 120, marginTop: 12 }}>
              {ov.volume_14d.map(d => {
                const h = Math.min(100, d.messages * 8 + d.conversations * 12);
                return (
                  <div key={d.day} title={`${d.day}: ${d.conversations} conv, ${d.messages} msg`}
                    style={{ flex: 1, height: `${Math.max(4, h)}%`, background: '#4f46e5', borderRadius: '4px 4px 0 0', opacity: 0.75 }} />
                );
              })}
            </div>
            <div className="row" style={{ marginTop: 4 }}>
              <span className="small muted">{ov.volume_14d[0]?.day.slice(5)}</span>
              <span className="grow" />
              <span className="small muted">{ov.volume_14d[ov.volume_14d.length - 1]?.day.slice(5)}</span>
            </div>
          </div>
          <div className="row" style={{ alignItems: 'flex-start' }}>
            <div className="card grow"><b>Conversations by channel</b><Bars data={ov.by_channel} /></div>
            <div className="card grow"><b>Open load by team</b><Bars data={ov.by_team} /></div>
            <div className="card grow"><b>Tickets by category</b><Bars data={ov.tickets_by_category} /></div>
          </div>
          <div className="card" style={{ marginTop: 12, padding: 0, overflow: 'hidden' }}>
            <div style={{ padding: '12px 16px' }}><b>🏅 Agent scorecard</b></div>
            {ov.agents.length === 0 ? <p className="muted small" style={{ padding: '0 16px 16px' }}>No assigned work yet.</p> : (
              <table className="table">
                <thead><tr><th>Worker</th><th>Active</th><th>Tickets resolved</th><th>Avg response (min)</th></tr></thead>
                <tbody>
                  {ov.agents.map(a => (
                    <tr key={a.id}>
                      <td><b>{a.name}</b></td>
                      <td>{a.active}</td>
                      <td>{a.resolved_tickets}</td>
                      <td>{a.avg_response_min ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
}
