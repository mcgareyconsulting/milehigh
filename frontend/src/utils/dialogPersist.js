/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Tab-scoped persistence for an open dialog so a Safari reload on
 *   iPad rotate (BUG-14) can reopen it. sessionStorage dies with the tab.
 * exports:
 *   persistOpenDialog, readOpenDialog
 * imports_from: []
 * imported_by: [frontend/src/pages/JobLogContent.jsx, frontend/src/pages/Archive.jsx,
 *   frontend/src/pages/DraftingWorkLoad.jsx]
 */

const PREFIX = 'mhmw_open_dialog:';

export function persistOpenDialog(key, payload) {
    try {
        if (payload == null) sessionStorage.removeItem(PREFIX + key);
        else sessionStorage.setItem(PREFIX + key, JSON.stringify(payload));
    } catch {
        /* private-mode Safari / quota — non-fatal */
    }
}

export function readOpenDialog(key) {
    try {
        const raw = sessionStorage.getItem(PREFIX + key);
        return raw ? JSON.parse(raw) : null;
    } catch {
        return null;
    }
}
