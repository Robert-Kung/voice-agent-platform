'use client';

import { useEffect, useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import { GitBranch, Layers, Maximize2, Sparkles, X } from 'lucide-react';
import { buildFlowFromConfig } from '@/components/admin/agent-flow-builder';
import type { FlowNodeType } from '@/components/admin/agent-flow-builder';
import { CollapsibleSection } from '@/components/admin/collapsible-section';
import type { GraphSelection } from '@/components/admin/graph-canvas';
import { ModelVoiceView } from '@/components/admin/model-voice-view';
import { NodeInspector } from '@/components/admin/node-inspector';
import { ProfileEditorHeader } from '@/components/admin/profile-editor-header';
import { ProfileEditorLayout } from '@/components/admin/profile-editor-layout';
import {
  AdvancedSection,
  HandoffSection,
  HoursSection,
  IdentitySection,
  QaSection,
  ToolsSection,
} from '@/components/admin/profile-sections';
import { PromptEditor } from '@/components/admin/prompt-editor';
import { useProfileForm } from '@/hooks/use-profile-form';
import { graphToPrompt, normalizeGraph } from '@/lib/agent-graph';
import { specPrimary } from '@/lib/model-catalog';

const NO_SELECTION: GraphSelection = { nodeId: null, edgeId: null };

// Lazy-load the flow builder
const AgentFlowBuilder = dynamic(
  () => import('@/components/admin/agent-flow-builder').then((m) => m.AgentFlowBuilder),
  {
    ssr: false,
    loading: () => (
      <div className="bg-card border-border h-[200px] animate-pulse rounded-lg border" />
    ),
  }
);

const GraphCanvas = dynamic(
  () => import('@/components/admin/graph-canvas').then((m) => m.GraphCanvas),
  {
    ssr: false,
    loading: () => (
      <div className="bg-card border-border h-full min-h-[480px] animate-pulse rounded-xl border" />
    ),
  }
);

export default function ProfileEditorV2Page() {
  const form = useProfileForm();
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  // Full-width Model & Voice view (D1). A page-level render swap, NOT a route:
  // the editor form stays mounted so the unsaved draft survives the round trip.
  const [stackView, setStackView] = useState(false);
  // Graph-convert confirm modal (lives in EditorModeControl) — tracked here so the
  // Model & Voice view's ESC-to-return yields while it is open (ESC priority, D1).
  const [modeConfirmOpen, setModeConfirmOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [selection, setSelection] = useState<GraphSelection>(NO_SELECTION);
  const [confirmSave, setConfirmSave] = useState<'save' | 'saveAndTry' | null>(null);

  const isGraphMode = form.editorMode === 'graph' && !!form.known.graph;
  // editor_mode is the runtime strategy-source switch, not a view preference:
  // saving after a mode switch needs an explicit confirmation (review D5).
  const editorModeChanged = !form.isNew && form.editorMode !== form.savedEditorMode;
  // models.mode selects the runtime engine (cost/latency/graph-execution) — also a
  // strategy change gated by the same confirm (spec task 2.4).
  const engineModeChanged = !form.isNew && form.modelsMode !== form.savedModelMode;

  // A graph-mode save overwrites `instructions` with the flatten. When the
  // current instructions are not the flatten of the last-persisted graph, they
  // were hand-edited in prompt mode — confirm before silently destroying that.
  const overwritesHandEditedInstructions = useMemo(() => {
    if (!isGraphMode || form.isNew) return false;
    const persistedGraph = normalizeGraph(
      (form.profile?.config as Record<string, unknown> | undefined)?.graph
    );
    if (!persistedGraph) return false;
    return (form.known.instructions ?? '').trim() !== graphToPrompt(persistedGraph).trim();
  }, [isGraphMode, form.isNew, form.profile, form.known.instructions]);

  // Execution path is implied by the profile-declared engine mode (models.mode,
  // default realtime). pipeline → graph runs natively; realtime → degrades to the
  // flattened instructions (graph branches don't drive the conversation). This is
  // the *declared* mode only — a deployment-layer AGENT_MODE env can override the
  // actual runtime path, so copy must not assert the runtime path as certain.
  const declaredMode: 'pipeline' | 'realtime' = form.modelsMode;

  // Short stack summary for the header chip — reflects the profile-declared stack.
  const stackSummary =
    declaredMode === 'realtime'
      ? 'Realtime · Gemini Live'
      : `Pipeline · ${specPrimary(form.known.models?.llm)?.model ? '自訂' : 'LLM 預設'}`;

  const needsSaveConfirm =
    editorModeChanged || engineModeChanged || overwritesHandEditedInstructions;
  const guardedSave = () => {
    if (needsSaveConfirm) setConfirmSave('save');
    else void form.handleSave();
  };
  const guardedSaveAndTry = () => {
    if (needsSaveConfirm) setConfirmSave('saveAndTry');
    else void form.handleSaveAndTry();
  };

  const clearSelectionFor = (kind: 'nodeId' | 'edgeId', id: string) => {
    setSelection((s) => (s[kind] === id ? NO_SELECTION : s));
  };

  if (form.loading) {
    return (
      <div className="flex h-[calc(100vh-3.5rem)] items-center justify-center">
        <span className="text-foreground/50">Loading…</span>
      </div>
    );
  }

  if (form.error) {
    return (
      <div className="flex h-[calc(100vh-3.5rem)] items-center justify-center">
        <span className="text-red-500">Error: {form.error}</span>
      </div>
    );
  }

  return (
    <>
      <ProfileEditorLayout
        header={
          <ProfileEditorHeader
            displayName={form.displayName}
            profileName={form.name}
            language={form.known.language}
            isDirty={form.isDirty}
            isNew={form.isNew}
            saving={form.saving}
            trying={form.trying}
            onSave={guardedSave}
            onTry={form.handleTry}
            onSaveAndTry={guardedSaveAndTry}
            onPanelToggle={() => setPanelOpen((o) => !o)}
            modeControl={<EditorModeControl form={form} onConfirmingChange={setModeConfirmOpen} />}
            stackSummary={stackSummary}
            onStackClick={() => setStackView((v) => !v)}
          />
        }
        fullWidth={
          stackView ? (
            <ModelVoiceView
              form={form}
              onBack={() => setStackView(false)}
              escEnabled={!showGenerateModal && !confirmSave && !modeConfirmOpen}
            />
          ) : undefined
        }
        center={
          isGraphMode ? (
            <div className="flex h-full flex-col gap-3">
              {/* Execution-status banner, conditional on the profile-declared mode. */}
              {declaredMode === 'pipeline' ? (
                <div className="text-foreground/60 border-border bg-foreground/5 rounded-md border px-3 py-2 text-xs">
                  此 profile 宣告 pipeline 模式：部署後 graph 由 runtime 原生執行（每個節點一個
                  Agent，依轉移規則切換）。實際執行路徑仍可被部署層的 <code>AGENT_MODE</code> 覆蓋。
                </div>
              ) : (
                <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-600 dark:text-amber-400">
                  此 profile 宣告 realtime 模式：graph 的節點分支不會驅動對話——改由存檔時自動攤平的
                  單一 instructions 執行。Graph 原生執行僅在 pipeline
                  模式有效。實際執行路徑仍可被部署層的 <code>AGENT_MODE</code> 覆蓋。
                </div>
              )}
              {/* Branching-layer frame: the graph is layout-positioned as a layer
                  ON TOP of the always-on global base (right panel), not an
                  alternative to it (spec: global-as-base-layer IA, affordance not copy). */}
              <div className="border-primary/30 bg-primary/[0.03] flex min-h-0 flex-1 flex-col rounded-lg border border-dashed p-2">
                <div className="text-primary/70 mb-1.5 flex items-center gap-1.5 px-1 text-[11px] font-medium tracking-wide">
                  <GitBranch size={12} />
                  分支層 Branching layer
                  <span className="text-foreground/40 font-normal">
                    · 疊在 Global 底層之上，只負責流程分支
                  </span>
                </div>
                <div className="min-h-0 flex-1">
                  <GraphCanvas
                    graph={form.known.graph!}
                    selection={selection}
                    onSelect={setSelection}
                    onAddNode={form.addNode}
                    onRemoveNode={(id) => {
                      form.removeNode(id);
                      clearSelectionFor('nodeId', id);
                    }}
                    onRemoveEdge={(id) => {
                      form.removeEdge(id);
                      clearSelectionFor('edgeId', id);
                    }}
                    onConnect={form.addEdge}
                    onNodeDragStop={form.setNodePosition}
                  />
                </div>
              </div>
            </div>
          ) : (
            <div className="flex h-full flex-col gap-3">
              {form.known.graph && (
                <div className="border-border bg-foreground/5 text-foreground/60 rounded-md border px-3 py-2 text-xs">
                  此 prompt 為最近一次 graph 攤平結果（非轉換前原文）；prompt
                  模式下執行與編輯皆以此為準，graph 後續編輯不會反映於此。
                </div>
              )}
              <div className="min-h-0 flex-1">
                <PromptEditor
                  form={form}
                  onGenerateClick={() => setShowGenerateModal(true)}
                  onSave={guardedSave}
                />
              </div>
            </div>
          )
        }
        rightPanel={
          <RightPanel
            form={form}
            isGraphMode={isGraphMode}
            selection={selection}
            onSelect={setSelection}
          />
        }
        panelOpen={panelOpen}
        onPanelClose={() => setPanelOpen(false)}
      />

      {/* Save confirmation (strategy switches / hand-edited instructions overwrite).
          A single combined dialog lists every strategy change, never stacked. */}
      {confirmSave && (
        <SaveConfirmModal
          targetMode={form.editorMode}
          targetEngine={form.modelsMode}
          declaredMode={declaredMode}
          editorModeChanged={editorModeChanged}
          engineModeChanged={engineModeChanged}
          overwritesHandEdited={overwritesHandEditedInstructions}
          onCancel={() => setConfirmSave(null)}
          onConfirm={() => {
            const action = confirmSave === 'save' ? form.handleSave : form.handleSaveAndTry;
            setConfirmSave(null);
            void action();
          }}
        />
      )}

      {/* AI Generate Modal */}
      {showGenerateModal && (
        <GeneratePromptModal
          currentInstructions={form.known.instructions ?? ''}
          onClose={() => setShowGenerateModal(false)}
          onGenerated={(prompt) => {
            form.updateKnown('instructions', prompt);
            setShowGenerateModal(false);
          }}
        />
      )}
    </>
  );
}

// ─── Editor mode control (header) ─────────────────────────────────

function EditorModeControl({
  form,
  onConfirmingChange,
}: {
  form: ReturnType<typeof useProfileForm>;
  /** Notify the page when the graph-convert confirm modal opens/closes so the
   *  Model & Voice view's ESC-to-return yields to it (ESC priority, D1). */
  onConfirmingChange?: (open: boolean) => void;
}) {
  const [confirmGraph, setConfirmGraph] = useState<null | (() => void)>(null);

  useEffect(() => {
    onConfirmingChange?.(confirmGraph !== null);
  }, [confirmGraph, onConfirmingChange]);

  // Graph requires pipeline. Switching a realtime profile into graph would create
  // an unsavable graph+realtime state, so confirm first; the hook coerces
  // models.mode to pipeline as part of the switch (spec D4 / task 4.2).
  const intoGraph = (apply: () => void) => {
    if (form.modelsMode === 'realtime') setConfirmGraph(() => apply);
    else apply();
  };

  const control = !form.known.graph ? (
    <button
      type="button"
      onClick={() => intoGraph(form.convertToGraph)}
      title="把現有 instructions 轉成單節點對話 graph（存檔時需確認切換執行來源）"
      className="border-border text-foreground/60 hover:bg-foreground/5 hover:text-foreground hidden items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs md:flex"
    >
      <GitBranch size={13} />
      轉成 Graph
    </button>
  ) : (
    <div className="hidden items-center gap-2 md:flex">
      <div className="border-border flex rounded-md border p-0.5">
        {(['prompt', 'graph'] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            onClick={() =>
              mode === 'graph'
                ? intoGraph(() => form.setEditorMode('graph'))
                : form.setEditorMode('prompt')
            }
            className={`rounded px-2.5 py-0.5 text-xs font-medium transition-colors ${
              form.editorMode === mode
                ? 'bg-primary text-primary-foreground'
                : 'text-foreground/50 hover:text-foreground'
            }`}
          >
            {mode === 'prompt' ? 'Prompt' : 'Graph'}
          </button>
        ))}
      </div>
      {form.editorMode === 'graph' && (
        <span
          title="Graph 執行僅在 pipeline 部署生效。realtime 部署會 fallback 到攤平的 instructions（realtime 下 node 切換會被 Gemini Live 拒絕/忽略）。"
          className="rounded border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 text-[11px] font-medium text-amber-600/80 dark:text-amber-400/80"
        >
          需 pipeline 部署
        </span>
      )}
    </div>
  );

  return (
    <>
      {control}
      {confirmGraph && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
          onClick={(e) => e.target === e.currentTarget && setConfirmGraph(null)}
        >
          <div className="bg-background border-border w-full max-w-md rounded-xl border p-6 shadow-xl">
            <h2 className="text-foreground mb-2 text-base font-semibold">
              轉成 Graph 需切換為 Pipeline
            </h2>
            <p className="text-foreground/70 mb-4 text-sm leading-relaxed">
              Graph 執行僅支援 pipeline 引擎（realtime 下 node 切換會被 Gemini Live 拒絕/忽略）。 此
              profile 目前是 Realtime——轉成 Graph 會一併把引擎切為
              <span className="font-semibold"> Pipeline</span>。可稍後在 Stack 設定改回（但 Graph
              模式下 Realtime 會被鎖定）。
            </p>
            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setConfirmGraph(null)}
                className="border-border hover:bg-foreground/5 rounded-md border px-4 py-1.5 text-sm"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => {
                  confirmGraph();
                  setConfirmGraph(null);
                }}
                className="bg-primary text-primary-foreground rounded-md px-4 py-1.5 text-sm font-medium hover:opacity-90"
              >
                切換並轉成 Graph
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// ─── Save confirmation (mode switch / hand-edit overwrite) ────────

function SaveConfirmModal({
  targetMode,
  targetEngine,
  declaredMode,
  editorModeChanged,
  engineModeChanged,
  overwritesHandEdited,
  onConfirm,
  onCancel,
}: {
  targetMode: 'prompt' | 'graph';
  targetEngine: 'pipeline' | 'realtime';
  declaredMode: 'pipeline' | 'realtime';
  editorModeChanged: boolean;
  engineModeChanged: boolean;
  overwritesHandEdited: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const anyStrategyChange = editorModeChanged || engineModeChanged;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onCancel()}
    >
      <div className="bg-background border-border w-full max-w-md rounded-xl border p-6 shadow-xl">
        <h2 className="text-foreground mb-2 text-base font-semibold">
          {anyStrategyChange ? '切換 runtime 執行策略' : '確認覆蓋 instructions'}
        </h2>
        {anyStrategyChange && (
          <p className="text-foreground/70 mb-3 text-sm leading-relaxed">
            這次存檔會改動線上 runtime 的執行策略，不只是編輯器視圖：
          </p>
        )}
        {anyStrategyChange && (
          <ul className="mb-3 space-y-1.5 text-sm">
            {editorModeChanged && (
              <li className="text-foreground/70 flex gap-2">
                <span className="text-foreground/40">•</span>
                <span>
                  策略來源（editor_mode）切換為
                  <span className="font-semibold">
                    {targetMode === 'graph' ? ' Graph' : ' Prompt'}
                  </span>
                </span>
              </li>
            )}
            {engineModeChanged && (
              <li className="text-foreground/70 flex gap-2">
                <span className="text-foreground/40">•</span>
                <span>
                  執行引擎（models.mode）切換為
                  <span className="font-semibold">
                    {targetEngine === 'realtime' ? ' Realtime' : ' Pipeline'}
                  </span>
                  ，影響成本 / 延遲 / graph 執行
                </span>
              </li>
            )}
          </ul>
        )}
        {overwritesHandEdited && (
          <p className="mb-3 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs leading-relaxed text-amber-600 dark:text-amber-400">
            目前的 instructions 與上次 graph 攤平結果不同（曾在 prompt 模式手動編輯過）。Graph
            模式存檔會以最新攤平結果覆蓋這些手改內容，無法復原。
          </p>
        )}
        {editorModeChanged && targetMode === 'prompt' && (
          <p className="text-foreground/50 mb-3 text-xs leading-relaxed">
            注意：Prompt 模式顯示的是最近一次 graph 攤平結果，不是轉換前的原文；之後的 graph
            編輯也不會反映到 prompt。
          </p>
        )}
        {editorModeChanged && targetMode === 'graph' && (
          <p className="text-foreground/50 mb-3 text-xs leading-relaxed">
            {declaredMode === 'pipeline'
              ? '此 profile 宣告 pipeline 模式：部署後 graph 由 runtime 原生執行。實際執行路徑仍可被部署層的 AGENT_MODE 覆蓋。'
              : '此 profile 宣告 realtime 模式：graph 的節點分支不會驅動對話，改由自動攤平的 instructions 執行；graph 原生執行僅在 pipeline 模式有效。實際執行路徑仍可被部署層的 AGENT_MODE 覆蓋。'}
          </p>
        )}
        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="border-border hover:bg-foreground/5 rounded-md border px-4 py-1.5 text-sm"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="bg-primary text-primary-foreground rounded-md px-4 py-1.5 text-sm font-medium hover:opacity-90"
          >
            確認並儲存
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Right Panel ──────────────────────────────────────────────────

function RightPanel({
  form,
  isGraphMode,
  selection,
  onSelect,
}: {
  form: ReturnType<typeof useProfileForm>;
  isGraphMode: boolean;
  selection: GraphSelection;
  onSelect: (selection: GraphSelection) => void;
}) {
  const { nodes, edges } = useMemo(() => buildFlowFromConfig(form.known), [form.known]);
  const [flowExpanded, setFlowExpanded] = useState(false);

  useEffect(() => {
    if (!flowExpanded) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setFlowExpanded(false);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [flowExpanded]);

  // Node/edge selected on the canvas → inspector replaces the global panels.
  if (isGraphMode && (selection.nodeId || selection.edgeId)) {
    return (
      <NodeInspector form={form} selection={selection} onDeselect={() => onSelect(NO_SELECTION)} />
    );
  }

  const handleNodeSelect = (_nodeId: string | null, nodeType: FlowNodeType | null) => {
    if (!nodeType) return;
    // Scroll to corresponding section
    const sectionMap: Record<string, string> = {
      instructions: 'section-qa', // instructions is already in center
      qa_database: 'section-qa',
      service_hours: 'section-hours',
      human_handoff: 'section-handoff',
      builtin_tool: 'section-tools',
      http_tool: 'section-tools',
    };
    const targetId = sectionMap[nodeType];
    if (targetId) {
      document.getElementById(targetId)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <div className="space-y-0">
      {/* Persistent "global / applies everywhere" container header — the layout
          affordance that frames every section below (prompt, identity, QA, hours,
          tools, model/voice stack) as the always-on base layer applying to the
          whole agent in BOTH prompt and graph modes (spec: global-as-base-layer IA). */}
      <div className="border-border bg-foreground/[0.03] mb-2 rounded-lg border px-3 py-2">
        <div className="text-foreground/70 flex items-center gap-1.5 text-[11px] font-semibold tracking-wide uppercase">
          <Layers size={12} />
          Global · 適用整個 Agent
        </div>
        <p className="text-foreground/50 mt-0.5 text-[11px] leading-relaxed">
          {isGraphMode
            ? '以下設定（含模型/語音 stack）對所有節點永遠生效；graph 只在這層之上加流程分支，不是取代它。'
            : '以下設定（含模型/語音 stack）套用於整個 agent。單一流程用 Prompt 即可；需要多情境分支時再「轉成 Graph」，graph 會疊在同一 global 之上。'}
        </p>
      </div>

      {/* Graph mode: global prompt shared by all nodes */}
      {isGraphMode && (
        <CollapsibleSection title="Global Prompt" id="section-global-prompt" defaultOpen>
          <p className="text-foreground/50 mb-2 text-xs">
            跨所有節點共用的角色、語氣與鐵則；與各節點 prompt 組合後生效。
          </p>
          <textarea
            value={form.known.graph?.global_prompt ?? ''}
            onChange={(e) => form.updateGlobalPrompt(e.target.value)}
            rows={6}
            placeholder="例如：你是電梯維修中心的語音客服，使用繁體中文，語氣冷靜務實…"
            className="border-border bg-background text-foreground focus:ring-primary/40 w-full resize-y rounded-md border px-3 py-2 font-mono text-xs focus:ring-2 focus:outline-none"
          />
        </CollapsibleSection>
      )}

      {/* Flow minimap at top (prompt mode only — graph mode edits on the center canvas) */}
      {!isGraphMode && (
        <>
          <div className="border-border mb-0 border-b pb-3">
            <div className="flex items-center justify-between px-4 pt-2 pb-1">
              <span className="text-foreground/50 text-xs font-medium tracking-wider uppercase">
                Flow Overview
              </span>
              <button
                type="button"
                onClick={() => setFlowExpanded(true)}
                title="展開全螢幕"
                className="text-foreground/40 hover:text-foreground rounded p-1"
              >
                <Maximize2 size={12} />
              </button>
            </div>
            <div className="min-h-[300px] px-2">
              <AgentFlowBuilder
                nodes={nodes}
                edges={edges}
                onNodeSelect={handleNodeSelect}
                readOnly
              />
            </div>
          </div>

          {/* Fullscreen flow overlay */}
          {flowExpanded && (
            <div
              className="bg-background fixed inset-0 z-50 flex flex-col"
              onClick={(e) => e.target === e.currentTarget && setFlowExpanded(false)}
            >
              <div className="border-border flex items-center justify-between border-b px-4 py-2">
                <span className="text-sm font-medium">Flow Overview</span>
                <button
                  type="button"
                  onClick={() => setFlowExpanded(false)}
                  className="text-foreground/50 hover:text-foreground rounded p-1"
                >
                  <X size={18} />
                </button>
              </div>
              <div className="flex-1">
                <AgentFlowBuilder
                  nodes={nodes}
                  edges={edges}
                  onNodeSelect={handleNodeSelect}
                  readOnly
                />
              </div>
            </div>
          )}
        </>
      )}

      {/* Collapsible sections */}
      <ToolsSection form={form} />
      <QaSection form={form} />
      <HoursSection form={form} />
      <HandoffSection form={form} />
      <IdentitySection form={form} />
      <AdvancedSection form={form} />
    </div>
  );
}

// ─── Generate Prompt Modal ────────────────────────────────────────

type GenerateMode = 'create' | 'enhance';

function GeneratePromptModal({
  currentInstructions,
  onClose,
  onGenerated,
}: {
  currentInstructions: string;
  onClose: () => void;
  onGenerated: (prompt: string) => void;
}) {
  const hasExisting = currentInstructions.trim().length > 0;
  const [mode, setMode] = useState<GenerateMode>(hasExisting ? 'enhance' : 'create');
  const [description, setDescription] = useState('');
  const [direction, setDirection] = useState('');
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  const canGenerate =
    mode === 'create' ? description.trim().length > 0 : direction.trim().length > 0;

  const handleGenerate = async () => {
    if (!canGenerate) return;
    setGenerating(true);
    setError(null);
    try {
      const body =
        mode === 'create'
          ? { mode: 'create', description: description.trim() }
          : { mode: 'enhance', existing_prompt: currentInstructions, direction: direction.trim() };

      const res = await fetch('/api/admin/generate-prompt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(data.detail || 'Generation failed');
      }
      const data = await res.json();
      setPreview(data.prompt);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setGenerating(false);
    }
  };

  const handleReset = () => {
    setPreview(null);
    setError(null);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-background border-border w-full max-w-lg rounded-xl border p-6 shadow-xl">
        {/* Header */}
        <div className="mb-4 flex items-start justify-between gap-2">
          <h2 className="text-foreground flex items-center gap-2 text-lg font-semibold">
            <Sparkles size={18} />
            AI Generate Prompt
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-foreground/60 hover:bg-foreground/5 hover:text-foreground -mt-1 -mr-1 rounded-md p-1"
          >
            <X size={16} />
          </button>
        </div>

        {/* Mode tabs */}
        {!preview && (
          <div className="border-border mb-4 flex rounded-md border p-0.5">
            {(['create', 'enhance'] as GenerateMode[]).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => {
                  setMode(m);
                  setError(null);
                }}
                disabled={m === 'enhance' && !hasExisting}
                className={`flex-1 rounded py-1 text-xs font-medium transition-colors ${
                  mode === m
                    ? 'bg-primary text-primary-foreground'
                    : 'text-foreground/50 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40'
                }`}
              >
                {m === 'create' ? '全新建立' : '補強現有'}
              </button>
            ))}
          </div>
        )}

        {preview !== null ? (
          /* Preview pane */
          <>
            <p className="text-foreground/60 mb-3 text-xs">
              {mode === 'enhance'
                ? '補強結果預覽 — 確認後將覆寫現有 prompt。'
                : '生成結果預覽 — 確認後將覆寫現有 prompt。'}
            </p>
            <textarea
              value={preview}
              readOnly
              rows={12}
              className="border-border bg-foreground/5 text-foreground mb-3 w-full resize-y rounded-md border px-3 py-2 font-mono text-xs focus:outline-none"
            />
            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={handleReset}
                className="border-border hover:bg-foreground/5 rounded-md border px-4 py-1.5 text-sm"
              >
                重新產生
              </button>
              <button
                type="button"
                onClick={() => onGenerated(preview)}
                className="rounded-md bg-green-600 px-4 py-1.5 text-sm font-medium text-white hover:opacity-90"
              >
                Replace
              </button>
            </div>
          </>
        ) : mode === 'create' ? (
          /* Create form */
          <>
            <p className="text-foreground/60 mb-3 text-sm">
              描述業務場景與功能需求，AI 會從頭產生 system prompt 初稿。
            </p>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              placeholder="例如：一家台北的牙醫診所客服，需要處理預約掛號、費用查詢、營業時間詢問，語氣親切專業。"
              className="border-border bg-background text-foreground focus:ring-primary/40 mb-3 w-full resize-y rounded-md border px-3 py-2 text-sm focus:ring-2 focus:outline-none"
              autoFocus
            />
            {error && <p className="mb-2 text-xs text-red-500">{error}</p>}
            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                className="border-border hover:bg-foreground/5 rounded-md border px-4 py-1.5 text-sm"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleGenerate}
                disabled={generating || !canGenerate}
                className="bg-primary text-primary-foreground rounded-md px-4 py-1.5 text-sm font-medium hover:opacity-90 disabled:opacity-50"
              >
                {generating ? '生成中…' : 'Generate'}
              </button>
            </div>
          </>
        ) : (
          /* Enhance form */
          <>
            <div className="border-border bg-foreground/5 mb-3 rounded-md border px-3 py-2">
              <p className="text-foreground/40 mb-1 text-[10px] tracking-wider uppercase">
                現有 Prompt（前 300 字）
              </p>
              <p className="text-foreground/70 line-clamp-4 font-mono text-xs whitespace-pre-wrap">
                {currentInstructions.slice(0, 300)}
                {currentInstructions.length > 300 ? '…' : ''}
              </p>
            </div>
            <p className="text-foreground/60 mb-2 text-sm">描述你希望補強或改進的方向：</p>
            <textarea
              value={direction}
              onChange={(e) => setDirection(e.target.value)}
              rows={3}
              placeholder="例如：加強拒絕非相關問題的措辭、補充預約取消的流程、語氣更親切一些"
              className="border-border bg-background text-foreground focus:ring-primary/40 mb-3 w-full resize-y rounded-md border px-3 py-2 text-sm focus:ring-2 focus:outline-none"
              autoFocus
            />
            {error && <p className="mb-2 text-xs text-red-500">{error}</p>}
            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                className="border-border hover:bg-foreground/5 rounded-md border px-4 py-1.5 text-sm"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleGenerate}
                disabled={generating || !canGenerate}
                className="bg-primary text-primary-foreground rounded-md px-4 py-1.5 text-sm font-medium hover:opacity-90 disabled:opacity-50"
              >
                {generating ? '補強中…' : 'Enhance'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
