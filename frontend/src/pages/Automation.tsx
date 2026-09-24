import { useEffect, useState } from 'react';
import { api, Rule } from '../api/client';
import { Badge, EmptyState, ErrorBanner, SkeletonList, useToast } from '../components/ui';

// Preset automations that cover 90% of FTY needs — one click to enable
const PRESETS = [
  { name: 'VIP → urgent + manager', trigger: 'message_created', cond: { contains: 'vip' }, action: { set_priority: 'urgent', escalate: true }, icon: '⭐', desc: 'Messages containing "vip" get urgent priority and go to a manager.' },
  { name: 'Instagram complaints → Support', trigger: 'message_created', cond: { channel: 'instagram', contains: 'complaint' }, action: { set_team: 'Customer Support', set_priority: 'high' }, icon: '📱', desc: 'Instagram complaints are triaged to Customer Support as high priority.' },
  { name: 'Returns → auto-assign', trigger: 'message_created', cond: { contains: 'return' }, action: { set_team: 'Customer Support', auto_assign: true }, icon: '↩️', desc: 'Messages mentioning return/refund are assigned to the next available support agent.' },
  { name: 'Uncategorized tickets → normal', trigger: 'ticket_created', cond: { contains: 'general' }, action: { set_priority: 'normal' }, icon: '🎫', desc: 'New tickets with “general” category start as normal priority.' },
];

const TRIGGER_LABEL: Record<string, string> = {
  message_created: 'When a customer sends a message',
  ticket_created: 'When a ticket is created',
};
const COND_LABEL: Record<string, string> = {
  contains: 'message contains',
  channel: 'channel is',
  priority: 'priority is',
};
const ACTION_LABEL: Record<string, string> = {
  set_priority: 'Set priority to',
  set_team: 'Move to team',
  auto_assign: 'Auto-assign to next worker',
  escalate: 'Escalate to manager',
};

function ruleToSentence(r: Rule): string {
  const cond = Object.entries(r.conditions).map(([k, v]) => `${COND_LABEL[k] || k} "${v}"`).join(' and ') || 'always';
  const acts = Object.entries(r.actions).map(([k, v]) => {
    if (k === 'auto_assign' && v) return ACTION_LABEL[k];
    if (k === 'escalate' && v) return ACTION_LABEL[k];
    return `${ACTION_LABEL[k] || k} ${v}`;
  }).join(', ');
  return `${TRIGGER_LABEL[r.trigger] || r.trigger} • If ${cond} → ${acts}`;
}

