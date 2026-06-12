import { describe, expect, it } from 'vitest';
import {
  type AgentGraph,
  GRAPH_SCHEMA_VERSION,
  graphToPrompt,
  normalizeGraph,
  prepareGraphSave,
  promptToGraph,
  validateGraph,
} from '../agent-graph';

function makeGraph(overrides: Partial<AgentGraph> = {}): AgentGraph {
  return {
    schema_version: GRAPH_SCHEMA_VERSION,
    global_prompt: '',
    nodes: [
      {
        id: 'start',
        type: 'start',
        title: '接聽',
        prompt: '打招呼',
        tools: [],
        position: { x: 0, y: 0 },
      },
    ],
    edges: [],
    ...overrides,
  };
}

// ── promptToGraph (7.2) ────────────────────────────────────────────

describe('promptToGraph', () => {
  it('builds a single start node from instructions + tool names', () => {
    const graph = promptToGraph({
      instructions: '你是客服',
      tools: [{ name: 'get_current_time' }, { name: 'create_ticket' }],
    });
    expect(graph.schema_version).toBe(1);
    expect(graph.nodes).toHaveLength(1);
    expect(graph.nodes[0]).toMatchObject({
      id: 'start',
      type: 'start',
      prompt: '你是客服',
      tools: ['get_current_time', 'create_ticket'],
    });
    expect(graph.edges).toHaveLength(0);
  });

  it('adds handoff node + edge when human_operator.enabled', () => {
    const graph = promptToGraph({ instructions: 'x', human_operator: { enabled: true } });
    expect(graph.nodes.map((n) => n.type)).toEqual(['start', 'handoff']);
    expect(graph.edges).toHaveLength(1);
    expect(graph.edges[0]).toMatchObject({
      source: 'start',
      target: 'handoff',
      trigger: 'user_turn',
    });
    expect(graph.edges[0].condition).not.toBe('');
  });

  it('partial human_operator without enabled adds no handoff', () => {
    const graph = promptToGraph({ instructions: 'x', human_operator: {} });
    expect(graph.nodes).toHaveLength(1);
  });

  it('handles empty tools and missing instructions', () => {
    const graph = promptToGraph({});
    expect(graph.nodes[0].prompt).toBe('');
    expect(graph.nodes[0].tools).toEqual([]);
  });

  it('preserves special characters in instructions', () => {
    const text = '【⚠️ 規定】「複誦」→ create_maintenance_ticket\n- 換行 & "quotes"';
    const graph = promptToGraph({ instructions: text });
    expect(graph.nodes[0].prompt).toBe(text);
  });
});

// ── graphToPrompt (7.2) ────────────────────────────────────────────

describe('graphToPrompt', () => {
  const graph = makeGraph({
    global_prompt: '使用繁體中文，語氣冷靜。',
    nodes: [
      {
        id: 'start',
        type: 'start',
        title: '接聽',
        prompt: '打招呼並蒐集資料',
        tools: ['create_ticket'],
        position: { x: 0, y: 0 },
      },
      {
        id: 'transfer',
        type: 'handoff',
        title: '轉接',
        prompt: '',
        tools: [],
        position: { x: 1, y: 1 },
      },
      { id: 'bye', type: 'end', title: '結束', prompt: '', tools: [], position: { x: 2, y: 2 } },
    ],
    edges: [
      {
        id: 'e1',
        source: 'start',
        target: 'transfer',
        trigger: 'tool_result',
        condition: '建單失敗',
        label: '失敗',
      },
      { id: 'e2', source: 'start', target: 'bye', condition: '' },
    ],
  });

  it('serializes global prompt, node sections, and edge rules', () => {
    const out = graphToPrompt(graph);
    expect(out).toContain('使用繁體中文');
    expect(out).toContain('## 階段：接聽（入口）');
    expect(out).toContain('## 階段：轉接（轉接真人：呼叫 transfer_to_human）');
    expect(out).toContain('## 階段：結束（結束通話）');
    expect(out).toContain('此階段可用工具：create_ticket');
    expect(out).toContain('工具回傳後，當「建單失敗」 → 進入「轉接」');
    expect(out).toContain('無條件 → 進入「結束」');
  });

  it('is deterministic (same graph → same flatten)', () => {
    expect(graphToPrompt(graph)).toBe(graphToPrompt(graph));
  });

  it('puts the start node first even when not first in array', () => {
    const reordered = makeGraph({
      nodes: [
        { id: 'b', type: 'prompt', title: 'B', prompt: '', tools: [], position: { x: 0, y: 0 } },
        { id: 'start', type: 'start', title: 'A', prompt: '', tools: [], position: { x: 0, y: 0 } },
      ],
      edges: [{ id: 'e', source: 'start', target: 'b', condition: '' }],
    });
    const out = graphToPrompt(reordered);
    expect(out.indexOf('階段：A')).toBeLessThan(out.indexOf('階段：B'));
  });

  it('omits empty global prompt without leading blank section', () => {
    const out = graphToPrompt(makeGraph());
    expect(out.startsWith('# 對話流程')).toBe(true);
  });
});

