// Conversation graph data model + pure helpers (graph-agent-schema spec).
// Keep this module free of React / Next imports so vitest can run it as plain node code.

// ── Types ──────────────────────────────────────────────────────────

export type GraphNodeType = 'start' | 'prompt' | 'end' | 'handoff';
export type EdgeTrigger = 'user_turn' | 'tool_result';
export type EditorMode = 'prompt' | 'graph';

export interface GraphNode {
  id: string;
  type: GraphNodeType;
  title: string;
  prompt: string;
  tools: string[];
  position: { x: number; y: number };
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  trigger?: EdgeTrigger;
  condition: string;
  label?: string;
}

export interface AgentGraph {
  schema_version: number;
  global_prompt: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GraphIssue {
  code: string;
  message: string;
}

export interface GraphValidation {
  errors: GraphIssue[];
  warnings: GraphIssue[];
  valid: boolean;
}

// ── Constants ──────────────────────────────────────────────────────

export const GRAPH_SCHEMA_VERSION = 1;
export const EDGE_TRIGGERS: readonly EdgeTrigger[] = ['user_turn', 'tool_result'];
export const GRAPH_NODE_TYPES: readonly GraphNodeType[] = ['start', 'prompt', 'end', 'handoff'];
// cleanLegacyTools strips these from config.tools, so the legal-tool check must
// include them explicitly or the handoff flow itself would be flagged dangling.
export const AUTO_MOUNTED_TOOL_NAMES: readonly string[] = ['lookup_qa', 'transfer_to_human'];

export const NODE_TYPE_LABELS: Record<GraphNodeType, string> = {
  start: '入口',
  prompt: '情境',
  end: '結束',
  handoff: '轉真人',
};

export function edgeTrigger(edge: GraphEdge): EdgeTrigger {
  return edge.trigger === 'tool_result' ? 'tool_result' : 'user_turn';
}

// ── promptToGraph (migration) ──────────────────────────────────────

export interface PromptToGraphSource {
  instructions?: string;
  tools?: Array<{ name: string }>;
  human_operator?: { enabled?: boolean };
}

export function promptToGraph(source: PromptToGraphSource): AgentGraph {
  const nodes: GraphNode[] = [
    {
      id: 'start',
      type: 'start',
      title: '主流程',
      prompt: source.instructions ?? '',
      tools: (source.tools ?? []).map((t) => t.name).filter(Boolean),
      position: { x: 80, y: 160 },
    },
  ];
  const edges: GraphEdge[] = [];

  if (source.human_operator?.enabled) {
    nodes.push({
      id: 'handoff',
      type: 'handoff',
      title: '轉接真人',
      prompt: '',
      tools: [],
      position: { x: 480, y: 160 },
    });
    edges.push({
      id: 'e-start-handoff',
      source: 'start',
      target: 'handoff',
      trigger: 'user_turn',
      condition: '需要轉接真人',
      label: '轉真人',
    });
  }

  return {
    schema_version: GRAPH_SCHEMA_VERSION,
    global_prompt: '',
    nodes,
    edges,
  };
}

// ── graphToPrompt (fallback flatten) ───────────────────────────────

// Deterministic structured flatten — regenerated on every graph-mode save so the
// `instructions` fallback (degraded execution path incl. SIP) never goes stale.
export function graphToPrompt(graph: AgentGraph): string {
  const titleOf = (id: string) => {
    const n = graph.nodes.find((node) => node.id === id);
    return n ? n.title || n.id : id;
  };

  const lines: string[] = [];
  if (graph.global_prompt.trim()) {
    lines.push(graph.global_prompt.trim(), '');
  }
  lines.push('# 對話流程', '');
  lines.push(
    '以下流程由對話圖（graph）自動攤平生成。判斷目前對話所處的階段，遵循該階段的指示；符合轉移規則時進入下一階段（多條規則依列出順序，先命中者生效）。',
    ''
  );

  const ordered = [
    ...graph.nodes.filter((n) => n.type === 'start'),
    ...graph.nodes.filter((n) => n.type !== 'start'),
  ];

  for (const node of ordered) {
    const marker =
      node.type === 'start'
        ? '（入口）'
        : node.type === 'end'
          ? '（結束通話）'
          : node.type === 'handoff'
            ? '（轉接真人：呼叫 transfer_to_human）'
            : '';
    lines.push(`## 階段：${node.title || node.id}${marker}`, '');
    if (node.prompt.trim()) {
      lines.push(node.prompt.trim(), '');
    }
    if (node.tools.length > 0) {
      lines.push(`此階段可用工具：${node.tools.join('、')}`, '');
    }
    const outgoing = graph.edges.filter((e) => e.source === node.id);
    if (outgoing.length > 0) {
      lines.push('轉移規則：');
      for (const edge of outgoing) {
        const when =
          edgeTrigger(edge) === 'tool_result'
            ? edge.condition.trim()
              ? `工具回傳後，當「${edge.condition.trim()}」`
              : '工具回傳後'
            : edge.condition.trim()
              ? `當「${edge.condition.trim()}」`
              : '無條件';
        lines.push(`- ${when} → 進入「${titleOf(edge.target)}」`);
      }
      lines.push('');
    }
  }

  return lines.join('\n').trimEnd() + '\n';
}

// ── validateGraph (frontend UX feedback only; runtime gate is the backend
//    validator owned by graph-runtime-executor) ─────────────────────

export function validateGraph(
  graph: AgentGraph,
  availableTools: string[],
  configToolNames: string[] = []
): GraphValidation {
  const errors: GraphIssue[] = [];
  const warnings: GraphIssue[] = [];

  const ids = new Set<string>();
  for (const node of graph.nodes) {
    if (ids.has(node.id)) {
      errors.push({ code: 'duplicate_node_id', message: `節點 id 重複：${node.id}` });
    }
    ids.add(node.id);
    if (!GRAPH_NODE_TYPES.includes(node.type)) {
      errors.push({
        code: 'invalid_node_type',
        message: `節點「${node.title || node.id}」的 type 非法：${node.type}`,
      });
    }
  }

  const startNodes = graph.nodes.filter((n) => n.type === 'start');
  if (startNodes.length === 0) {
    errors.push({ code: 'no_start', message: '缺少 start 入口節點' });
  } else if (startNodes.length > 1) {
    errors.push({ code: 'multiple_start', message: 'start 入口節點只能有一個' });
  }

  const nodeById = new Map(graph.nodes.map((n) => [n.id, n]));
  for (const edge of graph.edges) {
    for (const endpoint of [edge.source, edge.target]) {
      if (!nodeById.has(endpoint)) {
        errors.push({
          code: 'edge_endpoint_missing',
          message: `邊 ${edge.id} 引用不存在的節點：${endpoint}`,
        });
      }
    }
    const target = nodeById.get(edge.target);
    if (target?.type === 'start') {
      errors.push({ code: 'edge_into_start', message: `start 節點不可有入邊（${edge.id}）` });
    }
    const source = nodeById.get(edge.source);
    if (source?.type === 'end') {
      errors.push({ code: 'edge_out_of_end', message: `end 節點不可有出邊（${edge.id}）` });
    }
    if (edge.trigger !== undefined && !EDGE_TRIGGERS.includes(edge.trigger)) {
      errors.push({
        code: 'invalid_trigger',
        message: `邊 ${edge.id} 的 trigger 非法：${edge.trigger}`,
      });
    }
  }

  // Reachability from start (BFS) — a disconnected cycle must not pass a mere
  // isolated-node check.
  if (startNodes.length === 1) {
    const reached = new Set<string>([startNodes[0].id]);
    const queue = [startNodes[0].id];
    while (queue.length > 0) {
      const current = queue.shift() as string;
      for (const edge of graph.edges) {
        if (edge.source === current && nodeById.has(edge.target) && !reached.has(edge.target)) {
          reached.add(edge.target);
          queue.push(edge.target);
        }
      }
    }
    for (const node of graph.nodes) {
      if (!reached.has(node.id)) {
        errors.push({
          code: 'unreachable_node',
          message: `節點「${node.title || node.id}」從 start 不可達`,
        });
      }
    }
  }

  // Multiple unconditional out-edges on one (source, trigger): later ones are
  // unreachable under array-order priority.
  const unconditionalSeen = new Set<string>();
  for (const edge of graph.edges) {
    if (edge.condition.trim()) continue;
    const key = `${edge.source}::${edgeTrigger(edge)}`;
    if (unconditionalSeen.has(key)) {
      const title = nodeById.get(edge.source)?.title || edge.source;
      warnings.push({
        code: 'ambiguous_unconditional',
        message: `節點「${title}」有多條無條件出邊，依順序優先，後面的永遠不會生效`,
      });
    }
    unconditionalSeen.add(key);
  }

  // Dangling tool references. Skip when the builtin list failed to load (empty)
  // to avoid false warnings. Legal set = config.tools ∪ builtins ∪ auto-mounted.
  if (availableTools.length > 0) {
    const legal = new Set([...configToolNames, ...availableTools, ...AUTO_MOUNTED_TOOL_NAMES]);
    for (const node of graph.nodes) {
      for (const tool of node.tools) {
        if (!legal.has(tool)) {
          warnings.push({
            code: 'dangling_tool',
            message: `節點「${node.title || node.id}」引用了不存在的工具：${tool}`,
          });
        }
      }
    }
  }

  return { errors, warnings, valid: errors.length === 0 };
}
