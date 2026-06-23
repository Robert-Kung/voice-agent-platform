'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { nanoid } from 'nanoid';
import { toast } from 'sonner';
import { profilesApi, testApi, toolsApi } from '@/lib/admin-api';
import type { Profile } from '@/lib/admin-api';
import {
  AUTO_MOUNTED_TOOL_NAMES,
  type AgentGraph,
  type EditorMode,
  type GraphEdge,
  type GraphNode,
  type GraphNodeType,
  NODE_TYPE_LABELS,
  normalizeGraph,
  prepareGraphSave,
  promptToGraph,
} from '@/lib/agent-graph';
import type { ModelMode, ModelSpec, ModelsConfig, RealtimeBlock } from '@/lib/model-catalog';

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
  tool_description?: string;
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
  graph?: AgentGraph;
  editor_mode?: EditorMode;
  models?: ModelsConfig;
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
  'graph',
  'editor_mode',
  'models',
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
const AUTO_MOUNTED_TOOLS = new Set(AUTO_MOUNTED_TOOL_NAMES);

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

// Load-boundary sanitizer: config_json is free-form, so a hand-edited or
// API-written graph block can violate the AgentGraph shape every consumer
// (canvas, flatten, validator) assumes. Unusable graphs are dropped entirely —
// the profile then behaves as if it had no graph instead of bricking the page.
export function normalizeKnownGraph(known: KnownConfig): KnownConfig {
  if (known.graph === undefined) return known;
  const normalized = normalizeGraph(known.graph);
  const out = { ...known };
  if (normalized) out.graph = normalized;
  else delete out.graph;
  return out;
}

// A model spec carries no pinned intent unless it names a provider, model, or
// voice. `voice` counts because a user may re-pick a tts voice while leaving the
// model inherited (models.tts.voice is independent of the model id) — dropping the
// block then would silently lose the voice on save (review H2).
function specHasValue(spec: ModelSpec | ModelSpec[] | undefined): boolean {
  const s = Array.isArray(spec) ? spec[0] : spec;
  if (!s) return false;
  return Boolean(
    (s.provider && s.provider.trim()) || (s.model && s.model.trim()) || (s.voice && s.voice.trim())
  );
}

// Drop empty sub-blocks so a `models` block that the user opened but never pinned
// isn't persisted as noise — keeping the runtime's "未宣告即 fallback" contract
// (design D2). Returns undefined when nothing meaningful remains.
export function pruneModels(models: ModelsConfig | undefined): ModelsConfig | undefined {
  if (!models) return undefined;
  const out: ModelsConfig = {};
  if (models.mode === 'pipeline' || models.mode === 'realtime') out.mode = models.mode;
  for (const kind of ['llm', 'stt', 'tts'] as const) {
    if (specHasValue(models[kind])) out[kind] = models[kind];
  }
  if (models.realtime) {
    const rt: RealtimeBlock = {};
    const { model, voice, provider, thinking_budget, stt } = models.realtime;
    if (model && model.trim()) rt.model = model;
    if (voice && voice.trim()) rt.voice = voice;
    if (provider && provider.trim()) rt.provider = provider;
    if (typeof thinking_budget === 'number') rt.thinking_budget = thinking_budget;
    if (specHasValue(stt)) rt.stt = stt;
    if (Object.keys(rt).length > 0) out.realtime = rt;
  }
  return Object.keys(out).length > 0 ? out : undefined;
}

