'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { deployApi, profilesApi } from '@/lib/admin-api';
import type { DeployLogs, DeployStatus, Profile } from '@/lib/admin-api';

const LOG_TYPES: Array<'deploy' | 'build'> = ['deploy', 'build'];

export default function DeployPage() {
  const [status, setStatus] = useState<DeployStatus | null>(null);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [logs, setLogs] = useState<DeployLogs | null>(null);
  const [logType, setLogType] = useState<'deploy' | 'build'>('deploy');
  const [loading, setLoading] = useState(true);
  const [logsLoading, setLogsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [logsError, setLogsError] = useState<string | null>(null);
  const [lastFetched, setLastFetched] = useState<Date | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [deploying, setDeploying] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const loadAll = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([deployApi.status(), profilesApi.list(true)])
      .then(([s, ps]) => {
        setStatus(s);
        setProfiles(ps);
        setLastFetched(new Date());
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const loadLogs = useCallback(() => {
    setLogsLoading(true);
    setLogsError(null);
    deployApi
      .logs(300, logType)
      .then(setLogs)
      .catch((e: Error) => setLogsError(e.message))
      .finally(() => setLogsLoading(false));
  }, [logType]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  const livePlaceholder = useMemo(() => profiles.find((p) => p.is_live) || null, [profiles]);
  const others = useMemo(() => profiles.filter((p) => !p.is_live), [profiles]);
  const selected = useMemo(
    () => profiles.find((p) => p.id === selectedId) || null,
    [profiles, selectedId]
  );

  // Default selection: prefer live profile if clean (disabled), else first dirty.
  useEffect(() => {
    if (selectedId !== null) return;
    if (profiles.length === 0) return;
    const live = profiles.find((p) => p.is_live);
    if (live) setSelectedId(live.id);
    else setSelectedId(profiles[0].id);
  }, [profiles, selectedId]);

  const action = useMemo(() => {
    if (!selected) return { label: 'Deploy & Activate', disabled: true, slow: false };
    if (selected.is_live && !selected.is_dirty) {
      return { label: 'Already active', disabled: true, slow: false };
    }
    if (selected.is_live && selected.is_dirty) {
      return { label: 'Re-deploy', disabled: false, slow: true };
    }
    if (selected.is_dirty) {
      return { label: 'Deploy & Activate', disabled: false, slow: true };
    }
    return { label: 'Activate', disabled: false, slow: false };
  }, [selected]);

  const handleConfirm = async () => {
    if (!selected) return;
    setConfirmOpen(false);
    setDeploying(true);
    toast.info(
      action.slow
        ? `"${selected.name}" — build + rollout 需 3–6 分鐘…`
        : `切換 AGENT_PROFILE → "${selected.name}" 中…`
    );
    try {
      const result = await deployApi.switchProfile(selected.id);
      toast.success(
        result.mode === 'secret-only'
          ? `已切換 AGENT_PROFILE → ${result.active_profile}`
          : `已 deploy + 啟用 "${result.active_profile}"`
      );
      loadAll();
      loadLogs();
    } catch (e) {
      toast.error(`失敗: ${(e as Error).message}`);
    } finally {
      setDeploying(false);
    }
  };

  const agent = status?.agent;
  const secrets = status?.secrets || [];
  const activeProfileSecret = secrets.find((s) => s.Name === 'AGENT_PROFILE');

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold">Deploy</h2>
          <p className="text-foreground/60 text-sm">LiveKit Cloud agent and profile activation</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              loadAll();
              loadLogs();
            }}
            disabled={loading || logsLoading}
            title="Refresh status, profiles, and logs"
            className="border-border hover:bg-foreground/10 inline-flex items-center gap-1.5 rounded-md border px-2 py-1.5 text-xs disabled:opacity-50"
          >
            <span aria-hidden className={loading || logsLoading ? 'animate-spin' : ''}>
              ⟳
            </span>
            <span className="text-foreground/60">
              {lastFetched
                ? `updated ${lastFetched.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`
                : '—'}
            </span>
          </button>
        </div>
      </div>

      <div className="border-border bg-foreground/5 rounded-md border p-3 text-xs">
        <strong>Note:</strong> Secret <em>values</em> are hidden by the{' '}
        <code className="rounded bg-black/20 px-1">lk</code> CLI. The active profile shown below is
        tracked by this admin UI — if someone flips <code>AGENT_PROFILE</code> via the{' '}
        <code>lk</code> CLI directly, it may go stale until the next admin-UI action.
      </div>

      {error ? (
        <div className="rounded-md border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-700 dark:text-red-400">
          <div className="mb-2 font-medium">Failed to fetch status</div>
          <pre className="text-xs whitespace-pre-wrap">{error}</pre>
        </div>
      ) : loading && !status ? (
        <div className="space-y-3">
          <div className="bg-foreground/10 h-24 w-full animate-pulse rounded" />
          <div className="bg-foreground/10 h-48 w-full animate-pulse rounded" />
        </div>
      ) : (
        <>
          <section>
            <h3 className="mb-2 text-lg font-semibold">Agent</h3>
            {agent ? (
              <div className="border-border overflow-hidden rounded-md border">
                <table className="w-full text-sm">
                  <tbody>
                    <StatusRow label="ID" value={<code>{agent.ID}</code>} />
                    <StatusRow label="Version" value={<code>{agent.Version}</code>} />
                    <StatusRow
                      label="Status"
                      value={
                        <span
                          className={`rounded px-2 py-0.5 text-xs ${statusBadge(agent.Status)}`}
                        >
                          {agent.Status}
                        </span>
                      }
                    />
                    <StatusRow label="Region" value={agent.Region} />
                    <StatusRow label="Replicas" value={agent.Replicas} />
                    <StatusRow label="CPU" value={agent.CPU} />
                    <StatusRow label="Memory" value={agent.Mem} />
                    <StatusRow
                      label="Deployed At"
                      value={
                        <span title={agent['Deployed At']}>{formatIso(agent['Deployed At'])}</span>
                      }
                    />
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-foreground/60 text-sm">No agent deployed.</p>
            )}
          </section>

          <section>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-lg font-semibold">Active profile</h3>
              {livePlaceholder && (
                <span className="text-foreground/50 text-xs">
                  {livePlaceholder.is_dirty ? 'has un-deployed edits' : 'up to date'}
                </span>
              )}
            </div>
            {profiles.length === 0 ? (
              <p className="text-foreground/60 text-sm">No active profiles in DB.</p>
            ) : (
              <div className="border-border overflow-hidden rounded-md border">
                <div className="divide-border divide-y">
                  {livePlaceholder && (
                    <ProfileRow
                      profile={livePlaceholder}
                      selected={selectedId === livePlaceholder.id}
                      onSelect={() => setSelectedId(livePlaceholder.id)}
                      isLive
                    />
                  )}
                  {!livePlaceholder && (
                    <div className="text-foreground/50 p-3 text-xs">
                      No live profile recorded yet. Pick one below and deploy to make it live.
                    </div>
                  )}
                </div>
              </div>
            )}
          </section>

          <section>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-lg font-semibold">Switch to</h3>
              <span className="text-foreground/50 text-xs">
                {others.length} other profile{others.length === 1 ? '' : 's'}
              </span>
            </div>
            {others.length === 0 ? (
              <p className="text-foreground/60 text-sm">No other active profiles.</p>
            ) : (
              <div className="border-border overflow-hidden rounded-md border">
                <div className="divide-border divide-y">
                  {others.map((p) => (
                    <ProfileRow
                      key={p.id}
                      profile={p}
                      selected={selectedId === p.id}
                      onSelect={() => setSelectedId(p.id)}
                    />
                  ))}
                </div>
              </div>
            )}
          </section>

          <div className="flex items-center justify-end gap-3">
            {selected && (
              <span className="text-foreground/60 text-xs">
                Target: <code className="font-mono">{selected.name}</code>
                {action.slow ? ' · slow (3–6 min)' : action.disabled ? '' : ' · fast (~60s)'}
              </span>
            )}
            <button
              onClick={() => setConfirmOpen(true)}
              disabled={action.disabled || deploying}
              className="bg-primary text-primary-foreground rounded-md px-4 py-2 text-sm font-medium transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
              title={
                action.slow ? 'Deploy YAML + set AGENT_PROFILE (3–6 min)' : 'Set AGENT_PROFILE'
              }
            >
              {deploying ? 'Deploying…' : action.label}
            </button>
          </div>

          <ConfirmDialog
            open={confirmOpen}
            title={action.slow ? 'Deploy & activate this profile?' : 'Activate this profile?'}
            description={
              selected
                ? action.slow
                  ? `將匯出 "${selected.name}" 的 YAML、重新 build + rollout Cloud image，並設為 active。通常需 3–6 分鐘。`
                  : `將 AGENT_PROFILE 切換至 "${selected.name}"。通常約 60 秒。`
                : ''
            }
            confirmLabel={action.label}
            cancelLabel="Cancel"
            onConfirm={handleConfirm}
            onCancel={() => setConfirmOpen(false)}
          />

          <section>
            <h3 className="mb-2 text-lg font-semibold">Secrets</h3>
            {activeProfileSecret && (
              <p className="text-foreground/60 mb-2 text-xs">
                <code className="rounded bg-black/20 px-1">AGENT_PROFILE</code> last updated:{' '}
                {formatIso(activeProfileSecret['Updated At'])}
              </p>
            )}
            {secrets.length === 0 ? (
              <p className="text-foreground/60 text-sm">No secrets configured.</p>
            ) : (
              <div className="border-border overflow-hidden rounded-md border">
                <table className="w-full text-sm">
                  <thead className="border-border text-foreground/60 bg-foreground/5 border-b">
                    <tr>
                      <th className="p-3 text-left font-medium">Name</th>
                      <th className="p-3 text-left font-medium">Created</th>
                      <th className="p-3 text-left font-medium">Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {secrets.map((s) => (
                      <tr key={s.Name} className="border-border border-b last:border-0">
                        <td className="p-3 font-mono text-xs">{s.Name}</td>
                        <td className="text-foreground/70 p-3 text-xs">
                          {formatIso(s['Created At'])}
                        </td>
                        <td className="text-foreground/70 p-3 text-xs">
                          {formatIso(s['Updated At'])}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}

      <section>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-lg font-semibold">Logs</h3>
          <div className="flex items-center gap-2">
            <div className="border-border inline-flex overflow-hidden rounded border text-xs">
              {LOG_TYPES.map((t) => (
                <button
                  key={t}
                  onClick={() => setLogType(t)}
                  className={`px-2 py-1 ${
                    logType === t ? 'bg-foreground/10 font-medium' : 'hover:bg-foreground/5'
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
            <button
              onClick={loadLogs}
              disabled={logsLoading}
              aria-label="Refresh logs"
              title="Refresh logs"
              className="border-border hover:bg-foreground/10 rounded border px-2 py-1 text-xs disabled:opacity-50"
            >
              <span className={logsLoading ? 'inline-block animate-spin' : 'inline-block'}>⟳</span>
            </button>
          </div>
        </div>
        {logsError ? (
          <div className="rounded-md border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-700 dark:text-red-400">
            {logsError}
          </div>
        ) : (
          <pre className="border-border text-foreground/90 max-h-[480px] overflow-auto rounded-md border bg-black/80 p-3 text-xs leading-relaxed text-green-200">
            {logsLoading && !logs
              ? 'Fetching logs…'
              : (logs?.lines || []).join('\n') || '(no log output)'}
          </pre>
        )}
      </section>
    </div>
  );
}

function ProfileRow({
  profile,
  selected,
  onSelect,
  isLive = false,
}: {
  profile: Profile;
  selected: boolean;
  onSelect: () => void;
  isLive?: boolean;
}) {
  return (
    <label
      className={`flex cursor-pointer items-center gap-3 p-3 transition-colors ${
        selected ? 'bg-primary/5' : 'hover:bg-foreground/5'
      }`}
    >
      <input
        type="radio"
        name="target-profile"
        checked={selected}
        onChange={onSelect}
        className="accent-primary"
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm">{profile.name}</span>
          {profile.display_name && (
            <span className="text-foreground/60 truncate text-xs">{profile.display_name}</span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2">
        {isLive && (
          <span className="rounded bg-green-500/20 px-2 py-0.5 text-xs text-green-700 dark:text-green-400">
            current
          </span>
        )}
        {profile.is_dirty ? (
          <span
            className="rounded bg-amber-500/20 px-2 py-0.5 text-xs text-amber-700 dark:text-amber-400"
            title="DB has un-deployed edits"
          >
            ● dirty
          </span>
        ) : (
          <span className="bg-foreground/10 text-foreground/60 rounded px-2 py-0.5 text-xs">
            clean
          </span>
        )}
        {profile.last_deployed_at && (
          <span
            className="text-foreground/50 text-[10px]"
            title={new Date(profile.last_deployed_at).toLocaleString()}
          >
            {formatDate(profile.last_deployed_at)}
          </span>
        )}
      </div>
    </label>
  );
}

function StatusRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <tr className="border-border border-b last:border-0">
      <td className="text-foreground/60 w-40 p-3 text-xs font-medium">{label}</td>
      <td className="p-3 text-sm">{value}</td>
    </tr>
  );
}

function statusBadge(s: string): string {
  const v = s.toLowerCase();
  if (v === 'running') return 'bg-green-500/20 text-green-700 dark:text-green-400';
  if (v === 'sleeping') return 'bg-blue-500/20 text-blue-700 dark:text-blue-400';
  if (v === 'failed' || v === 'error') return 'bg-red-500/20 text-red-700 dark:text-red-400';
  return 'bg-gray-500/20 text-gray-600 dark:text-gray-400';
}

function formatIso(iso: string): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}`;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}`;
}
