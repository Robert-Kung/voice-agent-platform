import { afterEach, describe, expect, it, vi } from 'vitest';
import { testRunsApi } from '../admin-api';

function jsonResponse(body: unknown, init: { status?: number; headers?: Record<string, string> } = {}) {
  return {
    ok: (init.status ?? 200) < 400,
    status: init.status ?? 200,
    statusText: 'OK',
    headers: {
      get: (name: string) => init.headers?.[name] ?? null,
    },
    json: async () => body,
    text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
  } as Response;
}

describe('testRunsApi', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('creates a profile text test run with dry-run mode', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ id: 'run-1', events: [], status: 'completed' })
    );
    vi.stubGlobal('fetch', fetchMock);

    const run = await testRunsApi.create('profile-1', {
      message: 'hi',
      tool_execution_mode: 'dry_run',
    });

    expect(run.id).toBe('run-1');
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/admin-proxy/api/profiles/profile-1/test-runs',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ message: 'hi', tool_execution_mode: 'dry_run' }),
      })
    );
  });

  it('lists recent runs with total count metadata', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse([{ id: 'run-1' }], { headers: { 'X-Total-Count': '7' } })
      )
    );

    const page = await testRunsApi.list('profile-1', { limit: 5, offset: 0 });

    expect(page.items).toHaveLength(1);
    expect(page.total).toBe(7);
  });

  it('gets one run detail', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ id: 'run-1', events: [] })));

    const run = await testRunsApi.get('profile-1', 'run-1');

    expect(run.id).toBe('run-1');
  });

  it('throws user-readable API errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse('bad request', { status: 400 })));

    await expect(testRunsApi.create('profile-1', { message: 'hi' })).rejects.toThrow(
      'API 400: bad request'
    );
  });
});
