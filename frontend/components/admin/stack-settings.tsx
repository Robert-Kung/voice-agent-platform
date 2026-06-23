'use client';

import { useState } from 'react';
import { Info, Lock } from 'lucide-react';
import { useModelCatalog } from '@/hooks/use-model-catalog';
import type { UseProfileFormReturn } from '@/hooks/use-profile-form';
import {
  type CatalogModel,
  type ModelCatalog,
  type ModelSpec,
  type VoiceOption,
  isDirectCapable,
  parseLegacyVoiceModel,
  resolveField,
  specPrimary,
} from '@/lib/model-catalog';

// Engine-mode model/voice stack settings, opened from the header Stack chip (D7).
// Reads/writes the profile config's `models` block via the form hook; the legal
// lists + compiled defaults come from the backend model-defaults endpoint (single
// source of truth) consumed through useModelCatalog.

interface StackSettingsProps {
  form: UseProfileFormReturn;
}

// ── inherited / pinned badge ─────────────────────────────────────
function SourceBadge({ source }: { source: 'pinned' | 'inherited' }) {
  if (source === 'pinned') {
    return (
      <span className="bg-primary/10 text-primary rounded px-1.5 py-0.5 text-[10px] font-medium">
        pinned
      </span>
    );
  }
  return (
    <span
      title="顯示的是編譯預設值（inherited）；未寫入此 profile，會跟著未來內建預設變動。部署層 env 仍可覆蓋。"
      className="text-foreground/40 border-border rounded border px-1.5 py-0.5 text-[10px] font-medium"
    >
      inherited
    </span>
  );
}

function FieldRow({
  label,
  source,
  children,
}: {
  label: string;
  source: 'pinned' | 'inherited';
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <span className="text-foreground/70 text-xs font-medium">{label}</span>
        <SourceBadge source={source} />
      </div>
      {children}
    </div>
  );
}

const selectCls =
  'border-border bg-background text-foreground focus:ring-primary/40 w-full rounded-md border px-2.5 py-1.5 text-xs focus:ring-2 focus:outline-none';

export function StackSettings({ form }: StackSettingsProps) {
  const { catalog, loading, error } = useModelCatalog();
  const isGraph = form.editorMode === 'graph';
  const mode = form.modelsMode;

  return (
    <div className="space-y-4">
      {/* Engine-mode tabs */}
      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-foreground/50 text-[11px] font-medium tracking-wider uppercase">
            引擎模式 (Engine)
          </span>
          {loading && <span className="text-foreground/40 text-[10px]">載入模型清單…</span>}
        </div>
        <div className="border-border flex rounded-md border p-0.5">
          <EngineTab
            active={mode === 'realtime'}
            disabled={isGraph}
            onClick={() => form.setModelMode('realtime')}
            label="Realtime"
            sublabel="Speech-to-Speech"
            lockedReason={isGraph ? 'Graph 執行僅支援 pipeline，realtime 不可選' : undefined}
          />
          <EngineTab
            active={mode === 'pipeline'}
            onClick={() => form.setModelMode('pipeline')}
            label="Pipeline"
            sublabel="STT + LLM + TTS"
          />
        </div>
        {isGraph && (
          <p className="text-foreground/50 mt-1.5 flex items-start gap-1 text-[11px] leading-relaxed">
            <Lock size={11} className="mt-0.5 shrink-0" />此 profile 為 graph 模式：node 切換需
            pipeline，realtime 下會被 Gemini Live 拒絕/忽略，故引擎鎖定 Pipeline。
          </p>
        )}
        {form.graphRealtimeConflict && (
          <div className="mt-2 flex items-start justify-between gap-2 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-[11px] leading-relaxed text-red-600 dark:text-red-400">
            <span>
              後端拒絕：graph × realtime 互斥。graph 執行僅支援 pipeline，請將引擎改回 Pipeline
              後再存檔（未存編輯已保留）。
            </span>
            <button
              type="button"
              onClick={form.clearGraphRealtimeConflict}
              className="shrink-0 underline"
            >
              知道了
            </button>
          </div>
        )}
        {error && (
          <p className="text-foreground/40 mt-1.5 text-[11px]">
            無法取得最新模型清單，暫用內建預設（{error}）。
          </p>
        )}
      </div>

      {mode === 'realtime' ? (
        <RealtimePanel form={form} catalog={catalog} />
      ) : (
        <PipelinePanel form={form} catalog={catalog} />
      )}
    </div>
  );
}

