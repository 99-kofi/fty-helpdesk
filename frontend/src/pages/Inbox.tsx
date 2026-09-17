import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, Agent, AiSuggestion, Conversation, Customer, HistoryEntry, Message, Team } from '../api/client';
import { useInboxSocket } from '../hooks/useInboxSocket';
import { Avatar, Badge, ChannelIcon, EmptyState, ErrorBanner, SkeletonList, useToast } from '../components/ui';

const STATUSES = ['all', 'new', 'open', 'assigned', 'in_progress', 'waiting_for_customer', 'resolved', 'closed', 'reopened'];
const WORKER_STATUSES = ['in_progress', 'waiting_for_customer', 'resolved'] as const;
const CHANNELS = ['all', 'instagram', 'whatsapp', 'facebook', 'email', 'web'];
const PRIORITIES = ['all', 'low', 'normal', 'high', 'urgent'];
const PRIORITY_ORDER: Record<string, number> = { urgent: 4, high: 3, normal: 2, low: 1 };
const QUEUES = [
  { id: 'all', label: '📥 All', icon: '' },
  { id: 'unassigned', label: '🆕 Unassigned', icon: '' },
  { id: 'mine', label: '🙋 Your Queue', icon: '' },
  { id: 'urgent', label: '🔴 Urgent', icon: '' },
];

