'use client';

import { Info, Lock } from 'lucide-react';
import { useModelCatalog } from '@/hooks/use-model-catalog';
import type { UseProfileFormReturn } from '@/hooks/use-profile-form';
import { type ModelSpec, resolveField, specPrimary } from '@/lib/model-catalog';

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
      <SpecField
        label="STT 來源 (轉文字餵給 Gemini)"
        kind="stt"
        spec={specPrimary(rt?.stt)}
        providers={catalog.pipeline.stt_providers}
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

  const llmModel = resolveField(
    llm?.provider && llm?.model ? `${llm.provider}/${llm.model}` : undefined,
    `${catalog.pipeline.defaults.llm.provider}/${catalog.pipeline.defaults.llm.model}`
  );

  return (
    <div className="space-y-3">
      <FieldRow label="LLM" source={llmModel.source}>
        <select
          className={selectCls}
          value={llmModel.value}
          onChange={(e) => {
            const [provider, ...rest] = e.target.value.split('/');
            form.updateModelSpec('llm', { provider, model: rest.join('/'), via: 'inference' });
          }}
        >
          {/* Pinned-but-unlisted value stays selectable so a custom model round-trips. */}
          {!catalog.pipeline.llm_options.some(
            (o) => `${o.provider}/${o.model}` === llmModel.value
          ) && <option value={llmModel.value}>{llmModel.value}</option>}
          {catalog.pipeline.llm_options.map((o) => {
            const id = `${o.provider}/${o.model}`;
            return (
              <option key={id} value={id}>
                {id}
              </option>
            );
          })}
        </select>
      </FieldRow>

      <SpecField
        label="STT (語音轉文字)"
        kind="stt"
        spec={stt}
        providers={catalog.pipeline.stt_providers}
        compiledDefault={catalog.pipeline.defaults.stt}
        onChange={(patch) => form.updateModelSpec('stt', patch)}
      />

      <SpecField
        label="TTS / 語音 (Voice)"
        kind="tts"
        spec={tts}
        providers={catalog.pipeline.tts_providers}
        compiledDefault={catalog.pipeline.defaults.tts}
        onChange={(patch) => form.updateModelSpec('tts', patch)}
        hint="Pipeline 的語音編在 TTS 的 model id（多數 provider 以 model 帶 voice）。"
      />
    </div>
  );
}

function SpecField({
  label,
  spec,
  providers,
  compiledDefault,
  onChange,
  hint,
}: {
  label: string;
  kind: 'stt' | 'tts';
  spec: ModelSpec | undefined;
  providers: string[];
  compiledDefault: ModelSpec;
  onChange: (patch: Partial<ModelSpec>) => void;
  hint?: string;
}) {
  const provider = resolveField(spec?.provider, compiledDefault.provider ?? '');
  const model = resolveField(spec?.model, compiledDefault.model ?? '');
  // pinned if either field is set by the user
  const source = spec?.provider || spec?.model ? 'pinned' : 'inherited';
  const providerOptions = providers.includes(provider.value)
    ? providers
    : [provider.value, ...providers];

  return (
    <FieldRow label={label} source={source}>
      <div className="flex gap-2">
        {/* Always write a COMPLETE spec: pinning one field seeds the other from
            the currently-shown value (pinned or compiled default), so we never
            persist a model-less or provider-less spec the backend would 422. */}
        <select
          className={`${selectCls} flex-[2]`}
          value={provider.value}
          onChange={(e) =>
            onChange({ provider: e.target.value, model: model.value, via: 'inference' })
          }
        >
          {providerOptions.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <input
          className={`${selectCls} flex-[3]`}
          value={model.value}
          onChange={(e) =>
            onChange({ provider: provider.value, model: e.target.value, via: 'inference' })
          }
          placeholder={compiledDefault.model}
        />
      </div>
      {hint && <p className="text-foreground/40 text-[10px]">{hint}</p>}
    </FieldRow>
  );
}
