'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { profilesApi, toolsApi } from '@/lib/admin-api';
import type { Profile } from '@/lib/admin-api';

const KNOWN_KEYS = [
  'name',
  'agent_name',
  'language',
  'timezone',
  'welcome_message',
  'human_operator_instructions',
  'human_operator_greeting',
  'instructions',
  'tools',
] as const;

const LANGUAGES = [
  { value: 'zh', label: '中文 (zh)' },
  { value: 'en', label: 'English (en)' },
  { value: 'ja', label: '日本語 (ja)' },
];

const TIMEZONES = [
  'Asia/Taipei',
  'Asia/Tokyo',
  'Asia/Shanghai',
  'Asia/Hong_Kong',
  'America/Los_Angeles',
  'America/New_York',
  'UTC',
];

type ToolEntry = { name: string; config?: unknown };

interface KnownConfig {
  name?: string;
  agent_name?: string;
  language?: string;
  timezone?: string;
  welcome_message?: string;
  human_operator_instructions?: string;
  human_operator_greeting?: string;
  instructions?: string;
  tools?: ToolEntry[];
}

const NAME_PATTERN = /^[a-z][a-z0-9_]*$/;

function splitConfig(config: Record<string, unknown>): {
  known: KnownConfig;
  extra: Record<string, unknown>;
} {
  const known: KnownConfig = {};
  const extra: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(config)) {
    if ((KNOWN_KEYS as readonly string[]).includes(k)) {
      (known as Record<string, unknown>)[k] = v;
    } else {
      extra[k] = v;
    }
  }
  return { known, extra };
}

function buildConfig(known: KnownConfig, extra: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = { ...extra };
  for (const k of KNOWN_KEYS) {
    const v = known[k];
    if (v === undefined || v === '' || (Array.isArray(v) && v.length === 0)) continue;
    out[k] = v;
  }
  return out;
}