// ── validateGraph (7.3) ────────────────────────────────────────────

const BUILTINS = ['get_current_time', 'lookup_qa', 'transfer_to_human'];

describe('validateGraph errors', () => {
  it('valid minimal graph passes', () => {
    const v = validateGraph(makeGraph(), BUILTINS);
    expect(v.valid).toBe(true);
    expect(v.errors).toEqual([]);
  });

  it('missing start node', () => {
    const v = validateGraph(
      makeGraph({
        nodes: [
          { id: 'a', type: 'prompt', title: 'A', prompt: '', tools: [], position: { x: 0, y: 0 } },
        ],
      }),
      BUILTINS
    );
    expect(v.errors.map((e) => e.code)).toContain('no_start');
  });

  it('multiple start nodes', () => {
    const g = makeGraph();
    g.nodes.push({
      id: 's2',
      type: 'start',
      title: 'S2',
      prompt: '',
      tools: [],
      position: { x: 0, y: 0 },
    });
    const v = validateGraph(g, BUILTINS);
    expect(v.errors.map((e) => e.code)).toContain('multiple_start');
  });

  it('duplicate node ids', () => {
    const g = makeGraph();
    g.nodes.push({ ...g.nodes[0], type: 'prompt' });
    const v = validateGraph(g, BUILTINS);
    expect(v.errors.map((e) => e.code)).toContain('duplicate_node_id');
  });

  it('edge endpoint not found', () => {
    const g = makeGraph({ edges: [{ id: 'e', source: 'start', target: 'ghost', condition: '' }] });
    const v = validateGraph(g, BUILTINS);
    expect(v.errors.map((e) => e.code)).toContain('edge_endpoint_missing');
  });

  it('edge into start and edge out of end', () => {
    const g = makeGraph({
      nodes: [
        { id: 'start', type: 'start', title: 'S', prompt: '', tools: [], position: { x: 0, y: 0 } },
        { id: 'fin', type: 'end', title: 'E', prompt: '', tools: [], position: { x: 0, y: 0 } },
      ],
      edges: [
        { id: 'e1', source: 'start', target: 'fin', condition: '' },
        { id: 'e2', source: 'fin', target: 'start', condition: '' },
      ],
    });
    const codes = validateGraph(g, BUILTINS).errors.map((e) => e.code);
    expect(codes).toContain('edge_into_start');
    expect(codes).toContain('edge_out_of_end');
  });

  it('invalid trigger value', () => {
    const g = makeGraph({
      nodes: [
        { id: 'start', type: 'start', title: 'S', prompt: '', tools: [], position: { x: 0, y: 0 } },
        { id: 'a', type: 'prompt', title: 'A', prompt: '', tools: [], position: { x: 0, y: 0 } },
      ],
      edges: [
        { id: 'e', source: 'start', target: 'a', condition: '', trigger: 'on_timer' as never },
      ],
    });
    expect(validateGraph(g, BUILTINS).errors.map((e) => e.code)).toContain('invalid_trigger');
  });

  it('disconnected cycle is unreachable (not just isolated nodes)', () => {
    const g = makeGraph({
      nodes: [
        { id: 'start', type: 'start', title: 'S', prompt: '', tools: [], position: { x: 0, y: 0 } },
        { id: 'a', type: 'prompt', title: 'A', prompt: '', tools: [], position: { x: 0, y: 0 } },
        { id: 'b', type: 'prompt', title: 'B', prompt: '', tools: [], position: { x: 0, y: 0 } },
      ],
      edges: [
        { id: 'e1', source: 'a', target: 'b', condition: '' },
        { id: 'e2', source: 'b', target: 'a', condition: '' },
      ],
    });
    const unreachable = validateGraph(g, BUILTINS).errors.filter(
      (e) => e.code === 'unreachable_node'
    );
    expect(unreachable).toHaveLength(2);
  });
});

