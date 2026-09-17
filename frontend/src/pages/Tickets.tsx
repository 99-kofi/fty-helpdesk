import { useEffect, useMemo, useState } from 'react';
import { api, Agent, Ticket } from '../api/client';
import { Badge, EmptyState, ErrorBanner, SkeletonList, useToast } from '../components/ui';

const STATUSES = ['all', 'in_progress', 'waiting_for_customer', 'resolved'];
const WORKER_STATUSES = ['in_progress', 'waiting_for_customer', 'resolved'] as const;

export default function Tickets() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [me, setMe] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [fStatus, setFStatus] = useState('all');
  const [newConv, setNewConv] = useState('');
  const [newCat, setNewCat] = useState('');
  const { toast, node } = useToast();

  async function load() {
    try {
      setErr(null);
      const [t, a, myself] = await Promise.all([
        api<Ticket[]>('/tickets'),
        api<Agent[]>('/agents').catch(() => [] as Agent[]),
        api<Agent>('/auth/me').catch(() => null as unknown as Agent),
      ]);
      setTickets(t);
      setAgents(a);
      setMe(myself);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to load tickets');
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); }, []);

  const filtered = useMemo(
    () => tickets.filter(t => fStatus === 'all' || t.status === fStatus),
    [tickets, fStatus]
  );

  async function update(id: number, patch: { status?: string; assigned_to?: string }) {
    const q = new URLSearchParams();
    if (patch.status) q.set('status', patch.status);
    if (patch.assigned_to !== undefined) q.set('assigned_to', patch.assigned_to);
    try {
      await api(`/tickets/${id}?${q.toString()}`, { method: 'PATCH' });
      toast(`Ticket #${id} updated`);
      load();
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Update failed');
    }
  }

  async function create() {
    if (!newConv.trim()) { toast('Enter a conversation ID first'); return; }
    try {
      await api('/tickets', {
        method: 'POST',
        body: JSON.stringify({ conversation_id: Number(newConv), category: newCat || 'general', priority: 'normal' }),
      });
      setNewConv('');
      setNewCat('');
      toast('Ticket created');
      load();
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Create failed');
    }
  }

  const isAdmin = me?.role === 'admin';

  return (
    <div>
      {node}
      <div className="row" style={{ marginBottom: 12 }}>
        <h1 style={{ margin: 0 }}>🎫 Tickets</h1>
        <span className="grow" />
        <select className="select" value={fStatus} onChange={e => setFStatus(e.target.value)}>
          {(isAdmin ? STATUSES : ['all', ...WORKER_STATUSES]).map(s => <option key={s} value={s}>{s === 'all' ? 'All statuses' : s.replace(/_/g, ' ')}</option>)}
        </select>
      </div>
      {err && <ErrorBanner message={err} onRetry={load} />}
      {isAdmin && (
      <div className="card" style={{ marginBottom: 12 }}>
        <b>＋ New ticket</b>
        <div className="row" style={{ marginTop: 8 }}>
          <input className="input" style={{ maxWidth: 160 }} placeholder="Conversation ID" value={newConv} onChange={e => setNewConv(e.target.value)} />
          <input className="input" style={{ maxWidth: 220 }} placeholder="Category (order, return…)" value={newCat} onChange={e => setNewCat(e.target.value)} />
          <button className="btn btn-primary" onClick={create}>Create</button>
        </div>
      </div>
      )}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {loading ? <SkeletonList /> : filtered.length === 0 ? (
          <EmptyState icon="🎫" title="No tickets" hint="Create one above, or file one from the Inbox side panel." />
        ) : (
          <table className="table">
            <thead><tr><th>ID</th><th>Conversation</th><th>Category</th><th>Status</th><th>Priority</th><th>Assignee</th><th></th></tr></thead>
            <tbody>
              {filtered.map(t => (
                <tr key={t.id}>
                  <td><b>#{t.id}</b></td>
                  <td>#{t.conversation_id}</td>
                  <td>{t.category ?? '—'}</td>
                  <td>
                    <select className="select" value={t.status} onChange={e => update(t.id, { status: e.target.value })}>
                      {WORKER_STATUSES.map(s => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
                    </select>
                  </td>
                  <td><Badge value={t.priority} /></td>
                  <td>
                    <select
                      className="select" value={t.assigned_to ?? ''} disabled={!isAdmin} title={isAdmin ? 'Reassign (admin)' : 'Only the admin reassigns'}
                      onChange={e => update(t.id, { assigned_to: e.target.value })}
                    >
                      <option value="">Unassigned</option>
                      {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                    </select>
                  </td>
                  <td><Badge value={t.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
