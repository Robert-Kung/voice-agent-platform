'use client';

import { useEffect, useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import { GitBranch, Maximize2, Sparkles, X } from 'lucide-react';
import { buildFlowFromConfig } from '@/components/admin/agent-flow-builder';
import type { FlowNodeType } from '@/components/admin/agent-flow-builder';
import { CollapsibleSection } from '@/components/admin/collapsible-section';
import type { GraphSelection } from '@/components/admin/graph-canvas';
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
  const [panelOpen, setPanelOpen] = useState(false);
  const [selection, setSelection] = useState<GraphSelection>(NO_SELECTION);
  const [confirmSave, setConfirmSave] = useState<'save' | 'saveAndTry' | null>(null);

  const isGraphMode = form.editorMode === 'graph' && !!form.known.graph;
  // editor_mode is the runtime strategy-source switch, not a view preference:
  // saving after a mode switch needs an explicit confirmation (review D5).
  const modeChanged = !form.isNew && form.editorMode !== form.savedEditorMode;

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

  // Execution path is implied by the profile-declared mode (models.mode, default
  // realtime). pipeline → graph runs natively; realtime → degrades to the
  // flattened instructions (graph branches don't drive the conversation). This is
  // the *declared* mode only — a deployment-layer AGENT_MODE env can override the
  // actual runtime path, so copy must not assert the runtime path as certain.
  const declaredMode: 'pipeline' | 'realtime' = useMemo(() => {
    try {
      const m = (JSON.parse(form.extraJson) as { models?: { mode?: unknown } }).models?.mode;
      // Mirror the backend's coercion (agent.py: str(...).strip().lower()) so a
      // capitalized models.mode shows the same banner the runtime will honor.
      return typeof m === 'string' && m.trim().toLowerCase() === 'pipeline'
        ? 'pipeline'
        : 'realtime';
    } catch {
      return 'realtime';
    }
  }, [form.extraJson]);

  const needsSaveConfirm = modeChanged || overwritesHandEditedInstructions;
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
            modeControl={<EditorModeControl form={form} />}
          />
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

      {/* Save confirmation (mode switch / hand-edited instructions overwrite) */}
      {confirmSave && (
        <SaveConfirmModal
          targetMode={form.editorMode}
          declaredMode={declaredMode}
          modeChanged={modeChanged}
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

function EditorModeControl({ form }: { form: ReturnType<typeof useProfileForm> }) {
  if (!form.known.graph) {
    return (
      <button
        type="button"
        onClick={form.convertToGraph}
        title="把現有 instructions 轉成單節點對話 graph（存檔時需確認切換執行來源）"
        className="border-border text-foreground/60 hover:bg-foreground/5 hover:text-foreground hidden items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs md:flex"
      >
        <GitBranch size={13} />
        轉成 Graph
      </button>
    );
  }
  return (
    <div className="hidden items-center gap-2 md:flex">
      <div className="border-border flex rounded-md border p-0.5">
        {(['prompt', 'graph'] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            onClick={() => form.setEditorMode(mode)}
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
}

// ─── Save confirmation (mode switch / hand-edit overwrite) ────────

function SaveConfirmModal({
  targetMode,
  declaredMode,
  modeChanged,
  overwritesHandEdited,
  onConfirm,
  onCancel,
}: {
  targetMode: 'prompt' | 'graph';
  declaredMode: 'pipeline' | 'realtime';
  modeChanged: boolean;
  overwritesHandEdited: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onCancel()}
    >
      <div className="bg-background border-border w-full max-w-md rounded-xl border p-6 shadow-xl">
        <h2 className="text-foreground mb-2 text-base font-semibold">
          {modeChanged ? '切換執行策略來源' : '確認覆蓋 instructions'}
        </h2>
        {modeChanged && (
          <p className="text-foreground/70 mb-3 text-sm leading-relaxed">
            這次存檔會把線上 runtime 的策略來源切換為
            <span className="font-semibold">{targetMode === 'graph' ? ' Graph' : ' Prompt'}</span>
            ，不只是編輯器視圖。
          </p>
        )}
        {overwritesHandEdited && (
          <p className="mb-3 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs leading-relaxed text-amber-600 dark:text-amber-400">
            目前的 instructions 與上次 graph 攤平結果不同（曾在 prompt 模式手動編輯過）。Graph
            模式存檔會以最新攤平結果覆蓋這些手改內容，無法復原。
          </p>
        )}
        {modeChanged && targetMode === 'prompt' && (
          <p className="text-foreground/50 mb-3 text-xs leading-relaxed">
            注意：Prompt 模式顯示的是最近一次 graph 攤平結果，不是轉換前的原文；之後的 graph
            編輯也不會反映到 prompt。
          </p>
        )}
        {modeChanged && targetMode === 'graph' && (
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