export default function ProfileDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;
  const isNew = id === 'new';

  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [name, setName] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [known, setKnown] = useState<KnownConfig>({ tools: [] });
  const [extraJson, setExtraJson] = useState('{}');
  const [showAdvanced, setShowAdvanced] = useState(false);

  const [availableTools, setAvailableTools] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [initialSnapshot, setInitialSnapshot] = useState<string>('');

  // Snapshot for dirty-check
  const currentSnapshot = useMemo(
    () => JSON.stringify({ name, displayName, known, extraJson }),
    [name, displayName, known, extraJson]
  );
  const isDirty = currentSnapshot !== initialSnapshot;

  useEffect(() => {
    toolsApi
      .list()
      .then(setAvailableTools)
      .catch(() => setAvailableTools([]));
  }, []);

  useEffect(() => {
    if (isNew) {
      const initialKnown: KnownConfig = {
        language: 'zh',
        timezone: 'Asia/Taipei',
        instructions: '',
        tools: [],
      };
      setProfile({
        id: 'new',
        name: '',
        display_name: '',
        description: '',
        is_active: true,
        is_dirty: true,
        is_live: false,
        last_deployed_at: null,
        config: initialKnown as Record<string, unknown>,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
      setName('');
      setDisplayName('');
      setKnown(initialKnown);
      setExtraJson('{}');
      setInitialSnapshot(
        JSON.stringify({ name: '', displayName: '', known: initialKnown, extraJson: '{}' })
      );
      setLoading(false);
      return;
    }

    profilesApi
      .get(id)
      .then((p) => {
        const { known: k, extra } = splitConfig(p.config || {});
        if (!k.tools) k.tools = [];
        const ej = Object.keys(extra).length ? JSON.stringify(extra, null, 2) : '{}';
        setProfile(p);
        setName(p.name);
        setDisplayName(p.display_name);
        setKnown(k);
        setExtraJson(ej);
        setInitialSnapshot(
          JSON.stringify({ name: p.name, displayName: p.display_name, known: k, extraJson: ej })
        );
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id, isNew]);

  // Warn on unload when dirty (P1 #7)
  useEffect(() => {
    if (!isDirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [isDirty]);

  const updateKnown = <K extends keyof KnownConfig>(key: K, value: KnownConfig[K]) => {
    setKnown((prev) => ({ ...prev, [key]: value }));
  };

  const toggleTool = (toolName: string) => {
    setKnown((prev) => {
      const tools = prev.tools || [];
      const exists = tools.find((t) => t.name === toolName);
      if (exists) {
        return { ...prev, tools: tools.filter((t) => t.name !== toolName) };
      }
      return { ...prev, tools: [...tools, { name: toolName }] };
    });
  };

  const handleSave = async () => {
    let extraObj: Record<string, unknown>;
    try {
      const parsed = extraJson.trim() ? JSON.parse(extraJson) : {};
      if (typeof parsed !== 'object' || Array.isArray(parsed) || parsed === null) {
        throw new Error('Advanced JSON must be an object');
      }
      extraObj = parsed as Record<string, unknown>;
    } catch (e) {
      toast.error(`Advanced JSON 解析失敗: ${(e as Error).message}`);
      setShowAdvanced(true);
      return;
    }

    if (isNew) {
      if (!NAME_PATTERN.test(name)) {
        toast.error('Profile name 必須是小寫字母開頭，僅含 a-z, 0-9, _');
        return;
      }
      if (!displayName.trim()) {
        toast.error('Display Name 不可為空');
        return;
      }
    }

    const finalConfig = buildConfig({ ...known, name: known.name || displayName }, extraObj);

    setSaving(true);
    try {
      if (isNew) {
        const created = await profilesApi.create({
          name,
          display_name: displayName,
          config: finalConfig,
        });
        toast.success(`Profile "${created.name}" 建立成功`);
        // Mark clean before navigation
        setInitialSnapshot(currentSnapshot);
        router.push(`/admin/profiles/${created.id}`);
      } else {
        const updated = await profilesApi.update(id, {
          display_name: displayName,
          config: finalConfig,
        });
        setProfile(updated);
        const { known: k, extra } = splitConfig(updated.config || {});
        if (!k.tools) k.tools = [];
        const ej = Object.keys(extra).length ? JSON.stringify(extra, null, 2) : '{}';
        setKnown(k);
        setExtraJson(ej);
        setInitialSnapshot(
          JSON.stringify({
            name: updated.name,
            displayName: updated.display_name,
            known: k,
            extraJson: ej,
          })
        );
        toast.success('Saved.');
      }
    } catch (e) {
      toast.error(`儲存失敗: ${(e as Error).message}`);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="text-foreground/60">Loading…</div>;
  if (error) return <div className="text-red-500">Error: {error}</div>;
  if (!profile) return <div>Profile not found.</div>;

  const selectedTools = new Set((known.tools || []).map((t) => t.name));
  const inputClass =
    'border-border w-full rounded-md border bg-transparent px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40';
  const textareaClass = `${inputClass} font-sans`;

  return (
    <div className="space-y-6">
      <div>
        <Link href="/admin/profiles" className="text-primary text-sm hover:underline">
          ← Back to profiles
        </Link>
      </div>

      <div>
        <h2 className="text-2xl font-bold">
          {isNew ? 'New Profile' : displayName || profile.name}
        </h2>
        {!isNew && (
          <p className="text-foreground/60 font-mono text-xs">
            {profile.name} · {profile.id}
          </p>
        )}
        {isDirty && !isNew && (
          <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">● 未儲存的變更</p>
        )}
      </div>

      <div className="space-y-5">
        {/* Identity */}
        <section className="border-border space-y-4 rounded-md border p-4">
          <h3 className="text-foreground/70 text-sm font-semibold tracking-wide uppercase">
            Identity
          </h3>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium">
                Name <span className="text-foreground/50">(unique, immutable)</span>
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={!isNew}
                placeholder="e.g. dental_clinic"
                pattern={NAME_PATTERN.source}
                className={`${inputClass} font-mono ${!isNew ? 'opacity-60' : ''}`}
              />
              {isNew && (
                <p className="text-foreground/60 mt-1 text-xs">
                  小寫字母開頭，僅含 <code>a-z 0-9 _</code>
                </p>
              )}
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Display Name</label>
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="例如：幸福牙醫診所"
                className={inputClass}
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Agent Name</label>
              <input
                type="text"
                value={known.agent_name ?? ''}
                onChange={(e) => updateKnown('agent_name', e.target.value)}
                placeholder="voice-assistant-clinic"
                className={`${inputClass} font-mono`}
              />
              <p className="text-foreground/60 mt-1 text-xs">LiveKit WorkerOptions 用</p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-sm font-medium">Language</label>
                <select
                  value={known.language ?? ''}
                  onChange={(e) => updateKnown('language', e.target.value)}
                  className={inputClass}
                >
                  <option value="">—</option>
                  {LANGUAGES.map((l) => (
                    <option key={l.value} value={l.value}>
                      {l.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Timezone</label>
                <select
                  value={known.timezone ?? ''}
                  onChange={(e) => updateKnown('timezone', e.target.value)}
                  className={inputClass}
                >
                  <option value="">—</option>
                  {TIMEZONES.map((tz) => (
                    <option key={tz} value={tz}>
                      {tz}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        </section>

        {/* Messages */}
        <section className="border-border space-y-4 rounded-md border p-4">
          <h3 className="text-foreground/70 text-sm font-semibold tracking-wide uppercase">
            Messages
          </h3>
          <div>
            <label className="mb-1 block text-sm font-medium">Welcome Message</label>
            <textarea
              value={known.welcome_message ?? ''}
              onChange={(e) => updateKnown('welcome_message', e.target.value)}
              rows={4}
              placeholder="進線第一句歡迎語…"
              className={textareaClass}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">
              Instructions <span className="text-foreground/50">(system prompt)</span>
            </label>
            <textarea
              value={known.instructions ?? ''}
              onChange={(e) => updateKnown('instructions', e.target.value)}
              rows={12}
              placeholder="主 Agent 的 system prompt…"
              className={textareaClass}
            />
          </div>
        </section>

        {/* Human Operator */}
        <section className="border-border space-y-4 rounded-md border p-4">
          <h3 className="text-foreground/70 text-sm font-semibold tracking-wide uppercase">
            Human Operator
          </h3>
          <div>
            <label className="mb-1 block text-sm font-medium">Operator Greeting</label>
            <input
              type="text"
              value={known.human_operator_greeting ?? ''}
              onChange={(e) => updateKnown('human_operator_greeting', e.target.value)}
              placeholder="親切告知已轉接櫃檯人員。兩句話以內。"
              className={inputClass}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Operator Instructions</label>
            <textarea
              value={known.human_operator_instructions ?? ''}
              onChange={(e) => updateKnown('human_operator_instructions', e.target.value)}
              rows={4}
              placeholder="轉人工後 Agent 的 system instructions…"
              className={textareaClass}
            />
          </div>
        </section>

        {/* Tools */}
        <section className="border-border space-y-3 rounded-md border p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-foreground/70 text-sm font-semibold tracking-wide uppercase">
              Tools
            </h3>
            <span className="text-foreground/60 text-xs">
              {selectedTools.size} / {availableTools.length} 啟用
            </span>
          </div>
          {availableTools.length === 0 ? (
            <p className="text-foreground/60 text-sm">無法載入工具清單</p>
          ) : (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {availableTools.map((toolName) => {
                const checked = selectedTools.has(toolName);
                const customConfig = (known.tools || []).find(
                  (t) => t.name === toolName && t.config !== undefined
                );
                return (
                  <label
                    key={toolName}
                    className={`flex cursor-pointer items-start gap-2 rounded-md border px-3 py-2 text-sm transition-colors ${
                      checked
                        ? 'border-primary/50 bg-primary/5'
                        : 'border-border hover:bg-foreground/5'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleTool(toolName)}
                      className="mt-0.5"
                    />
                    <span className="flex-1">
                      <span className="font-mono text-xs">{toolName}</span>
                      {customConfig && (
                        <span className="ml-1 text-xs text-amber-600 dark:text-amber-400">
                          (custom config)
                        </span>
                      )}
                    </span>
                  </label>
                );
              })}
            </div>
          )}
        </section>

        {/* Advanced JSON */}
        <section className="border-border rounded-md border">
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex w-full items-center justify-between p-4 text-left"
          >
            <span className="text-foreground/70 text-sm font-semibold tracking-wide uppercase">
              Advanced JSON
              <span className="text-foreground/50 ml-2 text-xs normal-case">
                (services / qa_data / 其他自訂欄位)
              </span>
            </span>
            <span className="text-foreground/60">{showAdvanced ? '▾' : '▸'}</span>
          </button>
          {showAdvanced && (
            <div className="border-border border-t p-4">
              <textarea
                value={extraJson}
                onChange={(e) => setExtraJson(e.target.value)}
                rows={15}
                spellCheck={false}
                className="border-border w-full rounded-md border bg-transparent px-3 py-2 font-mono text-xs"
              />
              <p className="text-foreground/60 mt-2 text-xs">
                只放上方表單未涵蓋的欄位（如 <code>services</code>、<code>qa_data</code>
                ）。儲存時會與表單欄位合併。
              </p>
            </div>
          )}
        </section>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || (!isDirty && !isNew)}
            className="bg-primary text-primary-foreground rounded-md px-4 py-2 text-sm font-medium transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {saving ? 'Saving…' : isNew ? 'Create Profile' : 'Save'}
          </button>
          {!isNew && (
            <Link
              href={`/?profile=${encodeURIComponent(profile.name)}`}
              className="border-border hover:bg-foreground/5 rounded-md border px-4 py-2 text-sm"
            >
              Try this profile →
            </Link>
          )}
          {isDirty && <span className="text-xs text-amber-600 dark:text-amber-400">未儲存</span>}
        </div>
      </div>
    </div>
  );
}
