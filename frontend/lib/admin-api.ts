// Management API client for admin UI.
//
// All requests go through the same-origin Next.js proxy at /api/admin-proxy.
// The proxy injects X-Admin-Token from server-side env (ADMIN_API_TOKEN) and
// is gated by middleware.ts on the ADMIN_PASSWORD session cookie. The token
// never reaches the browser bundle.
//
// Backend FastAPI URL is configured server-side via ADMIN_API_URL — see
// frontend/app/api/admin-proxy/[...path]/route.ts.
import type { ModelCatalog } from './model-catalog';

const API_BASE = '/api/admin-proxy';

export interface Profile {
  id: string;
  name: string;
  display_name: string;
  description: string;
  is_active: boolean;
  is_dirty: boolean;
  is_live: boolean;
  last_deployed_at: string | null;
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
  agent_mode: 'realtime' | 'pipeline' | null;
}

export interface SessionsListPage {
  items: SessionSummary[];
  total: number;
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

export type ToolExecutionMode = 'dry_run' | 'live';

export interface ProfileTestRunSummary {
  id: string;
  profile_id: string;
  status: 'created' | 'running' | 'completed' | 'failed' | 'cancelled';
  tool_execution_mode: ToolExecutionMode;
  user_message: string;
  profile_config_hash: string;
  profile_snapshot_at: string;
  final_summary: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface ProfileTestRunEvent {
  id: number;
  seq: number;
  event_type: string;
  severity: 'info' | 'warning' | 'error' | string;
  timestamp: string;
  payload: Record<string, unknown>;
}

export interface ProfileTestRunDetail extends ProfileTestRunSummary {
  events: ProfileTestRunEvent[];
}

export interface ProfileTestRunsListPage {
  items: ProfileTestRunSummary[];
  total: number;
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

async function requestWithTotal<T>(path: string): Promise<{ items: T; total: number }> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    cache: 'no-store',
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text || res.statusText}`);
  }
  const items = (await res.json()) as T;
  const total = parseInt(res.headers.get('X-Total-Count') || '0', 10);
  return { items, total: Number.isFinite(total) ? total : 0 };
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}`;
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
  reactivate: (id: string) =>
    request<Profile>(`/api/profiles/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ is_active: true }),
    }),
};

// ── Tools registry ─────────────────────────────────────────

export const toolsApi = {
  list: () => request<{ tools: string[] }>('/api/tools').then((r) => r.tools),
};

// ── Model defaults (read-only source of truth) ─────────────

export const modelDefaultsApi = {
  get: () => request<ModelCatalog>('/api/model-defaults'),
};

// ── Sessions ───────────────────────────────────────────────

export const sessionsApi = {
  list: async (params?: {
    profile_id?: string;
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<SessionsListPage> => {
    const qs = new URLSearchParams();
    if (params?.profile_id) qs.set('profile_id', params.profile_id);
    if (params?.status) qs.set('status', params.status);
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    const suffix = qs.toString() ? `?${qs}` : '';
    const { items, total } = await requestWithTotal<SessionSummary[]>(`/api/sessions${suffix}`);
    return { items, total };
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

// ── Profile text test runs ───────────────────────────────────────

export const testRunsApi = {
  create: (profileId: string, data: { message: string; tool_execution_mode?: ToolExecutionMode }) =>
    request<ProfileTestRunDetail>(`/api/profiles/${profileId}/test-runs`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  list: async (
    profileId: string,
    params?: { limit?: number; offset?: number }
  ): Promise<ProfileTestRunsListPage> => {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    const suffix = qs.toString() ? `?${qs}` : '';
    const { items, total } = await requestWithTotal<ProfileTestRunSummary[]>(
      `/api/profiles/${profileId}/test-runs${suffix}`
    );
    return { items, total };
  },
  get: (profileId: string, runId: string) =>
    request<ProfileTestRunDetail>(`/api/profiles/${profileId}/test-runs/${runId}`),
};

// ── Deploy (LiveKit Cloud) ────────────────────────────────

export interface CloudAgent {
  ID: string;
  Version: string;
  Region: string;
  Status: string;
  CPU: string;
  Mem: string;
  Replicas: string;
  'Deployed At': string;
}

export interface CloudSecret {
  Name: string;
  'Created At': string;
  'Updated At': string;
}

export interface DeployStatus {
  agent: CloudAgent | null;
  secrets: CloudSecret[];
  raw: { status: string; secrets: string };
}

export interface DeployLogs {
  lines: string[];
  log_type: 'deploy' | 'build';
}

export interface DeployResult {
  status: string;
  mode: 'single' | 'all' | 'secret-only';
  exported_profiles?: string[];
  profiles_marked_clean?: number;
  active_profile?: string;
  stdout?: unknown;
}

export interface DeployProgress {
  is_deploying: boolean;
  profile_name: string | null;
  elapsed_s: number | null;
  phase: 'build' | 'activate' | null;
  last_result: { status: 'ok' | 'error'; active_profile?: string; error?: string } | null;
}

export const deployApi = {
  status: () => request<DeployStatus>('/api/deploy/status'),
  logs: (tail = 200, logType: 'deploy' | 'build' = 'deploy') =>
    request<DeployLogs>(`/api/deploy/logs?tail=${tail}&log_type=${logType}`),
  progress: () => request<DeployProgress>('/api/deploy/progress'),
  deploy: (profileId?: string) =>
    request<DeployResult>('/api/deploy/deploy', {
      method: 'POST',
      body: JSON.stringify(profileId ? { profile_id: profileId } : {}),
    }),
  switchProfile: (profileId: string) =>
    request<DeployResult>('/api/deploy/switch-profile', {
      method: 'POST',
      body: JSON.stringify({ profile_id: profileId }),
    }),
};

// ── Stats ──────────────────────────────────────────────────

export const statsApi = {
  profiles: () => request<ProfileStats[]>('/api/stats/profiles'),
  daily: (profileId?: string) => {
    const suffix = profileId ? `?profile_id=${profileId}` : '';
    return request<DailyStats[]>(`/api/stats/daily${suffix}`);
  },
};

// ── Local connect-mode test ─────────────────────────────────

export interface TestStartResponse {
  room: string;
  pid: number;
  log_path: string;
}

export const testApi = {
  start: (profile: string) =>
    request<TestStartResponse>('/api/test/start', {
      method: 'POST',
      body: JSON.stringify({ profile }),
    }),
  stop: (room: string) =>
    request<{ ok: boolean }>(`/api/test/stop/${encodeURIComponent(room)}`, {
      method: 'DELETE',
    }),
};
