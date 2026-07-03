'use client';

import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Bot, ChevronDown, ChevronRight, Clock3, GitBranch, Play, RefreshCw, ShieldCheck, Wrench } from 'lucide-react';
import type { ProfileTestRunDetail, ProfileTestRunEvent, ProfileTestRunSummary, ToolExecutionMode } from '@/lib/admin-api';
import { formatDate, testRunsApi } from '@/lib/admin-api';
import { cn } from '@/lib/shadcn/utils';

interface ProfileTextTestPanelProps {
  profileId: string | null;
  isNew: boolean;
  isDirty: boolean;
}

const eventLabels: Record<string, string> = {
  test_started: 'Started',
  prompt_rendered: 'Prompt',
  graph_validated: 'Graph',
  node_entered: 'Node',
  edge_selected: 'Edge',
  tool_call: 'Tool call',
  tool_result: 'Tool result',
  handoff: 'Handoff',
  fallback: 'Fallback',
  assistant_output: 'Placeholder output',
  test_completed: 'Completed',
  runner_error: 'Error',
  timeout: 'Timeout',
};

export function ProfileTextTestPanel({ profileId, isNew, isDirty }: ProfileTextTestPanelProps) {
  const [message, setMessage] = useState('');
  const [mode, setMode] = useState<ToolExecutionMode>('dry_run');
  const [running, setRunning] = useState(false);
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeRun, setActiveRun] = useState<ProfileTestRunDetail | null>(null);
  const [recentRuns, setRecentRuns] = useState<ProfileTestRunSummary[]>([]);
  const [expanded, setExpanded] = useState<Set<number>>(() => new Set());

  const canRun = Boolean(profileId && !isNew && message.trim() && !running);

  const loadRecent = async () => {
    if (!profileId || isNew) return;
    setLoadingRuns(true);
    try {
      const page = await testRunsApi.list(profileId, { limit: 5, offset: 0 });
      setRecentRuns(page.items);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoadingRuns(false);
    }
  };

  useEffect(() => {
    void loadRecent();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profileId, isNew]);

  const runTest = async () => {
    if (!profileId || !canRun) return;
    setRunning(true);
    setError(null);
    try {
      const run = await testRunsApi.create(profileId, {
        message: message.trim(),
        tool_execution_mode: mode,
      });
      setActiveRun(run);
      setExpanded(new Set(run.events.filter((e) => e.severity !== 'info').map((e) => e.id)));
      setMessage('');
      await loadRecent();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRunning(false);
    }
  };

  const inspectRun = async (runId: string) => {
    if (!profileId) return;
    setError(null);
    try {
      const run = await testRunsApi.get(profileId, runId);
      setActiveRun(run);
      setExpanded(new Set(run.events.filter((e) => e.severity !== 'info').map((e) => e.id)));
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const assistantOutput = useMemo(() => findAssistantOutput(activeRun), [activeRun]);
  const fallback = activeRun?.events.find((e) => e.event_type === 'fallback');
  const warnings = activeRun?.events.filter((e) => e.severity === 'warning') ?? [];
  const errors = activeRun?.events.filter((e) => e.severity === 'error') ?? [];
  const path = useMemo(() => graphPath(activeRun), [activeRun]);

  return (
    <section className="border-border bg-foreground/[0.025] mb-3 rounded-lg border px-3 py-3">
      <div className="mb-2 flex items-start justify-between gap-3">
        <div>
          <div className="text-foreground/80 flex items-center gap-1.5 text-xs font-semibold tracking-wide uppercase">
            <Bot size={13} />
            Flow Test
          </div>
          <p className="text-foreground/45 mt-0.5 text-[11px] leading-relaxed">
            Checks saved prompt/graph wiring without LLM, voice, or external side effects.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadRecent()}
          disabled={loadingRuns || !profileId || isNew}
          aria-label="Reload recent flow test runs"
          className="text-foreground/45 hover:bg-foreground/5 hover:text-foreground inline-flex size-7 items-center justify-center rounded-md disabled:opacity-40"
        >
          <RefreshCw size={13} className={loadingRuns ? 'animate-spin' : undefined} />
        </button>
      </div>

      {isDirty && (
        <div className="mb-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1.5 text-[11px] leading-relaxed text-amber-700 dark:text-amber-300">
          Unsaved edits are not included. Save first to test the latest profile.
        </div>
      )}

      <div className="mb-2 flex rounded-md border border-border p-0.5" role="group" aria-label="Tool execution mode">
        {(['dry_run', 'live'] as ToolExecutionMode[]).map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => setMode(value)}
            className={cn(
              'flex-1 rounded px-2 py-1 text-[11px] font-medium transition-colors',
              mode === value
                ? 'bg-primary text-primary-foreground'
                : 'text-foreground/55 hover:bg-foreground/5 hover:text-foreground'
            )}
          >
            {value === 'dry_run' ? 'Dry-run' : 'Live'}
          </button>
        ))}
      </div>

      <div className="flex gap-2">
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          rows={2}
          disabled={isNew}
          placeholder={isNew ? 'Create profile before testing' : 'Type a sample message...'}
          className="border-border bg-background text-foreground focus:ring-primary/35 min-h-[64px] flex-1 resize-y rounded-md border px-2.5 py-2 text-xs focus:ring-2 focus:outline-none disabled:opacity-50"
        />
        <button
          type="button"
          onClick={() => void runTest()}
          disabled={!canRun}
          className="bg-primary text-primary-foreground hover:opacity-90 inline-flex w-10 shrink-0 items-center justify-center rounded-md disabled:opacity-45"
          aria-label="Run flow test"
        >
          {running ? <RefreshCw size={15} className="animate-spin" /> : <Play size={15} />}
        </button>
      </div>

      {error && (
        <div className="mt-2 rounded-md border border-red-500/30 bg-red-500/10 px-2 py-1.5 text-[11px] text-red-600 dark:text-red-300">
          {error}
        </div>
      )}

      {activeRun && (
        <div className="mt-3 space-y-2">
          <RunSummary run={activeRun} warnings={warnings.length} errors={errors.length} />
          {fallback && <FallbackBanner event={fallback} />}
          {path.length > 0 && <GraphPath events={path} />}
          {assistantOutput && (
            <div className="border-border rounded-md border px-2 py-1.5">
              <div className="text-foreground/45 mb-1 text-[10px] font-medium uppercase">Placeholder output</div>
              <p className="text-foreground/75 text-xs leading-relaxed">{assistantOutput}</p>
            </div>
          )}
          <div className="space-y-1.5">
            {activeRun.events.map((event) => (
              <EventRow
                key={event.id}
                event={event}
                open={expanded.has(event.id)}
                onToggle={() => {
                  setExpanded((prev) => {
                    const next = new Set(prev);
                    if (next.has(event.id)) next.delete(event.id);
                    else next.add(event.id);
                    return next;
                  });
                }}
              />
            ))}
          </div>
        </div>
      )}

      {recentRuns.length > 0 && (
        <div className="mt-3 border-t border-border pt-2">
          <div className="text-foreground/45 mb-1.5 text-[10px] font-medium uppercase">Recent</div>
          <div className="grid gap-1">
            {recentRuns.map((run) => (
              <button
                key={run.id}
                type="button"
                onClick={() => void inspectRun(run.id)}
                className="hover:bg-foreground/5 flex min-w-0 items-center justify-between gap-2 rounded px-2 py-1 text-left"
              >
                <span className="text-foreground/65 min-w-0 truncate text-xs">{run.user_message}</span>
                <span className="text-foreground/35 shrink-0 font-mono text-[10px]">
                  {formatDate(run.created_at)}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function RunSummary({ run, warnings, errors }: { run: ProfileTestRunDetail; warnings: number; errors: number }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
      <Badge tone={run.status === 'completed' ? 'success' : run.status === 'failed' ? 'error' : 'muted'}>
        {run.status}
      </Badge>
      <Badge tone={run.tool_execution_mode === 'dry_run' ? 'safe' : 'warning'}>
        {run.tool_execution_mode === 'dry_run' ? <ShieldCheck size={11} /> : <Wrench size={11} />}
        {run.tool_execution_mode}
      </Badge>
      {warnings > 0 && <Badge tone="warning">{warnings} warning</Badge>}
      {errors > 0 && <Badge tone="error">{errors} error</Badge>}
      <span className="text-foreground/35 ml-auto inline-flex items-center gap-1 font-mono">
        <Clock3 size={11} />
        {formatDate(run.created_at)}
      </span>
    </div>
  );
}

function FallbackBanner({ event }: { event: ProfileTestRunEvent }) {
  return (
    <div className="rounded-md border border-amber-500/35 bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-700 dark:text-amber-300">
      <div className="flex items-center gap-1 font-medium">
        <AlertTriangle size={12} />
        Fallback: {String(event.payload.reason ?? 'graph fallback')}
      </div>
    </div>
  );
}

function GraphPath({ events }: { events: ProfileTestRunEvent[] }) {
  return (
    <div className="border-border rounded-md border px-2 py-1.5">
      <div className="text-foreground/45 mb-1 flex items-center gap-1 text-[10px] font-medium uppercase">
        <GitBranch size={11} />
        Path
      </div>
      <div className="flex flex-wrap items-center gap-1 text-[11px]">
        {events.map((event, index) => (
          <span key={`${event.id}-${index}`} className="contents">
            {index > 0 && <span className="text-foreground/25">→</span>}
            <span className="bg-foreground/5 rounded px-1.5 py-0.5">
              {event.event_type === 'edge_selected'
                ? `${String(event.payload.trigger ?? 'edge')}:${String(event.payload.target ?? '')}`
                : String(event.payload.title ?? event.payload.node_id ?? event.event_type)}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}

function EventRow({ event, open, onToggle }: { event: ProfileTestRunEvent; open: boolean; onToggle: () => void }) {
  const label = eventLabels[event.event_type] ?? event.event_type;
  return (
    <div className="border-border rounded-md border bg-background/60">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="hover:bg-foreground/5 flex w-full items-center gap-2 px-2 py-1.5 text-left"
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <Badge tone={event.severity === 'error' ? 'error' : event.severity === 'warning' ? 'warning' : 'muted'}>
          {event.severity}
        </Badge>
        <span className="text-foreground/75 min-w-0 flex-1 truncate text-xs">{label}</span>
        {eventToolState(event).map((state) => (
          <Badge key={state} tone={state === 'error' || state === 'timeout' ? 'error' : state === 'live' ? 'warning' : 'safe'}>
            {state}
          </Badge>
        ))}
        <span className="text-foreground/35 hidden font-mono text-[10px] sm:inline">{formatDate(event.timestamp)}</span>
        <span className="text-foreground/35 font-mono text-[10px]">#{event.seq}</span>
      </button>
      {open && (
        <pre className="text-foreground/60 max-h-56 overflow-auto border-t border-border px-2 py-2 text-[10px] leading-relaxed">
          {JSON.stringify(event.payload, null, 2)}
        </pre>
      )}
    </div>
  );
}

function Badge({ children, tone }: { children: React.ReactNode; tone: 'muted' | 'safe' | 'success' | 'warning' | 'error' }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] font-medium',
        tone === 'muted' && 'border-border bg-foreground/5 text-foreground/55',
        tone === 'safe' && 'border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
        tone === 'success' && 'border-green-500/25 bg-green-500/10 text-green-700 dark:text-green-300',
        tone === 'warning' && 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300',
        tone === 'error' && 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300'
      )}
    >
      {children}
    </span>
  );
}

export function findAssistantOutput(run: ProfileTestRunDetail | null): string | null {
  if (!run) return null;
  const summaryText = run.final_summary.assistant_output;
  if (typeof summaryText === 'string' && summaryText.trim()) return summaryText;
  const eventText = run.events.find((e) => e.event_type === 'assistant_output')?.payload.text;
  return typeof eventText === 'string' ? eventText : null;
}

export function graphPath(run: ProfileTestRunDetail | null): ProfileTestRunEvent[] {
  if (!run) return [];
  return run.events.filter((e) => e.event_type === 'node_entered' || e.event_type === 'edge_selected');
}

export function eventToolState(event: ProfileTestRunEvent): string[] {
  if (event.event_type !== 'tool_call') return [];
  const states: string[] = [];
  if (typeof event.payload.mode === 'string') states.push(event.payload.mode);
  if (event.payload.timed_out === true) states.push('timeout');
  else if (event.payload.executed === true) states.push('executed');
  else states.push('skipped');
  if ((event.payload.result as { success?: unknown } | undefined)?.success === false) states.push('error');
  return states;
}
