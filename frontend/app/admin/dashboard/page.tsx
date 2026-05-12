'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Activity, DollarSign, Layers, Radio } from 'lucide-react';
import { formatDate, profilesApi, sessionsApi, statsApi } from '@/lib/admin-api';
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
        setSessions(ss.items);
        setProfileStats(pstats);
        setDailyStats(dstats);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading)
    return (
      <div className="space-y-6">
        <div className="bg-muted h-8 w-48 animate-pulse rounded-md" />
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="bg-card h-24 animate-pulse rounded-xl" />
          ))}
        </div>
      </div>
    );

  if (error)
    return (
      <div className="bg-destructive/10 text-destructive border-destructive/20 rounded-xl border p-6">
        <p className="font-medium">Error loading data: {error}</p>
        <p className="text-muted-foreground mt-1 text-sm">
          Make sure the management API is running on{' '}
          {process.env.NEXT_PUBLIC_ADMIN_API_URL || 'http://localhost:8080'}
        </p>
      </div>
    );

  const runningCount = sessions.filter((s) => s.status === 'running').length;
  const totalCost = dailyStats.reduce((acc, d) => acc + d.total_cost_usd, 0);
  const totalSessions = dailyStats.reduce((acc, d) => acc + d.session_count, 0);

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Dashboard</h2>
        <p className="text-muted-foreground text-sm">Agent platform overview</p>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard
          icon={Layers}
          label="Active Profiles"
          value={profiles.length}
          accent="text-chart-1"
        />
        <StatCard
          icon={Radio}
          label="Running Sessions"
          value={runningCount}
          accent="text-chart-2"
          pulse={runningCount > 0}
        />
        <StatCard
          icon={Activity}
          label="Total Sessions"
          value={totalSessions}
          accent="text-chart-3"
        />
        <StatCard
          icon={DollarSign}
          label="Total Cost"
          value={`$${totalCost.toFixed(4)}`}
          accent="text-chart-4"
        />
      </div>

      {/* Daily Trend */}
      {dailyStats.length > 1 && (
        <section className="bg-card border-border overflow-hidden rounded-xl border p-5">
          <h3 className="text-muted-foreground mb-3 text-xs font-medium tracking-wider uppercase">
            7-Day Session Trend
          </h3>
          <MiniBarChart data={dailyStats.slice(-7)} />
        </section>
      )}

      {/* Profile Stats */}
      <section>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-base font-semibold">Profile Stats</h3>
          <Link href="/admin/profiles" className="text-primary text-sm font-medium hover:underline">
            View all →
          </Link>
        </div>
        {profileStats.length === 0 ? (
          <EmptyState message="No sessions yet." />
        ) : (
          <div className="bg-card border-border overflow-hidden rounded-xl border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium tracking-wider uppercase">
                    Profile
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium tracking-wider uppercase">
                    Sessions
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium tracking-wider uppercase">
                    Total Duration
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium tracking-wider uppercase">
                    Avg Duration
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium tracking-wider uppercase">
                    Total Cost
                  </th>
                </tr>
              </thead>
              <tbody className="divide-border divide-y">
                {profileStats.map((s, i) => (
                  <tr key={i} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3 font-medium">{s.profile_name || '(unknown)'}</td>
                    <td className="px-4 py-3 text-right font-mono text-xs tabular-nums">
                      {s.session_count}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs tabular-nums">
                      {formatDuration(s.total_duration_seconds)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs tabular-nums">
                      {formatDuration(s.avg_duration_seconds)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs tabular-nums">
                      ${s.total_cost_usd.toFixed(4)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Recent Sessions */}
      <section>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-base font-semibold">Recent Sessions</h3>
          <Link href="/admin/sessions" className="text-primary text-sm font-medium hover:underline">
            View all →
          </Link>
        </div>
        {sessions.length === 0 ? (
          <EmptyState message="No sessions yet." />
        ) : (
          <div className="bg-card border-border overflow-hidden rounded-xl border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium tracking-wider uppercase">
                    Room
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium tracking-wider uppercase">
                    Status
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium tracking-wider uppercase">
                    Started
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium tracking-wider uppercase">
                    Duration
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium tracking-wider uppercase">
                    Cost
                  </th>
                </tr>
              </thead>
              <tbody className="divide-border divide-y">
                {sessions.slice(0, 5).map((s) => (
                  <tr key={s.id} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3">
                      <Link
                        href={`/admin/sessions/${s.id}`}
                        className="text-primary font-medium hover:underline"
                      >
                        {s.room_name}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={s.status} />
                    </td>
                    <td className="text-muted-foreground px-4 py-3 text-xs whitespace-nowrap">
                      <span title={new Date(s.started_at).toLocaleString()}>
                        {formatDate(s.started_at)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs tabular-nums">
                      {formatDuration(s.duration_seconds)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs tabular-nums">
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

function StatCard({
  icon: Icon,
  label,
  value,
  accent,
  pulse,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | number;
  accent: string;
  pulse?: boolean;
}) {
  return (
    <div className="bg-card border-border relative overflow-hidden rounded-xl border p-4">
      <div className="flex items-center gap-2">
        <Icon className={`size-4 ${accent}`} />
        <span className="text-muted-foreground text-xs font-medium tracking-wider uppercase">
          {label}
        </span>
        {pulse && (
          <span className="relative ml-auto flex size-2">
            <span className="bg-chart-2 absolute inline-flex size-full animate-ping rounded-full opacity-75 motion-reduce:animate-none" />
            <span className="bg-chart-2 relative inline-flex size-2 rounded-full" />
          </span>
        )}
      </div>
      <div className="mt-2 text-2xl font-bold tracking-tight">{value}</div>
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="bg-card text-muted-foreground border-border rounded-xl border p-8 text-center text-sm">
      {message}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const cls =
    status === 'running'
      ? 'bg-chart-2/15 text-chart-2 border-chart-2/30'
      : status === 'completed'
        ? 'bg-green-500/15 text-green-400 border-green-500/30'
        : 'bg-destructive/15 text-destructive border-destructive/30';
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${cls}`}
    >
      {status === 'running' && (
        <span className="mr-1.5 inline-block size-1.5 animate-pulse rounded-full bg-current" />
      )}
      {status}
    </span>
  );
}

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '—';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}m ${secs}s`;
}

function MiniBarChart({ data }: { data: DailyStats[] }) {
  const maxVal = Math.max(...data.map((d) => d.session_count), 1);
  return (
    <div>
      <div className="flex items-end gap-1.5" style={{ height: 56 }}>
        {data.map((d, i) => {
          const pct = (d.session_count / maxVal) * 100;
          const isLast = i === data.length - 1;
          return (
            <div
              key={d.date}
              className={`min-w-[6px] flex-1 rounded-t transition-all ${
                isLast ? 'bg-chart-1' : 'bg-chart-1/40'
              } hover:bg-chart-1`}
              style={{ height: `${Math.max(pct, 4)}%` }}
              title={`${d.date}: ${d.session_count} sessions, $${d.total_cost_usd.toFixed(4)}`}
            />
          );
        })}
      </div>
      <div className="mt-1.5 flex gap-1.5">
        {data.map((d) => (
          <span
            key={d.date}
            className="text-muted-foreground flex-1 text-center text-[9px] leading-none"
          >
            {d.date.slice(5)}
          </span>
        ))}
      </div>
    </div>
  );
}