function EngineTab({
  active,
  disabled,
  onClick,
  label,
  sublabel,
  lockedReason,
}: {
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
  label: string;
  sublabel: string;
  lockedReason?: string;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      title={lockedReason}
      className={`flex flex-1 flex-col items-center rounded px-2 py-1.5 text-center transition-colors ${
        active
          ? 'bg-primary text-primary-foreground'
          : 'text-foreground/50 hover:text-foreground disabled:hover:text-foreground/50 disabled:cursor-not-allowed disabled:opacity-40'
      }`}
    >
      <span className="flex items-center gap-1 text-xs font-medium">
        {disabled && <Lock size={10} />}
        {label}
      </span>
      <span className="text-[10px] opacity-70">{sublabel}</span>
    </button>
  );
}

// ── Realtime panel ───────────────────────────────────────────────
function RealtimePanel({
  form,
  catalog,
}: {
  form: UseProfileFormReturn;
  catalog: ReturnType<typeof useModelCatalog>['catalog'];
}) {
  const rt = form.known.models?.realtime;
  const model = resolveField(rt?.model, catalog.realtime.defaults.model);
  const voice = resolveField(rt?.voice, catalog.realtime.defaults.voice);

  return (
    <div className="space-y-3">
      <p className="text-foreground/50 flex items-start gap-1 text-[11px] leading-relaxed">
        <Info size={11} className="mt-0.5 shrink-0" />
        Realtime 的 LLM 鎖定為封裝後的 Gemini Live（TextInputRealtimeModel：攔截音訊改以 Deepgram
        STT 轉文字輸入，規避 audio-token 累積延遲）。不提供非 Gemini realtime
        provider，已知失效變體不可選。
      </p>

      <FieldRow label="Realtime 模型 (Gemini Live)" source={model.source}>
        <select
          className={selectCls}
          value={model.value}
          onChange={(e) => form.updateRealtime({ model: e.target.value })}
        >
          {catalog.realtime.model_allowlist.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </FieldRow>

      <FieldRow label="語音 (Voice)" source={voice.source}>
        <input
          className={selectCls}
          list="realtime-voice-suggestions"
          value={voice.value}
          onChange={(e) => form.updateRealtime({ voice: e.target.value })}
          placeholder={catalog.realtime.defaults.voice}
        />
        <datalist id="realtime-voice-suggestions">
          {catalog.realtime.voice_suggestions.map((v) => (
            <option key={v} value={v} />
          ))}
        </datalist>
        <p className="text-foreground/40 text-[10px]">
          自由輸入 Gemini Live voice 名稱（建議值見下拉）；部署層 GOOGLE_REALTIME_VOICE 可覆蓋。
        </p>
      </FieldRow>

      {/* Text-input STT source feeding Gemini — selectable (signal flow:
          語音 → STT → text → Gemini Live), without exposing a non-Gemini LLM. */}
      <CatalogSpecField
        label="STT 來源 (轉文字餵給 Gemini)"
        kind="stt"
        spec={specPrimary(rt?.stt)}
        catalog={catalog}
        compiledDefault={catalog.realtime.defaults.stt}
        onChange={(patch) =>
          form.updateRealtime({ stt: { ...(specPrimary(rt?.stt) ?? {}), ...patch } })
        }
      />
    </div>
  );
}

// ── Pipeline panel ───────────────────────────────────────────────
function PipelinePanel({
  form,
  catalog,
}: {
  form: UseProfileFormReturn;
  catalog: ReturnType<typeof useModelCatalog>['catalog'];
}) {
  const llm = specPrimary(form.known.models?.llm);
  const stt = specPrimary(form.known.models?.stt);
  const tts = specPrimary(form.known.models?.tts);

  return (
    <div className="space-y-3">
      <CatalogSpecField
        label="LLM"
        kind="llm"
        spec={llm}
        catalog={catalog}
        compiledDefault={catalog.pipeline.defaults.llm}
        onChange={(patch) => form.updateModelSpec('llm', patch)}
      />

      <CatalogSpecField
        label="STT (語音轉文字)"
        kind="stt"
        spec={stt}
        catalog={catalog}
        compiledDefault={catalog.pipeline.defaults.stt}
        onChange={(patch) => form.updateModelSpec('stt', patch)}
      />

      <CatalogSpecField
        label="TTS"
        kind="tts"
        spec={tts}
        catalog={catalog}
        compiledDefault={catalog.pipeline.defaults.tts}
        onChange={(patch) => form.updateModelSpec('tts', patch)}
      />
    </div>
  );
}

// "estimate incomplete" pill for a model with no cost rate (design D7).
function UnpricedBadge() {
  return (
    <span
      title="此模型在成本表沒有費率，成本估算會標示為不完整（不影響選用）。"
      className="rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-600 dark:text-amber-400"
    >
      無成本估算
    </span>
  );
}

// via:inference / via:direct segmented toggle, human-labeled. Only rendered for
// (kind, provider) pairs the runtime can build directly (e.g. google LLM).
function ViaToggle({
  via,
  onChange,
}: {
  via: 'inference' | 'direct';
  onChange: (v: 'inference' | 'direct') => void;
}) {
  const opts: { v: 'inference' | 'direct'; label: string; title: string }[] = [
    { v: 'inference', label: '透過 LiveKit 閘道', title: '經 LiveKit Inference 閘道，免自備金鑰' },
    {
      v: 'direct',
      label: '用自己的 API 金鑰',
      title: '直連 provider SDK，用部署層 GOOGLE_API_KEY',
    },
  ];
  return (
    <div className="border-border flex rounded-md border p-0.5">
      {opts.map((o) => (
        <button
          key={o.v}
          type="button"
          title={o.title}
          onClick={() => onChange(o.v)}
          className={`flex-1 rounded px-2 py-1 text-[11px] font-medium transition-colors ${
            via === o.v
              ? 'bg-primary text-primary-foreground'
              : 'text-foreground/50 hover:text-foreground'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// Cascade-aware provider→model (+ via, + tts voice) field, sourced from the
// catalog. Provider and model are dropdowns; a pinned-but-unlisted value stays
// selectable (custom/cloned escape hatch). Changing provider RESETS model (and
// tts voice) so no invalid provider/model combo survives a switch (review C2/D8).
function CatalogSpecField({
  label,
  kind,
  spec,
  catalog,
  compiledDefault,
  onChange,
}: {
  label: string;
  kind: 'llm' | 'stt' | 'tts';
  spec: ModelSpec | undefined;
  catalog: ModelCatalog;
  compiledDefault: ModelSpec;
  onChange: (patch: Partial<ModelSpec>) => void;
}) {
  const kindCatalog = catalog.pipeline.catalog[kind];
  const provider = resolveField(spec?.provider, compiledDefault.provider ?? '');
  const model = resolveField(spec?.model, compiledDefault.model ?? '');
  const source = spec?.provider || spec?.model || spec?.voice ? 'pinned' : 'inherited';
  const via: 'inference' | 'direct' = spec?.via === 'direct' ? 'direct' : 'inference';

  const providerNames = Object.keys(kindCatalog).sort();
  const providerOptions = providerNames.includes(provider.value)
    ? providerNames
    : [provider.value, ...providerNames];

  const modelsForProvider: CatalogModel[] = kindCatalog[provider.value] ?? [];
  const modelListed = modelsForProvider.some((m) => m.model === model.value);
  const currentPriced = modelsForProvider.find((m) => m.model === model.value)?.priced ?? false;

  // Legacy voice-in-model-id (model:voiceId) — surface non-destructively. Parse the
  // provider-relative model value only; the spec's model field is provider-relative,
  // so adopting must yield "sonic-3", not "cartesia/sonic-3" (which would double-prefix
  // to cartesia/cartesia/sonic-3 at runtime via _model_id).
  const legacy = kind === 'tts' ? parseLegacyVoiceModel(model.value) : null;

  function firstModelOf(p: string): string {
    return (kindCatalog[p] ?? [])[0]?.model ?? '';
  }

  function onProviderChange(p: string) {
    // Reset model to the new provider's default + clear stale tts voice + reset via.
    const patch: Partial<ModelSpec> = {
      provider: p,
      model: firstModelOf(p) || model.value,
      via: isDirectCapable(catalog, kind, p) ? via : 'inference',
    };
    if (kind === 'tts') patch.voice = '';
    onChange(patch);
  }

  return (
    <FieldRow label={label} source={source}>
      <div className="space-y-1.5">
        {/* Provider */}
        <select
          className={selectCls}
          value={provider.value}
          onChange={(e) => onProviderChange(e.target.value)}
        >
          {providerOptions.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>

        {/* Model — dropdown filtered to provider; pinned-but-unlisted stays selectable */}
        <select
          className={selectCls}
          value={model.value}
          onChange={(e) => onChange({ provider: provider.value, model: e.target.value, via })}
        >
          {!modelListed && model.value && (
            <option value={model.value}>{model.value}（自訂）</option>
          )}
          {modelsForProvider.map((m) => (
            <option key={m.model} value={m.model}>
              {m.model}
              {m.priced ? '' : ' · 無成本估算'}
            </option>
          ))}
        </select>

        {/* Unpriced flag below the field (native <select> can't badge options) */}
        {model.value && modelListed && !currentPriced && (
          <div className="flex items-center gap-1.5">
            <UnpricedBadge />
            <span className="text-foreground/40 text-[10px]">成本估算將標示為不完整</span>
          </div>
        )}

        {/* via toggle — only where the runtime can build direct (e.g. google LLM) */}
        {isDirectCapable(catalog, kind, provider.value) && (
          <ViaToggle
            via={via}
            onChange={(v) =>
              // Seed provider+model (like the model <select> above), not just
              // `via`. On an inherited spec, a `{ via }`-only patch is dropped by
              // pruneModels (specHasValue ignores via) → the direct choice silently
              // vanishes on save (review P1).
              onChange({ provider: provider.value, model: model.value, via: v })
            }
          />
        )}

        {/* TTS voice picker (separate models.tts.voice field) */}
        {kind === 'tts' && (
          <TtsVoiceControl
            provider={provider.value}
            voice={spec?.voice}
            voices={catalog.pipeline.voices[provider.value] ?? []}
            legacy={!spec?.voice && legacy ? legacy : null}
            onChange={(voice) => onChange({ voice })}
            onAdoptLegacy={(l) => onChange({ model: l.model, voice: l.voice })}
          />
        )}
      </div>
    </FieldRow>
  );
}

const VOICE_CUSTOM = '__custom__';
const VOICE_NONE = '';

// Per-provider suggested-voice picker for pipeline TTS. Suggested voices in a
// dropdown + a "自訂" option that reveals a free-text input (custom/cloned ids).
// When a provider has no suggested voices, degrades to free-text directly (M8).
function TtsVoiceControl({
  provider,
  voice,
  voices,
  legacy,
  onChange,
  onAdoptLegacy,
}: {
  provider: string;
  voice: string | undefined;
  voices: VoiceOption[];
  legacy: { model: string; voice: string } | null;
  onChange: (voice: string) => void;
  onAdoptLegacy: (l: { model: string; voice: string }) => void;
}) {
  const current = voice ?? '';
  const inSuggested = voices.some((v) => v.id === current);
  const [custom, setCustom] = useState(Boolean(current) && !inSuggested);
  const showFreeText = voices.length === 0 || custom || (Boolean(current) && !inSuggested);

  return (
    <div className="border-border/60 mt-0.5 space-y-1 rounded-md border border-dashed p-2">
      <span className="text-foreground/60 text-[11px] font-medium">語音 (Voice)</span>
      {legacy && (
        <div className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[10px] leading-relaxed text-amber-700 dark:text-amber-400">
          偵測到舊格式：語音編在 model id 內（{legacy.model}:{legacy.voice}）。
          <button type="button" className="ml-1 underline" onClick={() => onAdoptLegacy(legacy)}>
            改用獨立語音欄位
          </button>
        </div>
      )}
      {voices.length > 0 && (
        <select
          className={selectCls}
          value={custom ? VOICE_CUSTOM : current}
          onChange={(e) => {
            const v = e.target.value;
            if (v === VOICE_CUSTOM) {
              setCustom(true);
              return;
            }
            setCustom(false);
            onChange(v);
          }}
        >
          <option value={VOICE_NONE}>（用 model 內建語音）</option>
          {voices.map((v) => (
            <option key={v.id} value={v.id}>
              {v.label}
            </option>
          ))}
          <option value={VOICE_CUSTOM}>自訂 / 複製的語音…</option>
        </select>
      )}
      {showFreeText && (
        <input
          className={selectCls}
          value={current}
          onChange={(e) => onChange(e.target.value)}
          placeholder={
            voices.length === 0
              ? '輸入 voice id（此 provider 無建議清單）'
              : '輸入自訂 / 複製的 voice id'
          }
        />
      )}
      <p className="text-foreground/40 text-[10px]">
        選好語音後用 ▶ Try 試聽；留空則用 model 內建語音。
      </p>
    </div>
  );
}
