'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { formatDate, profilesApi, sessionsApi } from '@/lib/admin-api';
import type { Profile, SessionSummary } from '@/lib/admin-api';

const PAGE_SIZE_OPTIONS = [10, 25, 50] as const;

export default function SessionsPage() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [profileFilter, setProfileFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [pageSize, setPageSize] = useState<number>(25);
  const [page, setPage] = useState(0);

  useEffect(() => {
    profilesApi
      .list(false)
      .then(setProfiles)
      .catch(() => {});
  }, []);

  // Reset to page 0 whenever filters or page size change.
  useEffect(() => {
    setPage(0);
  }, [profileFilter, statusFilter, pageSize]);

  useEffect(() => {
    setLoading(true);
    sessionsApi
      .list({
        profile_id: profileFilter || undefined,
        status: statusFilter || undefined,
        limit: pageSize,
        offset: page * pageSize,
      })
      .then(({ items, total: t }) => {
        setSessions(items);
        setTotal(t);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [profileFilter, statusFilter, pageSize, page]);

  const profileNameMap = new Map(profiles.map((p) => [p.id, p.display_name || p.name]));
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const showingFrom = total === 0 ? 0 : page * pageSize + 1;
  const showingTo = Math.min(total, (page + 1) * pageSize);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Sessions</h2>
        <p className="text-foreground/60 text-sm">Agent conversation sessions</p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <select
          value={profileFilter}
          onChange={(e) => setProfileFilter(e.target.value)}
          className="border-border bg-background text-foreground rounded-md border px-3 py-1.5 text-sm"
        >
          <option value="">All profiles</option>
          {profiles.map((p) => (
            <option key={p.id} value={p.id}>
              {p.display_name || p.name}
            </option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="border-border bg-background text-foreground rounded-md border px-3 py-1.5 text-sm"
        >
          <option value="">All statuses</option>
          <option value="running">Running</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
        </select>
        <label className="text-foreground/70 ml-auto flex items-center gap-2 text-xs">
          Page size
          <select
            value={pageSize}
            onChange={(e) => setPageSize(Number(e.target.value))}
            className="border-border bg-background text-foreground rounded-md border px-2 py-1 text-xs"
          >
            {PAGE_SIZE_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading && sessions.length === 0 ? (
        <div className="space-y-2">
          <div className="bg-foreground/10 h-10 animate-pulse rounded" />
          <div className="bg-foreground/10 h-10 animate-pulse rounded" />
          <div className="bg-foreground/10 h-10 animate-pulse rounded" />
        </div>
      ) : error ? (
        <div className="text-red-500">Error: {error}</div>
      ) : sessions.length === 0 ? (
        <div className="border-border text-foreground/60 rounded-md border p-6 text-center text-sm">
          No sessions found.
        </div>
      ) : (
        <div className="border-border overflow-hidden rounded-md border">
          <table className="w-full text-sm">
            <thead className="border-border text-foreground/60 bg-foreground/5 border-b">
              <tr>
                <th className="p-3 text-left font-medium whitespace-nowrap">Room</th>
                <th className="p-3 text-left font-medium whitespace-nowrap">Profile</th>
                <th className="p-3 text-left font-medium whitespace-nowrap">Mode</th>
                <th className="p-3 text-left font-medium whitespace-nowrap">Status</th>
                <th className="p-3 text-left font-medium whitespace-nowrap">Started</th>
                <th className="p-3 text-right font-medium whitespace-nowrap">Duration</th>
                <th className="p-3 text-right font-medium whitespace-nowrap">Cost</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr
                  key={s.id}
                  className="border-border hover:bg-foreground/5 border-b last:border-0"
                >
                  <td className="p-3 font-mono text-xs">
                    <Link href={`/admin/sessions/${s.id}`} className="text-primary hover:underline">
                      {s.room_name}
                    </Link>
                  </td>
                  <td className="text-foreground/80 p-3">
                    {s.profile_id ? profileNameMap.get(s.profile_id) || '(unknown)' : '—'}
                  </td>
                  <td className="p-3">
                    <ModeBadge mode={s.agent_mode} />
                  </td>
                  <td className="p-3">
                    <StatusBadge status={s.status} />
                  </td>
                  <td className="text-foreground/70 p-3 text-xs whitespace-nowrap">
                    <span title={new Date(s.started_at).toLocaleString()}>
                      {formatDate(s.started_at)}
                    </span>
                  </td>
                  <td className="p-3 text-right whitespace-nowrap">
                    {formatDuration(s.duration_seconds)}
                  </td>
                  <td className="p-3 text-right whitespace-nowrap">
                    {s.total_cost_usd != null ? `$${s.total_cost_usd.toFixed(4)}` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="text-foreground/70 flex flex-wrap items-center justify-between gap-3 text-xs">
        <span>
          {total === 0 ? 'No results' : `Showing ${showingFrom}–${showingTo} of ${total}`}
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0 || loading}
            className="border-border hover:bg-foreground/10 rounded border px-2 py-1 disabled:opacity-40"
          >
            ← Prev
          </button>
          <span className="font-mono">
            {page + 1} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page + 1 >= totalPages || loading}
            className="border-border hover:bg-foreground/10 rounded border px-2 py-1 disabled:opacity-40"
          >
            Next →
          </button>
        </div>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const cls =
    status === 'running'
      ? 'bg-blue-500/20 text-blue-700 dark:text-blue-400'
      : status === 'completed'
        ? 'bg-green-500/20 text-green-700 dark:text-green-400'
        : 'bg-red-500/20 text-red-700 dark:text-red-400';
  return <span className={`rounded px-2 py-0.5 text-xs font-medium ${cls}`}>{status}</span>;
}

function ModeBadge({ mode }: { mode: SessionSummary['agent_mode'] }) {
  if (!mode) return <span className="text-foreground/40 text-xs">—</span>;
  const cls =
    mode === 'realtime'
      ? 'bg-purple-500/20 text-purple-700 dark:text-purple-400'
      : 'bg-cyan-500/20 text-cyan-700 dark:text-cyan-400';
  return <span className={`rounded px-2 py-0.5 text-xs font-medium ${cls}`}>{mode}</span>;
}

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '—';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}m ${secs}s`;
}
