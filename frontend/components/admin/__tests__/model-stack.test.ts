import { describe, expect, it } from 'vitest';
import { buildConfig, pruneModels, splitConfig } from '@/hooks/use-profile-form';
import type { KnownConfig } from '@/hooks/use-profile-form';
import backendConstants from '@/lib/__fixtures__/backend-model-constants.json';
import { promptToGraph } from '@/lib/agent-graph';
import {
  FALLBACK_MODEL_CATALOG,
  type ModelsConfig,
  resolveField,
  specPrimary,
} from '@/lib/model-catalog';

// profile-editor-stack-ux: pure-function guards for the model/voice stack.
// (vitest runs in node env — no hook rendering; we test the data transforms the
// hook composes: buildConfig/splitConfig round-trip, pruneModels, helpers.)

describe('models round-trip (task 1.1)', () => {
  it('survives buildConfig → splitConfig intact', () => {
    const models: ModelsConfig = {
      mode: 'pipeline',
      llm: { provider: 'openai', model: 'gpt-4.1-mini', via: 'inference' },
      tts: { provider: 'cartesia', model: 'sonic-3:abc', via: 'inference' },
      realtime: { voice: 'Puck', model: 'gemini-2.5-flash-native-audio-preview-12-2025' },
    };
    const known: KnownConfig = { instructions: 'hi', tools: [], models };
    const config = buildConfig(known, {});
    const { known: back } = splitConfig(config);
    expect(back.models).toEqual(models);
  });
});

describe("keep-but-don't-clear (task 1.2)", () => {
  it('mode switch preserves the inactive engine sub-block', () => {
    // mirrors useProfileForm.setModelMode: only mode changes, the rest is spread
    const seeded: ModelsConfig = {
      mode: 'pipeline',
      llm: { provider: 'openai', model: 'gpt-4.1-mini' },
      realtime: { voice: 'Charon' },
    };
    const toRealtime: ModelsConfig = { ...seeded, mode: 'realtime' };
    const backToPipeline: ModelsConfig = { ...toRealtime, mode: 'pipeline' };
    expect(backToPipeline.llm).toEqual({ provider: 'openai', model: 'gpt-4.1-mini' });
    expect(backToPipeline.realtime).toEqual({ voice: 'Charon' });
  });

  it('pruneModels keeps both engine sub-blocks (non-destructive persist)', () => {
    const models: ModelsConfig = {
      mode: 'realtime',
      llm: { provider: 'openai', model: 'gpt-4.1-mini' },
      realtime: { voice: 'Kore' },
    };
    expect(pruneModels(models)).toEqual(models);
  });
});

describe('pruneModels drops unpinned noise (design D2)', () => {
  it('returns undefined for an empty/never-pinned block', () => {
    expect(pruneModels(undefined)).toBeUndefined();
    expect(pruneModels({})).toBeUndefined();
    expect(pruneModels({ llm: {}, tts: { provider: '' } })).toBeUndefined();
    expect(pruneModels({ realtime: { voice: '' } })).toBeUndefined();
  });

  it('keeps an explicit engine-mode choice even with no pinned specs', () => {
    expect(pruneModels({ mode: 'pipeline' })).toEqual({ mode: 'pipeline' });
  });

  it('drops empty sub-specs but keeps pinned ones', () => {
    expect(
      pruneModels({ mode: 'pipeline', llm: { provider: 'google', model: 'x' }, stt: {} })
    ).toEqual({ mode: 'pipeline', llm: { provider: 'google', model: 'x' } });
  });
});

describe('compiled-default helper (task 1.4)', () => {
  it('marks a present value pinned and an absent one inherited', () => {
    expect(resolveField('gpt-4.1', 'gemini-3.1-flash-lite')).toEqual({
      value: 'gpt-4.1',
      source: 'pinned',
    });
    expect(resolveField(undefined, 'gemini-3.1-flash-lite')).toEqual({
      value: 'gemini-3.1-flash-lite',
      source: 'inherited',
    });
    expect(resolveField('   ', 'fallback')).toEqual({ value: 'fallback', source: 'inherited' });
  });

  it('specPrimary handles single spec and fallback list', () => {
    expect(specPrimary({ provider: 'a', model: 'b' })).toEqual({ provider: 'a', model: 'b' });
    expect(specPrimary([{ provider: 'a' }, { provider: 'c' }])).toEqual({ provider: 'a' });
    expect(specPrimary(undefined)).toBeUndefined();
  });
});

describe('model-list source-of-truth contract (task 7.1 — anti-drift)', () => {
  // The shared fixture is also checked from pytest against the live backend
  // constants, so a backend change fails BOTH sides until the fixture + this
  // fallback are updated together. Guards the FE fallback ↔ backend parity.
  it('FALLBACK_MODEL_CATALOG matches the backend constants fixture', () => {
    expect(FALLBACK_MODEL_CATALOG.direct_providers).toEqual(backendConstants.direct_providers);
    expect(FALLBACK_MODEL_CATALOG.realtime.llm_providers).toEqual(
      backendConstants.realtime.llm_providers
    );
    expect(FALLBACK_MODEL_CATALOG.realtime.model_allowlist).toEqual(
      backendConstants.realtime.model_allowlist
    );
    expect(FALLBACK_MODEL_CATALOG.realtime.defaults.model).toBe(
      backendConstants.realtime.defaults.model
    );
    expect(FALLBACK_MODEL_CATALOG.realtime.defaults.voice).toBe(
      backendConstants.realtime.defaults.voice
    );
    for (const kind of ['llm', 'stt', 'tts'] as const) {
      const got = FALLBACK_MODEL_CATALOG.pipeline.defaults[kind];
      const want = backendConstants.pipeline.defaults[kind];
      expect({ provider: got.provider, model: got.model }).toEqual(want);
    }
  });

  it('realtime variant ↔ cost sync: the offered default is in the allowlist', () => {
    // The backend allowlist only contains priced variants (pytest asserts each
    // resolves to a dedicated cost rate). Here we guard that the UI's default
    // realtime model is itself selectable from the allowlist it offers.
    expect(FALLBACK_MODEL_CATALOG.realtime.model_allowlist).toContain(
      FALLBACK_MODEL_CATALOG.realtime.defaults.model
    );
    expect(FALLBACK_MODEL_CATALOG.realtime.model_allowlist.length).toBeGreaterThan(0);
  });
});

describe('global config survives prompt↔graph convert/revert (task 5.3)', () => {
  it('promptToGraph does not touch the models stack', () => {
    const models: ModelsConfig = {
      mode: 'pipeline',
      llm: { provider: 'openai', model: 'gpt-4.1-mini' },
    };
    const known: KnownConfig = {
      instructions: '你是客服',
      tools: [{ name: 'get_current_time' }],
      human_operator: { enabled: true },
      models,
    };
    // Conversion builds a graph from instructions/tools but leaves models on `known`.
    const graph = promptToGraph(known);
    expect(graph.nodes.length).toBeGreaterThan(0);
    // models is preserved verbatim through a build → save → load cycle in graph mode.
    const graphConfig = buildConfig({ ...known, graph, editor_mode: 'graph' }, {});
    const reverted = buildConfig({ ...splitConfig(graphConfig).known, editor_mode: 'prompt' }, {});
    expect(splitConfig(reverted).known.models).toEqual(models);
  });
});