export default function Automation() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [trigger, setTrigger] = useState('message_created');
  const [condKey, setCondKey] = useState('contains');
  const [condVal, setCondVal] = useState('');
  const [actKey, setActKey] = useState('set_priority');
  const [actVal, setActVal] = useState('high');
  const [slaResult, setSlaResult] = useState<string | null>(null);
  const { toast, node } = useToast();

  async function load() {
    try {
      setErr(null);
      setRules(await api<Rule[]>('/automation'));
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to load rules');
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); }, []);

  async function createFromPreset(p: typeof PRESETS[number]) {
    try {
      await api('/automation', { method: 'POST', body: JSON.stringify({ name: p.name, trigger: p.trigger, conditions: p.cond, actions: p.action }) });
      toast(`Added: ${p.name}`);
      load();
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Create failed');
    }
  }

  async function createCustom() {
    if (!name.trim()) { toast('Give it a short name'); return; }
    if (!condVal.trim() && condKey !== 'priority') { toast('Add what to look for'); return; }
    const cond: Record<string, unknown> = condVal.trim() ? { [condKey]: condVal.trim() } : {};
    const actions: Record<string, unknown> = {};
    if (actKey === 'auto_assign' || actKey === 'escalate') actions[actKey] = true;
    else actions[actKey] = actVal.trim() || 'high';
    try {
      await api('/automation', { method: 'POST', body: JSON.stringify({ name: name.trim(), trigger, conditions: cond, actions }) });
      setName(''); setCondVal('');
      toast('Automation created');
      load();
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Create failed');
    }
  }

  async function toggle(r: Rule) {
    await api(`/automation/${r.id}`, { method: 'PATCH', body: JSON.stringify({ enabled: !r.enabled }) });
    load();
  }
  async function remove(id: number) {
    if (!confirm('Delete this automation?')) return;
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
      <p className="muted small">Set up <b>if this → then that</b> rules. They run automatically after the assignment engine — no code needed.</p>
      {err && <ErrorBanner message={err} onRetry={load} />}

      {/* Presets */}
      <div className="card" style={{ marginBottom: 12 }}>
        <b>✨ Quick start — tap to add a working automation</b>
        <p className="small muted">These cover the most common FTY flows. Enable one, test it with a message, and tweak it later.</p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 10, marginTop: 10 }}>
          {PRESETS.map(p => {
            const exists = rules.some(r => r.name === p.name);
            return (
              <button key={p.name} className="card" style={{ textAlign: 'left', cursor: exists ? 'default' : 'pointer', opacity: exists ? 0.6 : 1, padding: 12 }} onClick={() => !exists && createFromPreset(p)} disabled={exists}>
                <div><span style={{ fontSize: 18 }}>{p.icon}</span> <b>{p.name}</b> {exists && <span className="badge b-normal">added</span>}</div>
                <div className="small muted" style={{ marginTop: 4 }}>{p.desc}</div>
                {!exists && <div className="small" style={{ marginTop: 6, color: 'var(--primary)' }}>+ Add</div>}
              </button>
            );
          })}
        </div>
      </div>

      {/* Simple builder */}
      <div className="card" style={{ marginBottom: 12 }}>
        <b>＋ Custom automation</b>
        <p className="small muted">Describe it in plain English — we handle the rest.</p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 10 }}>
          <div className="row" style={{ flexWrap: 'wrap' }}>
            <span className="small"><b>When</b></span>
            <select className="select" value={trigger} onChange={e => setTrigger(e.target.value)}>
              <option value="message_created">a customer sends a message</option>
              <option value="ticket_created">a ticket is created</option>
            </select>
            <span className="small"><b>and</b></span>
            <select className="select" value={condKey} onChange={e => setCondKey(e.target.value)}>
              <option value="contains">message contains</option>
              <option value="channel">channel is</option>
              <option value="priority">priority is</option>
            </select>
            <input className="input" style={{ maxWidth: 200 }} placeholder={condKey === 'contains' ? 'e.g. vip, return' : condKey === 'channel' ? 'instagram / web' : 'urgent / high'} value={condVal} onChange={e => setCondVal(e.target.value)} />
          </div>
          <div className="row" style={{ flexWrap: 'wrap' }}>
            <span className="small"><b>then</b></span>
            <select className="select" value={actKey} onChange={e => setActKey(e.target.value)}>
              <option value="set_priority">set priority to</option>
              <option value="set_team">move to team</option>
              <option value="auto_assign">auto-assign to next worker</option>
              <option value="escalate">escalate to manager</option>
            </select>
            {(actKey === 'set_priority') && (
              <select className="select" value={actVal} onChange={e => setActVal(e.target.value)}>
                <option value="low">low</option><option value="normal">normal</option><option value="high">high</option><option value="urgent">urgent</option>
              </select>
            )}
            {(actKey === 'set_team') && (
              <input className="input" style={{ maxWidth: 200 }} placeholder="e.g. Customer Support" value={actVal} onChange={e => setActVal(e.target.value)} />
            )}
            {(actKey === 'auto_assign' || actKey === 'escalate') && <span className="small muted">enabled</span>}
            <input className="input" style={{ maxWidth: 200 }} placeholder="Name (e.g. VIP handler)" value={name} onChange={e => setName(e.target.value)} />
            <button className="btn btn-primary" onClick={createCustom}>Create</button>
          </div>
        </div>
      </div>

      {loading ? <SkeletonList /> : rules.length === 0 ? (
        <EmptyState icon="🤖" title="No automations yet" hint="Tap a quick start above or build a custom one." />
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'hidden', marginBottom: 12 }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)' }}><b>Active automations ({rules.length})</b></div>
          {rules.map(r => (
            <div key={r.id} style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', opacity: r.enabled ? 1 : 0.6, display: 'flex', gap: 10, alignItems: 'center' }}>
              <div style={{ flex: 1 }}>
                <div><b>{r.name}</b> <Badge value={r.enabled ? 'on' : 'off'} /> <span className="small muted">{r.trigger === 'message_created' ? 'on message' : 'on ticket'}</span></div>
                <div className="small muted" style={{ marginTop: 2 }}>{ruleToSentence(r)}</div>
              </div>
              <button className="btn" style={{ padding: '4px 10px' }} onClick={() => toggle(r)}>{r.enabled ? 'Pause' : 'Resume'}</button>
              <button className="btn" style={{ padding: '4px 10px' }} onClick={() => remove(r.id)}>Delete</button>
            </div>
          ))}
        </div>
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
