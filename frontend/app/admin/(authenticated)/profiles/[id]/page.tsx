'use client';

import { useEffect, useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import { Maximize2, Sparkles, X } from 'lucide-react';
import { buildFlowFromConfig } from '@/components/admin/agent-flow-builder';
import type { FlowNodeType } from '@/components/admin/agent-flow-builder';
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

export default function ProfileEditorV2Page() {
  const form = useProfileForm();
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);

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
            onSave={form.handleSave}
            onTry={form.handleTry}
            onSaveAndTry={form.handleSaveAndTry}
            onPanelToggle={() => setPanelOpen((o) => !o)}
          />
        }
        center={
          <PromptEditor
            form={form}
            onGenerateClick={() => setShowGenerateModal(true)}
            onSave={form.handleSave}
          />
        }
        rightPanel={<RightPanel form={form} />}
        panelOpen={panelOpen}
        onPanelClose={() => setPanelOpen(false)}
      />

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

// ─── Right Panel ──────────────────────────────────────────────────

function RightPanel({ form }: { form: ReturnType<typeof useProfileForm> }) {
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

  const handleNodeSelect = (_nodeId: string | null, nodeType: FlowNodeType | null) => {
    if (!nodeType) return;
    // Scroll to corresponding section
    const sectionMap: Record<string, string> = {
      prompt: 'section-qa', // prompt is already in center
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
      {/* Flow minimap at top */}
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
          <AgentFlowBuilder nodes={nodes} edges={edges} onNodeSelect={handleNodeSelect} readOnly />
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