describe('validateGraph warnings', () => {
  it('multiple unconditional out-edges on one source warns', () => {
    const g = makeGraph({
      nodes: [
        { id: 'start', type: 'start', title: 'S', prompt: '', tools: [], position: { x: 0, y: 0 } },
        { id: 'a', type: 'prompt', title: 'A', prompt: '', tools: [], position: { x: 0, y: 0 } },
        { id: 'b', type: 'prompt', title: 'B', prompt: '', tools: [], position: { x: 0, y: 0 } },
      ],
      edges: [
        { id: 'e1', source: 'start', target: 'a', condition: '' },
        { id: 'e2', source: 'start', target: 'b', condition: '' },
      ],
    });
    const v = validateGraph(g, BUILTINS);
    expect(v.valid).toBe(true);
    expect(v.warnings.map((w) => w.code)).toContain('ambiguous_unconditional');
  });

  it('unconditional user_turn + tool_result on same source do not warn', () => {
    const g = makeGraph({
      nodes: [
        { id: 'start', type: 'start', title: 'S', prompt: '', tools: [], position: { x: 0, y: 0 } },
        { id: 'a', type: 'prompt', title: 'A', prompt: '', tools: [], position: { x: 0, y: 0 } },
      ],
      edges: [
        { id: 'e1', source: 'start', target: 'a', condition: '' },
        { id: 'e2', source: 'start', target: 'a', condition: '', trigger: 'tool_result' },
      ],
    });
    expect(validateGraph(g, BUILTINS).warnings).toEqual([]);
  });

  it('auto-mounted tools are not dangling even though absent from config.tools', () => {
    const g = makeGraph();
    g.nodes[0].tools = ['transfer_to_human', 'lookup_qa'];
    expect(validateGraph(g, ['get_current_time'], []).warnings).toEqual([]);
  });

  it('legal set is the union of config tools, builtins, and auto-mounted', () => {
    const g = makeGraph();
    g.nodes[0].tools = ['my_http_tool', 'get_current_time', 'lookup_qa', 'deleted_tool'];
    const v = validateGraph(g, ['get_current_time'], ['my_http_tool']);
    expect(v.warnings).toHaveLength(1);
    expect(v.warnings[0].message).toContain('deleted_tool');
  });

  it('skips tool check when availableTools failed to load (empty)', () => {
    const g = makeGraph();
    g.nodes[0].tools = ['anything_goes'];
    expect(validateGraph(g, [], []).warnings).toEqual([]);
  });
});

// ── normalizeGraph (free-form config boundary) ─────────────────────

describe('normalizeGraph', () => {
  it('passes a well-formed graph through intact', () => {
    const g = makeGraph();
    expect(normalizeGraph(g)).toEqual(g);
  });

  it('returns undefined for non-objects, empty objects, and missing/empty nodes', () => {
    expect(normalizeGraph(undefined)).toBeUndefined();
    expect(normalizeGraph(null)).toBeUndefined();
    expect(normalizeGraph('graph')).toBeUndefined();
    expect(normalizeGraph([])).toBeUndefined();
    expect(normalizeGraph({})).toBeUndefined();
    expect(normalizeGraph({ nodes: [], edges: [] })).toBeUndefined();
    expect(normalizeGraph({ nodes: 'not-an-array' })).toBeUndefined();
  });

  it('defaults missing node fields (prompt, tools, position, title)', () => {
    const g = normalizeGraph({ nodes: [{ id: 'start', type: 'start' }] });
    expect(g?.nodes[0]).toEqual({
      id: 'start',
      type: 'start',
      title: '',
      prompt: '',
      tools: [],
      position: { x: 0, y: 0 },
    });
    expect(g?.edges).toEqual([]);
    expect(g?.schema_version).toBe(GRAPH_SCHEMA_VERSION);
    expect(g?.global_prompt).toBe('');
  });

  it('defaults missing edge condition and drops non-string tools', () => {
    const g = normalizeGraph({
      nodes: [{ id: 'start', type: 'start', tools: ['ok', 42, null] }],
      edges: [{ id: 'e1', source: 'start', target: 'start' }],
    });
    expect(g?.nodes[0].tools).toEqual(['ok']);
    expect(g?.edges[0].condition).toBe('');
    expect(g?.edges[0].trigger).toBeUndefined();
  });

  it('keeps unknown node types so the validator can flag them', () => {
    const g = normalizeGraph({ nodes: [{ id: 'x', type: 'teleport' }] });
    expect(g?.nodes[0].type).toBe('teleport');
    const v = validateGraph(g as AgentGraph, []);
    expect(v.errors.map((e) => e.code)).toContain('invalid_node_type');
  });

  it('coerces non-numeric positions to 0 instead of NaN', () => {
    const g = normalizeGraph({
      nodes: [{ id: 'start', type: 'start', position: { x: 'left', y: NaN } }],
    });
    expect(g?.nodes[0].position).toEqual({ x: 0, y: 0 });
  });

  it('normalized malformed graphs do not crash validate or flatten', () => {
    const g = normalizeGraph({
      nodes: [{ id: 'start', type: 'start' }, { id: 'b' }],
      edges: [{ id: 'e1', source: 'start', target: 'b' }],
    }) as AgentGraph;
    expect(() => validateGraph(g, [])).not.toThrow();
    expect(() => graphToPrompt(g)).not.toThrow();
  });
});

