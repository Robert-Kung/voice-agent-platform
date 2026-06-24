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

/** One declarative model spec — mirrors runtime.constants normalize_spec shape.
 *  `voice` is a first-class TTS field (separate from the model id), passed to
 *  inference.TTS(voice=); only meaningful on tts specs. */
export interface ModelSpec {
  provider?: string;
  model?: string;
  via?: SpecVia;
  language?: string;
  voice?: string;
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

/** One catalog model: the model id under its provider + whether a cost rate exists
 *  (model-granular for LLM, provider-granular for STT/TTS — design D7). */
export interface CatalogModel {
  model: string;
  priced: boolean;
}

/** A suggested TTS voice for the per-provider picker. `id` is the value written to
 *  models.tts.voice (the inference.TTS voice= param). */
export interface VoiceOption {
  id: string;
  label: string;
}

/** Provider-keyed catalog: pick provider → its priced-annotated models. */
export type CatalogKind = Record<string, CatalogModel[]>;

/** provider → model → ordered BCP-47 language codes ([0] = default). */
export type LanguageMatrix = Record<string, Record<string, string[]>>;

export interface ModelCatalog {
  schema: number;
  direct_providers: string[];
  /** (kind:provider) pairs with a wired direct build path, e.g. "llm:google".
   *  The via:direct toggle is offered only for these. */
  direct_buildable: string[];
  pipeline: {
    defaults: { llm: ModelSpec; stt: ModelSpec; tts: ModelSpec };
    catalog: { llm: CatalogKind; stt: CatalogKind; tts: CatalogKind };
    voices: Record<string, VoiceOption[]>;
    /** Per-model language capability matrix (advisory): kind → provider → model →
     *  ordered BCP-47 codes ([0] = the model's default). Drives the language pickers. */
    languages: { stt: LanguageMatrix; tts: LanguageMatrix };
    // Legacy (compat) — still served, prefer `catalog`.
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

/** Whether the via:inference/via:direct toggle should show for a (kind, provider).
 *  Mirrors the backend DIRECT_BUILDABLE matrix surfaced as `direct_buildable`. */
export function isDirectCapable(
  catalog: ModelCatalog,
  kind: 'llm' | 'stt' | 'tts',
  provider: string | undefined
): boolean {
  if (!provider) return false;
  return catalog.direct_buildable.includes(`${kind}:${provider}`);
}

/** Ordered language codes the matrix lists for a (kind, provider, model). STT and
 *  TTS only (LLM has no language). Empty when the model isn't in the matrix. */
export function supportedLanguages(
  catalog: ModelCatalog,
  kind: 'stt' | 'tts',
  provider: string | undefined,
  model: string | undefined
): string[] {
  if (!provider || !model) return [];
  return catalog.pipeline.languages[kind]?.[provider]?.[model] ?? [];
}

/** The model's default language = its matrix list's first entry (e.g. zh-TW for
 *  Deepgram general, zh for cartesia, en for English-only). '' when unknown. */
export function languageDefault(
  catalog: ModelCatalog,
  kind: 'stt' | 'tts',
  provider: string | undefined,
  model: string | undefined
): string {
  return supportedLanguages(catalog, kind, provider, model)[0] ?? '';
}

/** Whether a language is in the model's matrix entry. A model with no matrix entry
 *  imposes no constraint (returns true) so off-catalog/free-text models never warn. */
export function isLanguageSupported(
  catalog: ModelCatalog,
  kind: 'stt' | 'tts',
  provider: string | undefined,
  model: string | undefined,
  language: string | undefined
): boolean {
  if (!language) return true;
  const langs = supportedLanguages(catalog, kind, provider, model);
  return langs.length === 0 || langs.includes(language);
}

/** Parse a legacy voice-encoded TTS model id (`provider/model:voiceId`, LiveKit's
 *  documented form) into its base model + voice, for non-destructive migration into
 *  the separate voice field. Returns null when there's no encoded voice. */
export function parseLegacyVoiceModel(
  model: string | undefined
): { model: string; voice: string } | null {
  if (!model) return null;
  const i = model.indexOf(':');
  if (i < 0) return null;
  const base = model.slice(0, i);
  const voice = model.slice(i + 1);
  if (!base || !voice) return null;
  return { model: base, voice };
}

// Offline fallback — mirrors the backend constants. Kept in sync via the vitest
// contract test (model-catalog.test.ts) against backend-model-constants.json.
const _c = (...models: string[]): CatalogModel[] =>
  models.map((m) => ({ model: m, priced: false }));

// Shared language lists (mirror runtime/constants.py MODEL_LANGUAGES; ordered, [0]=default).
const _DG_GENERAL = ['zh-TW', 'zh-Hant', 'zh-CN', 'zh-HK', 'en', 'en-US', 'ja', 'ko'];
const _EN_ONLY = ['en', 'en-US'];
const _MULTI_ZH = ['zh', 'en', 'ja', 'ko', 'es', 'fr', 'de'];
const _INWORLD_V1 = ['en', 'es', 'fr', 'de', 'ja', 'ko'];

export const FALLBACK_MODEL_CATALOG: ModelCatalog = {
  schema: 2,
  direct_providers: ['deepgram', 'google'],
  direct_buildable: ['llm:google', 'stt:deepgram'],
  pipeline: {
    defaults: {
      llm: { provider: 'google', model: 'gemini-3.1-flash-lite', via: 'inference' },
      stt: {
        provider: 'deepgram',
        model: 'nova-2',
        via: 'inference',
        language: 'zh-TW',
      },
      tts: {
        provider: 'cartesia',
        model: 'sonic-3:9626c31c-bec5-4cca-baa8-f8ba9e84c8bc',
        via: 'inference',
        language: 'zh',
      },
    },
    // priced flags are filled by the live endpoint; the offline fallback marks all
    // unpriced (false) — the contract test compares model lists, not the flag.
    catalog: {
      llm: {
        'deepseek-ai': _c('deepseek-v3'),
        google: _c(
          'gemini-3-flash',
          'gemini-2.5-pro',
          'gemini-2.5-flash',
          'gemini-2.5-flash-lite',
          'gemini-3.1-flash-lite'
        ),
        openai: _c(
          'gpt-4o',
          'gpt-4o-mini',
          'gpt-4.1',
          'gpt-4.1-mini',
          'gpt-4.1-nano',
          'gpt-5',
          'gpt-5-mini',
          'gpt-5-nano',
          'gpt-5.1',
          'gpt-5.1-chat-latest',
          'gpt-5.2',
          'gpt-5.2-chat-latest',
          'gpt-5.3-chat-latest',
          'gpt-5.4',
          'gpt-oss-120b'
        ),
      },
      stt: {
        cartesia: _c('ink-whisper'),
        deepgram: _c(
          'nova-3',
          'nova-3-medical',
          'nova-2',
          'nova-2-medical',
          'nova-2-conversationalai',
          'nova-2-phonecall'
        ),
      },
      tts: {
        cartesia: _c('sonic-3', 'sonic-2', 'sonic-turbo', 'sonic'),
        deepgram: _c('aura-2'),
        elevenlabs: _c(
          'eleven_flash_v2',
          'eleven_flash_v2_5',
          'eleven_turbo_v2',
          'eleven_turbo_v2_5',
          'eleven_multilingual_v2'
        ),
        inworld: _c(
          'inworld-tts-1.5-max',
          'inworld-tts-1.5-mini',
          'inworld-tts-1-max',
          'inworld-tts-1'
        ),
        rime: _c('arcana', 'mistv2'),
      },
    },
    voices: {
      cartesia: [
        {
          id: 'a167e0f3-df7e-4d52-a9c3-f949145efdab',
          label: 'Blake — Energetic American adult male',
        },
        {
          id: '5c5ad5e7-1020-476b-8b91-fdcbe9cc313c',
          label: 'Daniela — Calm, trusting Mexican female',
        },
        {
          id: '9626c31c-bec5-4cca-baa8-f8ba9e84c8bc',
          label: 'Jacqueline — Confident, young American female',
        },
        {
          id: 'f31cc6a7-c1e8-4764-980c-60a361443dd1',
          label: 'Robyn — Neutral, mature Australian female',
        },
      ],
      deepgram: [
        { id: 'apollo', label: 'Apollo — Comfortable, casual male' },
        { id: 'athena', label: 'Athena — Smooth, professional female' },
        { id: 'odysseus', label: 'Odysseus — Calm, professional male' },
        { id: 'theia', label: 'Theia — Expressive, polite female' },
      ],
      elevenlabs: [
        { id: 'Xb7hH8MSUJpSbSDYk0k2', label: 'Alice — Clear, friendly British woman' },
        { id: 'iP95p4xoKVk53GoZ742B', label: 'Chris — Natural, real American male' },
        { id: 'cjVigY5qzO86Huf0OWal', label: 'Eric — Smooth tenor Mexican male' },
        { id: 'cgSgspJ2msm6clMCkdW9', label: 'Jessica — Young, playful American female' },
      ],
      rime: [
        { id: 'astra', label: 'Astra — Chipper, upbeat American female' },
        { id: 'celeste', label: 'Celeste — Chill Gen-Z American female' },
        { id: 'luna', label: 'Luna — Chill but excitable American female' },
        { id: 'ursa', label: 'Ursa — Young, emo American male' },
      ],
      inworld: [
        { id: 'Ashley', label: 'Ashley — Warm, natural American female' },
        { id: 'Diego', label: 'Diego — Soothing, gentle Mexican male' },
        { id: 'Edward', label: 'Edward — Fast-talking, emphatic American male' },
        { id: 'Olivia', label: 'Olivia — Upbeat, friendly British female' },
      ],
    },
    languages: {
      stt: {
        deepgram: {
          'nova-3': _DG_GENERAL,
          'nova-2': _DG_GENERAL,
          'nova-3-medical': _EN_ONLY,
          'nova-2-medical': _EN_ONLY,
          'nova-2-conversationalai': _EN_ONLY,
          'nova-2-phonecall': _EN_ONLY,
        },
        cartesia: { 'ink-whisper': _MULTI_ZH },
      },
      tts: {
        cartesia: {
          'sonic-3': _MULTI_ZH,
          'sonic-2': _MULTI_ZH,
          'sonic-turbo': _MULTI_ZH,
          sonic: _MULTI_ZH,
        },
        deepgram: { 'aura-2': ['en', 'es', 'de', 'fr', 'nl', 'it', 'ja'] },
        elevenlabs: {
          eleven_flash_v2_5: _MULTI_ZH,
          eleven_turbo_v2_5: _MULTI_ZH,
          eleven_multilingual_v2: _MULTI_ZH,
          eleven_flash_v2: _EN_ONLY,
          eleven_turbo_v2: _EN_ONLY,
        },
        rime: {
          arcana: ['en', 'es', 'fr', 'de', 'hi', 'ja', 'pt', 'ar'],
          mistv2: ['en', 'es', 'fr', 'de'],
        },
        inworld: {
          'inworld-tts-1.5-max': _MULTI_ZH,
          'inworld-tts-1.5-mini': _MULTI_ZH,
          'inworld-tts-1-max': _INWORLD_V1,
          'inworld-tts-1': _INWORLD_V1,
        },
      },
    },
    llm_options: [
      { provider: 'deepseek-ai', model: 'deepseek-v3' },
      { provider: 'google', model: 'gemini-3-flash' },
      { provider: 'google', model: 'gemini-2.5-pro' },
      { provider: 'google', model: 'gemini-2.5-flash' },
      { provider: 'google', model: 'gemini-2.5-flash-lite' },
      { provider: 'google', model: 'gemini-3.1-flash-lite' },
      { provider: 'openai', model: 'gpt-4o' },
      { provider: 'openai', model: 'gpt-4o-mini' },
      { provider: 'openai', model: 'gpt-4.1' },
      { provider: 'openai', model: 'gpt-4.1-mini' },
      { provider: 'openai', model: 'gpt-4.1-nano' },
      { provider: 'openai', model: 'gpt-5' },
      { provider: 'openai', model: 'gpt-5-mini' },
      { provider: 'openai', model: 'gpt-5-nano' },
      { provider: 'openai', model: 'gpt-5.1' },
      { provider: 'openai', model: 'gpt-5.1-chat-latest' },
      { provider: 'openai', model: 'gpt-5.2' },
      { provider: 'openai', model: 'gpt-5.2-chat-latest' },
      { provider: 'openai', model: 'gpt-5.3-chat-latest' },
      { provider: 'openai', model: 'gpt-5.4' },
      { provider: 'openai', model: 'gpt-oss-120b' },
    ],
    stt_providers: ['cartesia', 'deepgram'],
    tts_providers: ['cartesia', 'deepgram', 'elevenlabs', 'inworld', 'rime'],
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
