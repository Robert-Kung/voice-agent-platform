'use client';

import { useCallback, useEffect } from 'react';
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
  useEdgesState,
  useNodesState,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type { AgentGraph, GraphNodeType } from '@/lib/agent-graph';
import { NODE_TYPE_LABELS, edgeTrigger } from '@/lib/agent-graph';
import { cn } from '@/lib/shadcn/utils';
import { NODE_COLORS, NODE_ICONS, NODE_ICON_COLORS } from './agent-flow-builder';

// Controlled editable conversation canvas (review D3 contract):
// `useProfileForm.known.graph` is the single source of truth. Nodes/edges are
// derived from the graph prop; changes flow upward only on semantic events
// (connect / delete / drag-stop / inspector edit) — never per pixel of drag.

export interface GraphSelection {
  nodeId: string | null;
  edgeId: string | null;
}

interface GraphCanvasProps {
  graph: AgentGraph;
  selection: GraphSelection;
  onSelect: (selection: GraphSelection) => void;
  onAddNode: (type: Exclude<GraphNodeType, 'start'>) => void;
  onRemoveNode: (id: string) => void;
  onRemoveEdge: (id: string) => void;
  onConnect: (source: string, target: string) => void;
  onNodeDragStop: (id: string, position: { x: number; y: number }) => void;
}

interface ConvNodeData {
  title: string;
  nodeType: GraphNodeType;
  toolCount: number;
  [key: string]: unknown;
}

function ConversationNode({ data, selected }: NodeProps<Node<ConvNodeData>>) {
  const Icon = NODE_ICONS[data.nodeType];
  return (
    <div
      className={cn(
        'min-w-32 rounded-lg border-2 px-4 py-3 shadow-md transition-all',
        NODE_COLORS[data.nodeType],
        selected && 'ring-primary/50 ring-2'
      )}
    >
      {data.nodeType !== 'start' && (
        <Handle
          type="target"
          position={Position.Left}
          className="!bg-primary !border-background !size-2.5"
        />
      )}
      <div className="flex items-center gap-2.5">
        <Icon className={cn('size-4 shrink-0', NODE_ICON_COLORS[data.nodeType])} />
        <div className="min-w-0">
          <div className="truncate text-xs font-semibold">{data.title}</div>
          <div className="text-muted-foreground text-[10px]">
            {NODE_TYPE_LABELS[data.nodeType]}
            {data.toolCount > 0 && ` · ${data.toolCount} tools`}
          </div>
        </div>
      </div>
      {data.nodeType !== 'end' && (
        <Handle
          type="source"
          position={Position.Right}
          className="!bg-primary !border-background !size-2.5"
        />
      )}
    </div>
  );
}

const nodeTypes = { convNode: ConversationNode };

function toFlowNodes(graph: AgentGraph, selection: GraphSelection): Node<ConvNodeData>[] {
  return graph.nodes.map((n) => ({
    id: n.id,
    type: 'convNode',
    position: n.position,
    selected: selection.nodeId === n.id,
    data: { title: n.title || n.id, nodeType: n.type, toolCount: n.tools.length },
  }));
}

function toFlowEdges(graph: AgentGraph, selection: GraphSelection): Edge[] {
  return graph.edges.map((e) => {
    const isToolResult = edgeTrigger(e) === 'tool_result';
    const conditionHint = e.condition.trim()
      ? e.condition.trim().length > 14
        ? `${e.condition.trim().slice(0, 14)}…`
        : e.condition.trim()
      : '';
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      animated: true,
      selected: selection.edgeId === e.id,
      label: e.label || conditionHint || (isToolResult ? '工具結果' : undefined),
      style: isToolResult ? { strokeDasharray: '6 3' } : undefined,
    };
  });
}

function GraphCanvasInner({
  graph,
  selection,
  onSelect,
  onAddNode,
  onRemoveNode,
  onRemoveEdge,
  onConnect,
  onNodeDragStop,
}: GraphCanvasProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState(toFlowNodes(graph, selection));
  const [edges, setEdges, onEdgesChange] = useEdgesState(toFlowEdges(graph, selection));

  // Re-derive local React Flow state whenever the authoritative graph changes.
  // Drag stays smooth because the graph prop only updates on drag-stop.
  useEffect(() => {
    setNodes(toFlowNodes(graph, selection));
    setEdges(toFlowEdges(graph, selection));
  }, [graph, selection, setNodes, setEdges]);

  const handleConnect = useCallback(
    (params: Connection) => {
      if (params.source && params.target) onConnect(params.source, params.target);
    },
    [onConnect]
  );

  const handleNodesDelete = useCallback(
    (deleted: Node[]) => {
      for (const node of deleted) onRemoveNode(node.id);
    },
    [onRemoveNode]
  );

  const handleEdgesDelete = useCallback(
    (deleted: Edge[]) => {
      for (const edge of deleted) onRemoveEdge(edge.id);
    },
    [onRemoveEdge]
  );

  return (
    <div className="bg-card border-border h-full min-h-[480px] overflow-hidden rounded-xl border">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={handleConnect}
        onNodesDelete={handleNodesDelete}
        onEdgesDelete={handleEdgesDelete}
        onNodeDragStop={(_, node) => onNodeDragStop(node.id, node.position)}
        onNodeClick={(_, node) => onSelect({ nodeId: node.id, edgeId: null })}
        onEdgeClick={(_, edge) => onSelect({ nodeId: null, edgeId: edge.id })}
        onPaneClick={() => onSelect({ nodeId: null, edgeId: null })}
        nodeTypes={nodeTypes}
        fitView
        deleteKeyCode={['Backspace', 'Delete']}
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
        <Controls className="!border-border !bg-card [&>button]:!border-border [&>button]:!bg-card [&>button]:!text-foreground hover:[&>button]:!bg-muted !rounded-lg !shadow-lg" />
        <Panel position="top-left" className="!m-3 flex items-center gap-1.5">
          {(['prompt', 'handoff', 'end'] as const).map((type) => (
            <button
              key={type}
              type="button"
              onClick={() => onAddNode(type)}
              className="bg-card/90 border-border hover:bg-muted rounded-md border px-2.5 py-1 text-xs font-medium backdrop-blur"
            >
              + {NODE_TYPE_LABELS[type]}
            </button>
          ))}
        </Panel>
        <Panel position="bottom-right" className="!m-3">
          <span className="bg-card/80 text-foreground/50 rounded px-2 py-1 text-[10px] backdrop-blur">
            拖曳連線建立轉移 · Delete 鍵刪除選取
          </span>
        </Panel>
      </ReactFlow>
    </div>
  );
}

export function GraphCanvas(props: GraphCanvasProps) {
  return (
    <ReactFlowProvider>
      <GraphCanvasInner {...props} />
    </ReactFlowProvider>
  );
}
