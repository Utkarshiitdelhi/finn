export const API_URL = (process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function req<T>(path: string, init?: RequestInit, timeoutMs = 70000): Promise<T> {
  // Render's free tier sleeps: the first request can take ~60 s, so the timeout is generous.
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(API_URL + path, {
      ...init,
      signal: ctrl.signal,
      headers: init?.body instanceof FormData ? init?.headers : { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    });
    if (!r.ok) {
      let msg = r.statusText;
      try {
        msg = (await r.json()).detail || msg;
      } catch {}
      throw new ApiError(r.status, String(msg));
    }
    return (await r.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

export type Tier = 'S' | 'A' | 'B' | 'C';

export interface ResultRow {
  metric: string;
  q: number | null;
  pq: number | null;
  yq: number | null;
  qoq_pct: number | null;
  yoy_pct: number | null;
  derived?: boolean;
}

export interface FeedCard {
  id: string;
  ticker: string;
  company: string;
  tier: Tier;
  score: number;
  category: string;
  category_label: string;
  headline: string;
  summary: string;
  filed_at: string;
  why: string[];
  sector: string;
  card: any;
  price_move: { pct?: number; vol_ratio?: number; day?: string };
  source_url: string;
  pinned: boolean;
  subject?: string;
  text?: string;
}

export interface Feed {
  window_hours: number;
  S: FeedCard[];
  A: FeedCard[];
  B: FeedCard[];
  C: { count: number; by_category: Record<string, number>; items: { id: string; ticker: string; headline: string; category_label: string }[] };
  pinned: FeedCard[];
  counts: Record<Tier, number>;
}

export interface Rule {
  id: number;
  spec: any;
  label: string;
  source: string;
  active: boolean;
  created_at: string;
  last_hit: { message: string; at: string } | null;
}

export interface Alert {
  id: number;
  rule: string;
  message: string;
  payload: any;
  at: string;
}

export interface AssistantReply {
  intent: 'ask' | 'command' | 'go' | 'none' | 'error';
  say: string;
  heard?: string;
  route?: string;
  answer?: string;
  cites?: any[];
  rule?: { spec: any; label: string };
  error?: string;
  closest?: any;
  closest_label?: string;
}

export const api = {
  health: () => req<{ ok: boolean }>('/health'),
  feed: (window: string, hours?: number) => req<Feed>(`/feed?window=${window}${hours ? `&hours=${hours}` : ''}`),
  filing: (id: string) => req<FeedCard>(`/filing/${encodeURIComponent(id)}`),
  filingAction: (id: string, action: 'dismiss' | 'pin') => req(`/filing/${encodeURIComponent(id)}/${action}`, { method: 'POST' }),
  alerts: () => req<Alert[]>('/alerts'),
  rules: () => req<Rule[]>('/rules'),
  parseRule: (text: string) => req<{ spec?: any; label?: string; error?: string; closest?: any }>('/rules/parse', { method: 'POST', body: JSON.stringify({ text }) }),
  createRule: (spec: any, source = 'form') => req<Rule>('/rules', { method: 'POST', body: JSON.stringify({ spec, source }) }),
  toggleRule: (id: number, active: boolean) => req<Rule>(`/rules/${id}?active=${active}`, { method: 'PATCH' }),
  deleteRule: (id: number) => req(`/rules/${id}`, { method: 'DELETE' }),
  company: (ticker: string) => req<any>(`/company/${ticker}`),
  impact: (series: string) => req<any>(`/impact/${encodeURIComponent(series)}`),
  search: (q: string) => req<{ ticker: string; name: string; held: boolean }[]>(`/search?q=${encodeURIComponent(q)}`),
  portfolio: () => req<any>('/portfolio'),
  prefs: (body: any) => req('/portfolio/prefs', { method: 'PUT', body: JSON.stringify(body) }),
  star: (ticker: string) => req(`/portfolio/star/${ticker}`, { method: 'POST' }),
  assistant: (text: string, ctx: any) => req<AssistantReply>('/assistant', { method: 'POST', body: JSON.stringify({ text, ctx }) }),
  voice: (uri: string, ctx: any) => {
    const fd = new FormData();
    // React Native's FormData accepts {uri, name, type} file parts
    fd.append('audio', { uri, name: 'voice.m4a', type: 'audio/m4a' } as any);
    fd.append('ctx', JSON.stringify(ctx));
    return req<AssistantReply>('/assistant/voice', { method: 'POST', body: fd });
  },
  pushTest: () => req<{ sent: number }>('/push/test', { method: 'POST' }),
  registerPush: (token: string, platform: string) => req('/push/register', { method: 'POST', body: JSON.stringify({ token, platform }) }),
};
