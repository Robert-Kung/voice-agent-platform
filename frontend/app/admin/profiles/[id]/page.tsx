'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { profilesApi, testApi, toolsApi } from '@/lib/admin-api';
import type { Profile } from '@/lib/admin-api';

const KNOWN_KEYS = [
  'name',
  'agent_name',
  'language',
  'timezone',
  'welcome_message',
  'welcome_instructions',
  'human_operator',
  'qa_mode',
  'qa_data',
  'services',
  // Legacy flat fields kept for backward-compat with un-migrated profiles
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

type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
type ParamType = 'string' | 'number' | 'integer' | 'boolean';
type QaMode = 'inline' | 'tool';

type HumanOperatorConfig = {
  enabled?: boolean;
  greeting?: string;
  instructions?: string;
  voice?: string;
  transfer_message?: string;
};

type QaEntry = {
  keywords: string[];
  answer: string;
};

// Services schema is loose because every business has different shapes.
// We expose the most common fields structurally; the rest stays as-is in
// the underlying object and shows in Advanced JSON.
type ServiceConfig = {
  always_open?: boolean;
  hours_text?: string | Record<string, string>;
  closed_days?: number[];
  schedule?: Record<string, { start: string; end: string }>;
};

type HttpToolParam = {
  name: string;
  type: ParamType;
  required?: boolean;
  description?: string;
};

// Built-in tools have just { name, config? }; Tier 3 HTTP tools also carry
// endpoint/method/auth/parameters. Backend distinguishes by `endpoint` presence.
type ToolEntry = {
  name: string;
  config?: unknown;
  description?: string;
  endpoint?: string;
  method?: HttpMethod;
  auth_header?: string;
  timeout_seconds?: number;
  parameters?: HttpToolParam[];
};

const HTTP_METHODS: HttpMethod[] = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];
const PARAM_TYPES: ParamType[] = ['string', 'number', 'integer', 'boolean'];

