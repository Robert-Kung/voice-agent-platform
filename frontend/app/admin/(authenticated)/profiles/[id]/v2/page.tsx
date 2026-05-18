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
      />

      {/* AI Generate Modal */}
      {showGenerateModal && (
        <GeneratePromptModal
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

  const handleNodeSelect = (nodeId: string | null, nodeType: FlowNodeType | null) => {
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

function GeneratePromptModal({
  onClose,
  onGenerated,
}: {
  onClose: () => void;
  onGenerated: (prompt: string) => void;
}) {
  const [description, setDescription] = useState('');
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);

  // Escape key closes modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const handleGenerate = async () => {
    if (!description.trim()) return;
    setGenerating(true);
    setError(null);
    try {
      const res = await fetch('/api/admin/generate-prompt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: description.trim() }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(body.detail || 'Generation failed');
      }
      const data = await res.json();
      setPreview(data.prompt);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setGenerating(false);
    }
  };

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose();
  };

  const isPreview = preview !== null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={handleBackdropClick}
    >
      <div className="bg-background border-border w-full max-w-lg rounded-xl border p-6 shadow-xl">
        <div className="mb-2 flex items-start justify-between gap-2">
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

        {!isPreview ? (
          <>
            <p className="text-foreground/60 mb-4 text-sm">
              描述這個 Agent 的業務類型和功能需求，AI 會產生 system prompt 初稿。
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
                disabled={generating || !description.trim()}
                className="bg-primary text-primary-foreground rounded-md px-4 py-1.5 text-sm font-medium hover:opacity-90 disabled:opacity-50"
              >
                {generating ? '生成中…' : 'Generate'}
              </button>
            </div>
          </>
        ) : (
          <>
            <p className="text-foreground/60 mb-3 text-sm">
              預覽生成結果。此操作將覆寫現有 system prompt。
            </p>
            <textarea
              value={preview ?? ''}
              readOnly
              rows={10}
              className="border-border bg-foreground/5 text-foreground mb-3 w-full resize-y rounded-md border px-3 py-2 font-mono text-xs focus:outline-none"
            />
            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setPreview(null);
                  setError(null);
                }}
                className="border-border hover:bg-foreground/5 rounded-md border px-4 py-1.5 text-sm"
              >
                重新產生
              </button>
              <button
                type="button"
                onClick={() => {
                  if (preview !== null) onGenerated(preview);
                }}
                className="rounded-md bg-green-600 px-4 py-1.5 text-sm font-medium text-white hover:opacity-90"
              >
                Replace
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
