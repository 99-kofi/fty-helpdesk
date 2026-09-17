import { useEffect, useState } from 'react';
import { api, Rule } from '../api/client';
import { Badge, EmptyState, ErrorBanner, SkeletonList, useToast } from '../components/ui';

const CONDITION_HINTS: Record<string, string> = {
  channel: 'exact channel, e.g. instagram',
  contains: 'keyword in the message, e.g. vip',
  intent: 'classified intent, e.g. complaint',
  min_confidence: 'number 0..1, e.g. 0.8',
  priority: 'low | normal | high | urgent',
};
const ACTION_HINTS: Record<string, string> = {
  set_priority: 'low | normal | high | urgent',
  set_team: 'team name, e.g. Customer Support',
  auto_assign: 'true to route to a worker now',
  escalate: 'true for urgent + manager',
};

export default function Automation() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [trigger, setTrigger] = useState('message_created');
  const [condKey, setCondKey] = useState('contains');
  const [condVal, setCondVal] = useState('');
  const [actKey, setActKey] = useState('set_priority');
  const [actVal, setActVal] = useState('urgent');
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

  function parseVal(v: string): unknown {
    if (v === 'true') return true;
    if (v === 'false') return false;
    const n = Number(v);
    if (v.trim() !== '' && !Number.isNaN(n)) return n;
    return v;
  }

  async function create() {
    if (!name.trim()) { toast('Give the rule a name'); return; }
    try {
      await api('/automation', {
        method: 'POST',
        body: JSON.stringify({
          name: name.trim(), trigger,
          conditions: condVal.trim() ? { [condKey]: parseVal(condVal) } : {},
          actions: { [actKey]: parseVal(actVal) },
        }),
      });
      setName(''); setCondVal('');
      toast('Rule created');
      load();
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Create failed (manager only?)');
    }
  }

  async function toggle(r: Rule) {
    await api(`/automation/${r.id}`, { method: 'PATCH', body: JSON.stringify({ enabled: !r.enabled }) });
    load();
  }

  async function remove(id: number) {
    if (!confirm('Delete this rule?')) return;
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
      <p className="muted small">WHEN something happens → IF conditions match → DO actions. Rules run after the assignment engine.</p>
      {err && <ErrorBanner message={err} onRetry={load} />}
      <div className="card" style={{ marginBottom: 12 }}>
        <b>＋ New rule</b>
        <div className="row" style={{ marginTop: 8 }}>
          <input className="input" style={{ maxWidth: 200 }} placeholder="Rule name" value={name} onChange={e => setName(e.target.value)} />
          <select className="select" value={trigger} onChange={e => setTrigger(e.target.value)}>
            <option value="message_created">WHEN customer message arrives</option>
            <option value="ticket_created">WHEN ticket is filed</option>
          </select>
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <span className="small muted">IF</span>
          <select className="select" value={condKey} onChange={e => setCondKey(e.target.value)}>
            {Object.keys(CONDITION_HINTS).map(k => <option key={k} value={k}>{k}</option>)}
          </select>
          <input className="input" style={{ maxWidth: 220 }} placeholder={CONDITION_HINTS[condKey]} value={condVal} onChange={e => setCondVal(e.target.value)} />
          <span className="small muted">THEN</span>
          <select className="select" value={actKey} onChange={e => setActKey(e.target.value)}>
            {Object.keys(ACTION_HINTS).map(k => <option key={k} value={k}>{k}</option>)}
          </select>
          <input className="input" style={{ maxWidth: 200 }} placeholder={ACTION_HINTS[actKey]} value={actVal} onChange={e => setActVal(e.target.value)} />
          <button className="btn btn-primary" onClick={create}>Create</button>
        </div>
      </div>
      {loading ? <SkeletonList /> : rules.length === 0 ? (
        <EmptyState icon="🤖" title="No rules yet" hint='Try: IF contains "vip" THEN set_priority urgent.' />
      ) : rules.map(r => (
        <div key={r.id} className="card" style={{ marginBottom: 10, opacity: r.enabled ? 1 : 0.6 }}>
          <div className="row">
            <b>{r.name}</b>
            <Badge value={r.trigger} />
            <Badge value={r.enabled ? 'open' : 'closed'} />
            <span className="grow" />
            <button className="btn" style={{ padding: '4px 10px' }} onClick={() => toggle(r)}>{r.enabled ? 'Disable' : 'Enable'}</button>
            <button className="btn" style={{ padding: '4px 10px' }} onClick={() => remove(r.id)}>Delete</button>
          </div>
          <div className="small muted" style={{ marginTop: 6 }}>
            IF <code>{JSON.stringify(r.conditions)}</code> THEN <code>{JSON.stringify(r.actions)}</code>
          </div>
        </div>
      ))}
      <div className="card" style={{ marginTop: 12 }}>
        <b>⏱ SLA watchdog</b>
        <p className="small muted">Escalates customers waiting over the response limit and stale tickets. Runs automatically in the background; trigger it now to test.</p>
        <button className="btn" onClick={runSla}>Run SLA check now</button>
        {slaResult && <p className="small" style={{ color: '#065f46' }}>{slaResult}</p>}
      </div>
    </div>
  );
}
