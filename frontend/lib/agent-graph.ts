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

export const TOOL_RESULT_EDGE_LABEL = '工具結果';

// ── normalizeGraph (load-boundary sanitizer) ───────────────────────

// config_json is free-form: hand-edited YAML or direct API writes can produce a
// graph block missing any field. Everything downstream (canvas, flatten,
// validator) assumes the full shape, so the load boundary coerces it here.
// Returns undefined for anything unusable (no/empty nodes) — the editor then
// treats the profile as having no graph at all instead of rendering a dead end.
export function normalizeGraph(raw: unknown): AgentGraph | undefined {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) return undefined;
  const g = raw as Record<string, unknown>;
  if (!Array.isArray(g.nodes)) return undefined;

  const str = (v: unknown, fallback = ''): string => (typeof v === 'string' ? v : fallback);
  const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0);

  const nodes: GraphNode[] = g.nodes
    .filter((n): n is Record<string, unknown> => typeof n === 'object' && n !== null)
    .map((n, i) => {
      const pos =
        typeof n.position === 'object' && n.position !== null
          ? (n.position as Record<string, unknown>)
          : {};
      return {
        id: str(n.id, `node-${i}`),
        // Unknown types survive normalization so validateGraph can flag them;
        // renderers fall back to a default icon/label.
        type: str(n.type, 'prompt') as GraphNodeType,
        title: str(n.title),
        prompt: str(n.prompt),
        tools: Array.isArray(n.tools)
          ? n.tools.filter((t): t is string => typeof t === 'string')
          : [],
        position: { x: num(pos.x), y: num(pos.y) },
      };
    });
  if (nodes.length === 0) return undefined;

  const edges: GraphEdge[] = (Array.isArray(g.edges) ? g.edges : [])
    .filter((e): e is Record<string, unknown> => typeof e === 'object' && e !== null)
    .map((e, i) => ({
      id: str(e.id, `edge-${i}`),
      source: str(e.source),
      target: str(e.target),
      ...(typeof e.trigger === 'string' ? { trigger: e.trigger as EdgeTrigger } : {}),
      condition: str(e.condition),
      ...(typeof e.label === 'string' && e.label ? { label: e.label } : {}),
    }));

  return {
    schema_version: typeof g.schema_version === 'number' ? g.schema_version : GRAPH_SCHEMA_VERSION,
    global_prompt: str(g.global_prompt),
    nodes,
    edges,
  };
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

// ── prepareGraphSave (save-gate orchestration, pure for testability) ──

export interface PrepareGraphSaveInput {
  graph?: AgentGraph;
  editor_mode?: EditorMode;
  tools?: Array<{ name: string }>;
  human_operator?: { enabled?: boolean };
}

export type PrepareGraphSaveResult =
  | { action: 'passthrough' }
  | { action: 'blocked'; errors: GraphIssue[]; warnings: GraphIssue[] }
  | { action: 'regenerated'; instructions: string; warnings: GraphIssue[] };

// Graph-mode saves must (a) block on structural errors and (b) regenerate the
// `instructions` fallback so the degraded path (Try/deploy/SIP) never goes stale.
export function prepareGraphSave(
  known: PrepareGraphSaveInput,
  availableTools: string[]
): PrepareGraphSaveResult {
  if (known.editor_mode !== 'graph' || !known.graph) return { action: 'passthrough' };
  const validation = validateGraph(
    known.graph,
    availableTools,
    (known.tools ?? []).map((t) => t.name),
    { handoffEnabled: known.human_operator?.enabled ?? false }
  );
  if (!validation.valid) {
    return { action: 'blocked', errors: validation.errors, warnings: validation.warnings };
  }
  return {
    action: 'regenerated',
    instructions: graphToPrompt(known.graph),
    warnings: validation.warnings,
  };
}

// ── validateGraph (frontend UX feedback only; runtime gate is the backend
//    validator owned by graph-runtime-executor) ─────────────────────

export interface ValidateGraphOptions {
  // Pass the profile's human_operator.enabled when known: a handoff node whose
  // flatten instructs transfer_to_human is a stall/hallucination trap when the
  // tool is never mounted.
  handoffEnabled?: boolean;
}

export function validateGraph(
  graph: AgentGraph,
  availableTools: string[],
  configToolNames: string[] = [],
  opts: ValidateGraphOptions = {}
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

  const edgeIds = new Set<string>();
  for (const edge of graph.edges) {
    if (edgeIds.has(edge.id)) {
      // updateEdge/removeEdge key on edge.id — duplicates silently corrupt edits.
      errors.push({ code: 'duplicate_edge_id', message: `邊 id 重複：${edge.id}` });
    }
    edgeIds.add(edge.id);
    if (edge.source === edge.target && edge.source) {
      warnings.push({
        code: 'self_loop',
        message: `邊 ${edge.id} 的起點與終點是同一節點（自我迴圈）`,
      });
    }
  }

  if (opts.handoffEnabled === false && graph.nodes.some((n) => n.type === 'handoff')) {
    warnings.push({
      code: 'handoff_disabled',
      message:
        'graph 含轉真人節點，但 Handoff（human_operator）未啟用——執行時無 transfer_to_human 工具可呼叫',
    });
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

  // tool_result edge from a node with no domain tool → dead transition. The
  // runtime wraps a node's domain tools to hand off after they return; a node
  // sourcing a tool_result edge but listing no domain tool (empty, or only
  // auto-mounted) has nothing to wrap, so that transition can never fire.
  const toolResultSources = new Set(
    graph.edges.filter((e) => edgeTrigger(e) === 'tool_result').map((e) => e.source)
  );
  for (const node of graph.nodes) {
    if (!toolResultSources.has(node.id)) continue;
    const domainTools = node.tools.filter((t) => !AUTO_MOUNTED_TOOL_NAMES.includes(t));
    if (domainTools.length === 0) {
      warnings.push({
        code: 'tool_result_no_tool',
        message: `節點「${node.title || node.id}」有 tool_result 出邊但沒有 domain 工具——該轉移永遠不會觸發`,
      });
    }
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
