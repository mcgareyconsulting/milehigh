/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Provides session-based authentication helpers (check current user, logout) used across all protected pages.
 * exports:
 *   checkAuth: Calls /api/auth/me and returns user data or null
 *   logout: POSTs to /api/auth/logout to end the session
 *   roleFlagsFor: Derives the nav role gates ({isAdmin, canSeeReport, canUseBBChat}) from a user
 *   readCachedRoleFlags: Last-known role gates from localStorage, for optimistic first paint
 *   cacheRoleFlags: Persists (or clears, for a null user) the role gates
 * imports_from: [./api]
 * imported_by: [App.jsx, pages/JobLog.jsx, pages/DraftingWorkLoad.jsx, pages/Board.jsx, pages/Archive.jsx, components/Navbar.jsx, components/AppShell.jsx]
 * invariants:
 *   - checkAuth and logout swallow network errors and never throw
 *   - The role-flag cache is a first-paint hint only, never an authorization decision:
 *     the server gates every route, and checkAuth's answer always overwrites it.
 *   - logout clears the cache, so the next user never inherits the previous one's rail.
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
// Auth utility functions
import { API_BASE_URL } from './api';

export const checkAuth = async () => {
    try {
        const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
            credentials: 'include'
        });
        if (response.ok) {
            const data = await response.json();
            return data;
        }
        return null;
    } catch (err) {
        return null;
    }
};

export const logout = async () => {
    clearCachedRoleFlags();
    try {
        await fetch(`${API_BASE_URL}/api/auth/logout`, {
            method: 'POST',
            credentials: 'include'
        });
    } catch (err) {
        console.error('Logout error:', err);
    }
};

// Monthly invoicing report is visible to khearn plus any admin.
export const userCanAccessInvoicing = (user) =>
    !!user && (user.is_admin || (user.username || '').toLowerCase() === 'khearn@mhmw.com');

// Katie downstream Job Log quick-filter is restricted to exactly these two users
// (intentionally NOT admins — by email only).
export const userCanAccessKatieFilter = (user) => {
    const u = (user?.username || '').toLowerCase();
    return u === 'khearn@mhmw.com' || u === 'mcgareyconsulting@gmail.com';
};



// --- Role-gate cache -------------------------------------------------------
// The nav's role-gated rows (Subs / Meetings / Board / T&M / Matching / Invoicing)
// used to appear only after checkAuth's round-trip, so an admin watched the left
// rail re-lay itself out mid-load — Rail sizes its rows from the viewport against
// the row count, so six late rows resize all of them, not just append. Seeding
// from the last known answer makes the common case (same user, same browser) paint
// the right rail immediately. It is a rendering hint and nothing more: it grants no
// access, and checkAuth's real answer replaces it a moment later either way.
const ROLE_CACHE_KEY = 'mhmw_role_flags';

export const NO_ROLE_FLAGS = { isAdmin: false, canSeeReport: false, canUseBBChat: false };

export const roleFlagsFor = (user) => ({
    isAdmin: !!user?.is_admin,
    canSeeReport: userCanAccessInvoicing(user),
    // Admins always have Carmen-chat access; others need the per-user flag.
    canUseBBChat: !!user && !!(user.is_admin || user.is_carmen_chat),
});

export const readCachedRoleFlags = () => {
    try {
        const raw = localStorage.getItem(ROLE_CACHE_KEY);
        if (!raw) return NO_ROLE_FLAGS;
        const parsed = JSON.parse(raw);
        return {
            isAdmin: !!parsed?.isAdmin,
            canSeeReport: !!parsed?.canSeeReport,
            canUseBBChat: !!parsed?.canUseBBChat,
        };
    } catch {
        // Unparseable or storage unavailable (private mode) — fall back to the
        // pre-fix behaviour of starting closed.
        return NO_ROLE_FLAGS;
    }
};

export const clearCachedRoleFlags = () => {
    try {
        localStorage.removeItem(ROLE_CACHE_KEY);
    } catch {
        /* storage unavailable — nothing cached to clear */
    }
};

// Pass the user from checkAuth; a null user (logged out / session expired) clears
// the cache so the flags can't outlive the session that earned them.
export const cacheRoleFlags = (user) => {
    if (!user) {
        clearCachedRoleFlags();
        return NO_ROLE_FLAGS;
    }
    const flags = roleFlagsFor(user);
    try {
        localStorage.setItem(ROLE_CACHE_KEY, JSON.stringify(flags));
    } catch {
        /* storage unavailable — the flags still apply for this page load */
    }
    return flags;
};
