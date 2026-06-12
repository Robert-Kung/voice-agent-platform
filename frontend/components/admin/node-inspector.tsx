'use client';

import { Trash2 } from 'lucide-react';
import type { UseProfileFormReturn } from '@/hooks/use-profile-form';
import {
  AUTO_MOUNTED_TOOL_NAMES,
  EDGE_TRIGGERS,
  NODE_TYPE_LABELS,
  edgeTrigger,
} from '@/lib/agent-graph';
import type { GraphSelection } from './graph-canvas';

const inputClass =
  'border-border bg-background text-foreground w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40';

const TRIGGER_LABELS: Record<string, string> = {
  user_turn: '使用者回合（依對話內容判斷）',
  tool_result: '工具結果（工具回傳後立即評估）',
};

interface NodeInspectorProps {
  form: UseProfileFormReturn;
  selection: GraphSelection;
  onDeselect: () => void;
}

export function NodeInspector({ form, selection, onDeselect }: NodeInspectorProps) {
  const graph = form.known.graph;
  if (!graph) return null;

  if (selection.nodeId) {
    const node = graph.nodes.find((n) => n.id === selection.nodeId);
    if (!node) return null;
    return <NodePanel form={form} node={node} onDeselect={onDeselect} />;
  }
  if (selection.edgeId) {
    const edge = graph.edges.find((e) => e.id === selection.edgeId);
    if (!edge) return null;
    return <EdgePanel form={form} edge={edge} onDeselect={onDeselect} />;
  }
  return null;
}

// ─── Node panel ───────────────────────────────────────────────────

function NodePanel({
  form,
  node,
  onDeselect,
}: {
  form: UseProfileFormReturn;
  node: NonNullable<UseProfileFormReturn['known']['graph']>['nodes'][number];
  onDeselect: () => void;
}) {
  const { known, availableTools, updateKnown, updateNode, removeNode } = form;

  const httpToolNames = (known.tools || [])
    .filter((t) => !!t.endpoint)
    .map((t) => t.name)
    .filter(Boolean);
  const builtinNames = availableTools.filter((n) => !AUTO_MOUNTED_TOOL_NAMES.includes(n));
  // Auto-mounted tools are legal references (validateGraph agrees) but absent
  // from the attachable lists; render them with a badge instead of as orphans.
  const autoMountedReferenced = node.tools.filter((t) => AUTO_MOUNTED_TOOL_NAMES.includes(t));
  // Referenced names outside the attachable lists (e.g. a deleted HTTP tool) stay
  // visible so the user can detach them deliberately — validateGraph warns, never auto-removes.
  const knownNames = new Set([...builtinNames, ...httpToolNames, ...AUTO_MOUNTED_TOOL_NAMES]);
  const orphanNames = node.tools.filter((t) => !knownNames.has(t));

  const toggleNodeTool = (name: string) => {
    const tools = node.tools.includes(name)
      ? node.tools.filter((t) => t !== name)
      : [...node.tools, name];
    updateNode(node.id, { tools });
  };

  return (
    <div className="space-y-4 px-4 py-3">
      <PanelHeader
        title={`Node：${NODE_TYPE_LABELS[node.type]}`}
        subtitle={node.id}
        onDeselect={onDeselect}
      />

      <div>
        <label className="text-foreground/60 mb-1 block text-xs font-medium">Title</label>
        <input
          type="text"
          value={node.title}
          onChange={(e) => updateNode(node.id, { title: e.target.value })}
          className={inputClass}
        />
      </div>

      {node.type === 'start' && (
        <div className="border-border bg-foreground/5 space-y-3 rounded-md border p-3">
          <p className="text-foreground/50 text-[11px] leading-relaxed">
            開場欄位（存於 profile 頂層，僅入口節點顯示）：pipeline 逐字朗讀 Welcome
            Message；realtime 依 Welcome Instructions 生成。
          </p>
          <div>
            <label className="text-foreground/60 mb-1 block text-xs font-medium">
              Welcome Message
            </label>
            <textarea
              value={known.welcome_message ?? ''}
              onChange={(e) => updateKnown('welcome_message', e.target.value)}
              rows={2}
              className={`${inputClass} resize-y`}
            />
          </div>
          <div>
            <label className="text-foreground/60 mb-1 block text-xs font-medium">
              Welcome Instructions
            </label>
            <textarea
              value={known.welcome_instructions ?? ''}
              onChange={(e) => updateKnown('welcome_instructions', e.target.value)}
              rows={2}
              className={`${inputClass} resize-y`}
            />
          </div>
        </div>
      )}

      <div>
        <label className="text-foreground/60 mb-1 block text-xs font-medium">
          Prompt
          <span className="text-foreground/40 ml-2 font-normal">
            {node.type === 'handoff' ? '（此轉接的話術 / 指示）' : '（此階段的 focused prompt）'}
          </span>
        </label>
        <textarea
          value={node.prompt}
          onChange={(e) => updateNode(node.id, { prompt: e.target.value })}
          rows={node.type === 'end' ? 3 : 10}
          placeholder={node.type === 'end' ? '（可留空）' : '這個階段 Agent 該做什麼…'}
          className={`${inputClass} resize-y font-mono text-xs`}
        />
      </div>

      <div>
        <label className="text-foreground/60 mb-1 block text-xs font-medium">
          Tools
          <span className="text-foreground/40 ml-2 font-normal">
            （引用全域工具，定義在 Tools 面板維護）
          </span>
        </label>
        <div className="space-y-1.5">
          {[...builtinNames, ...httpToolNames].map((name) => (
            <ToolCheckbox
              key={name}
              name={name}
              checked={node.tools.includes(name)}
              onToggle={() => toggleNodeTool(name)}
            />
          ))}
          {autoMountedReferenced.map((name) => (
            <ToolCheckbox
              key={name}
              name={name}
              checked
              badge="自動掛載"
              onToggle={() => toggleNodeTool(name)}
            />
          ))}
          {orphanNames.map((name) => (
            <ToolCheckbox
              key={name}
              name={name}
              checked
              badge="找不到此工具定義"
              badgeTone="warn"
              onToggle={() => toggleNodeTool(name)}
            />
          ))}
          {builtinNames.length + httpToolNames.length + orphanNames.length === 0 && (
            <p className="text-foreground/50 text-xs">無可用工具</p>
          )}
        </div>
      </div>

      <button
        type="button"
        disabled={node.type === 'start'}
        title={node.type === 'start' ? 'start 入口節點不可刪除' : undefined}
        onClick={() => {
          removeNode(node.id);
          onDeselect();
        }}
        className="border-border flex w-full items-center justify-center gap-1.5 rounded-md border px-3 py-1.5 text-xs text-red-500 hover:bg-red-500/5 disabled:cursor-not-allowed disabled:opacity-40"
      >
        <Trash2 size={13} />
        刪除節點（含相連的邊）
      </button>
    </div>
  );
}