interface KnownConfig {
  name?: string;
  agent_name?: string;
  language?: string;
  timezone?: string;
  welcome_message?: string;
  welcome_instructions?: string;
  human_operator?: HumanOperatorConfig;
  qa_mode?: QaMode;
  qa_data?: QaEntry[];
  services?: Record<string, ServiceConfig>;
  // Legacy
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

/** Migrate legacy flat human_operator_* fields into the namespace block.
 *  YAML on disk may still have the old shape; we normalise on read so the UI
 *  always sees one consistent structure. The flat keys are dropped from `known`
 *  so they don't get re-saved alongside the namespace.
 */
function migrateLegacyHumanOperator(known: KnownConfig): KnownConfig {
  const hasLegacy =
    known.human_operator_instructions !== undefined || known.human_operator_greeting !== undefined;
  if (!hasLegacy) return known;
  const ho: HumanOperatorConfig = { ...(known.human_operator || {}) };
  if (ho.enabled === undefined) ho.enabled = true; // legacy schema implied enabled
  if (ho.instructions === undefined && known.human_operator_instructions) {
    ho.instructions = known.human_operator_instructions;
  }
  if (ho.greeting === undefined && known.human_operator_greeting) {
    ho.greeting = known.human_operator_greeting;
  }
  const out = { ...known, human_operator: ho };
  delete out.human_operator_instructions;
  delete out.human_operator_greeting;
  return out;
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
  const [trying, setTrying] = useState(false);
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
        const { known: raw, extra } = splitConfig(p.config || {});
        const k = migrateLegacyHumanOperator(raw);
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

  // ── Tier 3 HTTP tool CRUD ────────────────────────────────
  const addHttpTool = () => {
    setKnown((prev) => {
      const tools = prev.tools || [];
      const placeholder: ToolEntry = {
        name: `http_tool_${tools.filter((t) => !!t.endpoint).length + 1}`,
        description: '',
        endpoint: 'https://',
        method: 'POST',
        parameters: [],
      };
      return { ...prev, tools: [...tools, placeholder] };
    });
  };

  const updateHttpTool = (idx: number, patch: Partial<ToolEntry>) => {
    setKnown((prev) => {
      const tools = [...(prev.tools || [])];
      tools[idx] = { ...tools[idx], ...patch };
      return { ...prev, tools };
    });
  };

  const removeHttpTool = (idx: number) => {
    setKnown((prev) => ({
      ...prev,
      tools: (prev.tools || []).filter((_, i) => i !== idx),
    }));
  };

  const updateHttpToolParam = (
    toolIdx: number,
    paramIdx: number,
    patch: Partial<HttpToolParam>
  ) => {
    setKnown((prev) => {
      const tools = [...(prev.tools || [])];
      const params = [...(tools[toolIdx].parameters || [])];
      params[paramIdx] = { ...params[paramIdx], ...patch };
      tools[toolIdx] = { ...tools[toolIdx], parameters: params };
      return { ...prev, tools };
    });
  };

  const addHttpToolParam = (toolIdx: number) => {
    setKnown((prev) => {
      const tools = [...(prev.tools || [])];
      const params = [...(tools[toolIdx].parameters || [])];
      params.push({ name: '', type: 'string' });
      tools[toolIdx] = { ...tools[toolIdx], parameters: params };
      return { ...prev, tools };
    });
  };

  const removeHttpToolParam = (toolIdx: number, paramIdx: number) => {
    setKnown((prev) => {
      const tools = [...(prev.tools || [])];
      const params = (tools[toolIdx].parameters || []).filter((_, i) => i !== paramIdx);
      tools[toolIdx] = { ...tools[toolIdx], parameters: params };
      return { ...prev, tools };
    });
  };

  // ── Handoff (human_operator namespace) ────────────────────
  const updateHandoff = <K extends keyof HumanOperatorConfig>(
    key: K,
    value: HumanOperatorConfig[K]
  ) => {
    setKnown((prev) => ({
      ...prev,
      human_operator: { ...(prev.human_operator || {}), [key]: value },
    }));
  };

  // ── QA Database CRUD ──────────────────────────────────────
  const setQaMode = (mode: QaMode) => {
    setKnown((prev) => ({ ...prev, qa_mode: mode }));
  };

  const addQaEntry = () => {
    setKnown((prev) => ({
      ...prev,
      qa_data: [...(prev.qa_data || []), { keywords: [], answer: '' }],
    }));
  };

  const updateQaEntry = (idx: number, patch: Partial<QaEntry>) => {
    setKnown((prev) => {
      const list = [...(prev.qa_data || [])];
      list[idx] = { ...list[idx], ...patch };
      return { ...prev, qa_data: list };
    });
  };

  const removeQaEntry = (idx: number) => {
    setKnown((prev) => ({
      ...prev,
      qa_data: (prev.qa_data || []).filter((_, i) => i !== idx),
    }));
  };

  // ── Services CRUD ─────────────────────────────────────────
  const addService = () => {
    setKnown((prev) => {
      const services = { ...(prev.services || {}) };
      // Find first available service_N name
      let i = 1;
      while (services[`service_${i}`]) i += 1;
      services[`service_${i}`] = { always_open: false, hours_text: '' };
      return { ...prev, services };
    });
  };

  const renameService = (oldKey: string, newKey: string) => {
    if (!newKey || oldKey === newKey) return;
    setKnown((prev) => {
      const services = { ...(prev.services || {}) };
      if (services[newKey]) return prev; // refuse collision
      services[newKey] = services[oldKey];
      delete services[oldKey];
      return { ...prev, services };
    });
  };

  const updateService = (key: string, patch: Partial<ServiceConfig>) => {
    setKnown((prev) => {
      const services = { ...(prev.services || {}) };
      services[key] = { ...services[key], ...patch };
      return { ...prev, services };
    });
  };

  const removeService = (key: string) => {
    setKnown((prev) => {
      const services = { ...(prev.services || {}) };
      delete services[key];
      return { ...prev, services };
    });
  };

  const handleTry = async () => {
    if (!profile || isNew) return;
    if (isDirty) {
      toast.error('有未儲存變更。先儲存後再 Try（Try 跑的是 DB 最新版本）。');
      return;
    }
    setTrying(true);
    try {
      const { room } = await testApi.start(profile.name);
      window.open(`/?room=${encodeURIComponent(room)}`, '_blank');
    } catch (e) {
      toast.error(`無法啟動測試 agent: ${(e as Error).message}`);
    } finally {
      setTrying(false);
    }
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
        const { known: raw, extra } = splitConfig(updated.config || {});
        const k = migrateLegacyHumanOperator(raw);
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

  // Built-in tools = entries without `endpoint`; Tier 3 HTTP tools = entries with `endpoint`
  const builtinSelected = new Set(
    (known.tools || []).filter((t) => !t.endpoint).map((t) => t.name)
  );
  const httpTools = (known.tools || []).filter((t) => !!t.endpoint);
  const httpToolIndices = (known.tools || [])
    .map((t, i) => (t.endpoint ? i : -1))
    .filter((i) => i >= 0);
  const inputClass =
    'border-border bg-background text-foreground w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40';
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
              <p className="text-foreground/60 mt-1 text-xs">
                LiveKit worker 識別名稱（agent_name）
              </p>
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
            <label className="mb-1 block text-sm font-medium">
              Welcome Message <span className="text-foreground/50">(pipeline 逐字 TTS)</span>
            </label>
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
              Welcome Instructions{' '}
              <span className="text-foreground/50">(realtime 模式 Gemini 描述性提示)</span>
            </label>
            <textarea
              value={known.welcome_instructions ?? ''}
              onChange={(e) => updateKnown('welcome_instructions', e.target.value)}
              rows={3}
              placeholder="向來電者打招呼，簡短介紹自己並詢問需要什麼協助。"
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

        {/* Handoff (Human Operator) */}
        <section className="border-border space-y-3 rounded-md border p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-foreground/70 text-sm font-semibold tracking-wide uppercase">
              Handoff to Human
            </h3>
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={!!known.human_operator?.enabled}
                onChange={(e) => updateHandoff('enabled', e.target.checked)}
              />
              啟用真人轉接
            </label>
          </div>
          <p className="text-foreground/60 text-xs">
            開啟後 agent 會掛上 <code>transfer_to_human</code> 工具。LLM 在無法回答 /
            使用者要求轉接時會切換到人工 persona（不同聲音 + 你寫的 instructions）。
          </p>

          {known.human_operator?.enabled && (
            <div className="space-y-3 pt-1">
              <div>
                <label className="mb-1 block text-sm font-medium">Greeting (轉接後第一句)</label>
                <input
                  type="text"
                  value={known.human_operator?.greeting ?? ''}
                  onChange={(e) => updateHandoff('greeting', e.target.value)}
                  placeholder="親切告知已轉接門市人員，並詢問有什麼可以協助的。兩句話以內。"
                  className={inputClass}
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">
                  Instructions (人工 persona 的 system prompt)
                </label>
                <textarea
                  value={known.human_operator?.instructions ?? ''}
                  onChange={(e) => updateHandoff('instructions', e.target.value)}
                  rows={3}
                  placeholder="你是 XX 的門市人員。告知使用者已轉接成功…"
                  className={textareaClass}
                />
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <div>
                  <label className="mb-1 block text-sm font-medium">Voice (realtime)</label>
                  <input
                    type="text"
                    value={known.human_operator?.voice ?? ''}
                    onChange={(e) => updateHandoff('voice', e.target.value)}
                    placeholder="Puck"
                    className={inputClass}
                  />
                  <p className="text-foreground/60 mt-1 text-xs">
                    Gemini Live 聲音名稱（如 Puck / Kore / Charon）。預設 Puck，與主 agent Kore
                    區分讓使用者聽到切換。
                  </p>
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">Transfer Message</label>
                  <input
                    type="text"
                    value={known.human_operator?.transfer_message ?? ''}
                    onChange={(e) => updateHandoff('transfer_message', e.target.value)}
                    placeholder="正在為您轉接服務人員，請稍候。"
                    className={inputClass}
                  />
                </div>
              </div>
            </div>
          )}
        </section>

        {/* QA Database */}
        <section className="border-border space-y-3 rounded-md border p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-foreground/70 text-sm font-semibold tracking-wide uppercase">
              QA Database
            </h3>
            <div className="flex items-center gap-3">
              <span className="text-foreground/60 text-xs">{(known.qa_data || []).length} 條</span>
              <div className="border-border inline-flex overflow-hidden rounded border text-xs">
                {(['inline', 'tool'] as QaMode[]).map((m) => {
                  const active = (known.qa_mode ?? 'inline') === m;
                  return (
                    <button
                      key={m}
                      type="button"
                      onClick={() => setQaMode(m)}
                      className={`px-2 py-1 ${
                        active ? 'bg-foreground/10 font-medium' : 'hover:bg-foreground/5'
                      }`}
                      title={
                        m === 'inline'
                          ? 'QA 啟動時嵌入 instructions（零延遲、適合 ≤30 條）'
                          : 'LLM 透過 lookup_qa tool 查詢（QA 量大時用）'
                      }
                    >
                      {m === 'inline' ? 'Inline (推薦)' : 'Tool call'}
                    </button>
                  );
                })}
              </div>
              <button
                type="button"
                onClick={addQaEntry}
                className="border-border hover:bg-foreground/5 rounded border px-2 py-1 text-xs"
              >
                + Add QA
              </button>
            </div>
          </div>
          <p className="text-foreground/60 text-xs">
            <strong>Inline</strong>：啟動時把 QA 拼進 system instructions，零延遲（推薦）。
            <strong className="ml-2">Tool call</strong>：QA 量大塞不進 context 時改成 LLM 主動呼叫
            lookup_qa tool。
          </p>

          {(known.qa_data || []).length === 0 && (
            <p className="text-foreground/60 rounded-md border border-dashed py-4 text-center text-sm">
              尚無 QA 條目
            </p>
          )}
          <div className="space-y-2">
            {(known.qa_data || []).map((qa, idx) => (
              <div
                key={idx}
                className="border-border bg-foreground/5 space-y-2 rounded-md border p-3"
              >
                <div className="flex items-start gap-2">
                  <div className="flex-1">
                    <label className="text-foreground/70 mb-1 block text-xs">
                      Keywords（逗號或頓號分隔；substring 比對 → 越具體越精準）
                    </label>
                    <input
                      type="text"
                      value={(qa.keywords || []).join('、')}
                      onChange={(e) =>
                        updateQaEntry(idx, {
                          keywords: e.target.value
                            .split(/[,，、]/)
                            .map((k) => k.trim())
                            .filter(Boolean),
                        })
                      }
                      placeholder="費用、價格、多少錢"
                      className={inputClass}
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => removeQaEntry(idx)}
                    className="border-border hover:bg-foreground/10 mt-5 shrink-0 rounded border px-2 py-1 text-xs text-red-600 dark:text-red-400"
                  >
                    Remove
                  </button>
                </div>
                <div>
                  <label className="text-foreground/70 mb-1 block text-xs">Answer</label>
                  <textarea
                    value={qa.answer ?? ''}
                    onChange={(e) => updateQaEntry(idx, { answer: e.target.value })}
                    rows={2}
                    placeholder="代檢費用為 600 元，含證照費。"
                    className={textareaClass}
                  />
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Service Hours */}
        <section className="border-border space-y-3 rounded-md border p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-foreground/70 text-sm font-semibold tracking-wide uppercase">
              Service Hours
            </h3>
            <button
              type="button"
              onClick={addService}
              className="border-border hover:bg-foreground/5 rounded border px-2 py-1 text-xs"
            >
              + Add Service
            </button>
          </div>
          <p className="text-foreground/60 text-xs">
            營業時間會自動嵌入 instructions，搭配 <code>get_current_time</code> 工具讓 LLM
            自行判斷是否營業。 進階排程（schedule / closed_days）可在 Advanced JSON 編輯。
          </p>

          {Object.keys(known.services || {}).length === 0 && (
            <p className="text-foreground/60 rounded-md border border-dashed py-4 text-center text-sm">
              尚未設定營業時間
            </p>
          )}
          <div className="space-y-2">
            {Object.entries(known.services || {}).map(([key, svc]) => (
              <div
                key={key}
                className="border-border bg-foreground/5 space-y-2 rounded-md border p-3"
              >
                <div className="flex items-start gap-2">
                  <div className="flex-1">
                    <label className="text-foreground/70 mb-1 block text-xs">
                      Service Key (英數 + 底線)
                    </label>
                    <input
                      type="text"
                      defaultValue={key}
                      onBlur={(e) => renameService(key, e.target.value.trim())}
                      placeholder="inspection / restaurant / fuel"
                      className={inputClass + ' font-mono text-xs'}
                    />
                  </div>
                  <label className="mt-5 flex shrink-0 items-center gap-1 text-xs">
                    <input
                      type="checkbox"
                      checked={!!svc.always_open}
                      onChange={(e) => updateService(key, { always_open: e.target.checked })}
                    />
                    24h
                  </label>
                  <button
                    type="button"
                    onClick={() => removeService(key)}
                    className="border-border hover:bg-foreground/10 mt-5 shrink-0 rounded border px-2 py-1 text-xs text-red-600 dark:text-red-400"
                  >
                    Remove
                  </button>
                </div>
                <div>
                  <label className="text-foreground/70 mb-1 block text-xs">
                    Hours Text（口語化描述，自由格式）
                  </label>
                  <input
                    type="text"
                    value={typeof svc.hours_text === 'string' ? svc.hours_text : ''}
                    onChange={(e) => updateService(key, { hours_text: e.target.value })}
                    placeholder="平日上午 8 點至下午 6 點，週六上午 8 點至中午，週日休息"
                    disabled={typeof svc.hours_text === 'object'}
                    className={inputClass}
                  />
                  {typeof svc.hours_text === 'object' && (
                    <p className="text-foreground/60 mt-1 text-xs">
                      此服務使用結構化 hours_text（多時段），請在 Advanced JSON 編輯。
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Built-in Tools (Tier 1) */}
        <section className="border-border space-y-3 rounded-md border p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-foreground/70 text-sm font-semibold tracking-wide uppercase">
              Built-in Tools
            </h3>
            <span className="text-foreground/60 text-xs">
              {builtinSelected.size} / {availableTools.length} 啟用
            </span>
          </div>
          <p className="text-foreground/60 text-xs">
            內建通用工具。<code>lookup_qa</code> 與 <code>transfer_to_human</code> 由 QA / Handoff
            設定自動啟用，不在這裡勾選。
          </p>
          {availableTools.length === 0 ? (
            <p className="text-foreground/60 text-sm">無法載入工具清單</p>
          ) : (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {availableTools
                .filter((n) => n !== 'lookup_qa' && n !== 'transfer_to_human')
                .map((toolName) => {
                  const checked = builtinSelected.has(toolName);
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
                      </span>
                    </label>
                  );
                })}
            </div>
          )}
        </section>

        {/* Custom HTTP Tools (Tier 3) */}
        <section className="border-border space-y-3 rounded-md border p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-foreground/70 text-sm font-semibold tracking-wide uppercase">
              Custom HTTP Tools
            </h3>
            <button
              type="button"
              onClick={addHttpTool}
              className="border-border hover:bg-foreground/5 rounded border px-2 py-1 text-xs"
            >
              + Add HTTP Tool
            </button>
          </div>
          <p className="text-foreground/60 text-xs">
            把對話結果送到外部 API（例：通報故障、開單、查 CRM）。Endpoint 必須是公網 HTTPS；secret
            用 <code>{'${ENV_VAR}'}</code> 從環境變數取得。
          </p>
          {httpTools.length === 0 && (
            <p className="text-foreground/60 rounded-md border border-dashed py-4 text-center text-sm">
              尚未設定自定義 HTTP 工具
            </p>
          )}
          {httpTools.map((tool, htIdx) => {
            const realIdx = httpToolIndices[htIdx];
            return (
              <div
                key={realIdx}
                className="border-border bg-foreground/5 space-y-3 rounded-md border p-3"
              >
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    placeholder="tool_name (lowercase, snake_case)"
                    value={tool.name}
                    onChange={(e) => updateHttpTool(realIdx, { name: e.target.value })}
                    className={inputClass}
                  />
                  <button
                    type="button"
                    onClick={() => removeHttpTool(realIdx)}
                    className="border-border hover:bg-foreground/10 shrink-0 rounded border px-2 py-1 text-xs text-red-600 dark:text-red-400"
                  >
                    Remove
                  </button>
                </div>

                <div>
                  <label className="text-foreground/70 mb-1 block text-xs">
                    Description (給 LLM 看)
                  </label>
                  <input
                    type="text"
                    placeholder="例：通報電梯故障給維修人員"
                    value={tool.description || ''}
                    onChange={(e) => updateHttpTool(realIdx, { description: e.target.value })}
                    className={inputClass}
                  />
                </div>

                <div className="grid grid-cols-1 gap-2 md:grid-cols-[1fr_120px]">
                  <div>
                    <label className="text-foreground/70 mb-1 block text-xs">Endpoint URL</label>
                    <input
                      type="text"
                      placeholder="https://api.example.com/path"
                      value={tool.endpoint || ''}
                      onChange={(e) => updateHttpTool(realIdx, { endpoint: e.target.value })}
                      className={inputClass}
                    />
                  </div>
                  <div>
                    <label className="text-foreground/70 mb-1 block text-xs">Method</label>
                    <select
                      value={tool.method || 'POST'}
                      onChange={(e) =>
                        updateHttpTool(realIdx, { method: e.target.value as HttpMethod })
                      }
                      className={inputClass}
                    >
                      {HTTP_METHODS.map((m) => (
                        <option key={m} value={m}>
                          {m}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div>
                  <label className="text-foreground/70 mb-1 block text-xs">
                    Auth Header (optional, 支援 <code>{'${ENV_VAR}'}</code>)
                  </label>
                  <input
                    type="text"
                    placeholder="Bearer ${MY_API_KEY}"
                    value={tool.auth_header || ''}
                    onChange={(e) => updateHttpTool(realIdx, { auth_header: e.target.value })}
                    className={inputClass + ' font-mono text-xs'}
                  />
                </div>

                <div>
                  <div className="mb-1 flex items-center justify-between">
                    <label className="text-foreground/70 block text-xs">Parameters</label>
                    <button
                      type="button"
                      onClick={() => addHttpToolParam(realIdx)}
                      className="border-border hover:bg-foreground/5 rounded border px-2 py-0.5 text-xs"
                    >
                      + Param
                    </button>
                  </div>
                  {(tool.parameters || []).length === 0 && (
                    <p className="text-foreground/50 text-xs">尚無參數</p>
                  )}
                  <div className="space-y-2">
                    {(tool.parameters || []).map((param, pIdx) => (
                      <div
                        key={pIdx}
                        className="border-border grid grid-cols-1 gap-2 rounded-md border p-2 text-xs md:grid-cols-[1fr_100px_1fr_70px_auto]"
                      >
                        <input
                          type="text"
                          placeholder="param_name"
                          value={param.name}
                          onChange={(e) =>
                            updateHttpToolParam(realIdx, pIdx, { name: e.target.value })
                          }
                          className="border-border bg-background text-foreground rounded border px-2 py-1 font-mono text-xs"
                        />
                        <select
                          value={param.type}
                          onChange={(e) =>
                            updateHttpToolParam(realIdx, pIdx, {
                              type: e.target.value as ParamType,
                            })
                          }
                          className="border-border bg-background text-foreground rounded border px-2 py-1 text-xs"
                        >
                          {PARAM_TYPES.map((t) => (
                            <option key={t} value={t}>
                              {t}
                            </option>
                          ))}
                        </select>
                        <input
                          type="text"
                          placeholder="description（給 LLM 提示）"
                          value={param.description || ''}
                          onChange={(e) =>
                            updateHttpToolParam(realIdx, pIdx, { description: e.target.value })
                          }
                          className="border-border bg-background text-foreground rounded border px-2 py-1 text-xs"
                        />
                        <label className="flex items-center justify-center gap-1">
                          <input
                            type="checkbox"
                            checked={!!param.required}
                            onChange={(e) =>
                              updateHttpToolParam(realIdx, pIdx, { required: e.target.checked })
                            }
                          />
                          required
                        </label>
                        <button
                          type="button"
                          onClick={() => removeHttpToolParam(realIdx, pIdx)}
                          className="text-foreground/60 px-1 hover:text-red-600"
                          title="刪除參數"
                        >
                          ✕
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            );
          })}
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
                (進階排程 / 其他自訂欄位)
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
                className="border-border bg-background text-foreground w-full rounded-md border px-3 py-2 font-mono text-xs"
              />
              <p className="text-foreground/60 mt-2 text-xs">
                只放上方表單未涵蓋的欄位（如 services 內的 schedule / closed_days、其他客製欄位）。
                儲存時會與表單欄位合併。
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
            <button
              onClick={handleTry}
              disabled={trying || isDirty}
              title={
                isDirty
                  ? '先儲存變更，否則 Try 跑的會是上次儲存版本'
                  : '啟動本機 connect-mode agent 並開啟測試頁'
              }
              className="border-border hover:bg-foreground/5 rounded-md border px-4 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
            >
              {trying ? '啟動中…' : 'Try (本機)'}
            </button>
          )}
          {!isNew && (
            <Link
              href={`/admin/deploy?profile=${encodeURIComponent(profile.name)}`}
              className="border-border hover:bg-foreground/5 rounded-md border px-4 py-2 text-sm"
              title="到 Deploy 頁面把此 profile 上 LiveKit Cloud"
            >
              Deploy →
            </Link>
          )}
          {isDirty && <span className="text-xs text-amber-600 dark:text-amber-400">未儲存</span>}
        </div>
      </div>
    </div>
  );
}
