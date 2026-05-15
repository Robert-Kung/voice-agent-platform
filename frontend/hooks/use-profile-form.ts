'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { profilesApi, testApi, toolsApi } from '@/lib/admin-api';
import type { Profile } from '@/lib/admin-api';

// ── Types ──────────────────────────────────────────────────────────

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
export type ParamType = 'string' | 'number' | 'integer' | 'boolean';
export type QaMode = 'inline' | 'tool';

export type HumanOperatorConfig = {
  enabled?: boolean;
  greeting?: string;
  instructions?: string;
  voice?: string;
  transfer_message?: string;
};

export type QaEntry = {
  keywords: string[];
  answer: string;
};

export type ServiceConfig = {
  always_open?: boolean;
  hours_text?: string | Record<string, string>;
  closed_days?: number[];
  schedule?: Record<string, { start: string; end: string }>;
};

export type HttpToolParam = {
  name: string;
  type: ParamType;
  required?: boolean;
  description?: string;
};

export type ToolEntry = {
  name: string;
  config?: unknown;
  description?: string;
  endpoint?: string;
  method?: HttpMethod;
  auth_header?: string;
  timeout_seconds?: number;
  parameters?: HttpToolParam[];
};

export interface KnownConfig {
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
  human_operator_instructions?: string;
  human_operator_greeting?: string;
  instructions?: string;
  tools?: ToolEntry[];
}

// ── Constants ──────────────────────────────────────────────────────

export const KNOWN_KEYS = [
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
  'human_operator_instructions',
  'human_operator_greeting',
  'instructions',
  'tools',
] as const;

export const LANGUAGES = [
  { value: 'zh', label: '中文 (zh)' },
  { value: 'en', label: 'English (en)' },
  { value: 'ja', label: '日本語 (ja)' },
];

export const TIMEZONES = [
  'Asia/Taipei',
  'Asia/Tokyo',
  'Asia/Shanghai',
  'Asia/Hong_Kong',
  'America/Los_Angeles',
  'America/New_York',
  'UTC',
];

export const HTTP_METHODS: HttpMethod[] = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];
export const PARAM_TYPES: ParamType[] = ['string', 'number', 'integer', 'boolean'];
export const NAME_PATTERN = /^[a-z][a-z0-9_]*$/;

const RENAMED_TOOLS: Record<string, string> = {
  get_current_datetime: 'get_current_time',
};
const DELETED_TOOL_NAMES = new Set([
  'check_business_status',
  'check_weather',
  'book_appointment',
  'search_menu',
  'calculate_price',
  'replay_last_prompt',
]);
const AUTO_MOUNTED_TOOLS = new Set(['lookup_qa', 'transfer_to_human']);

// ── Helpers ────────────────────────────────────────────────────────

