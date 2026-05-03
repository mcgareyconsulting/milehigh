/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Provides session-based authentication helpers (check current user, logout) used across all protected pages.
 * exports:
 *   checkAuth: Calls /api/auth/me and returns user data or null
 *   logout: POSTs to /api/auth/logout to end the session
 * imports_from: [./api]
 * imported_by: [App.jsx, pages/JobLog.jsx, pages/DraftingWorkLoad.jsx, pages/Board.jsx, pages/Archive.jsx, components/Navbar.jsx, components/AppShell.jsx]
 * invariants:
 *   - Both functions swallow network errors and never throw
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
    try {
        await fetch(`${API_BASE_URL}/api/auth/logout`, {
            method: 'POST',
            credentials: 'include'
        });
    } catch (err) {
        console.error('Logout error:', err);
    }
};

// Users opted in to native scrollbars on Job Log / DWL / Archive tables.
// Usernames are stored lowercased server-side; compare lowercased.
const USERS_WITH_VISIBLE_SCROLLBARS = new Set(['khearn@mhmw.com']);

export const userWantsVisibleScrollbars = (user) =>
    !!user?.username && USERS_WITH_VISIBLE_SCROLLBARS.has(user.username.toLowerCase());

