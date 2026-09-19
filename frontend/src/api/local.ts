import type { Agent, Conversation, Customer, KBArticle, Message, Rule, Team, Ticket } from './client';

type User = Agent & { password: string };
type Store = { users: User[]; customers: Customer[]; conversations: Conversation[]; messages: Message[]; tickets: Ticket[]; knowledge: KBArticle[]; rules: Rule[]; teams: Team[]; channels: any[] };
const KEY = 'fty_helpdesk_local_v1'; const USER = 'fty_local_user_id';
const empty = (): Store => ({ users: [{ id: 1, name: 'Administrator', email: 'admin@fty.local', password: 'admin123', role: 'admin', team: null, availability: 'available', max_active: 10 }], customers: [], conversations: [], messages: [], tickets: [], knowledge: [], rules: [], teams: [], channels: ['instagram', 'whatsapp', 'facebook', 'email', 'web'].map(channel => ({ channel, connected: false, has_token: false, oauth_ready: false })) });
const load = () => { try { return JSON.parse(localStorage.getItem(KEY) || '') as Store; } catch { const s = empty(); localStorage.setItem(KEY, JSON.stringify(s)); return s; } };
const save = (s: Store) => localStorage.setItem(KEY, JSON.stringify(s));
const next = (xs: { id: number }[]) => Math.max(0, ...xs.map(x => x.id)) + 1;
const payload = (i?: RequestInit): any => { try { return i?.body ? JSON.parse(String(i.body)) : {}; } catch { return {}; } };
const current = (s: Store) => { const u = s.users.find(x => x.id === Number(localStorage.getItem(USER))); if (!u) throw new Error('Please log in again.'); return u; };
const safe = (u: User): Agent => { const { password, ...a } = u; return a; };

export function loginLocal(email: string, password: string) { const u = load().users.find(x => x.email.toLowerCase() === email.toLowerCase() && x.password === password); if (!u) return false; localStorage.setItem(USER, String(u.id)); localStorage.setItem('fty_token', `local-${u.id}`); return true; }
export function logoutLocal() { localStorage.removeItem(USER); }

export async function localApi<T>(raw: string, init?: RequestInit): Promise<T> {
  const [path, search = ''] = raw.split('?'); const q = new URLSearchParams(search); const method = (init?.method || 'GET').toUpperCase(); const s = load(); const data = payload(init); let out: any = {};
  if (path === '/auth/me') out = safe(current(s));
  else if (path === '/agents') out = s.users.map(safe);
  else if (path === '/customers') { if (method === 'GET') out = s.customers; else { current(s); const x = { id: next(s.customers), name: data.name || null, email: data.email || null, phone: data.phone || null }; s.customers.push(x); out = x; } }
  else if (path === '/conversations') out = s.conversations;
  else if (path === '/tickets') { if (method === 'GET') out = s.tickets; else { const x = { id: next(s.tickets), conversation_id: Number(data.conversation_id), category: data.category || null, status: 'in_progress', priority: data.priority || 'normal', assigned_to: null }; s.tickets.push(x); out = x; } }
  else if (path === '/knowledge/categories') out = [...new Set(s.knowledge.map(x => x.category))];
  else if (path === '/knowledge') { if (method === 'GET') { const term = (q.get('q') || '').toLowerCase(), cat = q.get('category'); out = s.knowledge.filter(x => (!cat || x.category === cat) && (!term || `${x.title} ${x.body}`.toLowerCase().includes(term))); } else { const x = { id: next(s.knowledge), category: data.category || 'General', title: data.title, body: data.body }; s.knowledge.push(x); out = x; } }
  else if (path === '/automation') { if (method === 'GET') out = s.rules; else { const x = { id: next(s.rules), name: data.name, trigger: data.trigger, conditions: data.conditions || {}, actions: data.actions || {}, enabled: true }; s.rules.push(x); out = x; } }
  else if (path === '/automation/sla-check') out = { conversations_escalated: 0, tickets_escalated: 0 };
  else if (path === '/teams') { if (method === 'GET') out = s.teams; else { const x = { id: next(s.teams), name: data.name, description: null, members: [] }; s.teams.push(x); out = x; } }
  else if (path === '/channels') out = s.channels;
  else if (path === '/users') { const x: User = { id: next(s.users), name: data.name, email: data.email, password: data.password, role: data.role || 'agent', team: null, availability: 'available', max_active: 10 }; s.users.push(x); out = safe(x); }
  else if (path === '/analytics/overview') { const open = s.conversations.filter(x => !['resolved', 'closed'].includes(x.status)); out = { totals: { conversations: s.conversations.length, messages: s.messages.length, tickets: s.tickets.length, open_conversations: open.length, unassigned: open.filter(x => x.assigned_agent_id == null).length, urgent: open.filter(x => x.priority === 'urgent').length }, avg_first_response_min: null, avg_resolution_hours: null, volume_14d: Array.from({ length: 14 }, (_, i) => ({ day: new Date(Date.now() - (13 - i) * 86400000).toISOString().slice(0, 10), conversations: 0, messages: 0 })), by_channel: {}, by_team: {}, tickets_by_category: {}, agents: s.users.map(u => ({ id: u.id, name: u.name, active: 0, resolved_tickets: 0, avg_response_min: null })) }; }
  else if (path === '/conversations/updates') out = { latest: Math.max(0, ...s.messages.map(x => x.id)), messages: [] };
  else if (path.startsWith('/conversations/')) { const p = path.split('/'), c = s.conversations.find(x => x.id === Number(p[2])); if (!c) throw new Error('Conversation not found'); if (p[3] === 'messages') { if (method === 'GET') out = s.messages.filter(x => x.conversation_id === c.id); else { const x = { id: next(s.messages), conversation_id: c.id, sender_type: data.sender_type || 'agent', sender_id: String(current(s).id), content: data.content }; s.messages.push(x); out = x; } } else if (p[3] === 'history') out = []; else if (p[3] === 'status') { c.status = q.get('status') || c.status; out = { ok: true }; } else if (p[3] === 'assign') { c.assigned_agent_id = q.get('clear') ? null : Number(q.get('agent_id')) || c.assigned_agent_id; c.assigned_team = q.get('team') || c.assigned_team; c.priority = q.get('priority') || c.priority; out = { ok: true }; } }
  else if (path.startsWith('/tickets/')) { const x = s.tickets.find(t => t.id === Number(path.split('/')[2])); if (x) { x.status = q.get('status') || x.status; x.assigned_to = q.has('assigned_to') ? Number(q.get('assigned_to')) || null : x.assigned_to; out = { ok: true }; } }
  else if (path.startsWith('/knowledge/')) { const x = s.knowledge.find(t => t.id === Number(path.split('/')[2])); if (method === 'DELETE') s.knowledge = s.knowledge.filter(t => t !== x); else if (x) Object.assign(x, data); out = x || {}; }
  else if (path.startsWith('/automation/')) { const x = s.rules.find(t => t.id === Number(path.split('/')[2])); if (method === 'DELETE') s.rules = s.rules.filter(t => t !== x); else if (x) Object.assign(x, data); out = x || {}; }
  else if (path.startsWith('/agents/') || path.startsWith('/users/')) { const x = s.users.find(t => t.id === Number(path.split('/')[2])); if (x) Object.assign(x, data); out = x ? safe(x) : {}; }
  else if (path === '/ai/suggest') out = { intent: 'general', confidence: 0, requires_human: true, suggestions: [] };
  save(s); return out as T;
}
