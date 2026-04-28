'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { formatDate, sessionsApi } from '@/lib/admin-api';
import type { SessionDetail, SessionEvent } from '@/lib/admin-api';

type TabKey = 'conversation' | 'metrics' | 'raw';

export default function SessionDetailPage() {
  const params = useParams();
  const id = params.id as string;

  const [session, setSession] = useState<SessionDetail | null>(null);
  const [events, setEvents] = useState<SessionEvent[]>([]);
  const [livekitUrl, setLivekitUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>('conversation');

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

  const { conversation, metrics } = useMemo(() => groupEvents(events), [events]);

  // If conversation is empty, default tab to metrics so user sees something useful.
  useEffect(() => {
    if (!loading && conversation.length === 0 && metrics.length > 0 && tab === 'conversation') {
      setTab('metrics');
    }
  }, [loading, conversation.length, metrics.length, tab]);

  if (loading) {
    return (
      <div className="space-y-3">
        <div className="bg-foreground/10 h-6 w-32 animate-pulse rounded" />
        <div className="bg-foreground/10 h-32 animate-pulse rounded" />
      </div>
    );
  }
  if (error) return <div className="text-red-500">Error: {error}</div>;
  if (!session) return <div>Session not found.</div>;

  const usage = (session.raw_report.usage_summary as Record<string, number>) || {};
  const cost = (session.raw_report.cost as Record<string, unknown>) || {};
  const isRealtime = session.agent_mode === 'realtime' || cost.mode === 'realtime';

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

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <InfoCard label="Status" value={<StatusBadge status={session.status} />} />
        <InfoCard label="Mode" value={<ModeBadge mode={session.agent_mode} />} />
        <InfoCard label="Duration" value={formatDuration(session.duration_seconds)} />
        <InfoCard
          label="Total Cost"
          value={
            session.total_cost_usd != null ? (
              `$${session.total_cost_usd.toFixed(4)}`
            ) : (
              <span className="text-foreground/50">—</span>
            )
          }
        />
        <InfoCard label="Started" value={formatDate(session.started_at)} />
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

      <UsageSection usage={usage} isRealtime={isRealtime} />
      <CostSection cost={cost} isRealtime={isRealtime} />

      <section>
        <div className="border-border mb-3 flex items-center gap-1 border-b">
          <TabButton active={tab === 'conversation'} onClick={() => setTab('conversation')}>
            Conversation ({conversation.length})
          </TabButton>
          <TabButton active={tab === 'metrics'} onClick={() => setTab('metrics')}>
            Metrics ({metrics.length})
          </TabButton>
          <TabButton active={tab === 'raw'} onClick={() => setTab('raw')}>
            Raw ({events.length})
          </TabButton>
        </div>

        {tab === 'conversation' && <ConversationTab events={conversation} />}
        {tab === 'metrics' && <MetricsTab events={metrics} isRealtime={isRealtime} />}
        {tab === 'raw' && <RawEventsTab events={events} />}
      </section>
    </div>
  );
}

// ── Tabs ───────────────────────────────────────────────────────

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`-mb-px border-b-2 px-3 py-2 text-sm transition-colors ${
        active
          ? 'border-primary text-primary'
          : 'text-foreground/60 hover:text-foreground/90 border-transparent'
      }`}
    >
      {children}
    </button>
  );
}