export default function Inbox() {
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [customers, setCustomers] = useState<Record<number, Customer>>({});
  const [agents, setAgents] = useState<Agent[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [me, setMe] = useState<Agent | null>(null);
  const [active, setActive] = useState<number | null>(null);
  const [msgs, setMsgs] = useState<Message[]>([]);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [draft, setDraft] = useState('');
  const [search, setSearch] = useState('');
  const [fChannel, setFChannel] = useState('all');
  const [fStatus, setFStatus] = useState('all');
  const [fPriority, setFPriority] = useState('all');
  const [queue, setQueue] = useState('all');
  const [aAgent, setAAgent] = useState('');
  const [aTeam, setATeam] = useState('');
  const [aPriority, setAPriority] = useState('');
  const [aReason, setAReason] = useState('');
  const [loadingList, setLoadingList] = useState(true);
  const [loadingThread, setLoadingThread] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [ai, setAi] = useState<AiSuggestion | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [ticketCat, setTicketCat] = useState('');
  const [unread, setUnread] = useState(0);
  const [canNotify, setCanNotify] = useState(
    typeof Notification !== 'undefined' && Notification.permission === 'default'
  );
  const cursorRef = useRef(0);
  const activeRef = useRef<number | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const { toast, node: toastNode } = useToast();

  useEffect(() => { activeRef.current = active; }, [active]);
  useEffect(() => () => { document.title = 'FTY HelpDesk'; }, []);

  const loadList = useCallback(async () => {
    try {
      setErr(null);
      const [c, custs, ag, tm, myself] = await Promise.all([
        api<Conversation[]>('/conversations'),
        api<Customer[]>('/customers').catch(() => [] as Customer[]),
        api<Agent[]>('/agents').catch(() => [] as Agent[]),
        api<Team[]>('/teams').catch(() => [] as Team[]),
        api<Agent>('/auth/me').catch(() => null as unknown as Agent),
      ]);
      setConvs(c);
      const map: Record<number, Customer> = {};
      for (const cu of custs) map[cu.id] = cu;
      setCustomers(map);
      setAgents(ag);
      setTeams(tm);
      setMe(myself);
      // Mark everything seen up to now so only truly new messages notify.
      api<{ latest: number }>('/conversations/updates?since=0')
        .then(u => { cursorRef.current = u.latest; })
        .catch(() => {});
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to load inbox');
    } finally {
      setLoadingList(false);
    }
  }, []);

  const loadThread = useCallback(async (id: number) => {
    setLoadingThread(true);
    try {
      setMsgs(await api<Message[]>(`/conversations/${id}/messages`));
      setAi(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to load messages');
    } finally {
      setLoadingThread(false);
    }
  }, []);

  useEffect(() => { loadList(); }, [loadList]);
  useEffect(() => { if (me && me.role !== 'admin') setQueue('mine'); }, [me]);
  useEffect(() => { if (active != null) loadThread(active); }, [active, loadThread]);

  // Sync availability updates across sidebar and topbar
  useEffect(() => {
    function onAvailChange(e: Event) {
      const custom = e as CustomEvent<{ availability: string }>;
      if (custom.detail?.availability) {
        setMe(prev => prev ? { ...prev, availability: custom.detail.availability } : null);
      }
    }
    window.addEventListener('fty:availability-change', onAvailChange);
    return () => window.removeEventListener('fty:availability-change', onAvailChange);
  }, []);

  // Notification feed: new customer messages anywhere in the inbox
  const checkUpdates = useCallback(async () => {
    try {
      const u = await api<{ latest: number; messages: { id: number; conversation_id: number; content: string }[] }>(
        `/conversations/updates?since=${cursorRef.current}`
      );
      cursorRef.current = u.latest;
      const fresh = u.messages.filter(m => m.conversation_id !== activeRef.current);
      if (fresh.length > 0) {
        setUnread(n => {
          const v = n + fresh.length;
          document.title = `(${v}) FTY HelpDesk`;
          return v;
        });
        const last = fresh[fresh.length - 1];
        toast(`💬 New message in #${last.conversation_id}: ${last.content.slice(0, 80)}`);
        if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
          new Notification('FTY HelpDesk', { body: `${fresh.length} new customer message(s) — #${last.conversation_id}` });
        }
      }
    } catch { /* silent — next tick retries */ }
  }, [toast]);

  // Realtime: any socket event or poll tick refreshes list + open thread
  const refresh = useCallback(() => {
    api<Conversation[]>('/conversations').then(setConvs).catch(() => {});
    if (active != null) api<Message[]>(`/conversations/${active}/messages`).then(setMsgs).catch(() => {});
    checkUpdates();
  }, [active, checkUpdates]);
  const { live } = useInboxSocket(active, refresh);

  function selectConv(id: number) {
    setActive(id);
    setUnread(0);
    document.title = 'FTY HelpDesk';
    api<HistoryEntry[]>(`/conversations/${id}/history`).then(setHistory).catch(() => setHistory([]));
  }

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight });
  }, [msgs]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const list = convs.filter(c => {
      if (queue === 'unassigned' && c.assigned_agent_id != null) return false;
      if (queue === 'mine' && (me == null || c.assigned_agent_id !== me.id)) return false;
      if (queue === 'urgent' && c.priority !== 'urgent') return false;
      if (fChannel !== 'all' && c.channel !== fChannel) return false;
      if (fStatus !== 'all' && c.status !== fStatus) return false;
      if (fPriority !== 'all' && c.priority !== fPriority) return false;
      if (!q) return true;
      const cu = customers[c.customer_id];
      return `#${c.id}`.includes(q)
        || (cu?.name ?? '').toLowerCase().includes(q)
        || (cu?.email ?? '').toLowerCase().includes(q)
        || (c.assigned_team ?? '').toLowerCase().includes(q);
    });

    // Work top-down: 🔴 urgent first, then high, normal, low; then newest first
    return list.sort((a, b) => {
      const pDiff = (PRIORITY_ORDER[b.priority] || 0) - (PRIORITY_ORDER[a.priority] || 0);
      if (pDiff !== 0) return pDiff;
      return b.id - a.id;
    });
  }, [convs, customers, search, fChannel, fStatus, fPriority, queue, me]);

  // Automatically select the first (highest priority) conversation in the current queue
  useEffect(() => {
    if (filtered.length > 0) {
      if (active == null || !filtered.some(c => c.id === active)) {
        setActive(filtered[0].id);
      }
    }
  }, [filtered, active]);

  const counts = useMemo(() => ({
    unassigned: convs.filter(c => c.assigned_agent_id == null).length,
    mine: me ? convs.filter(c => c.assigned_agent_id === me.id).length : 0,
    urgent: convs.filter(c => c.priority === 'urgent').length,
  }), [convs, me]);

  const conv = convs.find(c => c.id === active) ?? null;
  const isAdmin = me?.role === 'admin';
  const visibleQueues = isAdmin ? QUEUES : [{ id: 'mine', label: '🙋 Your Queue', icon: '' }];
  const customer = conv ? customers[conv.customer_id] : undefined;
  const lastCustomerMsg = useMemo(
    () => [...msgs].reverse().find(m => m.sender_type === 'customer')?.content ?? '',
    [msgs]
  );

  async function patchSelfAvailability(availability: string) {
    if (!me) return;
    try {
      await api(`/agents/${me.id}`, { method: 'PATCH', body: JSON.stringify({ availability }) });
      setMe(prev => prev ? { ...prev, availability } : null);
      window.dispatchEvent(new CustomEvent('fty:availability-change', { detail: { availability } }));
      if (availability === 'away') {
        toast('🟡 Status set to Away (busy) — no new conversations will be routed to you.');
      } else if (availability === 'offline') {
        toast('🔴 Status set to Offline (done) — routing paused.');
      } else {
        toast('🟢 Status set to Available — new conversations will be routed to you.');
      }
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to update availability');
    }
  }

  async function send(nextStatus?: string) {
    if (active == null || !draft.trim() || sending) return;
    const text = draft.trim();
    setDraft('');
    setSending(true);
    try {
      // Optimistic bubble
      setMsgs(m => [...m, { id: -Date.now(), conversation_id: active, sender_type: 'agent', sender_id: 'you', content: text }]);
      const saved = await api<Message>(`/conversations/${active}/messages`, {
        method: 'POST',
        body: JSON.stringify({ sender_type: 'agent', content: text }),
      });
      setMsgs(m => m.map(x => (x.id < 0 ? saved : x)));

      // Move status as you go
      const targetStatus = nextStatus || (conv && ['new', 'open', 'assigned'].includes(conv.status) ? 'in_progress' : undefined);
      if (targetStatus && conv && conv.status !== targetStatus) {
        await api(`/conversations/${conv.id}/status?status=${targetStatus}`, { method: 'PATCH' });
        setConvs(prev => prev.map(c => c.id === conv.id ? { ...c, status: targetStatus } : c));
        toast(`Status moved to ${targetStatus.replace(/_/g, ' ')}`);
      }
      loadList();
    } catch (e) {
      setDraft(text);
      toast(e instanceof Error ? e.message : 'Send failed');
    } finally {
      setSending(false);
    }
  }

  async function assign() {
    if (!conv) return;
    const q = new URLSearchParams();
    if (aAgent) q.set('agent_id', aAgent);
    if (aTeam) q.set('team', aTeam);
    if (aPriority) q.set('priority', aPriority);
    if (aReason.trim()) q.set('reason', aReason.trim());
    try {
      await api(`/conversations/${conv.id}/assign?${q.toString()}`, { method: 'PATCH' });
      toast(aAgent || aTeam ? 'Conversation assigned' : 'Updated');
      setAReason('');
      loadList();
      selectConv(conv.id);
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Assign failed');
    }
  }

  async function clearAssign() {
    if (!conv) return;
    await api(`/conversations/${conv.id}/assign?clear=true`, { method: 'PATCH' });
    toast('Sent back to Unassigned queue');
    setAAgent('');
    loadList();
    selectConv(conv.id);
  }

  async function setConvStatus(status: string) {
    if (!conv) return;
    try {
      await api(`/conversations/${conv.id}/status?status=${status}`, { method: 'PATCH' });
      setConvs(prev => prev.map(c => c.id === conv.id ? { ...c, status } : c));
      toast(`Status moved to ${status.replace(/_/g, ' ')}`);
      loadList();
      selectConv(conv.id);
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Status update failed');
    }
  }

  async function createTicket() {
    if (!conv) return;
    await api('/tickets', {
      method: 'POST',
      body: JSON.stringify({ conversation_id: conv.id, category: ticketCat || 'general', priority: conv.priority }),
    });
    setTicketCat('');
    toast(`Ticket created for #${conv.id}`);
  }

  async function askAi() {
    if (!lastCustomerMsg) { toast('No customer message to analyze yet'); return; }
    setAiLoading(true);
    try {
      setAi(await api<AiSuggestion>(`/ai/suggest?content=${encodeURIComponent(lastCustomerMsg)}`, { method: 'POST' }));
    } catch (e) {
      toast(e instanceof Error ? e.message : 'AI suggestion failed');
    } finally {
      setAiLoading(false);
    }
  }

  return (
    <div>
      {toastNode}
      <div className="topbar" style={{ margin: '-20px -20px 16px' }}>
        <h1>📨 Inbox</h1>
        <span className="small muted"><span className={`live-dot ${live ? '' : 'off'}`} /> {live ? 'Live' : 'Polling'}</span>
        {unread > 0 && <span className="badge b-high">{unread} new</span>}
        {canNotify && (
          <button className="btn" style={{ padding: '4px 10px' }} onClick={async () => {
            const p = await Notification.requestPermission();
            setCanNotify(p === 'default');
            if (p === 'granted') toast('Browser notifications enabled');
          }}>
            🔔 Notify
          </button>
        )}
        {me && (
          <div className="avail-widget" title="Your availability status: controls whether new inquiries are routed to you">
            <span className={`status-dot ${me.availability || 'available'}`} />
            <select
              className="avail-select"
              value={me.availability || 'available'}
              onChange={e => patchSelfAvailability(e.target.value)}
              title="Set 🟡 Away when busy, 🔴 Offline when done — nothing new gets routed to you."
            >
              <option value="available">🟢 Available</option>
              <option value="away">🟡 Away (Busy)</option>
              <option value="offline">🔴 Offline (Done)</option>
            </select>
            {me.availability && me.availability !== 'available' && (
              <span className="paused-notice">
                {me.availability === 'away' ? '🟡 Away' : '🔴 Offline'} · routing paused
              </span>
            )}
          </div>
        )}
        <span className="grow" />
        <input className="input" style={{ maxWidth: 220 }} placeholder="🔍 Search name, email, #id…" value={search} onChange={e => setSearch(e.target.value)} />
        <select className="select" value={fChannel} onChange={e => setFChannel(e.target.value)}>
          {CHANNELS.map(c => <option key={c} value={c}>{c === 'all' ? 'All channels' : c}</option>)}
        </select>
        <select className="select" value={fStatus} onChange={e => setFStatus(e.target.value)}>
          {(isAdmin ? STATUSES : ['all', ...WORKER_STATUSES]).map(s => (
            <option key={s} value={s}>{s === 'all' ? 'All statuses' : s.replace(/_/g, ' ')}</option>
          ))}
        </select>
        <select className="select" value={fPriority} onChange={e => setFPriority(e.target.value)}>
          {PRIORITIES.map(p => <option key={p} value={p}>{p === 'all' ? 'All priorities' : p}</option>)}
        </select>
      </div>
      <div className="toolbar">
        {visibleQueues.map(qb => {
          const n = qb.id === 'unassigned' ? counts.unassigned : qb.id === 'mine' ? counts.mine : qb.id === 'urgent' ? counts.urgent : convs.length;
          return (
            <button key={qb.id} className={`chip ${queue === qb.id ? 'active' : ''}`} onClick={() => setQueue(qb.id)}>
              {qb.label} <b>{n}</b>
            </button>
          );
        })}
      </div>

      {err && <ErrorBanner message={err} onRetry={loadList} />}

      <div className="inbox">
        <div className="conv-list">
          {loadingList ? <SkeletonList /> : filtered.length === 0 ? (
            <EmptyState icon="📭" title="No conversations" hint="Try clearing filters — new channel messages will appear here live." />
          ) : filtered.map(c => {
            const cu = customers[c.customer_id];
            return (
              <div
                key={c.id}
                className={`conv-item ${c.priority === 'urgent' ? 'is-urgent' : ''} ${active === c.id ? 'active' : ''}`}
                onClick={() => selectConv(c.id)}
              >
                <div className="row">
                  <Avatar name={cu?.name ?? `#${c.customer_id}`} />
                  <div className="grow" style={{ minWidth: 0 }}>
                    <div className="title">{cu?.name ?? `Customer #${c.customer_id}`} <ChannelIcon channel={c.channel} /></div>
                    <div className="small muted">#{c.id} · {c.channel} · {c.assigned_team ?? 'unassigned'}</div>
                  </div>
                </div>
                <div className="row" style={{ marginTop: 6, justifyContent: 'space-between' }}>
                  <Badge value={c.status} />
                  {c.priority === 'urgent' ? (
                    <span className="priority-tag-urgent">🔴 Urgent</span>
                  ) : (
                    <Badge value={c.priority} />
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <div className="thread">
          {!conv ? (
            <EmptyState icon="💬" title="Select a conversation" hint="Pick a thread on the left to read and reply." />
          ) : (
            <>
              <div className="thread-head row" style={{ flexWrap: 'wrap', gap: 8 }}>
                <div>
                  <b>#{conv.id}</b> {customer?.name && <span>· {customer.name}</span>}{' '}
                  <span className="muted small">{customer?.email ?? ''}</span>
                </div>
                <span className="grow" />
                <Badge value={conv.channel} />
                {conv.priority === 'urgent' ? (
                  <span className="priority-tag-urgent">🔴 Urgent</span>
                ) : (
                  <Badge value={conv.priority} />
                )}

                {/* Status Stepper: In progress → Waiting for customer → Resolved */}
                <div className="status-stepper" title="Move status as you go">
                  <button
                    type="button"
                    className={`status-step step-in_progress ${conv.status === 'in_progress' ? 'active' : ''}`}
                    onClick={() => setConvStatus('in_progress')}
                    title="Mark In progress"
                  >
                    ⚡ In progress
                  </button>
                  <button
                    type="button"
                    className={`status-step step-waiting_for_customer ${conv.status === 'waiting_for_customer' ? 'active' : ''}`}
                    onClick={() => setConvStatus('waiting_for_customer')}
                    title="Mark Waiting for customer"
                  >
                    ⏳ Waiting for customer
                  </button>
                  <button
                    type="button"
                    className={`status-step step-resolved ${conv.status === 'resolved' ? 'active' : ''}`}
                    onClick={() => setConvStatus('resolved')}
                    title="Mark Resolved"
                  >
                    ✅ Resolved
                  </button>
                </div>

                {/* Drop down list pruned of unnecessary statuses (new, open, assigned, reopened, closed) */}
                <select
                  className="select"
                  style={{ maxWidth: 180 }}
                  value={conv.status}
                  onChange={e => setConvStatus(e.target.value)}
                  title="Workflow status"
                >
                  {!WORKER_STATUSES.includes(conv.status as any) && (
                    <option value={conv.status} disabled>Current: {conv.status.replace(/_/g, ' ')}</option>
                  )}
                  <option value="in_progress">⚡ In progress</option>
                  <option value="waiting_for_customer">⏳ Waiting for customer</option>
                  <option value="resolved">✅ Resolved</option>
                </select>
              </div>
              <div className="thread-body" ref={bodyRef}>
                {loadingThread ? <SkeletonList rows={3} /> : msgs.length === 0 ? (
                  <EmptyState icon="✉️" title="No messages yet" hint="Be the first to reply below." />
                ) : msgs.map(m => (
                  <div key={m.id} className={`msg msg-${m.sender_type}`}>
                    <div className="who">{m.sender_type}{m.sender_id ? ` · ${m.sender_id}` : ''}</div>
                    {m.content}
                  </div>
                ))}
                {ai && (
                  <div className="ai-box">
                    <b>🤖 AI suggestion</b> <span className="small muted">(intent: {ai.intent}, confidence: {Math.round(ai.confidence * 100)}%{ai.requires_human ? ' — human review required' : ''})</span>
                    {ai.suggestions.map((s, i) => (
                      <div key={i} style={{ marginTop: 6 }}>
                        <b>{s.title}</b>
                        <p style={{ margin: '4px 0' }}>{s.body}</p>
                        <button className="btn" style={{ padding: '4px 10px' }} onClick={() => setDraft(s.body)}>Use as reply</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div className="composer">
                <input
                  className="input" value={draft} onChange={e => setDraft(e.target.value)}
                  placeholder="Type response… (Enter to send)" disabled={sending}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
                />
                <button className="btn" onClick={askAi} disabled={aiLoading} title="Suggest a reply from the knowledge base">
                  {aiLoading ? '…' : '🤖 Suggest'}
                </button>
                <button
                  className="btn"
                  onClick={() => send('waiting_for_customer')}
                  disabled={sending || !draft.trim()}
                  title="Send reply and move status to Waiting for customer"
                >
                  ⏳ Reply & Wait
                </button>
                <button className="btn btn-primary" onClick={() => send()} disabled={sending || !draft.trim()}>
                  {sending ? 'Sending…' : 'Send'}
                </button>
              </div>
            </>
          )}
        </div>

        {conv && (
          <div className="side-panel">
            <div className="card">
              <b>👤 Customer</b>
              <div className="small" style={{ marginTop: 6 }}>
                <div>{customer?.name ?? `Customer #${conv.customer_id}`}</div>
                <div className="muted">{customer?.email ?? 'no email'}</div>
                <div className="muted">{customer?.phone ?? 'no phone'}</div>
              </div>
            </div>
            {isAdmin && (
            <div className="card">
              <b>🔀 Assignment</b>
              <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
                <label className="small muted">Team</label>
                <select className="select" value={aTeam} onChange={e => { setATeam(e.target.value); setAAgent(''); }}>
                  <option value="">— keep —</option>
                  {teams.map(t => <option key={t.id} value={t.name}>{t.name}</option>)}
                </select>
                <label className="small muted">Worker</label>
                <select className="select" value={aAgent} onChange={e => setAAgent(e.target.value)}>
                  <option value="">— keep —</option>
                  {(aTeam ? (teams.find(t => t.name === aTeam)?.members ?? []) : agents).map((a: Agent | Team['members'][number]) => {
                    const id = 'user_id' in a ? a.user_id : a.id;
                    const nm = a.name;
                    const extra = 'active' in a ? ` · ${a.active} active` : '';
                    return <option key={id} value={id}>{nm}{extra}</option>;
                  })}
                </select>
                <label className="small muted">Priority</label>
                <select className="select" value={aPriority} onChange={e => setAPriority(e.target.value)}>
                  <option value="">— keep —</option>
                  {PRIORITIES.filter(p => p !== 'all').map(p => <option key={p} value={p}>{p}</option>)}
                </select>
                <input className="input" placeholder="Reason (optional)…" value={aReason} onChange={e => setAReason(e.target.value)} />
                <div className="row">
                  <button className="btn btn-primary grow" onClick={assign}>Assign</button>
                  <button className="btn" onClick={clearAssign} title="Send back to Unassigned queue">Clear</button>
                </div>
                <span className="small muted">
                  {conv.assigned_agent_id
                    ? `Now: ${agents.find(a => a.id === conv.assigned_agent_id)?.name ?? `#${conv.assigned_agent_id}`}`
                    : 'Unassigned — in the manager review queue.'}
                </span>
              </div>
            </div>
            )}
            <div className="card">
              <b>📜 History</b>
              <div className="timeline">
                {history.length === 0 && <div className="small muted" style={{ marginTop: 6 }}>No assignment events yet.</div>}
                {history.map(h => (
                  <div key={h.id} className="t-item">
                    <div className="small"><b>{h.action.replace(/_/g, ' ')}</b> · {h.assigned_by}</div>
                    {(h.detail || h.reason) && (
                      <div className="small muted">{[h.detail, h.reason].filter(Boolean).join(' — ')}</div>
                    )}
                    <div className="small muted">
                      {h.created_at ? new Date(h.created_at).toLocaleString() : ''}
                      {h.to_user_id ? ` → ${agents.find(a => a.id === h.to_user_id)?.name ?? `#${h.to_user_id}`}` : ''}
                      {h.to_team ? ` · ${h.to_team}` : ''}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="card">
              <b>🎫 New ticket</b>
              <div className="row" style={{ marginTop: 8 }}>
                <input className="input" placeholder="Category…" value={ticketCat} onChange={e => setTicketCat(e.target.value)} />
                <button className="btn" onClick={createTicket}>Create</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
