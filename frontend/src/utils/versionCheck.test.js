import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { checkVersion } from './versionCheck';
import { CLIENT_VERSION } from './version';

describe('checkVersion', () => {
  let fetchSpy;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, 'fetch');
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it('reports not stale when server SHA matches the client SHA', async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ version: CLIENT_VERSION, releasedAt: '2026-05-07T00:00:00Z' }),
    });
    const result = await checkVersion();
    expect(result).toEqual({ stale: false, server: CLIENT_VERSION });
  });

  it('reports stale when server SHA differs from the client SHA', async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ version: 'abc1234', releasedAt: '2026-05-07T00:00:00Z' }),
    });
    const result = await checkVersion();
    expect(result).toEqual({ stale: true, server: 'abc1234' });
  });

  it('reports not stale when fetch rejects (network error)', async () => {
    fetchSpy.mockRejectedValueOnce(new Error('network down'));
    const result = await checkVersion();
    expect(result).toEqual({ stale: false, server: null });
  });

  it('reports not stale when response is non-OK', async () => {
    fetchSpy.mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({}) });
    const result = await checkVersion();
    expect(result).toEqual({ stale: false, server: null });
  });

  it('reports not stale when server returns empty version', async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ version: '', releasedAt: '2026-05-07T00:00:00Z' }),
    });
    const result = await checkVersion();
    expect(result.stale).toBe(false);
  });
});