function ConversationTab({ events }: { events: SessionEvent[] }) {
  if (events.length === 0) {
    return (
      <div className="border-border text-foreground/60 rounded-md border p-6 text-center text-sm">
        No conversation transcript recorded for this session.
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {events.map((ev) => {
        const role = (ev.payload?.role as string) || 'message';
        const text = (ev.payload?.text as string) || '';
        const fn = parseFunctionCallText(text);

        // Tool calls / outputs render as a centered, collapsible row instead
        // of a chat bubble — they're plumbing, not dialogue.
        if (fn) {
          return <FunctionCallRow key={ev.id} kind={fn.kind} name={fn.name} raw={text} />;
        }

        const isUser = role === 'user';
        const isAssistant = role === 'assistant';
        const align = isUser ? 'items-end' : 'items-start';
        const bubble = isUser
          ? 'bg-primary/10 border-primary/30'
          : isAssistant
            ? 'bg-foreground/5 border-border'
            : 'bg-amber-500/10 border-amber-500/30 text-foreground/70';
        return (
          <div key={ev.id} className={`flex flex-col ${align}`}>
            <div className="text-foreground/50 mb-1 px-2 font-mono text-[10px] uppercase">
              {role}
            </div>
            <div
              className={`max-w-[85%] rounded-md border px-3 py-2 text-sm whitespace-pre-wrap ${bubble}`}
            >
              {text || <span className="text-foreground/40 italic">(empty)</span>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

interface ParsedFunctionCall {
  kind: 'call' | 'output';
  name: string;
}

// Detect chat_message rows whose text is the repr of a FunctionCall /
// FunctionCallOutput. Extract just the name= field so the conversation
// stays readable; the full repr is kept behind <details> for debugging.
function parseFunctionCallText(text: string): ParsedFunctionCall | null {
  if (!text) return null;
  const isCall = text.startsWith('FunctionCall(');
  const isOutput = text.startsWith('FunctionCallOutput(');
  if (!isCall && !isOutput) return null;
  const m = text.match(/name='([^']+)'/);
  return {
    kind: isCall ? 'call' : 'output',
    name: m?.[1] || '(unknown)',
  };
}

function FunctionCallRow({
  kind,
  name,
  raw,
}: {
  kind: 'call' | 'output';
  name: string;
  raw: string;
}) {
  const arrow = kind === 'call' ? '→' : '←';
  const label = kind === 'call' ? 'tool call' : 'tool result';
  return (
    <div className="flex justify-center">
      <details className="border-border bg-foreground/5 group w-full max-w-[60%] rounded-md border px-3 py-1.5 text-xs">
        <summary className="text-foreground/70 flex cursor-pointer list-none items-center gap-2">
          <span className="text-foreground/40 font-mono">{arrow}</span>
          <span className="font-mono font-semibold">{name}</span>
          <span className="text-foreground/50">{label}</span>
          <span className="text-foreground/40 ml-auto transition-transform group-open:rotate-90">
            ▶
          </span>
        </summary>
        <pre className="text-foreground/70 mt-2 max-h-48 overflow-auto font-mono text-[11px] whitespace-pre-wrap">
          {raw}
        </pre>
      </details>
    </div>
  );
}

interface MetricRow {
  seq: number;
  type: string;
  timestamp: string;
  ttft: number | null;
  duration: number | null;
  inputTokens: number | null;
  outputTokens: number | null;
  audioDuration: number | null;
  model: string | null;
}

function summariseMetric(ev: SessionEvent): MetricRow {
  const p = ev.payload as Record<string, unknown>;
  const num = (k: string): number | null => {
    const v = p?.[k];
    return typeof v === 'number' && !Number.isNaN(v) ? v : null;
  };
  const meta = (p?.metadata as Record<string, unknown>) || {};
  return {
    seq: ev.seq,
    type: ev.event_type.replace(/^metric_/, ''),
    timestamp: ev.timestamp,
    ttft: num('ttft'),
    duration: num('duration'),
    inputTokens: num('input_tokens'),
    outputTokens: num('output_tokens'),
    audioDuration: num('audio_duration'),
    model: (meta?.model_name as string) || null,
  };
}

function MetricsTab({ events, isRealtime }: { events: SessionEvent[]; isRealtime: boolean }) {
  if (events.length === 0) {
    return (
      <div className="border-border text-foreground/60 rounded-md border p-6 text-center text-sm">
        No metric events.
      </div>
    );
  }
  const rows = events.map(summariseMetric);
  return (
    <div className="border-border overflow-x-auto rounded-md border">
      <table className="w-full text-xs">
        <thead className="border-border text-foreground/60 bg-foreground/5 border-b">
          <tr>
            <th className="p-2 text-left font-medium">#</th>
            <th className="p-2 text-left font-medium">Type</th>
            <th className="p-2 text-left font-medium">Model</th>
            <th className="p-2 text-right font-medium" title="Time to first token (s)">
              TTFT
            </th>
            <th className="p-2 text-right font-medium" title="Generation duration (s)">
              Dur
            </th>
            <th className="p-2 text-right font-medium">In tok</th>
            <th className="p-2 text-right font-medium">Out tok</th>
            <th className="p-2 text-right font-medium">Audio s</th>
            <th className="p-2 text-left font-medium">Time</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.seq} className="border-border border-b last:border-0">
              <td className="text-foreground/50 p-2 font-mono">{r.seq}</td>
              <td className="p-2">
                <span className="bg-foreground/10 rounded px-1.5 py-0.5 font-mono">{r.type}</span>
              </td>
              <td className="text-foreground/70 p-2 font-mono">{r.model || '—'}</td>
              <td className="p-2 text-right font-mono">{fmtNum(r.ttft, 2)}</td>
              <td className="p-2 text-right font-mono">{fmtNum(r.duration, 2)}</td>
              <td className="p-2 text-right font-mono">{fmtNum(r.inputTokens, 0)}</td>
              <td className="p-2 text-right font-mono">{fmtNum(r.outputTokens, 0)}</td>
              <td className="p-2 text-right font-mono">{fmtNum(r.audioDuration, 1)}</td>
              <td className="text-foreground/50 p-2 font-mono">
                {new Date(r.timestamp).toLocaleTimeString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {isRealtime && (
        <p className="text-foreground/50 border-border border-t p-2 text-[11px]">
          Realtime mode: TTFT/duration may show 0 because Gemini Live streams audio without discrete
          request boundaries.
        </p>
      )}
    </div>
  );
}

function RawEventsTab({ events }: { events: SessionEvent[] }) {
  if (events.length === 0) {
    return (
      <div className="border-border text-foreground/60 rounded-md border p-6 text-center text-sm">
        No events.
      </div>
    );
  }
  return (
    <div className="border-border rounded-md border">
      <table className="w-full text-sm">
        <thead className="border-border text-foreground/60 border-b">
          <tr>
            <th className="p-2 text-left font-medium">#</th>
            <th className="p-2 text-left font-medium">Type</th>
            <th className="p-2 text-left font-medium">Time</th>
            <th className="p-2 text-left font-medium">Payload</th>
          </tr>
        </thead>
        <tbody>
          {events.map((ev) => (
            <tr key={ev.id} className="border-border border-b align-top last:border-0">
              <td className="p-2 font-mono text-xs">{ev.seq}</td>
              <td className="p-2">
                <span className="bg-foreground/10 rounded px-1.5 py-0.5 font-mono text-xs">
                  {ev.event_type}
                </span>
              </td>
              <td className="text-foreground/70 p-2 font-mono text-xs">
                {new Date(ev.timestamp).toLocaleTimeString()}
              </td>
              <td className="p-2 font-mono text-xs">
                <pre className="max-w-[600px] overflow-auto whitespace-pre-wrap">
                  {JSON.stringify(ev.payload, null, 2)}
                </pre>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Cards ──────────────────────────────────────────────────────

function InfoCard({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="border-border rounded-md border p-3">
      <div className="text-foreground/60 text-[10px] font-medium tracking-wide uppercase">
        {label}
      </div>
      <div className="mt-1 text-base font-semibold">{value}</div>
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

function ModeBadge({ mode }: { mode: SessionDetail['agent_mode'] }) {
  if (!mode) return <span className="text-foreground/40 text-xs">—</span>;
  const cls =
    mode === 'realtime'
      ? 'bg-purple-500/20 text-purple-700 dark:text-purple-400'
      : 'bg-cyan-500/20 text-cyan-700 dark:text-cyan-400';
  return <span className={`rounded px-2 py-0.5 text-xs font-medium ${cls}`}>{mode}</span>;
}

function UsageSection({
  usage,
  isRealtime,
}: {
  usage: Record<string, number>;
  isRealtime: boolean;
}) {
  if (Object.keys(usage).length === 0) return null;

  const promptTokens = usage.llm_prompt_tokens ?? 0;
  const completionTokens = usage.llm_completion_tokens ?? 0;
  const audioIn = usage.llm_input_audio_tokens ?? 0;
  const textIn = usage.llm_input_text_tokens ?? 0;
  const cachedIn =
    (usage.llm_input_cached_audio_tokens ?? 0) + (usage.llm_input_cached_text_tokens ?? 0);
  const audioOut = usage.llm_output_audio_tokens ?? 0;
  const textOut = usage.llm_output_text_tokens ?? 0;
  const sttSec = usage.stt_audio_duration ?? 0;
  const ttsSec = usage.tts_audio_duration ?? 0;
  const ttsChars = usage.tts_characters_count ?? 0;

  return (
    <section>
      <h3 className="mb-2 text-base font-semibold">Usage Summary</h3>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <InfoCard
          label="LLM Input"
          value={
            <div className="space-y-0.5">
              <div>{fmtInt(promptTokens)} tok</div>
              <div className="text-foreground/60 text-[11px] font-normal">
                audio {fmtInt(audioIn)} · text {fmtInt(textIn)}
                {cachedIn > 0 && ` · cached ${fmtInt(cachedIn)}`}
              </div>
            </div>
          }
        />
        <InfoCard
          label="LLM Output"
          value={
            <div className="space-y-0.5">
              <div>{fmtInt(completionTokens)} tok</div>
              <div className="text-foreground/60 text-[11px] font-normal">
                audio {fmtInt(audioOut)} · text {fmtInt(textOut)}
              </div>
            </div>
          }
        />
        <InfoCard
          label={isRealtime ? 'STT (unused)' : 'STT Audio'}
          value={
            sttSec > 0 ? `${sttSec.toFixed(1)}s` : <span className="text-foreground/50">—</span>
          }
        />
        <InfoCard
          label="TTS"
          value={
            ttsChars > 0 || ttsSec > 0 ? (
              `${fmtInt(ttsChars)} ch · ${ttsSec.toFixed(1)}s`
            ) : (
              <span className="text-foreground/50">—</span>
            )
          }
        />
      </div>
      {isRealtime && (
        <p className="text-foreground/50 mt-2 text-xs">
          Realtime mode: completion 多為 audio_tokens (Gemini Live 直接生成語音)。STT 數據通常為 0
          因為語音直接送 LLM。
        </p>
      )}
    </section>
  );
}

function CostSection({ cost, isRealtime }: { cost: Record<string, unknown>; isRealtime: boolean }) {
  const totalUsd = cost.total_usd as number | null | undefined;
  if (totalUsd == null && !isRealtime) return null;

  const llmUsd = cost.llm_usd as number | null | undefined;
  const sttUsd = cost.stt_usd as number | null | undefined;
  const ttsUsd = cost.tts_usd as number | null | undefined;
  const rates = cost.rates_per_1m as Record<string, number> | undefined;
  const model = cost.model as string | undefined;

  const sttRatePerMin = cost.stt_rate_per_min as number | undefined;
  const sttProvider = cost.stt_provider as string | undefined;

  return (
    <section>
      <h3 className="mb-2 text-base font-semibold">Cost Breakdown</h3>
      <div className="border-border rounded-md border p-4">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <CostRow label="LLM" usd={llmUsd} />
          <CostRow label="STT" usd={sttUsd} />
          {!isRealtime && <CostRow label="TTS" usd={ttsUsd} />}
          <CostRow label="Total" usd={totalUsd ?? null} bold />
        </div>
        {isRealtime && rates && (
          <div className="border-border mt-4 space-y-2 border-t pt-3">
            <div>
              <div className="text-foreground/60 mb-1 text-xs font-medium">
                LLM — Gemini Live {model && <span className="font-mono">({model})</span>}
              </div>
              <div className="text-foreground/70 grid grid-cols-2 gap-1 text-xs md:grid-cols-5">
                <span>audio in: ${rates.audio_in}/1M</span>
                <span>audio out: ${rates.audio_out}/1M</span>
                <span>text in: ${rates.text_in}/1M</span>
                <span>text out: ${rates.text_out}/1M</span>
                <span>cached: ${rates.cached_in}/1M</span>
              </div>
            </div>
            {sttRatePerMin != null && (
              <div>
                <div className="text-foreground/60 mb-1 text-xs font-medium">
                  STT {sttProvider && <span className="font-mono">({sttProvider})</span>}
                </div>
                <div className="text-foreground/70 text-xs">${sttRatePerMin}/min audio</div>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function CostRow({
  label,
  usd,
  bold = false,
}: {
  label: string;
  usd: number | null | undefined;
  bold?: boolean;
}) {
  return (
    <div>
      <div className="text-foreground/60 text-[10px] font-medium tracking-wide uppercase">
        {label}
      </div>
      <div className={`mt-0.5 ${bold ? 'text-base font-semibold' : 'text-sm'}`}>
        {usd != null ? `$${usd.toFixed(4)}` : <span className="text-foreground/40">—</span>}
      </div>
    </div>
  );
}

// ── Helpers ────────────────────────────────────────────────────

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '—';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}m ${secs}s`;
}

function fmtInt(n: number): string {
  if (!n) return '0';
  return n.toLocaleString();
}

function fmtNum(n: number | null, digits: number): string {
  if (n == null || Number.isNaN(n)) return '—';
  return n.toFixed(digits);
}

function groupEvents(events: SessionEvent[]): {
  conversation: SessionEvent[];
  metrics: SessionEvent[];
} {
  const conversation: SessionEvent[] = [];
  const metrics: SessionEvent[] = [];
  for (const ev of events) {
    if (ev.event_type.startsWith('chat_')) {
      conversation.push(ev);
    } else if (ev.event_type.startsWith('metric_')) {
      metrics.push(ev);
    }
  }
  return { conversation, metrics };
}