function ToolCheckbox({
  name,
  checked,
  badge,
  badgeTone,
  onToggle,
}: {
  name: string;
  checked: boolean;
  badge?: string;
  badgeTone?: 'warn';
  onToggle: () => void;
}) {
  return (
    <label
      className={`flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-xs transition-colors ${
        checked ? 'border-primary/50 bg-primary/5' : 'border-border hover:bg-foreground/5'
      }`}
    >
      <input type="checkbox" checked={checked} onChange={onToggle} className="size-3" />
      <span className="font-mono">{name}</span>
      {badge && (
        <span
          className={`text-[10px] ${badgeTone === 'warn' ? 'text-amber-500' : 'text-foreground/40'}`}
        >
          {badge}
        </span>
      )}
    </label>
  );
}

// ─── Edge panel ───────────────────────────────────────────────────

function EdgePanel({
  form,
  edge,
  onDeselect,
}: {
  form: UseProfileFormReturn;
  edge: NonNullable<UseProfileFormReturn['known']['graph']>['edges'][number];
  onDeselect: () => void;
}) {
  const { known, updateEdge, removeEdge } = form;
  const graph = known.graph;
  const titleOf = (id: string) => graph?.nodes.find((n) => n.id === id)?.title || id;

  return (
    <div className="space-y-4 px-4 py-3">
      <PanelHeader
        title="Edge：轉移規則"
        subtitle={`${titleOf(edge.source)} → ${titleOf(edge.target)}`}
        onDeselect={onDeselect}
      />

      <div>
        <label className="text-foreground/60 mb-1 block text-xs font-medium">Trigger</label>
        <select
          value={edgeTrigger(edge)}
          onChange={(e) =>
            updateEdge(edge.id, { trigger: e.target.value as (typeof EDGE_TRIGGERS)[number] })
          }
          className={inputClass}
        >
          {EDGE_TRIGGERS.map((t) => (
            <option key={t} value={t}>
              {TRIGGER_LABELS[t]}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="text-foreground/60 mb-1 block text-xs font-medium">
          Condition
          <span className="text-foreground/40 ml-2 font-normal">（自然語言；留空＝無條件）</span>
        </label>
        <textarea
          value={edge.condition}
          onChange={(e) => updateEdge(edge.id, { condition: e.target.value })}
          rows={3}
          placeholder={
            edgeTrigger(edge) === 'tool_result'
              ? '例如：建單成功 / 建單失敗或 timeout'
              : '例如：來電者描述關人、受傷等緊急狀況'
          }
          className={`${inputClass} resize-y`}
        />
      </div>

      <div>
        <label className="text-foreground/60 mb-1 block text-xs font-medium">
          Label
          <span className="text-foreground/40 ml-2 font-normal">（畫布顯示，選填）</span>
        </label>
        <input
          type="text"
          value={edge.label ?? ''}
          onChange={(e) => updateEdge(edge.id, { label: e.target.value || undefined })}
          className={inputClass}
        />
      </div>

      <p className="text-foreground/40 text-[11px] leading-relaxed">
        同一節點多條出邊時，依建立順序先命中者生效；無條件邊之後的規則不會被評估。
      </p>

      <button
        type="button"
        onClick={() => {
          removeEdge(edge.id);
          onDeselect();
        }}
        className="border-border flex w-full items-center justify-center gap-1.5 rounded-md border px-3 py-1.5 text-xs text-red-500 hover:bg-red-500/5"
      >
        <Trash2 size={13} />
        刪除這條轉移
      </button>
    </div>
  );
}

// ─── Shared ───────────────────────────────────────────────────────

function PanelHeader({
  title,
  subtitle,
  onDeselect,
}: {
  title: string;
  subtitle: string;
  onDeselect: () => void;
}) {
  return (
    <div className="flex items-start justify-between">
      <div className="min-w-0">
        <h3 className="text-sm font-semibold">{title}</h3>
        <p className="text-foreground/40 truncate font-mono text-[11px]">{subtitle}</p>
      </div>
      <button
        type="button"
        onClick={onDeselect}
        className="text-foreground/40 hover:text-foreground shrink-0 text-xs"
      >
        返回全域設定
      </button>
    </div>
  );
}
