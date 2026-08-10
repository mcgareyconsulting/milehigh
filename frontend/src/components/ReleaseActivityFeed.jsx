/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Shared helpers for the release hub Activity rail (notes + stage/date/fab).
 * exports:
 *   ACTIVITY_ACTIONS: Set of non-note event actions that appear in the rail
 *   summarizeActivity: One human sentence + author for a ReleaseEvents row
 *   formatDateValue: Display a date payload without UTC off-by-one
 * imports_from: []
 * imported_by: [frontend/src/components/ReleaseNotesRail.jsx,
 *   frontend/src/components/ReleaseActivityFeed.test.jsx]
 * invariants:
 *   - Activity rail: notes (separate action), stage, fab order, ship date, start install,
 *     clear_hard_date. Everything else stays on Change Log only.
 *   - Pure helpers — no network, no React.
 * updated_by_agent: 2026-08-08T00:00:00Z
 */

/** Non-note actions that belong in the mixed activity rail. */
export const ACTIVITY_ACTIONS = new Set([
    'update_stage',
    'update_fab_order',
    'update_ship_date',
    'update_start_install',
    'clear_hard_date',
]);

/** Display a date payload value (ISO date or ASAP flag) without UTC off-by-one. */
export const formatDateValue = (value) => {
    if (value == null || value === '') return null;
    const s = String(value);
    if (/^asap$/i.test(s.trim())) return 'ASAP';
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
    if (m) {
        const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
        if (!isNaN(d)) {
            return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        }
    }
    return s;
};

export const fromTo = (payload = {}) => {
    const from = payload.from ?? payload.old ?? payload.old_value ?? null;
    const to = payload.to ?? payload.new ?? payload.new_value ?? null;
    return { from, to };
};

/**
 * One human sentence per event (Change Log / fallbacks). Rich chip rendering
 * in the rail uses structured fields from buildTimeline instead.
 */
export function summarizeActivity(event) {
    const action = event.action;
    const payload = event.payload || {};
    const { from, to } = fromTo(payload);
    const author = event.user_name || event.source || 'System';

    if (action === 'update_stage') {
        if (from && to && from !== to) return { text: `Stage ${from} → ${to}`, author };
        if (to) return { text: `Stage set to ${to}`, author };
        return { text: 'Stage updated', author };
    }

    if (action === 'update_fab_order') {
        if (from != null && to != null && String(from) !== String(to)) {
            return { text: `Fab Order ${from} → ${to}`, author };
        }
        if (to != null) return { text: `Fab Order set to ${to}`, author };
        return { text: 'Fab Order updated', author };
    }

    if (action === 'update_ship_date') {
        const toLabel = formatDateValue(to);
        if (toLabel == null) return { text: 'Ship date cleared', author };
        return { text: `Ship date set to ${toLabel}`, author };
    }

    if (action === 'update_start_install') {
        if (payload.asap === true || payload.to_asap === true || /^asap$/i.test(String(to || ''))) {
            return { text: 'Start install set to ASAP', author };
        }
        const toLabel = formatDateValue(to);
        if (toLabel == null) return { text: 'Start install cleared', author };
        return { text: `Start install set to ${toLabel}`, author };
    }

    if (action === 'clear_hard_date') {
        return { text: 'Hard start-install date cleared', author };
    }

    return null;
}
