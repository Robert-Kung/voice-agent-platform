'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { profilesApi, sessionsApi } from '@/lib/admin-api';
import type { Profile, SessionSummary } from '@/lib/admin-api';

export default function SessionsPage() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [profileFilter, setProfileFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  useEffect(() => {
    profilesApi
      .list(false)
      .then(setProfiles)
      .catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    sessionsApi
      .list({
        profile_id: profileFilter || undefined,
        status: statusFilter || undefined,
        limit: 100,
      })
      .then(setSessions)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [profileFilter, statusFilter]);

  const profileNameMap = new Map(profiles.map((p) => [p.id, p.display_name || p.name]));

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Sessions</h2>
        <p className="text-foreground/60 text-sm">Agent conversation sessions</p>
      </div>

      <div className="flex gap-3">
        <select
          value={profileFilter}
          onChange={(e) => setProfileFilter(e.target.value)}
          className="border-border rounded-md border bg-transparent px-3 py-1.5 text-sm"
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
          className="border-border rounded-md border bg-transparent px-3 py-1.5 text-sm"
        >
          <option value="">All statuses</option>
          <option value="running">Running</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      {loading ? (
        <div>Loading...</div>
      ) : error ? (
        <div className="text-red-500">Error: {error}</div>
      ) : sessions.length === 0 ? (
        <div className="text-foreground/60">No sessions found.</div>
      ) : (
        <div className="border-border rounded-md border">
          <table className="w-full text-sm">
            <thead className="border-border text-foreground/60 border-b">
              <tr>
                <th className="p-3 text-left font-medium">Room</th>
                <th className="p-3 text-left font-medium">Profile</th>
                <th className="p-3 text-left font-medium">Status</th>
                <th className="p-3 text-left font-medium">Started</th>
                <th className="p-3 text-right font-medium">Duration</th>
                <th className="p-3 text-right font-medium">Cost</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr key={s.id} className="border-border border-b last:border-0">
                  <td className="p-3">
                    <Link href={`/admin/sessions/${s.id}`} className="text-primary hover:underline">
                      {s.room_name}
                    </Link>
                  </td>
                  <td className="text-foreground/80 p-3">
                    {s.profile_id ? profileNameMap.get(s.profile_id) || '(unknown)' : '—'}
                  </td>
                  <td className="p-3">
                    <StatusBadge status={s.status} />
                  </td>
                  <td className="text-foreground/70 p-3">
                    {new Date(s.started_at).toLocaleString()}
                  </td>
                  <td className="p-3 text-right">{formatDuration(s.duration_seconds)}</td>
                  <td className="p-3 text-right">
                    {s.total_cost_usd != null ? `$${s.total_cost_usd.toFixed(4)}` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
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

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '—';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}m ${secs}s`;
}
