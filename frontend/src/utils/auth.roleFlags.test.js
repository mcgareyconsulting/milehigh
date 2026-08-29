/**
 * BUG-18: the nav's role-gated rows are seeded from the last known answer so an
 * admin doesn't paint the non-admin nav and then gain six rows a round-trip
 * later (which re-lays out the whole rail, since Rail derives row height from
 * the viewport against the row count).
 *
 * The cache is a first-paint hint, never an authorization decision — the server
 * gates every route. What has to hold is that it cannot outlive the session
 * that earned it, or the next user on a shared browser inherits the previous
 * one's rail.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
    NO_ROLE_FLAGS,
    roleFlagsFor,
    readCachedRoleFlags,
    cacheRoleFlags,
    clearCachedRoleFlags,
    logout,
} from './auth.js';

/** In-memory localStorage stub — vitest may ship a non-functional localStorage. */
function installMemoryLocalStorage() {
    const store = new Map();
    vi.stubGlobal('localStorage', {
        getItem: (k) => (store.has(k) ? store.get(k) : null),
        setItem: (k, v) => { store.set(String(k), String(v)); },
        removeItem: (k) => { store.delete(k); },
        clear: () => { store.clear(); },
    });
    return store;
}

const ADMIN = { username: 'daniel@mhmw.com', is_admin: true };
const DRAFTER = { username: 'colton@mhmw.com', is_admin: false };

describe('roleFlagsFor', () => {
    it('gives an admin every gate', () => {
        expect(roleFlagsFor(ADMIN)).toEqual({
            isAdmin: true, canSeeReport: true, canUseBBChat: true,
        });
    });

    it('gives a plain user none of them', () => {
        expect(roleFlagsFor(DRAFTER)).toEqual({
            isAdmin: false, canSeeReport: false, canUseBBChat: false,
        });
    });

    it('opens Carmen chat on the per-user flag without granting admin', () => {
        const flags = roleFlagsFor({ ...DRAFTER, is_carmen_chat: true });
        expect(flags.canUseBBChat).toBe(true);
        expect(flags.isAdmin).toBe(false);
    });

    it('keeps khearn on invoicing without granting admin', () => {
        const flags = roleFlagsFor({ username: 'KHearn@mhmw.com', is_admin: false });
        expect(flags.canSeeReport).toBe(true);
        expect(flags.isAdmin).toBe(false);
    });

    it('treats a null user (no session) as no gates', () => {
        expect(roleFlagsFor(null)).toEqual(NO_ROLE_FLAGS);
    });
});

describe('role-flag cache', () => {
    beforeEach(() => { installMemoryLocalStorage(); });
    afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

    it('starts closed when nothing is cached', () => {
        expect(readCachedRoleFlags()).toEqual(NO_ROLE_FLAGS);
    });

    it('round-trips an admin so the next load paints the full rail', () => {
        cacheRoleFlags(ADMIN);
        expect(readCachedRoleFlags()).toEqual(roleFlagsFor(ADMIN));
    });

    it('clears on logout so the next user does not inherit the rail', async () => {
        cacheRoleFlags(ADMIN);
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true }));

        await logout();

        expect(readCachedRoleFlags()).toEqual(NO_ROLE_FLAGS);
    });

    it('clears when checkAuth comes back empty (expired session)', () => {
        cacheRoleFlags(ADMIN);
        expect(cacheRoleFlags(null)).toEqual(NO_ROLE_FLAGS);
        expect(readCachedRoleFlags()).toEqual(NO_ROLE_FLAGS);
    });

    it('overwrites rather than merges, so gates cannot accumulate', () => {
        cacheRoleFlags(ADMIN);
        expect(cacheRoleFlags(DRAFTER)).toEqual(NO_ROLE_FLAGS);
        expect(readCachedRoleFlags()).toEqual(NO_ROLE_FLAGS);
    });

    it('falls back to closed on corrupt cache rather than throwing', () => {
        localStorage.setItem('mhmw_role_flags', 'not json');
        expect(readCachedRoleFlags()).toEqual(NO_ROLE_FLAGS);
    });

    it('never infers a gate from a truthy non-boolean in the cache', () => {
        localStorage.setItem('mhmw_role_flags', JSON.stringify({ isAdmin: 'yes' }));
        expect(readCachedRoleFlags()).toEqual({
            isAdmin: true, canSeeReport: false, canUseBBChat: false,
        });
    });

    it('survives storage being unavailable (private mode)', () => {
        vi.stubGlobal('localStorage', {
            getItem: () => { throw new Error('denied'); },
            setItem: () => { throw new Error('denied'); },
            removeItem: () => { throw new Error('denied'); },
        });

        expect(() => clearCachedRoleFlags()).not.toThrow();
        expect(cacheRoleFlags(ADMIN)).toEqual(roleFlagsFor(ADMIN));
        expect(readCachedRoleFlags()).toEqual(NO_ROLE_FLAGS);
    });
});
