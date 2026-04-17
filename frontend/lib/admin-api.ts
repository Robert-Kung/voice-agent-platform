// Management API client for admin UI.
// Base URL is configurable via NEXT_PUBLIC_ADMIN_API_URL (defaults to localhost:8080).

const API_BASE = process.env.NEXT_PUBLIC_ADMIN_API_URL || 'http://localhost:8080';

export interface Profile {
  id: string;
  name: string;
  display_name: string;
  description: string;
  is_active: boolean;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface SessionSummary {
  id: string;
  room_name: string;
  profile_id: string | null;
  participant_identity: string;
  started_at: string;
  ended_at: string | null;
  status: 'running' | 'completed' | 'failed';
  shutdown_reason: string;
  duration_seconds: number | null;
  total_cost_usd: number | null;
}

export interface SessionDetail extends SessionSummary {
  raw_report: Record<string, unknown>;
}

export interface SessionEvent {
  id: number;
  seq: number;
  event_type: string;
  timestamp: string;
  payload: Record<string, unknown>;
}

export interface ProfileStats {
  profile_id: string | null;
  profile_name: string | null;
  session_count: number;
  total_duration_seconds: number;
  total_cost_usd: number;
  avg_duration_seconds: number;
}

export interface DailyStats {
  date: string;
  session_count: number;
  total_duration_seconds: number;
  total_cost_usd: number;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
    cache: 'no-store',
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text || res.statusText}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Profiles ───────────────────────────────────────────────

export const profilesApi = {
  list: (activeOnly = true) => request<Profile[]>(`/api/profiles?active_only=${activeOnly}`),
  get: (id: string) => request<Profile>(`/api/profiles/${id}`),
  create: (data: {
    name: string;
    display_name?: string;
    description?: string;
    config?: Record<string, unknown>;
    is_active?: boolean;
  }) =>
    request<Profile>('/api/profiles', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  update: (
    id: string,
    data: Partial<{
      display_name: string;
      description: string;
      is_active: boolean;
      config: Record<string, unknown>;
    }>
  ) =>
    request<Profile>(`/api/profiles/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  deactivate: (id: string) => request<Profile>(`/api/profiles/${id}`, { method: 'DELETE' }),
};

// ── Sessions ───────────────────────────────────────────────

export const sessionsApi = {
  list: (params?: { profile_id?: string; status?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.profile_id) qs.set('profile_id', params.profile_id);
    if (params?.status) qs.set('status', params.status);
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    const suffix = qs.toString() ? `?${qs}` : '';
    return request<SessionSummary[]>(`/api/sessions${suffix}`);
  },
  get: (id: string) => request<SessionDetail>(`/api/sessions/${id}`),
  getEvents: (id: string, eventType?: string) => {
    const suffix = eventType ? `?event_type=${eventType}` : '';
    return request<SessionEvent[]>(`/api/sessions/${id}/events${suffix}`);
  },
  getLivekitLink: (id: string) =>
    request<{ session_id: string; room_name: string; url: string; note: string }>(
      `/api/sessions/${id}/livekit-link`
    ),
};

// ── Stats ──────────────────────────────────────────────────

export const statsApi = {
  profiles: () => request<ProfileStats[]>('/api/stats/profiles'),
  daily: (profileId?: string) => {
    const suffix = profileId ? `?profile_id=${profileId}` : '';
    return request<DailyStats[]>(`/api/stats/daily${suffix}`);
  },
};
