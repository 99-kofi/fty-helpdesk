export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') || '';
const API = `${API_BASE}/api/v1`;

function authHeaders(): HeadersInit {
  const t = localStorage.getItem('fty_token');
  return t ? { Authorization: `Bearer ${t}`, 'Content-Type': 'application/json' } : { 'Content-Type': 'application/json' };
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, { ...init, headers: { ...authHeaders(), ...(init?.headers || {}) } });
  if (res.status === 401) {
    localStorage.removeItem('fty_token');
    throw new ApiError(401, 'Session expired — please log in again.');
  }
  if (!res.ok) throw new ApiError(res.status, await res.text());
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export function isLoggedIn(): boolean {
  return !!localStorage.getItem('fty_token');
}

export function logout(): void {
  localStorage.removeItem('fty_token');
  location.hash = '#/login';
  location.reload();
}

export type Conversation = {
  id: number; customer_id: number; channel: string; status: string;
  priority: string; assigned_agent_id: number | null; assigned_team: string | null;
};
export type Message = {
  id: number; conversation_id: number; sender_type: string;
  sender_id: string | null; content: string;
};
export type Ticket = {
  id: number; conversation_id: number; category: string | null;
  status: string; priority: string; assigned_to: number | null;
};
export type Customer = { id: number; name: string | null; email: string | null; phone: string | null };
export type Agent = { id: number; name: string; email: string; role: string; team: string | null; availability?: string; max_active?: number };
export type AiSuggestion = {
  intent: string; confidence: number; requires_human: boolean;
  suggestions: { title: string; body: string }[];
};
export type TeamMember = { user_id: number; name: string; availability: string; active: number };
export type Team = { id: number; name: string; description: string | null; members: TeamMember[] };
export type HistoryEntry = {
  id: number; action: string; from_user_id: number | null; to_user_id: number | null;
  from_team: string | null; to_team: string | null; detail: string | null;
  reason: string | null; assigned_by: string; created_at: string | null;
};
export type Rule = {
  id: number; name: string; trigger: string;
  conditions: Record<string, unknown>; actions: Record<string, unknown>; enabled: boolean;
};
export type KBArticle = { id: number; category: string; title: string; body: string };
export type Overview = {
  totals: { conversations: number; messages: number; tickets: number; open_conversations: number; unassigned: number; urgent: number };
  avg_first_response_min: number | null;
  avg_resolution_hours: number | null;
  volume_14d: { day: string; conversations: number; messages: number }[];
  by_channel: Record<string, number>;
  by_team: Record<string, number>;
  tickets_by_category: Record<string, number>;
  agents: { id: number; name: string; active: number; resolved_tickets: number; avg_response_min: number | null }[];
};
