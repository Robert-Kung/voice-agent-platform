'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { profilesApi, sessionsApi, statsApi } from '@/lib/admin-api';
import type { DailyStats, Profile, ProfileStats, SessionSummary } from '@/lib/admin-api';

export default function DashboardPage() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [profileStats, setProfileStats] = useState<ProfileStats[]>([]);
  const [dailyStats, setDailyStats] = useState<DailyStats[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      profilesApi.list(),
      sessionsApi.list({ limit: 10 }),
      statsApi.profiles(),
      statsApi.daily(),
    ])
      .then(([ps, ss, pstats, dstats]) => {
        setProfiles(ps);
        setSessions(ss);
        setProfileStats(pstats);
        setDailyStats(dstats);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div>Loading...</div>;
  if (error)
    return (
      <div className="text-red-500">
        Error loading data: {error}
        <div className="text-foreground/60 mt-2 text-sm">
          Make sure the management API is running on{' '}
          {process.env.NEXT_PUBLIC_ADMIN_API_URL || 'http://localhost:8080'}
        </div>
      </div>
    );

  const runningCount = sessions.filter((s) => s.status === 'running').length;
  const totalCost = dailyStats.reduce((acc, d) => acc + d.total_cost_usd, 0);
  const totalSessions = dailyStats.reduce((acc, d) => acc + d.session_count, 0);

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold">Dashboard</h2>
        <p className="text-foreground/60 text-sm">Agent platform overview</p>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Active Profiles" value={profiles.length} />
        <StatCard label="Running Sessions" value={runningCount} />
        <StatCard label="Total Sessions" value={totalSessions} />
        <StatCard label="Total Cost" value={`$${totalCost.toFixed(4)}`} />
      </div>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-lg font-semibold">Profile Stats</h3>
          <Link href="/admin/profiles" className="text-primary text-sm hover:underline">
            View all →
          </Link>
        </div>
        {profileStats.length === 0 ? (
          <div className="text-foreground/60 text-sm">No sessions yet.</div>
        ) : (
          <div className="border-border rounded-md border">
            <table className="w-full text-sm">
              <thead className="border-border text-foreground/60 border-b">
                <tr>
                  <th className="p-3 text-left font-medium">Profile</th>
                  <th className="p-3 text-right font-medium">Sessions</th>
                  <th className="p-3 text-right font-medium">Total Duration</th>
                  <th className="p-3 text-right font-medium">Avg Duration</th>
                  <th className="p-3 text-right font-medium">Total Cost</th>
                </tr>
              </thead>
              <tbody>
                {profileStats.map((s, i) => (
                  <tr key={i} className="border-border border-b last:border-0">
                    <td className="p-3">{s.profile_name || '(unknown)'}</td>
                    <td className="p-3 text-right">{s.session_count}</td>
                    <td className="p-3 text-right">{formatDuration(s.total_duration_seconds)}</td>
                    <td className="p-3 text-right">{formatDuration(s.avg_duration_seconds)}</td>
                    <td className="p-3 text-right">${s.total_cost_usd.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-lg font-semibold">Recent Sessions</h3>
          <Link href="/admin/sessions" className="text-primary text-sm hover:underline">
            View all →
          </Link>
        </div>
        {sessions.length === 0 ? (
          <div className="text-foreground/60 text-sm">No sessions yet.</div>
        ) : (
          <div className="border-border rounded-md border">
            <table className="w-full text-sm">
              <thead className="border-border text-foreground/60 border-b">
                <tr>
                  <th className="p-3 text-left font-medium">Room</th>
                  <th className="p-3 text-left font-medium">Status</th>
                  <th className="p-3 text-left font-medium">Started</th>
                  <th className="p-3 text-right font-medium">Duration</th>
                  <th className="p-3 text-right font-medium">Cost</th>
                </tr>
              </thead>
              <tbody>
                {sessions.slice(0, 5).map((s) => (
                  <tr key={s.id} className="border-border border-b last:border-0">
                    <td className="p-3">
                      <Link
                        href={`/admin/sessions/${s.id}`}
                        className="text-primary hover:underline"
                      >
                        {s.room_name}
                      </Link>
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
      </section>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="border-border rounded-md border p-4">
      <div className="text-foreground/60 text-xs font-medium tracking-wide uppercase">{label}</div>
      <div className="mt-1 text-2xl font-bold">{value}</div>
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
