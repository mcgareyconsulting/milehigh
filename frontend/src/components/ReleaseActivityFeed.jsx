/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Shared helpers for date/stage activity summaries used by the release hub
 *   right rail (intermingled with notes). Display-only over ReleaseEvents.
 * exports:
 *   ACTIVITY_ACTIONS: Set of event actions that count as date/stage updates.
 *   summarizeActivity: One human sentence + author for a ReleaseEvents row.
 * imports_from: []
 * imported_by: [frontend/src/components/ReleaseNotesRail.jsx,
 *   frontend/src/components/ReleaseActivityFeed.test.jsx]
 * invariants:
 *   - Dates and stage changes only: update_stage, update_ship_date, update_start_install,
 *     clear_hard_date. Notes stay on their own action.
 *   - Pure helpers — no network, no React render of a standalone feed.
 * updated_by_agent: 2026-08-08T00:00:00Z
 */

/** Actions that belong in the mixed activity rail (roadmap N7: dates + stage). */
export const ACTIVITY_ACTIONS = new Set([
    'update_stage',
    'update_ship_date',
    'update_start_install',
    'clear_hard_date',
]);

/** Display a date payload value (ISO date or ASAP flag) without UTC off-by-one. */
const formatDateValue = (value) => {
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

const fromTo = (payload = {}) => {
    const from = payload.from ?? payload.old ?? payload.old_value ?? null;
    const to = payload.to ?? payload.new ?? payload.new_value ?? null;
    return { from, to };
};

/**
 * One human sentence per event. Full undo / payload detail lives on the Change Log tab.
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