export function splitConfig(config: Record<string, unknown>): {
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

export function migrateLegacyHumanOperator(known: KnownConfig): KnownConfig {
  const hasLegacy =
    known.human_operator_instructions !== undefined || known.human_operator_greeting !== undefined;
  if (!hasLegacy) return known;
  const ho: HumanOperatorConfig = { ...(known.human_operator || {}) };
  if (ho.enabled === undefined) ho.enabled = true;
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

export function cleanLegacyTools(known: KnownConfig): KnownConfig {
  const tools = known.tools || [];
  const seen = new Set<string>();
  const cleaned: ToolEntry[] = [];
  let changed = false;
  for (const t of tools) {
    if (t.endpoint) {
      cleaned.push(t);
      continue;
    }
    const renamed = RENAMED_TOOLS[t.name];
    if (renamed) {
      changed = true;
      if (seen.has(renamed)) continue;
      cleaned.push({ ...t, name: renamed });
      seen.add(renamed);
      continue;
    }
    if (DELETED_TOOL_NAMES.has(t.name) || AUTO_MOUNTED_TOOLS.has(t.name)) {
      changed = true;
      continue;
    }
    if (seen.has(t.name)) {
      changed = true;
      continue;
    }
    cleaned.push(t);
    seen.add(t.name);
  }
  if (!changed) return known;
  return { ...known, tools: cleaned };
}

export function buildConfig(
  known: KnownConfig,
  extra: Record<string, unknown>
): Record<string, unknown> {
  const out: Record<string, unknown> = { ...extra };
  for (const k of KNOWN_KEYS) {
    const v = known[k];
    if (v === undefined || v === '' || (Array.isArray(v) && v.length === 0)) continue;
    out[k] = v;
  }
  return out;
}

// ── Hook ───────────────────────────────────────────────────────────

export interface UseProfileFormReturn {
  // State
  profile: Profile | null;
  loading: boolean;
  error: string | null;
  name: string;
  setName: (v: string) => void;
  displayName: string;
  setDisplayName: (v: string) => void;
  known: KnownConfig;
  extraJson: string;
  setExtraJson: (v: string) => void;
  availableTools: string[];
  saving: boolean;
  trying: boolean;
  isDirty: boolean;
  isNew: boolean;

  // Computed
  builtinSelected: Set<string>;
  httpTools: ToolEntry[];
  httpToolIndices: number[];
  qaList: QaEntry[];

  // Actions
  updateKnown: <K extends keyof KnownConfig>(key: K, value: KnownConfig[K]) => void;
  toggleTool: (toolName: string) => void;
  addHttpTool: () => void;
  updateHttpTool: (idx: number, patch: Partial<ToolEntry>) => void;
  removeHttpTool: (idx: number) => void;
  updateHttpToolParam: (toolIdx: number, paramIdx: number, patch: Partial<HttpToolParam>) => void;
  addHttpToolParam: (toolIdx: number) => void;
  removeHttpToolParam: (toolIdx: number, paramIdx: number) => void;
  updateHandoff: <K extends keyof HumanOperatorConfig>(
    key: K,
    value: HumanOperatorConfig[K]
  ) => void;
  setQaMode: (mode: QaMode) => void;
  addQaEntry: () => void;
  updateQaEntry: (idx: number, patch: Partial<QaEntry>) => void;
  removeQaEntry: (idx: number) => void;
  addService: () => void;
  renameService: (oldKey: string, newKey: string) => void;
  updateService: (key: string, patch: Partial<ServiceConfig>) => void;
  removeService: (key: string) => void;
  handleSave: () => Promise<void>;
  handleTry: () => Promise<void>;
}

export function useProfileForm(): UseProfileFormReturn {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;
  const isNew = id === 'new';

  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [known, setKnown] = useState<KnownConfig>({ tools: [] });
  const [extraJson, setExtraJson] = useState('{}');

  const [availableTools, setAvailableTools] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [trying, setTrying] = useState(false);
  const [initialSnapshot, setInitialSnapshot] = useState<string>('');

  const currentSnapshot = useMemo(
    () => JSON.stringify({ name, displayName, known, extraJson }),
    [name, displayName, known, extraJson]
  );
  const isDirty = currentSnapshot !== initialSnapshot;

  // Load available tools
  useEffect(() => {
    toolsApi
      .list()
      .then(setAvailableTools)
      .catch(() => setAvailableTools([]));
  }, []);

  // Load profile
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
        const k = cleanLegacyTools(migrateLegacyHumanOperator(raw));
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

  // Warn on unload
  useEffect(() => {
    if (!isDirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [isDirty]);

  // ── Actions ──────────────────────────────────────────────────────

  const updateKnown = useCallback(<K extends keyof KnownConfig>(key: K, value: KnownConfig[K]) => {
    setKnown((prev) => ({ ...prev, [key]: value }));
  }, []);

  const toggleTool = useCallback((toolName: string) => {
    setKnown((prev) => {
      const tools = prev.tools || [];
      const exists = tools.find((t) => t.name === toolName);
      if (exists) {
        return { ...prev, tools: tools.filter((t) => t.name !== toolName) };
      }
      return { ...prev, tools: [...tools, { name: toolName }] };
    });
  }, []);

  const addHttpTool = useCallback(() => {
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
  }, []);

  const updateHttpTool = useCallback((idx: number, patch: Partial<ToolEntry>) => {
    setKnown((prev) => {
      const tools = [...(prev.tools || [])];
      tools[idx] = { ...tools[idx], ...patch };
      return { ...prev, tools };
    });
  }, []);

  const removeHttpTool = useCallback((idx: number) => {
    setKnown((prev) => ({
      ...prev,
      tools: (prev.tools || []).filter((_, i) => i !== idx),
    }));
  }, []);

  const updateHttpToolParam = useCallback(
    (toolIdx: number, paramIdx: number, patch: Partial<HttpToolParam>) => {
      setKnown((prev) => {
        const tools = [...(prev.tools || [])];
        const params = [...(tools[toolIdx].parameters || [])];
        params[paramIdx] = { ...params[paramIdx], ...patch };
        tools[toolIdx] = { ...tools[toolIdx], parameters: params };
        return { ...prev, tools };
      });
    },
    []
  );

  const addHttpToolParam = useCallback((toolIdx: number) => {
    setKnown((prev) => {
      const tools = [...(prev.tools || [])];
      const params = [...(tools[toolIdx].parameters || [])];
      params.push({ name: '', type: 'string' });
      tools[toolIdx] = { ...tools[toolIdx], parameters: params };
      return { ...prev, tools };
    });
  }, []);

  const removeHttpToolParam = useCallback((toolIdx: number, paramIdx: number) => {
    setKnown((prev) => {
      const tools = [...(prev.tools || [])];
      const params = (tools[toolIdx].parameters || []).filter((_, i) => i !== paramIdx);
      tools[toolIdx] = { ...tools[toolIdx], parameters: params };
      return { ...prev, tools };
    });
  }, []);

  const updateHandoff = useCallback(
    <K extends keyof HumanOperatorConfig>(key: K, value: HumanOperatorConfig[K]) => {
      setKnown((prev) => ({
        ...prev,
        human_operator: { ...(prev.human_operator || {}), [key]: value },
      }));
    },
    []
  );

  const setQaMode = useCallback((mode: QaMode) => {
    setKnown((prev) => ({ ...prev, qa_mode: mode }));
  }, []);

  const addQaEntry = useCallback(() => {
    setKnown((prev) => ({
      ...prev,
      qa_data: [...(prev.qa_data || []), { keywords: [], answer: '' }],
    }));
  }, []);

  const updateQaEntry = useCallback((idx: number, patch: Partial<QaEntry>) => {
    setKnown((prev) => {
      const list = [...(prev.qa_data || [])];
      list[idx] = { ...list[idx], ...patch };
      return { ...prev, qa_data: list };
    });
  }, []);

  const removeQaEntry = useCallback((idx: number) => {
    setKnown((prev) => ({
      ...prev,
      qa_data: (prev.qa_data || []).filter((_, i) => i !== idx),
    }));
  }, []);

  const addService = useCallback(() => {
    setKnown((prev) => {
      const services = { ...(prev.services || {}) };
      let i = 1;
      while (services[`service_${i}`]) i += 1;
      services[`service_${i}`] = { always_open: false, hours_text: '' };
      return { ...prev, services };
    });
  }, []);

  const renameService = useCallback((oldKey: string, newKey: string) => {
    if (!newKey || oldKey === newKey) return;
    setKnown((prev) => {
      const services = { ...(prev.services || {}) };
      if (services[newKey]) return prev;
      services[newKey] = services[oldKey];
      delete services[oldKey];
      return { ...prev, services };
    });
  }, []);

  const updateService = useCallback((key: string, patch: Partial<ServiceConfig>) => {
    setKnown((prev) => {
      const services = { ...(prev.services || {}) };
      services[key] = { ...services[key], ...patch };
      return { ...prev, services };
    });
  }, []);

  const removeService = useCallback((key: string) => {
    setKnown((prev) => {
      const services = { ...(prev.services || {}) };
      delete services[key];
      return { ...prev, services };
    });
  }, []);

  const handleTry = useCallback(async () => {
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
  }, [profile, isNew, isDirty]);

  const handleSave = useCallback(async () => {
    let extraObj: Record<string, unknown>;
    try {
      const parsed = extraJson.trim() ? JSON.parse(extraJson) : {};
      if (typeof parsed !== 'object' || Array.isArray(parsed) || parsed === null) {
        throw new Error('Advanced JSON must be an object');
      }
      extraObj = parsed as Record<string, unknown>;
    } catch (e) {
      toast.error(`Advanced JSON 解析失敗: ${(e as Error).message}`);
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
        setInitialSnapshot(currentSnapshot);
        router.push(`/admin/profiles/${created.id}/v2`);
      } else {
        const updated = await profilesApi.update(id, {
          display_name: displayName,
          config: finalConfig,
        });
        setProfile(updated);
        const { known: raw, extra } = splitConfig(updated.config || {});
        const k = cleanLegacyTools(migrateLegacyHumanOperator(raw));
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
  }, [name, displayName, known, extraJson, isNew, id, currentSnapshot, router]);

  // ── Computed ─────────────────────────────────────────────────────

  const builtinSelected = useMemo(
    () =>
      new Set(
        (known.tools || [])
          .filter((t) => !t.endpoint)
          .map((t) => t.name)
          .filter((n) => availableTools.includes(n))
      ),
    [known.tools, availableTools]
  );

  const httpTools = useMemo(() => (known.tools || []).filter((t) => !!t.endpoint), [known.tools]);

  const httpToolIndices = useMemo(
    () =>
      (known.tools || []).map((t, i) => (t.endpoint ? i : -1)).filter((i) => i >= 0),
    [known.tools]
  );

  const qaList = useMemo(() => known.qa_data || [], [known.qa_data]);

  return {
    profile,
    loading,
    error,
    name,
    setName,
    displayName,
    setDisplayName,
    known,
    extraJson,
    setExtraJson,
    availableTools,
    saving,
    trying,
    isDirty,
    isNew,
    builtinSelected,
    httpTools,
    httpToolIndices,
    qaList,
    updateKnown,
    toggleTool,
    addHttpTool,
    updateHttpTool,
    removeHttpTool,
    updateHttpToolParam,
    addHttpToolParam,
    removeHttpToolParam,
    updateHandoff,
    setQaMode,
    addQaEntry,
    updateQaEntry,
    removeQaEntry,
    addService,
    renameService,
    updateService,
    removeService,
    handleSave,
    handleTry,
  };
}