// ── prepareGraphSave (save gate) ───────────────────────────────────

describe('prepareGraphSave', () => {
  it('passes through prompt-mode and graph-less configs untouched', () => {
    expect(prepareGraphSave({ editor_mode: 'prompt', graph: makeGraph() }, []).action).toBe(
      'passthrough'
    );
    expect(prepareGraphSave({ editor_mode: 'graph' }, []).action).toBe('passthrough');
  });

  it('blocks save on structural errors', () => {
    const g = makeGraph({ edges: [{ id: 'e', source: 'start', target: 'ghost', condition: '' }] });
    const r = prepareGraphSave({ editor_mode: 'graph', graph: g }, []);
    expect(r.action).toBe('blocked');
    if (r.action === 'blocked') {
      expect(r.errors.map((e) => e.code)).toContain('edge_endpoint_missing');
    }
  });

  it('regenerates instructions from the graph on valid save', () => {
    const g = makeGraph();
    const r = prepareGraphSave({ editor_mode: 'graph', graph: g }, []);
    expect(r.action).toBe('regenerated');
    if (r.action === 'regenerated') {
      expect(r.instructions).toBe(graphToPrompt(g));
    }
  });

  it('warns when a handoff node exists but human_operator is disabled', () => {
    const g = makeGraph();
    g.nodes.push({
      id: 'h',
      type: 'handoff',
      title: '轉接',
      prompt: '',
      tools: [],
      position: { x: 0, y: 0 },
    });
    g.edges.push({ id: 'e', source: 'start', target: 'h', condition: '' });
    const r = prepareGraphSave(
      { editor_mode: 'graph', graph: g, human_operator: { enabled: false } },
      []
    );
    expect(r.action).toBe('regenerated');
    if (r.action === 'regenerated') {
      expect(r.warnings.map((w) => w.code)).toContain('handoff_disabled');
    }
    const enabled = prepareGraphSave(
      { editor_mode: 'graph', graph: g, human_operator: { enabled: true } },
      []
    );
    if (enabled.action === 'regenerated') {
      expect(enabled.warnings.map((w) => w.code)).not.toContain('handoff_disabled');
    }
  });
});

// ── new validator rules ────────────────────────────────────────────

describe('validateGraph additional rules', () => {
  it('duplicate edge ids are an error', () => {
    const g = makeGraph({
      nodes: [
        { id: 'start', type: 'start', title: 'S', prompt: '', tools: [], position: { x: 0, y: 0 } },
        { id: 'a', type: 'prompt', title: 'A', prompt: '', tools: [], position: { x: 0, y: 0 } },
      ],
      edges: [
        { id: 'e1', source: 'start', target: 'a', condition: 'x' },
        { id: 'e1', source: 'start', target: 'a', condition: 'y' },
      ],
    });
    expect(validateGraph(g, BUILTINS).errors.map((e) => e.code)).toContain('duplicate_edge_id');
  });

  it('self-loop edges warn', () => {
    const g = makeGraph({
      nodes: [
        { id: 'start', type: 'start', title: 'S', prompt: '', tools: [], position: { x: 0, y: 0 } },
        { id: 'a', type: 'prompt', title: 'A', prompt: '', tools: [], position: { x: 0, y: 0 } },
      ],
      edges: [
        { id: 'e1', source: 'start', target: 'a', condition: '' },
        { id: 'e2', source: 'a', target: 'a', condition: '再試一次' },
      ],
    });
    expect(validateGraph(g, BUILTINS).warnings.map((w) => w.code)).toContain('self_loop');
  });
});

// ── round trip ─────────────────────────────────────────────────────

describe('promptToGraph → graphToPrompt round trip', () => {
  it('flatten of a converted profile contains the original instructions', () => {
    const original = '你是客服。【規則】不可閒聊。';
    const graph = promptToGraph({ instructions: original, human_operator: { enabled: true } });
    const flattened = graphToPrompt(graph);
    expect(flattened).toContain(original);
    expect(flattened).toContain('轉接真人');
  });
});
