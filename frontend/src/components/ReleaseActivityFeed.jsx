/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Shared helpers for the release hub Activity rail (notes + stage/date/fab).
 * exports:
 *   ACTIVITY_ACTIONS: Set of non-note event actions that appear in the rail
 *   summarizeActivity: One human sentence + author for a ReleaseEvents row
 *   issueEventSummary: One sentence for a Release Issue Register event (shared with Change Log)
 *   ISSUE_ACTIONS: The release-event actions the Issue Register writes
 *   formatDateValue: Display a date payload without UTC off-by-one
 * imports_from: []
 * imported_by: [frontend/src/components/ReleaseNotesRail.jsx,
 *   frontend/src/components/ReleaseActivityFeed.test.jsx]
 * invariants:
 *   - Activity rail: notes (separate action), stage, fab order, ship date, start install,
 *     clear_hard_date, photo/drawing uploads, and issue create/update/evidence. Everything else
 *     stays on Change Log only.
 *   - Pure helpers — no network, no React.
 * updated_by_agent: 2026-09-15T00:00:00Z
 */

/** Issue Register events (app/brain/release_issues/service.py). Payload `to` holds the issue. */
export const ISSUE_ACTIONS = new Set([
    'create_issue',
    'update_issue',
    'add_issue_attachment',
]);

const ISSUE_FIELD_LABEL = {
    title: 'title',
    description: 'description',
    department: 'department',
    category: 'category',
    priority: 'priority',
    status: 'status',
    estimated_cost: 'estimated cost',
};

const issueCost = (value) => {
    if (value == null || value === '') return 'Unknown/TBD';
    const n = Number(value);
    return Number.isFinite(n)
        ? n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
        : String(value);
};

const describeIssueChange = (c) => {
    const label = ISSUE_FIELD_LABEL[c.field] || c.field;
    if (c.field === 'description') return 'description edited';
    if (c.field === 'estimated_cost') return `${label} ${issueCost(c.from)} → ${issueCost(c.to)}`;
    return `${label} ${c.from ?? '—'} → ${c.to ?? '—'}`;
};

export function issueEventSummary(event) {
    const to = event?.payload?.to && typeof event.payload.to === 'object' ? event.payload.to : {};
    const ref = [to.display_id, to.title ? `“${to.title}”` : null].filter(Boolean).join(' ');
    switch (event?.action) {
        case 'create_issue': {
            const bits = [to.department, to.priority].filter(Boolean).join(' · ');
            return `Issue opened — ${ref || 'untitled'}${bits ? ` (${bits})` : ''}`;
        }
        case 'update_issue': {
            const changes = Array.isArray(to.changes) ? to.changes : [];
            const detail = changes.map(describeIssueChange).join('; ');
            return `Issue ${ref || 'updated'}${detail ? ` — ${detail}` : ' updated'}`;
        }
        case 'add_issue_attachment':
            return `Evidence added to issue ${ref}${to.filename ? ` — ${to.filename}` : ''}`;
        default:
            return null;
    }
}

/** Non-note actions that belong in the mixed activity rail. */
export const ACTIVITY_ACTIONS = new Set([
    'update_stage',
    'update_fab_order',
    'update_ship_date',
    'update_start_install',
    'clear_hard_date',
    // Attachment events: a photo landing on a release is activity, and the rail
    // is where the shop looks first. Their payloads nest an object under `to`,
    // so each gets an explicit branch below rather than the from/to fallback.
    'upload_photo',
    'delete_photo',
    'upload_drawing',
    'save_drawing_version',
    'delete_drawing_version',
    ...ISSUE_ACTIONS,
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

    if (action === 'upload_photo') {
        const meta = to && typeof to === 'object' ? to : {};
        const bits = [meta.filename, meta.stage ? `at ${meta.stage}` : null].filter(Boolean);
        return { text: bits.length ? `Photo added — ${bits.join(' · ')}` : 'Photo added', author };
    }

    if (action === 'delete_photo') {
        return { text: 'Photo deleted', author };
    }

    if (action === 'upload_drawing') {
        const meta = to && typeof to === 'object' ? to : {};
        return {
            text: meta.filename ? `Drawing uploaded — ${meta.filename}` : 'Drawing uploaded',
            author,
        };
    }

    if (action === 'save_drawing_version') {
        const prev = from && typeof from === 'object' ? from.version : null;
        const next = to && typeof to === 'object' ? to.version : null;
        if (prev != null && next != null) return { text: `Markup saved — v${prev} → v${next}`, author };
        return { text: 'Markup saved', author };
    }

    if (ISSUE_ACTIONS.has(action)) {
        const text = issueEventSummary(event);
        return text ? { text, author } : null;
    }

    if (action === 'delete_drawing_version') {
        return {
            text: payload.version != null ? `Drawing v${payload.version} deleted` : 'Drawing version deleted',
            author,
        };
    }

    return null;
}
