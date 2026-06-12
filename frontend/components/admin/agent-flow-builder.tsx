'use client';

import { useCallback, useMemo } from 'react';
import {
  BrainCircuit,
  Clock,
  Database,
  Globe,
  MessageSquare,
  Phone,
  Play,
  Square,
  Wrench,
} from 'lucide-react';
import {
  Background,
  BackgroundVariant,
  type Connection,
  Controls,
  type Edge,
  Handle,
  type Node,
  type NodeProps,
  Panel,
  Position,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  useEdgesState,
  useNodesState,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type { AgentGraph } from '@/lib/agent-graph';
import { TOOL_RESULT_EDGE_LABEL, edgeTrigger, normalizeGraph } from '@/lib/agent-graph';
import { cn } from '@/lib/shadcn/utils';

// ─── Types ────────────────────────────────────────────────────────
// 'instructions' is the hub-and-spoke spoke for the legacy projection (renamed
// from 'prompt' to free that name for the conversation-graph prompt node).
export type FlowNodeType =
  | 'instructions'
  | 'qa_database'
  | 'service_hours'
  | 'human_handoff'
  | 'builtin_tool'
  | 'http_tool'
  | 'start'
  | 'prompt'
  | 'end'
  | 'handoff';

export interface FlowNodeData {
  label: string;
  type: FlowNodeType;
  enabled?: boolean;
  config?: Record<string, unknown>;
  [key: string]: unknown;
}

interface AgentFlowBuilderProps {
  nodes: Node<FlowNodeData>[];
  edges: Edge[];
  onNodesChange?: (nodes: Node<FlowNodeData>[]) => void;
  onEdgesChange?: (edges: Edge[]) => void;
  onNodeSelect?: (nodeId: string | null, nodeType: FlowNodeType | null) => void;
  readOnly?: boolean;
}

// ─── Node Icons ───────────────────────────────────────────────────
export const NODE_ICONS: Record<FlowNodeType, React.ComponentType<{ className?: string }>> = {
  instructions: MessageSquare,
  qa_database: Database,
  service_hours: Clock,
  human_handoff: Phone,
  builtin_tool: Wrench,
  http_tool: Globe,
  start: Play,
  prompt: MessageSquare,
  end: Square,
  handoff: Phone,
};

export const NODE_COLORS: Record<FlowNodeType, string> = {
  instructions: 'border-chart-1/50 bg-chart-1/10',
  qa_database: 'border-chart-2/50 bg-chart-2/10',
  service_hours: 'border-chart-3/50 bg-chart-3/10',
  human_handoff: 'border-chart-4/50 bg-chart-4/10',
  builtin_tool: 'border-chart-5/50 bg-chart-5/10',
  http_tool: 'border-primary/50 bg-primary/10',
  start: 'border-chart-2/50 bg-chart-2/10',
  prompt: 'border-chart-1/50 bg-chart-1/10',
  end: 'border-border bg-foreground/5',
  handoff: 'border-chart-4/50 bg-chart-4/10',
};

export const NODE_ICON_COLORS: Record<FlowNodeType, string> = {
  instructions: 'text-chart-1',
  qa_database: 'text-chart-2',
  service_hours: 'text-chart-3',
  human_handoff: 'text-chart-4',
  builtin_tool: 'text-chart-5',
  http_tool: 'text-primary',
  start: 'text-chart-2',
  prompt: 'text-chart-1',
  end: 'text-foreground/60',
  handoff: 'text-chart-4',
};

// ─── Custom Node Component ────────────────────────────────────────
function FlowNode({ data, selected }: NodeProps<Node<FlowNodeData>>) {
  const Icon = NODE_ICONS[data.type] || BrainCircuit;
  const colorClass = NODE_COLORS[data.type] || 'border-border bg-card';
  const iconColor = NODE_ICON_COLORS[data.type] || 'text-foreground';
  const isDisabled = data.enabled === false;

  return (
    <div
      className={cn(
        'rounded-lg border-2 px-4 py-3 shadow-md transition-all',
        colorClass,
        selected && 'ring-primary/50 ring-2',
        isDisabled && 'opacity-40'
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!bg-primary !border-background !size-2.5"
      />
      <div className="flex items-center gap-2.5">
        <Icon className={cn('size-4 shrink-0', iconColor)} />
        <div className="min-w-0">
          <div className="truncate text-xs font-semibold">{data.label}</div>
          {isDisabled && <div className="text-muted-foreground text-[10px]">disabled</div>}
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className="!bg-primary !border-background !size-2.5"
      />
    </div>
  );
}

// ─── Agent Core Node (center hub) ─────────────────────────────────
function AgentCoreNode({ selected }: NodeProps) {
  return (
    <div
      className={cn(
        'bg-primary/20 border-primary/60 flex items-center gap-2 rounded-xl border-2 px-5 py-4 shadow-lg',
        selected && 'ring-primary ring-2'
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!bg-primary !border-background !size-3"
      />
      <BrainCircuit className="text-primary size-5" />
      <span className="text-sm font-bold">Agent</span>
      <Handle
        type="source"
        position={Position.Right}
        className="!bg-primary !border-background !size-3"
      />
    </div>
  );
}

// ─── Node Types Registration ──────────────────────────────────────
const nodeTypes = {
  flowNode: FlowNode,
  agentCore: AgentCoreNode,
};

// ─── Layout Helper ────────────────────────────────────────────────
export function buildFlowFromConfig(config: {
  instructions?: string;
  qa_mode?: string;
  qa_data?: unknown[];
  services?: Record<string, unknown>;
  human_operator?: { enabled?: boolean };
  tools?: Array<{ name: string; endpoint?: string; description?: string }>;
  graph?: AgentGraph;
}): { nodes: Node<FlowNodeData>[]; edges: Edge[] } {
  // Profiles with a graph block render the conversation graph directly;
  // everything below stays the legacy hub-and-spoke projection (regression-locked).
  // normalizeGraph guards callers that pass raw (non-form-hook) config.
  const graph = normalizeGraph(config.graph);
  if (graph) {
    return {
      nodes: graph.nodes.map((n) => ({
        id: n.id,
        type: 'flowNode' as const,
        position: n.position,
        data: {
          label: n.title || n.id,
          type: n.type as FlowNodeType,
          enabled: true,
          config: { prompt: n.prompt, tools: n.tools },
        },
      })),
      edges: graph.edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        animated: true,
        label: e.label || (edgeTrigger(e) === 'tool_result' ? TOOL_RESULT_EDGE_LABEL : undefined),
      })),
    };
  }

  const nodes: Node<FlowNodeData>[] = [];
  const edges: Edge[] = [];

  // Agent core node (center)
  const coreId = 'agent-core';
  nodes.push({
    id: coreId,
    type: 'agentCore',
    position: { x: 400, y: 200 },
    data: { label: 'Agent', type: 'instructions' },
  });

  let leftY = 60;
  const LEFT_X = 80;
  const Y_GAP = 90;

  // Prompt node
  const promptId = 'prompt';
  nodes.push({
    id: promptId,
    type: 'flowNode',
    position: { x: LEFT_X, y: leftY },
    data: {
      label: 'Instructions',
      type: 'instructions',
      enabled: !!config.instructions,
    },
  });
  edges.push({ id: `e-${promptId}-core`, source: promptId, target: coreId, animated: true });
  leftY += Y_GAP;

  // QA Database
  if (config.qa_data && config.qa_data.length > 0) {
    const qaId = 'qa-database';
    nodes.push({
      id: qaId,
      type: 'flowNode',
      position: { x: LEFT_X, y: leftY },
      data: {
        label: `QA Database (${config.qa_mode || 'inline'})`,
        type: 'qa_database',
        enabled: true,
        config: { mode: config.qa_mode, count: config.qa_data.length },
      },
    });
    edges.push({ id: `e-${qaId}-core`, source: qaId, target: coreId, animated: true });
    leftY += Y_GAP;
  }

  // Service Hours
  if (config.services && Object.keys(config.services).length > 0) {
    const svcId = 'service-hours';
    nodes.push({
      id: svcId,
      type: 'flowNode',
      position: { x: LEFT_X, y: leftY },
      data: {
        label: 'Service Hours',
        type: 'service_hours',
        enabled: true,
      },
    });
    edges.push({ id: `e-${svcId}-core`, source: svcId, target: coreId, animated: true });
    leftY += Y_GAP;
  }

  // Human Handoff
  if (config.human_operator?.enabled) {
    const hoId = 'human-handoff';
    nodes.push({
      id: hoId,
      type: 'flowNode',
      position: { x: LEFT_X, y: leftY },
      data: {
        label: 'Human Handoff',
        type: 'human_handoff',
        enabled: true,
      },
    });
    edges.push({ id: `e-${hoId}-core`, source: hoId, target: coreId, animated: true });
    leftY += Y_GAP;
  }

  // Tools (right side)
  let rightY = 80;
  const RIGHT_X = 700;
  const tools = config.tools || [];

  for (const tool of tools) {
    const isHttp = !!tool.endpoint;
    const toolId = `tool-${tool.name}`;
    nodes.push({
      id: toolId,
      type: 'flowNode',
      position: { x: RIGHT_X, y: rightY },
      data: {
        label: tool.name,
        type: isHttp ? 'http_tool' : 'builtin_tool',
        enabled: true,
        config: { description: tool.description },
      },
    });
    edges.push({ id: `e-core-${toolId}`, source: coreId, target: toolId, animated: true });
    rightY += Y_GAP;
  }

  return { nodes, edges };
}

// ─── Main Component ───────────────────────────────────────────────
function AgentFlowBuilderInner({
  nodes: initialNodes,
  edges: initialEdges,
  onNodeSelect,
  readOnly,
}: AgentFlowBuilderProps) {
  const [nodes, setNodes, onNodesChangeHandler] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChangeHandler] = useEdgesState(initialEdges);

  const onConnect = useCallback(
    (params: Connection) => {
      if (readOnly) return;
      setEdges((eds) => addEdge({ ...params, animated: true }, eds));
    },
    [readOnly, setEdges]
  );

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      if (onNodeSelect) {
        const data = node.data as FlowNodeData;
        onNodeSelect(node.id, data.type);
      }
    },
    [onNodeSelect]
  );

  const onPaneClick = useCallback(() => {
    if (onNodeSelect) onNodeSelect(null, null);
  }, [onNodeSelect]);

  return (
    <div className="bg-card border-border h-[480px] overflow-hidden rounded-xl border">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={readOnly ? undefined : onNodesChangeHandler}
        onEdgesChange={readOnly ? undefined : onEdgesChangeHandler}
        onConnect={onConnect}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        nodeTypes={nodeTypes}
        fitView
        proOptions={{ hideAttribution: true }}
        className="!bg-transparent"
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          className="!bg-background"
          color="oklch(1 0 0 / 6%)"
        />
        <Controls
          showInteractive={!readOnly}
          className="!border-border !bg-card [&>button]:!border-border [&>button]:!bg-card [&>button]:!text-foreground hover:[&>button]:!bg-muted !rounded-lg !shadow-lg"
        />
        <Panel position="top-left" className="!m-3">
          <div className="bg-card/80 border-border rounded-md border px-3 py-1.5 text-xs font-medium backdrop-blur">
            Agent Flow
          </div>
        </Panel>
      </ReactFlow>
    </div>
  );
}

export function AgentFlowBuilder(props: AgentFlowBuilderProps) {
  return (
    <ReactFlowProvider>
      <AgentFlowBuilderInner {...props} />
    </ReactFlowProvider>
  );
}
