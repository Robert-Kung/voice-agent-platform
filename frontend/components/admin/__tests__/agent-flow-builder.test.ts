import { describe, expect, it } from 'vitest';
import { buildFlowFromConfig } from '../agent-flow-builder';

// REGRESSION (tasks 7.4): legacy (no-graph) configs must keep producing the exact
// hub-and-spoke projection they had before the graph-mode rewrite of buildFlowFromConfig.
// (Snapshots regenerated once for the planned FlowNodeType 'prompt'→'instructions'
// rename — review D3; structure/layout otherwise identical to the pre-change output.)

const fullLegacyConfig = {
  instructions: '你是測試客服',
  qa_mode: 'inline',
  qa_data: [{ keywords: ['營業'], answer: '九點到六點' }],
  services: { main: { always_open: false, hours_text: '09:00-18:00' } },
  human_operator: { enabled: true },
  tools: [
    { name: 'get_current_time' },
    { name: 'create_ticket', endpoint: 'https://example.com/t', description: '建單' },
  ],
};

const minimalLegacyConfig = {
  instructions: '',
};

describe('buildFlowFromConfig legacy projection (regression)', () => {
  it('full legacy config projects unchanged', () => {
    expect(buildFlowFromConfig(fullLegacyConfig)).toMatchSnapshot();
  });

  it('full legacy config keeps hand-verified pre-change structure', () => {
    // Structural assertions hand-checked against the pre-rewrite implementation,
    // since the snapshot itself was regenerated for the FlowNodeType rename.
    const { nodes, edges } = buildFlowFromConfig(fullLegacyConfig);
    expect(nodes.map((n) => n.id)).toEqual([
      'agent-core',
      'prompt',
      'qa-database',
      'service-hours',
      'human-handoff',
      'tool-get_current_time',
      'tool-create_ticket',
    ]);
    expect(nodes.find((n) => n.id === 'agent-core')?.position).toEqual({ x: 400, y: 200 });
    expect(nodes.find((n) => n.id === 'prompt')?.position).toEqual({ x: 80, y: 60 });
    expect(edges.map((e) => `${e.source}->${e.target}`)).toEqual([
      'prompt->agent-core',
      'qa-database->agent-core',
      'service-hours->agent-core',
      'human-handoff->agent-core',
      'agent-core->tool-get_current_time',
      'agent-core->tool-create_ticket',
    ]);
  });

  it('minimal legacy config projects unchanged', () => {
    expect(buildFlowFromConfig(minimalLegacyConfig)).toMatchSnapshot();
  });

  it('legacy config with disabled handoff and no qa omits those nodes', () => {
    const { nodes } = buildFlowFromConfig({
      instructions: 'x',
      human_operator: { enabled: false },
      tools: [],
    });
    expect(nodes.map((n) => n.id)).toEqual(['agent-core', 'prompt']);
  });
});

describe('buildFlowFromConfig graph projection', () => {
  it('renders config.graph directly when present', () => {
    const { nodes, edges } = buildFlowFromConfig({
      instructions: 'fallback (ignored for projection)',
      graph: {
        schema_version: 1,
        global_prompt: '',
        nodes: [
          {
            id: 'start',
            type: 'start',
            title: '接聽',
            prompt: 'p',
            tools: ['t1'],
            position: { x: 1, y: 2 },
          },
          {
            id: 'h',
            type: 'handoff',
            title: '轉接',
            prompt: '',
            tools: [],
            position: { x: 3, y: 4 },
          },
        ],
        edges: [
          { id: 'e1', source: 'start', target: 'h', trigger: 'tool_result', condition: '建單成功' },
        ],
      },
    });
    expect(nodes.map((n) => n.id)).toEqual(['start', 'h']);
    expect(nodes[0].position).toEqual({ x: 1, y: 2 });
    expect(nodes[0].data.type).toBe('start');
    expect(edges[0]).toMatchObject({ source: 'start', target: 'h', label: '工具結果' });
  });

  it('empty graph nodes falls back to legacy projection', () => {
    const { nodes } = buildFlowFromConfig({
      instructions: 'x',
      graph: { schema_version: 1, global_prompt: '', nodes: [], edges: [] },
    });
    expect(nodes.map((n) => n.id)).toContain('agent-core');
  });

  it('malformed graph block neither crashes nor blocks the legacy fallback', () => {
    const malformed = { nodes: [{ id: 'start', type: 'start' }], edges: [{ id: 'e' }] };
    expect(() =>
      buildFlowFromConfig({ instructions: 'x', graph: malformed as never })
    ).not.toThrow();
    const broken = buildFlowFromConfig({ instructions: 'x', graph: {} as never });
    expect(broken.nodes.map((n) => n.id)).toContain('agent-core');
  });
});
