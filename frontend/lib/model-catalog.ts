// Model/voice catalog types + the compiled-default helper for the profile editor
// stack UI (profile-editor-stack-ux).
//
// Source of truth is the backend read-only endpoint GET /api/model-defaults
// (api/routes_model_defaults.py), reflecting runtime.constants + db.cost. The
// frontend consumes it at runtime and falls back to FALLBACK_MODEL_CATALOG when
// the fetch fails — that fallback is kept in sync with the backend by the
// contract test against __fixtures__/backend-model-constants.json (the same
// parity discipline applied to the graph validator). Never hardcode a divergent
// second copy.

export type ModelMode = 'pipeline' | 'realtime';
export type SpecVia = 'inference' | 'direct';

/** One declarative model spec — mirrors runtime.constants normalize_spec shape. */
export interface ModelSpec {
  provider?: string;
  model?: string;
  via?: SpecVia;
  language?: string;
  options?: Record<string, unknown>;
}

/** models.realtime block — Gemini Live (TextInputRealtimeModel) + text-input STT. */
export interface RealtimeBlock {
  provider?: string;
  model?: string;
  voice?: string;
  thinking_budget?: number;
  stt?: ModelSpec | ModelSpec[];
}

/** The profile config's `models` block. llm/stt/tts accept a single spec or a
 *  fallback list; the v1 UI edits the primary (segment[0]) and preserves the tail. */
export interface ModelsConfig {
  mode?: ModelMode;
  llm?: ModelSpec | ModelSpec[];
  stt?: ModelSpec | ModelSpec[];
  tts?: ModelSpec | ModelSpec[];
  realtime?: RealtimeBlock;
}

export interface ModelCatalog {
  schema: number;
  direct_providers: string[];
  pipeline: {
    defaults: { llm: ModelSpec; stt: ModelSpec; tts: ModelSpec };
    llm_options: { provider: string; model: string }[];
    stt_providers: string[];
    tts_providers: string[];
  };
  realtime: {
    defaults: { model: string; voice: string; stt: ModelSpec };
    llm_providers: string[];
    model_allowlist: string[];
    voice_suggestions: string[];
  };
}

// Offline fallback — mirrors the backend constants. Kept in sync via the vitest
// contract test (model-catalog.test.ts) against backend-model-constants.json.
export const FALLBACK_MODEL_CATALOG: ModelCatalog = {
  schema: 1,
  direct_providers: ['deepgram', 'google'],
  pipeline: {
    defaults: {
      llm: { provider: 'google', model: 'gemini-3.1-flash-lite', via: 'inference' },
      stt: {
        provider: 'elevenlabs',
        model: 'scribe_v2_realtime',
        via: 'inference',
        language: 'zh',
      },
      tts: {
        provider: 'cartesia',
        model: 'sonic-3:9626c31c-bec5-4cca-baa8-f8ba9e84c8bc',
        via: 'inference',
        language: 'zh',
      },
    },
    llm_options: [
      { provider: 'google', model: 'gemini-2.5-flash' },
      { provider: 'google', model: 'gemini-2.5-flash-lite' },
      { provider: 'google', model: 'gemini-3.1-flash-lite' },
      { provider: 'google', model: 'gemini-2.0-flash' },
      { provider: 'openai', model: 'gpt-4o-mini' },
      { provider: 'openai', model: 'gpt-4.1-mini' },
      { provider: 'openai', model: 'gpt-4o' },
      { provider: 'openai', model: 'gpt-4.1' },
    ],
    stt_providers: ['deepgram', 'elevenlabs', 'google'],
    tts_providers: ['cartesia', 'elevenlabs', 'google', 'openai'],
  },
  realtime: {
    defaults: {
      model: 'gemini-2.5-flash-native-audio-preview-12-2025',
      voice: 'Kore',
      stt: { provider: 'deepgram', model: 'nova-2', via: 'inference', language: 'zh-TW' },
    },
    llm_providers: ['gemini', 'google'],
    model_allowlist: ['gemini-2.5-flash-native-audio-preview-12-2025'],
    voice_suggestions: ['Kore', 'Puck', 'Charon', 'Aoede', 'Fenrir'],
  },
};

// ── Spec helpers ─────────────────────────────────────────────────

/** The primary spec the UI edits/shows. Accepts a single spec or a fallback list. */
export function specPrimary(value: ModelSpec | ModelSpec[] | undefined): ModelSpec | undefined {
  if (Array.isArray(value)) return value[0];
  return value;
}

export type DefaultSource = 'pinned' | 'inherited';

export interface ResolvedField {
  value: string;
  source: DefaultSource;
}

/**
 * Resolve a displayed field value: a pinned value (present in the profile's
 * `models` block) tracks exactly what's saved; otherwise the compiled built-in
 * default is shown as `inherited` and is NOT written into config — preserving the
 * runtime's "未宣告即 fallback" non-destructive contract (design D2). The shown
 * default is the compiled default; a deployment env override may shadow it.
 */
export function resolveField(
  pinned: string | undefined | null,
  compiledDefault: string
): ResolvedField {
  const trimmed = (pinned ?? '').trim();
  if (trimmed) return { value: trimmed, source: 'pinned' };
  return { value: compiledDefault, source: 'inherited' };
}
