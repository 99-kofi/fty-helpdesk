import { useEffect, useState } from 'react';
import { api, Rule } from '../api/client';
import { Badge, EmptyState, ErrorBanner, SkeletonList, useToast } from '../components/ui';

// The only automations FTY needs — each is a simple on/off toggle
const PRESETS = [
  { name: 'VIP → urgent + manager', trigger: 'message_created', cond: { contains: 'vip' }, action: { set_priority: 'urgent', escalate: true }, icon: '⭐', desc: 'Messages with "vip" become urgent and go to a manager.' },
  { name: 'Instagram complaints → Support', trigger: 'message_created', cond: { channel: 'instagram', contains: 'complaint' }, action: { set_team: 'Customer Support', set_priority: 'high' }, icon: '📱', desc: 'Instagram complaints → Customer Support, high priority.' },
  { name: 'Returns → auto-assign', trigger: 'message_created', cond: { contains: 'return' }, action: { set_team: 'Customer Support', auto_assign: true }, icon: '↩️', desc: 'Return/refund messages auto-assign to the next free agent.' },
  { name: 'Uncategorized tickets → normal', trigger: 'ticket_created', cond: { contains: 'general' }, action: { set_priority: 'normal' }, icon: '🎫', desc: 'New “general” tickets start as normal priority.' },
];

export default function Automation() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [slaResult, setSlaResult] = useState<string | null>(null);
  const { toast, node } = useToast();

  async function load() {
    try {
      setErr(null);
      setRules(await api<Rule[]>('/automation'));
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to load automations');
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); }, []);

  async function enablePreset(p: typeof PRESETS[number]) {
    try {
      await api('/automation', { method: 'POST', body: JSON.stringify({ name: p.name, trigger: p.trigger, conditions: p.cond, actions: p.action }) });
      toast(`Enabled: ${p.name}`);
      load();
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Enable failed');
    }
  }
  async function toggle(r: Rule) {
    await api(`/automation/${r.id}`, { method: 'PATCH', body: JSON.stringify({ enabled: !r.enabled }) });
    load();
  }
  async function remove(id: number) {
    if (!confirm('Turn off this automation?')) return;
    await api(`/automation/${id}`, { method: 'DELETE' });
    load();
  }
  async function runSla() {
    try {
      const r = await api<{ conversations_escalated: number; tickets_escalated: number }>('/automation/sla-check', { method: 'POST' });
      setSlaResult(`Escalated ${r.conversations_escalated} conversation(s), ${r.tickets_escalated} ticket(s).`);
    } catch (e) {
      toast(e instanceof Error ? e.message : 'SLA check failed');
    }
  }

  return (
    <div>
      {node}
      <h1 style={{ marginTop: 0 }}>🤖 Automation</h1>
      <p className="muted small">Turn on the automations you need — they run automatically, no setup beyond a tap.</p>
      {err && <ErrorBanner message={err} onRetry={load} />}

      {loading ? <SkeletonList /> : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 12, marginBottom: 16 }}>
          {PRESETS.map(p => {
            const existing = rules.find(r => r.name === p.name);
            const on = !!existing?.enabled;
            const off = !!existing && !existing.enabled;
            return (
              <div key={p.name} className="card" style={{ padding: 16, opacity: existing && !on ? 0.7 : 1 }}>
                <div style={{ fontSize: 22 }}>{p.icon}</div>
                <div style={{ marginTop: 6 }}><b>{p.name}</b> {existing && <Badge value={on ? 'on' : 'off'} />}</div>
                <div className="small muted" style={{ marginTop: 4, minHeight: 32 }}>{p.desc}</div>
                {!existing ? (
                  <button className="btn btn-primary" style={{ marginTop: 10, width: '100%' }} onClick={() => enablePreset(p)}>Enable</button>
                ) : (
                  <div className="row" style={{ marginTop: 10 }}>
                    <button className="btn" style={{ flex: 1 }} onClick={() => toggle(existing)}>{on ? 'Pause' : 'Resume'}</button>
                    <button className="btn" onClick={() => remove(existing.id)}>Remove</button>
                  </div>
                )}
                {off && <div className="small muted" style={{ marginTop: 6 }}>Paused</div>}
              </div>
            );
          })}
        </div>
      )}

      {!loading && rules.filter(r => !PRESETS.some(p => p.name === r.name)).length > 0 && (
        <div className="card" style={{ padding: 0, overflow: 'hidden', marginBottom: 12 }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)' }}><b>Other automations</b></div>
          {rules.filter(r => !PRESETS.some(p => p.name === r.name)).map(r => (
            <div key={r.id} style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 10, alignItems: 'center' }}>
              <div style={{ flex: 1 }}><b>{r.name}</b> <Badge value={r.enabled ? 'on' : 'off'} /></div>
              <button className="btn" style={{ padding: '4px 10px' }} onClick={() => toggle(r)}>{r.enabled ? 'Pause' : 'Resume'}</button>
              <button className="btn" style={{ padding: '4px 10px' }} onClick={() => remove(r.id)}>Remove</button>
            </div>
          ))}
        </div>
      )}

      {!loading && rules.length === 0 && (
        <EmptyState icon="🤖" title="No automations yet" hint="Tap Enable on a card above to turn one on." />
      )}

      <div className="card">
        <b>⏱ SLA watchdog</b>
        <p className="small muted">If a customer waits too long or a ticket sits too long, it is escalated to a manager. Runs every few minutes — tap to test now.</p>
        <button className="btn" onClick={runSla}>Run SLA check now</button>
        {slaResult && <p className="small" style={{ color: '#6ee7b7', marginTop: 6 }}>{slaResult}</p>}
      </div>
    </div>
  );
}
