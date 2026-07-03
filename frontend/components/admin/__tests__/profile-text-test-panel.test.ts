import { describe, expect, it } from 'vitest';
import type { ProfileTestRunDetail } from '@/lib/admin-api';
import { eventToolState, findAssistantOutput, graphPath } from '../profile-text-test-panel';

const baseRun: ProfileTestRunDetail = {
  id: 'run-1',
  profile_id: 'profile-1',
  status: 'completed',
  tool_execution_mode: 'dry_run',
  user_message: '電梯壞了',
  profile_config_hash: 'hash',
  profile_snapshot_at: '2026-06-29T00:00:00Z',
  final_summary: {},
  created_at: '2026-06-29T00:00:00Z',
  updated_at: '2026-06-29T00:00:00Z',
  completed_at: '2026-06-29T00:00:01Z',
  events: [],
};

describe('ProfileTextTestPanel helpers', () => {
  it('prefers final summary assistant output over event output', () => {
    const run: ProfileTestRunDetail = {
      ...baseRun,
      final_summary: { assistant_output: 'summary output' },
      events: [
        {
          id: 1,
          seq: 1,
          event_type: 'assistant_output',
          severity: 'info',
          timestamp: '2026-06-29T00:00:00Z',
          payload: { text: 'event output', schema_version: 1 },
        },
      ],
    };

    expect(findAssistantOutput(run)).toBe('summary output');
  });

  it('falls back to assistant output event', () => {
    const run: ProfileTestRunDetail = {
      ...baseRun,
      events: [
        {
          id: 1,
          seq: 1,
          event_type: 'assistant_output',
          severity: 'info',
          timestamp: '2026-06-29T00:00:00Z',
          payload: { text: 'event output', schema_version: 1 },
        },
      ],
    };

    expect(findAssistantOutput(run)).toBe('event output');
  });

  it('returns graph path events in timeline order', () => {
    const run: ProfileTestRunDetail = {
      ...baseRun,
      events: [
        {
          id: 1,
          seq: 1,
          event_type: 'test_started',
          severity: 'info',
          timestamp: '2026-06-29T00:00:00Z',
          payload: { schema_version: 1 },
        },
        {
          id: 2,
          seq: 2,
          event_type: 'node_entered',
          severity: 'info',
          timestamp: '2026-06-29T00:00:01Z',
          payload: { node_id: 'start', title: '入口', schema_version: 1 },
        },
        {
          id: 3,
          seq: 3,
          event_type: 'edge_selected',
          severity: 'info',
          timestamp: '2026-06-29T00:00:02Z',
          payload: { trigger: 'tool_result', target: 'handoff', schema_version: 1 },
        },
        {
          id: 4,
          seq: 4,
          event_type: 'tool_call',
          severity: 'info',
          timestamp: '2026-06-29T00:00:03Z',
          payload: { mode: 'dry_run', schema_version: 1 },
        },
      ],
    };

    expect(graphPath(run).map((event) => event.event_type)).toEqual([
      'node_entered',
      'edge_selected',
    ]);
  });

  it('keeps fallback and error events out of graph path', () => {
    const run: ProfileTestRunDetail = {
      ...baseRun,
      events: [
        {
          id: 1,
          seq: 1,
          event_type: 'fallback',
          severity: 'warning',
          timestamp: '2026-06-29T00:00:00Z',
          payload: { reason: 'graph_missing_or_unusable', schema_version: 1 },
        },
        {
          id: 2,
          seq: 2,
          event_type: 'runner_error',
          severity: 'error',
          timestamp: '2026-06-29T00:00:01Z',
          payload: { error_type: 'TimeoutError', schema_version: 1 },
        },
      ],
    };

    expect(graphPath(run)).toEqual([]);
  });

  it('summarizes tool call state for compact timeline rows', () => {
    expect(
      eventToolState({
        id: 1,
        seq: 1,
        event_type: 'tool_call',
        severity: 'info',
        timestamp: '2026-06-29T00:00:00Z',
        payload: { mode: 'dry_run', executed: false, timed_out: false, result: { success: true } },
      })
    ).toEqual(['dry_run', 'skipped']);

    expect(
      eventToolState({
        id: 2,
        seq: 2,
        event_type: 'tool_call',
        severity: 'error',
        timestamp: '2026-06-29T00:00:00Z',
        payload: { mode: 'live', executed: false, timed_out: false, result: { success: false } },
      })
    ).toEqual(['live', 'skipped', 'error']);
  });
});
