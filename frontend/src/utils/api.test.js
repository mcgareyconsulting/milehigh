// Tests for the API_BASE_URL resolution.
//
// API_BASE_URL is read at module-evaluation time from import.meta.env, so the
// test resets module registry between cases via vi.resetModules() and uses
// vi.stubEnv() to override env values per case.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

describe('API_BASE_URL', () => {
    beforeEach(() => {
        vi.resetModules();
    });

    afterEach(() => {
        vi.unstubAllEnvs();
    });

    it('uses VITE_API_URL when set', async () => {
        vi.stubEnv('VITE_API_URL', 'https://api.example.com');
        const { API_BASE_URL } = await import('./api.js');
        expect(API_BASE_URL).toBe('https://api.example.com');
    });

    it('falls back to localhost:8000 in dev mode when VITE_API_URL is unset', async () => {
        vi.stubEnv('VITE_API_URL', '');
        vi.stubEnv('DEV', true);
        const { API_BASE_URL } = await import('./api.js');
        expect(API_BASE_URL).toBe('http://localhost:8000');
    });

    it('falls back to empty string in production mode when VITE_API_URL is unset', async () => {
        vi.stubEnv('VITE_API_URL', '');
        vi.stubEnv('DEV', false);
        const { API_BASE_URL } = await import('./api.js');
        expect(API_BASE_URL).toBe('');
    });
});
