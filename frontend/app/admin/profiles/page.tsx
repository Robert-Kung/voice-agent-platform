'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { toast } from 'sonner';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { profilesApi, testApi } from '@/lib/admin-api';
import type { Profile } from '@/lib/admin-api';

const TOOL_CHIP_LIMIT = 3;

export default function ProfilesPage() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showInactive, setShowInactive] = useState(false);
  const [search, setSearch] = useState('');
  const [pendingDeactivate, setPendingDeactivate] = useState<Profile | null>(null);
  const [expandedTools, setExpandedTools] = useState<Record<string, boolean>>({});

  const load = () => {
    setLoading(true);
    profilesApi
      .list(!showInactive)
      .then(setProfiles)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showInactive]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return profiles;
    return profiles.filter(
      (p) => p.name.toLowerCase().includes(q) || (p.display_name || '').toLowerCase().includes(q)
    );
  }, [profiles, search]);

  const handleDeactivate = async (profile: Profile) => {
    setPendingDeactivate(null);
    try {
      await profilesApi.deactivate(profile.id);
      toast.success(`Profile "${profile.name}" 已停用`);
      load();
    } catch (e) {
      toast.error(`停用失敗: ${(e as Error).message}`);
    }
  };

  const handleReactivate = async (profile: Profile) => {
    try {
      await profilesApi.reactivate(profile.id);
      toast.success(`Profile "${profile.name}" 已啟用`);
      load();
    } catch (e) {
      toast.error(`啟用失敗: ${(e as Error).message}`);
    }
  };

  const handleTry = async (profile: Profile) => {
    // Open the new tab synchronously inside the click handler so popup blockers
    // count it as a user-initiated navigation. window.open() called *after* an
    // await is treated as a programmatic popup and gets blocked in default
    // Chrome/Firefox/Safari settings — the user would click Try and see nothing
    // happen. We point the placeholder tab at the final URL once the API
    // returns, or close it on error.
    const tab = window.open('', '_blank');
    try {
      const { room } = await testApi.start(profile.name);
      const url = `/?room=${encodeURIComponent(room)}`;
      if (tab && !tab.closed) {
        tab.location.href = url;
      } else {
        // User had popups blocked despite the synchronous open — fall back to
        // same-tab navigation so they still get the test session.
        window.location.href = url;
      }
    } catch (e) {
      tab?.close();
      toast.error(`無法啟動測試 agent: ${(e as Error).message}`);
    }
  };

  if (loading)
    return (
      <div className="space-y-3">
        <div className="bg-foreground/10 h-8 w-32 animate-pulse rounded" />
        <div className="bg-foreground/10 h-12 w-full animate-pulse rounded" />
        <div className="bg-foreground/10 h-12 w-full animate-pulse rounded" />
      </div>
    );
  if (error) return <div className="text-red-500">Error: {error}</div>;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold">Profiles</h2>
          <p className="text-foreground/60 text-sm">Agent configuration profiles</p>
        </div>
        <Link
          href="/admin/profiles/new"
          className="bg-primary text-primary-foreground rounded-md px-3 py-1.5 text-sm font-medium transition-opacity hover:opacity-90"
        >
          + New Profile
        </Link>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by name or display name…"
          className="border-border bg-background text-foreground focus:ring-primary/40 min-w-[240px] flex-1 rounded-md border px-3 py-1.5 text-sm focus:ring-2 focus:outline-none"
        />
        <label className="flex items-center gap-2 text-sm whitespace-nowrap">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(e) => setShowInactive(e.target.checked)}
          />
          Show inactive
        </label>
        <span className="text-foreground/60 text-xs">
          {filtered.length} / {profiles.length}
        </span>
      </div>

      {filtered.length === 0 ? (
        <div className="border-border text-foreground/60 rounded-md border p-8 text-center">
          {search ? `沒有符合 "${search}" 的 profile` : '尚無 profile，點右上角建立第一個。'}
        </div>
      ) : (
        <div className="border-border overflow-hidden rounded-md border">
          <table className="w-full text-sm">
            <thead className="border-border text-foreground/60 bg-foreground/5 border-b">
              <tr>
                <th className="p-3 text-left font-medium whitespace-nowrap">Name</th>
                <th className="p-3 text-left font-medium whitespace-nowrap">Display Name</th>
                <th className="p-3 text-left font-medium">Tools</th>
                <th className="p-3 text-left font-medium whitespace-nowrap">Status</th>
                <th className="p-3 text-left font-medium whitespace-nowrap">Updated</th>
                <th className="p-3 text-right font-medium whitespace-nowrap">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((p) => {
                const tools = (p.config.tools as Array<{ name: string }> | undefined) || [];
                const expanded = expandedTools[p.id];
                const visibleTools = expanded ? tools : tools.slice(0, TOOL_CHIP_LIMIT);
                const overflow = tools.length - TOOL_CHIP_LIMIT;
                return (
                  <tr
                    key={p.id}
                    className="border-border hover:bg-foreground/5 border-b last:border-0"
                  >
                    <td className="p-3 font-mono text-xs whitespace-nowrap">
                      <Link
                        href={`/admin/profiles/${p.id}`}
                        className="text-primary hover:underline"
                      >
                        {p.name}
                      </Link>
                    </td>
                    <td className="p-3">{p.display_name}</td>
                    <td className="p-3">
                      {tools.length === 0 ? (
                        <span className="text-foreground/40 text-xs">(none)</span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {visibleTools.map((t) => (
                            <span
                              key={t.name}
                              className="border-border rounded border px-1.5 py-0.5 font-mono text-xs"
                            >
                              {t.name}
                            </span>
                          ))}
                          {!expanded && overflow > 0 && (
                            <button
                              type="button"
                              onClick={() =>
                                setExpandedTools((prev) => ({ ...prev, [p.id]: true }))
                              }
                              className="text-primary text-xs hover:underline"
                              title={tools
                                .slice(TOOL_CHIP_LIMIT)
                                .map((t) => t.name)
                                .join(', ')}
                            >
                              +{overflow} more
                            </button>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="p-3 whitespace-nowrap">
                      <div className="flex flex-col gap-1">
                        <span
                          className={`w-fit rounded px-2 py-0.5 text-xs ${
                            p.is_active
                              ? 'bg-green-500/20 text-green-700 dark:text-green-400'
                              : 'bg-gray-500/20 text-gray-600 dark:text-gray-400'
                          }`}
                        >
                          {p.is_active ? 'active' : 'inactive'}
                        </span>
                        {p.is_active && p.is_dirty && (
                          <span
                            className="w-fit rounded bg-amber-500/20 px-2 py-0.5 text-xs text-amber-700 dark:text-amber-400"
                            title="DB 有未 deploy 變更；啟用時會自動走完整 deploy"
                          >
                            ● dirty
                          </span>
                        )}
                        {p.is_active && !p.is_dirty && p.last_deployed_at && (
                          <span
                            className="text-foreground/50 text-[10px]"
                            title={new Date(p.last_deployed_at).toLocaleString()}
                          >
                            deployed {formatDate(p.last_deployed_at)}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="text-foreground/70 p-3 text-xs whitespace-nowrap">
                      <span title={new Date(p.updated_at).toLocaleString()}>
                        {formatDate(p.updated_at)}
                      </span>
                    </td>
                    <td className="p-3 text-right whitespace-nowrap">
                      <div className="inline-flex items-center gap-2">
                        <Link
                          href={`/admin/profiles/${p.id}`}
                          className="border-border hover:bg-foreground/10 rounded border px-2 py-1 text-xs"
                        >
                          Edit
                        </Link>
                        {p.is_active && (
                          <button
                            type="button"
                            onClick={() => handleTry(p)}
                            className="border-border hover:bg-foreground/10 rounded border px-2 py-1 text-xs"
                            title="啟動本機 connect-mode agent 並開啟測試頁"
                          >
                            Try
                          </button>
                        )}
                        {p.is_active ? (
                          <button
                            type="button"
                            onClick={() => setPendingDeactivate(p)}
                            className="rounded border border-red-500/40 px-2 py-1 text-xs text-red-600 hover:bg-red-500/10 dark:text-red-400"
                          >
                            Deactivate
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={() => handleReactivate(p)}
                            className="rounded border border-green-500/40 px-2 py-1 text-xs text-green-700 hover:bg-green-500/10 dark:text-green-400"
                          >
                            Reactivate
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={pendingDeactivate !== null}
        title="Deactivate profile?"
        description={
          pendingDeactivate
            ? `Profile "${pendingDeactivate.name}" 將被停用。可隨時透過 Reactivate 還原。`
            : ''
        }
        confirmLabel="Deactivate"
        cancelLabel="Cancel"
        variant="destructive"
        onConfirm={() => pendingDeactivate && handleDeactivate(pendingDeactivate)}
        onCancel={() => setPendingDeactivate(null)}
      />
    </div>
  );
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}`;
}