export function buildConfig(
  known: KnownConfig,
  extra: Record<string, unknown>
): Record<string, unknown> {
  const out: Record<string, unknown> = { ...extra };
  for (const k of KNOWN_KEYS) {
    let v: unknown = known[k];
    if (k === 'models') v = pruneModels(known.models);
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
  editorMode: EditorMode;
  savedEditorMode: EditorMode;
  setEditorMode: (mode: EditorMode) => void;
  convertToGraph: () => void;
  modelsMode: ModelMode;
  savedModelMode: ModelMode;
  setModelMode: (mode: ModelMode) => void;
  updateModelSpec: (kind: 'llm' | 'stt' | 'tts', patch: Partial<ModelSpec>) => void;
  updateRealtime: (patch: Partial<RealtimeBlock>) => void;
  graphRealtimeConflict: boolean;
  clearGraphRealtimeConflict: () => void;
  updateGlobalPrompt: (value: string) => void;
  addNode: (type: Exclude<GraphNodeType, 'start'>) => void;
  removeNode: (id: string) => void;
  updateNode: (id: string, patch: Partial<GraphNode>) => void;
  setNodePosition: (id: string, position: { x: number; y: number }) => void;
  addEdge: (source: string, target: string) => void;
  removeEdge: (id: string) => void;
  updateEdge: (id: string, patch: Partial<GraphEdge>) => void;
  handleSave: () => Promise<boolean>;
  handleTry: () => Promise<void>;
  handleSaveAndTry: () => Promise<void>;
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
  // Set when a save is rejected by the backend graph×realtime 422 (reachable only
  // via API/YAML bypass of the locked Realtime tab). Surfaced near the engine-mode
  // control as the exclusivity constraint, not a generic error (spec task 4.3).
  const [graphRealtimeConflict, setGraphRealtimeConflict] = useState(false);
  const clearGraphRealtimeConflict = useCallback(() => setGraphRealtimeConflict(false), []);

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
        const k = normalizeKnownGraph(cleanLegacyTools(migrateLegacyHumanOperator(raw)));
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

  // ── Graph actions ────────────────────────────────────────────────

  const updateGraph = useCallback((updater: (g: AgentGraph) => AgentGraph) => {
    setKnown((prev) => (prev.graph ? { ...prev, graph: updater(prev.graph) } : prev));
  }, []);

  // Graph executes only in pipeline (realtime rejects mid-session node swaps), so
  // switching into graph coerces a realtime models.mode to pipeline — never leaving
  // the unsavable graph+realtime state (spec D4 / task 4.2). The page surfaces the
  // confirmation before calling this.
  const setEditorMode = useCallback((mode: EditorMode) => {
    setKnown((prev) => {
      if (mode === 'graph' && prev.models?.mode === 'realtime') {
        return { ...prev, editor_mode: mode, models: { ...prev.models, mode: 'pipeline' } };
      }
      return { ...prev, editor_mode: mode };
    });
  }, []);

  const convertToGraph = useCallback(() => {
    setKnown((prev) => {
      const models =
        prev.models?.mode === 'realtime'
          ? { ...prev.models, mode: 'pipeline' as const }
          : prev.models;
      return {
        ...prev,
        // A previously converted profile keeps its graph; conversion only happens once.
        graph: prev.graph ?? promptToGraph(prev),
        editor_mode: 'graph',
        ...(models ? { models } : {}),
      };
    });
  }, []);

  // ── Models (engine/voice stack) actions ──────────────────────────
  // Selecting a tab pins models.mode (an explicit engine choice). Editing a spec
  // field pins only that spec; inactive sub-blocks are never cleared on a mode
  // switch (keep-but-don't-clear, task 1.2). Inherited compiled defaults are shown
  // by the UI but not written here (design D2).
  const setModelMode = useCallback((mode: ModelMode) => {
    setKnown((prev) => ({ ...prev, models: { ...(prev.models || {}), mode } }));
  }, []);

  const updateModelSpec = useCallback((kind: 'llm' | 'stt' | 'tts', patch: Partial<ModelSpec>) => {
    setKnown((prev) => {
      const models = { ...(prev.models || {}) };
      const existing = models[kind];
      // Preserve a fallback list's tail: edit the primary spec, keep the rest.
      if (Array.isArray(existing)) {
        models[kind] = [{ ...(existing[0] ?? {}), ...patch }, ...existing.slice(1)];
      } else {
        models[kind] = { ...(existing ?? {}), ...patch };
      }
      return { ...prev, models };
    });
  }, []);

  const updateRealtime = useCallback((patch: Partial<RealtimeBlock>) => {
    setKnown((prev) => ({
      ...prev,
      models: { ...(prev.models || {}), realtime: { ...(prev.models?.realtime || {}), ...patch } },
    }));
  }, []);

  const updateGlobalPrompt = useCallback(
    (value: string) => {
      updateGraph((g) => ({ ...g, global_prompt: value }));
    },
    [updateGraph]
  );

  const addNode = useCallback(
    (type: Exclude<GraphNodeType, 'start'>) => {
      updateGraph((g) => {
        const node: GraphNode = {
          id: `${type}-${nanoid(6)}`,
          type,
          title: NODE_TYPE_LABELS[type],
          prompt: '',
          tools: [],
          position: { x: 240 + (g.nodes.length % 4) * 60, y: 80 + g.nodes.length * 70 },
        };
        return { ...g, nodes: [...g.nodes, node] };
      });
    },
    [updateGraph]
  );

  const removeNode = useCallback(
    (id: string) => {
      updateGraph((g) => ({
        ...g,
        nodes: g.nodes.filter((n) => n.id !== id),
        edges: g.edges.filter((e) => e.source !== id && e.target !== id),
      }));
    },
    [updateGraph]
  );

  const updateNode = useCallback(
    (id: string, patch: Partial<GraphNode>) => {
      updateGraph((g) => ({
        ...g,
        nodes: g.nodes.map((n) => (n.id === id ? { ...n, ...patch } : n)),
      }));
    },
    [updateGraph]
  );

  const setNodePosition = useCallback(
    (id: string, position: { x: number; y: number }) => {
      updateGraph((g) => ({
        ...g,
        nodes: g.nodes.map((n) => (n.id === id ? { ...n, position } : n)),
      }));
    },
    [updateGraph]
  );

  const addEdge = useCallback(
    (source: string, target: string) => {
      updateGraph((g) => ({
        ...g,
        edges: [
          ...g.edges,
          { id: `e-${nanoid(6)}`, source, target, trigger: 'user_turn', condition: '' },
        ],
      }));
    },
    [updateGraph]
  );

  const removeEdge = useCallback(
    (id: string) => {
      updateGraph((g) => ({ ...g, edges: g.edges.filter((e) => e.id !== id) }));
    },
    [updateGraph]
  );

  const updateEdge = useCallback(
    (id: string, patch: Partial<GraphEdge>) => {
      updateGraph((g) => ({
        ...g,
        edges: g.edges.map((e) => (e.id === id ? { ...e, ...patch } : e)),
      }));
    },
    [updateGraph]
  );

  const startTry = useCallback(async (profileName: string) => {
    setTrying(true);
    try {
      const { room } = await testApi.start(profileName);
      window.open(`/?room=${encodeURIComponent(room)}`, '_blank');
    } catch (e) {
      toast.error(`無法啟動測試 agent: ${(e as Error).message}`);
    } finally {
      setTrying(false);
    }
  }, []);

  const handleTry = useCallback(async () => {
    if (!profile || isNew) return;
    if (isDirty) {
      toast.error('有未儲存變更。先儲存後再 Try（Try 跑的是 DB 最新版本）。');
      return;
    }
    await startTry(profile.name);
  }, [profile, isNew, isDirty, startTry]);

  const handleSave = useCallback(async (): Promise<boolean> => {
    let extraObj: Record<string, unknown>;
    try {
      const parsed = extraJson.trim() ? JSON.parse(extraJson) : {};
      if (typeof parsed !== 'object' || Array.isArray(parsed) || parsed === null) {
        throw new Error('Advanced JSON must be an object');
      }
      extraObj = parsed as Record<string, unknown>;
    } catch (e) {
      toast.error(`Advanced JSON 解析失敗: ${(e as Error).message}`);
      return false;
    }

    if (isNew) {
      if (!NAME_PATTERN.test(name)) {
        toast.error('Profile name 必須是小寫字母開頭，僅含 a-z, 0-9, _');
        return false;
      }
      if (!displayName.trim()) {
        toast.error('Display Name 不可為空');
        return false;
      }
    }

    let knownToSave: KnownConfig = { ...known, name: known.name || displayName };
    const graphSave = prepareGraphSave(known, availableTools);
    if (graphSave.action === 'blocked') {
      toast.error(`Graph 驗證失敗：${graphSave.errors.map((e) => e.message).join('；')}`);
      return false;
    }
    if (graphSave.action === 'regenerated') {
      for (const w of graphSave.warnings) {
        toast.warning(w.message);
      }
      knownToSave = { ...knownToSave, instructions: graphSave.instructions };
      setKnown((prev) => ({ ...prev, instructions: graphSave.instructions }));
    }

    const finalConfig = buildConfig(knownToSave, extraObj);

    setGraphRealtimeConflict(false);
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
        router.push(`/admin/profiles/${created.id}`);
      } else {
        const updated = await profilesApi.update(id, {
          display_name: displayName,
          config: finalConfig,
        });
        setProfile(updated);
        const { known: raw, extra } = splitConfig(updated.config || {});
        const k = normalizeKnownGraph(cleanLegacyTools(migrateLegacyHumanOperator(raw)));
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
        toast.success('Profile 已儲存', { duration: 3000 });
      }
    } catch (e) {
      const msg = (e as Error).message;
      if (msg.includes('graph_realtime_conflict')) {
        // Surfaced in-context near the engine-mode control; unsaved edits retained.
        setGraphRealtimeConflict(true);
        toast.error(
          'graph × realtime 互斥：graph 執行僅支援 pipeline，請改回 Pipeline 引擎後再存。'
        );
      } else {
        toast.error(`儲存失敗: ${msg}`);
      }
      return false;
    } finally {
      setSaving(false);
    }
    return true;
  }, [name, displayName, known, extraJson, isNew, id, currentSnapshot, router, availableTools]);

  const handleSaveAndTry = useCallback(async () => {
    // Gate on save success (a blocked graph validation or API error must not
    // launch Try), and start directly — handleTry's isDirty is a stale closure here.
    const ok = await handleSave();
    if (!ok || !profile || isNew) return;
    await startTry(profile.name);
  }, [handleSave, profile, isNew, startTry]);

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
    () => (known.tools || []).map((t, i) => (t.endpoint ? i : -1)).filter((i) => i >= 0),
    [known.tools]
  );

  const qaList = useMemo(() => known.qa_data || [], [known.qa_data]);

  const editorMode: EditorMode = known.editor_mode === 'graph' ? 'graph' : 'prompt';

  // Last persisted mode — saving after a mode switch changes the live runtime
  // strategy source, so the page gates that save behind an explicit confirm.
  const savedEditorMode: EditorMode = useMemo(() => {
    const persisted = (profile?.config as Record<string, unknown> | undefined)?.editor_mode;
    return persisted === 'graph' ? 'graph' : 'prompt';
  }, [profile]);

  // Effective engine mode: an absent/invalid models.mode resolves to the runtime
  // default (realtime), mirroring agent.py's coercion. models.mode is the runtime
  // engine selector (cost/latency/graph-execution), so saving a change to it is a
  // strategy change gated by the same confirm as editor_mode (spec task 2.4).
  const modelsMode: ModelMode = known.models?.mode === 'pipeline' ? 'pipeline' : 'realtime';

  const savedModelMode: ModelMode = useMemo(() => {
    const persisted = (profile?.config as { models?: { mode?: unknown } } | undefined)?.models
      ?.mode;
    return persisted === 'pipeline' ? 'pipeline' : 'realtime';
  }, [profile]);

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
    editorMode,
    savedEditorMode,
    setEditorMode,
    convertToGraph,
    modelsMode,
    savedModelMode,
    setModelMode,
    updateModelSpec,
    updateRealtime,
    graphRealtimeConflict,
    clearGraphRealtimeConflict,
    updateGlobalPrompt,
    addNode,
    removeNode,
    updateNode,
    setNodePosition,
    addEdge,
    removeEdge,
    updateEdge,
    handleSave,
    handleTry,
    handleSaveAndTry,
  };
}
