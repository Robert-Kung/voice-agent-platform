'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { sessionsApi } from '@/lib/admin-api';
import type { SessionDetail, SessionEvent } from '@/lib/admin-api';

export default function SessionDetailPage() {
  const params = useParams();
  const id = params.id as string;

  const [session, setSession] = useState<SessionDetail | null>(null);
  const [events, setEvents] = useState<SessionEvent[]>([]);
  const [livekitUrl, setLivekitUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      sessionsApi.get(id),
      sessionsApi.getEvents(id).catch(() => []),
      sessionsApi.getLivekitLink(id).catch(() => null),
    ])
      .then(([s, evs, link]) => {
        setSession(s);
        setEvents(evs);
        setLivekitUrl(link?.url || null);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div>Loading...</div>;
  if (error) return <div className="text-red-500">Error: {error}</div>;
  if (!session) return <div>Session not found.</div>;

  const usageSummary = (session.raw_report.usage_summary as Record<string, unknown>) || {};
  const cost = (session.raw_report.cost as Record<string, unknown>) || {};

  return (
    <div className="space-y-6">
      <div>
        <Link href="/admin/sessions" className="text-primary text-sm hover:underline">
          ← Back to sessions
        </Link>
      </div>

      <div>
        <h2 className="text-2xl font-bold">{session.room_name}</h2>
        <p className="text-foreground/60 font-mono text-xs">{session.id}</p>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <InfoCard label="Status" value={session.status} />
        <InfoCard label="Duration" value={formatDuration(session.duration_seconds)} />
        <InfoCard
          label="Cost"
          value={session.total_cost_usd != null ? `$${session.total_cost_usd.toFixed(4)}` : '—'}
        />
        <InfoCard label="Started" value={new Date(session.started_at).toLocaleString()} />
      </div>

      {livekitUrl && (
        <div>
          <a
            href={livekitUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="bg-primary text-primary-foreground inline-block rounded px-4 py-2 text-sm font-medium"
          >
            Open in LiveKit Cloud →
          </a>
          <p className="text-foreground/60 mt-1 text-xs">
            View recording and full session details on LiveKit Cloud dashboard.
          </p>
        </div>
      )}

      {Object.keys(usageSummary).length > 0 && (
        <section>
          <h3 className="mb-2 text-lg font-semibold">Usage Summary</h3>
          <pre className="border-border overflow-auto rounded-md border bg-transparent p-3 font-mono text-xs">
            {JSON.stringify(usageSummary, null, 2)}
          </pre>
        </section>
      )}

      {Object.keys(cost).length > 0 && (
        <section>
          <h3 className="mb-2 text-lg font-semibold">Cost Breakdown</h3>
          <pre className="border-border overflow-auto rounded-md border bg-transparent p-3 font-mono text-xs">
            {JSON.stringify(cost, null, 2)}
          </pre>
        </section>
      )}

      <section>
        <h3 className="mb-2 text-lg font-semibold">Events ({events.length})</h3>
        {events.length === 0 ? (
          <div className="text-foreground/60 text-sm">No events recorded for this session.</div>
        ) : (
          <div className="border-border rounded-md border">
            <table className="w-full text-sm">
              <thead className="border-border text-foreground/60 border-b">
                <tr>
                  <th className="p-3 text-left font-medium">Seq</th>
                  <th className="p-3 text-left font-medium">Type</th>
                  <th className="p-3 text-left font-medium">Timestamp</th>
                  <th className="p-3 text-left font-medium">Payload</th>
                </tr>
              </thead>
              <tbody>
                {events.map((ev) => (
                  <tr key={ev.id} className="border-border border-b align-top last:border-0">
                    <td className="p-3 font-mono text-xs">{ev.seq}</td>
                    <td className="p-3">
                      <span className="bg-foreground/10 rounded px-2 py-0.5 text-xs">
                        {ev.event_type}
                      </span>
                    </td>
                    <td className="text-foreground/70 p-3 text-xs">
                      {new Date(ev.timestamp).toLocaleTimeString()}
                    </td>
                    <td className="p-3 font-mono text-xs">
                      <pre className="whitespace-pre-wrap">
                        {JSON.stringify(ev.payload, null, 2)}
                      </pre>
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

function InfoCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-border rounded-md border p-4">
      <div className="text-foreground/60 text-xs font-medium tracking-wide uppercase">{label}</div>
      <div className="mt-1 text-lg font-semibold">{value}</div>
    </div>
  );
}

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '—';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}m ${secs}s`;
}
