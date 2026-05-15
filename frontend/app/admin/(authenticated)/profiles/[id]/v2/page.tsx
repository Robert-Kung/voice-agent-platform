'use client';

import { useState } from 'react';
import { useMemo } from 'react';
import dynamic from 'next/dynamic';
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
        <div className="px-4 pt-2 pb-1">
          <span className="text-foreground/50 text-[10px] font-medium tracking-wider uppercase">
            Flow Overview
          </span>
        </div>
        <div className="h-[200px] px-2">
          <AgentFlowBuilder nodes={nodes} edges={edges} onNodeSelect={handleNodeSelect} readOnly />
        </div>
      </div>

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
      onGenerated(data.prompt);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-background border-border w-full max-w-lg rounded-xl border p-6 shadow-xl">
        <h2 className="text-foreground mb-2 text-lg font-semibold">✨ AI Generate Prompt</h2>
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
      </div>
    </div>
  );
}
