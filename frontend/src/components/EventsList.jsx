/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Reusable events viewer — full table for Events page / EventsModal; hub
 *   Change Log layout (day groups, plain-language diffs, no Identifier) for ReleaseHubModal.
 * exports:
 *   EventsList: Self-contained events viewer (fetch, expand, undo)
 *   fieldLabelForAction: map raw action → human field label (tests)
 *   fromToOf: extract from/to from event payload (tests)
 * imports_from: [react, axios, react-dom, ../utils/api, ../utils/stageTint]
 * imported_by: [frontend/src/pages/Events.jsx, frontend/src/components/EventsModal.jsx,
 *   frontend/src/components/ReleaseHubModal.jsx]
 * invariants:
 *   - Refetches whenever any filter prop changes
 *   - Undo POST hits /brain/events/{id}/undo for job events and /brain/submittal-events/{id}/undo
 *   - Toast and undo-confirmation render via portal above wrapping modals
 *   - variant="default" keeps the Events page table; variant="hub" is release-modal only
 * updated_by_agent: 2026-08-08T00:00:00Z
 */
import { useState, useEffect, useMemo } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';

import { API_BASE_URL } from '../utils/api';
import { stageTint } from '../utils/stageTint';

const UNDO_WHITELIST = new Set([
    'update_stage',
    'update_notes',
    'update_fab_order',
    'update_start_install',
]);

const UNDO_ACTION_LABEL = {
    update_stage: 'Stage',
    update_notes: 'Notes',
    update_fab_order: 'Fab Order',
    update_start_install: 'Start Install',
};

/** Plain field labels for hub Change Log — never render raw action names. */
const ACTION_FIELD_LABEL = {
    ...UNDO_ACTION_LABEL,
    update_ship_date: 'Ship Date',
    clear_hard_date: 'Start Install',
    update_invoiced: 'Invoiced',
    update_job_comp: 'Install Prog',
    update_released: 'Released',
    update_comp_eta: 'Comp. ETA',
    update_paint_color: 'Paint Color',
    update_installer: 'Installer',
    update_num_guys: 'Crew',
    update_install_hrs: 'Install Hrs',
    update_fab_hrs: 'Fab Hrs',
    update_pm: 'PM',
    update_by: 'By',
};

export function fieldLabelForAction(action) {
    if (!action) return 'Change';
    if (ACTION_FIELD_LABEL[action]) return ACTION_FIELD_LABEL[action];
    // update_foo_bar → Foo Bar
    const stripped = String(action).replace(/^update_/, '').replace(/_/g, ' ');
    return stripped.replace(/\b\w/g, (c) => c.toUpperCase());
}

const DWL_UNDO_FIELDS = new Set([
    'order_number',
    'notes',
    'submittal_drafting_status',
]);

const DWL_FIELD_LABEL = {
    order_number: 'Order',
    notes: 'Notes',
    submittal_drafting_status: 'Drafting Status',
};

function dwlPayloadField(event) {
    if (event.type !== 'submittal') return null;
    if (event.action !== 'updated') return null;
    const payload = event.payload || {};
    const matches = Object.keys(payload).filter(k =>
        DWL_UNDO_FIELDS.has(k)
        && payload[k] && typeof payload[k] === 'object'
        && 'old' in payload[k] && 'new' in payload[k]
    );
    return matches.length === 1 ? matches[0] : null;
}

function getUndoEligibility(event) {
    const payload = event.payload || {};

    if (payload.undone_event_id != null) {
        const where = event.type === 'submittal' ? 'Drafting Work Load' : 'Job Log';
        return { canUndo: false, reason: `Undo events can't be undone — edit in ${where} directly` };
    }

    if (event.type === 'job') {
        if (!UNDO_WHITELIST.has(event.action)) return { canUndo: false, reason: 'Not undoable' };
        if (!('from' in payload) || !('to' in payload)) {
            return { canUndo: false, reason: 'Not undoable' };
        }
        if (payload.from === payload.to) {
            return { canUndo: false, reason: 'Already in this state' };
        }
        if (event.current_value !== payload.to) {
            return { canUndo: false, reason: 'Newer change exists — undo that first' };
        }
        return { canUndo: true, reason: null };
    }

    if (event.type === 'submittal') {
        const field = dwlPayloadField(event);
        if (field == null) return { canUndo: false, reason: 'Not undoable' };
        const inner = payload[field];
        if (inner.old === inner.new) {
            return { canUndo: false, reason: 'Already in this state' };
        }
        if (event.current_value !== inner.new) {
            return { canUndo: false, reason: 'Newer change exists — undo that first' };
        }
        return { canUndo: true, reason: null };
    }

    return { canUndo: false, reason: 'Not undoable' };
}

const formatDateTime = (dateString) => {
    if (!dateString) return '—';
    return new Date(dateString).toLocaleString();
};

const formatPayload = (payload) => {
    if (!payload) return '—';
    let value = payload;
    if (typeof value === 'string') {
        try {
            value = JSON.parse(value);
        } catch {
            return value;
        }
    }
    return JSON.stringify(value, null, 2);
};

const getSourceColor = (source) => {
    const colors = {
        'Trello': 'bg-blue-100 dark:bg-blue-900/50 text-blue-800 dark:text-blue-200',
        'Excel': 'bg-green-100 dark:bg-green-900/50 text-green-800 dark:text-green-200',
        'System': 'bg-gray-100 dark:bg-slate-600 text-gray-800 dark:text-slate-200',
        'Procore': 'bg-purple-100 dark:bg-purple-900/50 text-purple-800 dark:text-purple-200',
        'Brain': 'bg-amber-100 dark:bg-amber-900/50 text-amber-800 dark:text-amber-200',
    };
    return colors[source] || 'bg-gray-100 dark:bg-slate-600 text-gray-800 dark:text-slate-200';
};

const isUndoEvent = (event) => event?.payload?.undone_event_id != null;

const formatPayloadValue = (action, value) => {
    if (value === null || value === undefined || value === '') return '∅';
    return String(value);
};

export function fromToOf(event) {
    const payload = event?.payload || {};
    if (event?.type === 'submittal') {
        const field = dwlPayloadField(event);
        if (field) {
            const inner = payload[field] || {};
            return { from: inner.old, to: inner.new };
        }
    }
    const from = payload.from ?? payload.old ?? payload.old_value ?? null;
    const to = payload.to ?? payload.new ?? payload.new_value ?? null;
    return { from, to };
}

/** Pretty display for a from/to chip (dates without UTC off-by-one). */
function displayValue(value) {
    if (value === null || value === undefined || value === '') return '—';
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
}

function dayBucket(iso) {
    if (!iso) return { key: 'unknown', label: 'UNKNOWN DATE' };
    const d = new Date(iso);
    if (isNaN(d)) return { key: 'unknown', label: 'UNKNOWN DATE' };
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    const dow = d.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase();
    const mon = d.toLocaleDateString('en-US', { month: 'short' }).toUpperCase();
    const day = d.getDate();
    return { key, label: `${dow} · ${mon} ${day}` };
}

function formatTimeOnly(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    if (isNaN(d)) return '—';
    return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
}

function formatRangeLabel(events) {
    if (!events.length) return '';
    const times = events
        .map((e) => new Date(e.created_at).getTime())
        .filter((t) => Number.isFinite(t));
    if (!times.length) return '';
    const min = new Date(Math.min(...times));
    const max = new Date(Math.max(...times));
    const fmt = (d) => d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const a = fmt(min);
    const b = fmt(max);
    return a === b ? a : `${a} – ${b}`;
}

function groupEventsByDay(events) {
    const groups = [];
    const indexByKey = new Map();
    for (const event of events || []) {
        const { key, label } = dayBucket(event.created_at);
        let g = indexByKey.get(key);
        if (!g) {
            g = { key, label, events: [] };
            indexByKey.set(key, g);
            groups.push(g);
        }
        g.events.push(event);
    }
    return groups;
}

function buildLinkedRevertItems(undoTarget) {
    const items = [];
    if (undoTarget.linked_children && undoTarget.linked_children.length > 0) {
        for (const c of undoTarget.linked_children) {
            items.push({
                key: `child-${c.id}`,
                label: UNDO_ACTION_LABEL[c.action] || c.action,
                from: c.to,
                to: c.from,
            });
        }
    }
    const swap = undoTarget.payload?.swapped_with;
    if (swap && swap.submittal_id && swap.order_number) {
        items.push({
            key: `swap-${swap.submittal_id}`,
            label: `Order on submittal ${swap.submittal_id}`,
            from: swap.order_number.new,
            to: swap.order_number.old,
        });
    }
    return items;
}

const UNDO_DISCLAIMER = {
    submittal: 'Reverts the database value only — no Procore update is sent.',
    job: 'Undo reverts this row only. Cascaded changes outside this row (scheduling for other releases, other rows in the same stash session) are not rolled back.',
};

function DiffChip({ value, variant = 'old', stageName = null }) {
    const blank = value === null || value === undefined || value === '';
    const text = blank ? '—' : displayValue(value);
    let bg = 'var(--head-bg)';
    let fg = 'var(--text-2)';
    if (variant === 'new') {
        if (stageName) {
            const t = stageTint(stageName);
            bg = t.bg;
            fg = t.fg;
        } else {
            bg = 'var(--st-green-bg)';
            fg = 'var(--st-green-fg)';
        }
    }
    return (
        <span
            className="inline-block font-mono font-semibold"
            style={{
                fontSize: 12,
                padding: '2px 7px',
                borderRadius: 5,
                background: bg,
                color: fg,
                maxWidth: variant === 'old' ? 150 : 250,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                verticalAlign: 'middle',
            }}
            title={text}
        >
            {text}
        </span>
    );
}

function HubSourceChip({ source }) {
    const s = (source || '').toString();
    let bg = 'var(--head-bg)';
    let fg = 'var(--text-2)';
    if (s === 'Brain') {
        bg = 'var(--st-amber-bg)';
        fg = 'var(--st-amber-fg)';
    } else if (s === 'Trello') {
        bg = 'var(--st-blue-bg)';
        fg = 'var(--st-blue-fg)';
    } else if (s === 'Procore') {
        bg = 'var(--st-purple-bg)';
        fg = 'var(--st-purple-fg)';
    }
    return (
        <span
            className="inline-block font-semibold"
            style={{
                fontSize: 12,
                padding: '2px 7px',
                borderRadius: 5,
                background: bg,
                color: fg,
            }}
        >
            {s || '—'}
        </span>
    );
}

function HubDayDivider({ label }) {
    return (
        <div className="flex items-center" style={{ gap: 8, margin: '14px 0 6px' }}>
            <span
                className="font-bold uppercase shrink-0"
                style={{ fontSize: 11, letterSpacing: '.04em', color: 'var(--text-3)' }}
            >
                {label}
            </span>
            <div className="flex-1 min-w-0" style={{ height: 1, background: 'var(--border)' }} />
        </div>
    );
}

function HubChangeRow({
    event,
    expanded,
    onTogglePayload,
    onUndo,
}) {
    const { from, to } = fromToOf(event);
    const field = event.type === 'submittal'
        ? (DWL_FIELD_LABEL[dwlPayloadField(event)] || fieldLabelForAction(event.action))
        : fieldLabelForAction(event.action);
    const isStage = event.action === 'update_stage';
    const isNotes = event.action === 'update_notes'
        || (event.type === 'submittal' && dwlPayloadField(event) === 'notes');
    const longNotes = isNotes && (
        String(from || '').length > 80 || String(to || '').length > 80
    );
    const { canUndo, reason } = getUndoEligibility(event);
    const uniqueKey = `${event.type}-${event.id}`;

    return (
        <div
            className="border-b border-hairline"
            style={{ padding: '8px 0' }}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(30,90,200,.05)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
        >
            <div
                className="grid items-center gap-2"
                style={{
                    gridTemplateColumns: '66px 118px minmax(0,1fr) 64px 64px',
                }}
            >
                <span className="font-mono text-ink-3" style={{ fontSize: 12.5 }}>
                    {formatTimeOnly(event.created_at)}
                </span>
                <span className="text-ink truncate font-medium" style={{ fontSize: 13.5 }} title={event.user_name || ''}>
                    {event.user_name || '—'}
                </span>
                <div className="min-w-0">
                    <div className="flex items-center flex-wrap" style={{ gap: 6 }}>
                        <span className="text-ink-2 shrink-0" style={{ fontSize: 13 }}>{field}</span>
                        {!longNotes && (
                            <>
                                <DiffChip value={from} variant="old" />
                                <span className="text-ink-3" style={{ fontSize: 13 }}>→</span>
                                <DiffChip
                                    value={to}
                                    variant="new"
                                    stageName={isStage ? String(to || '') : null}
                                />
                            </>
                        )}
                        {longNotes && (
                            <button
                                type="button"
                                onClick={() => onTogglePayload(uniqueKey)}
                                className="font-mono text-brand bg-transparent border-0 cursor-pointer"
                                style={{ fontSize: 12 }}
                            >
                                payload {expanded ? '▴' : '▾'}
                            </button>
                        )}
                        {isUndoEvent(event) && (
                            <span
                                className="font-semibold uppercase"
                                style={{
                                    fontSize: 10.5,
                                    padding: '1px 5px',
                                    borderRadius: 4,
                                    background: 'var(--st-amber-bg)',
                                    color: 'var(--st-amber-fg)',
                                }}
                            >
                                undo
                            </span>
                        )}
                    </div>
                    {longNotes && !expanded && (
                        <div className="text-ink-2 truncate" style={{ fontSize: 13, marginTop: 3 }} title={displayValue(to)}>
                            {displayValue(to)}
                        </div>
                    )}
                </div>
                <div className="flex justify-center">
                    <HubSourceChip source={event.source} />
                </div>
                <div className="flex justify-end">
                    <button
                        type="button"
                        onClick={() => canUndo && onUndo(event)}
                        disabled={!canUndo}
                        title={canUndo ? 'Revert this change' : reason}
                        className="font-semibold border cursor-pointer disabled:cursor-not-allowed"
                        style={{
                            fontSize: 12,
                            padding: '3px 7px',
                            borderRadius: 6,
                            background: canUndo ? 'var(--surface)' : 'var(--surface-2)',
                            color: canUndo ? 'var(--accent)' : 'var(--text-3)',
                            borderColor: canUndo ? 'var(--border-strong)' : 'var(--border)',
                            opacity: canUndo ? 1 : 0.55,
                        }}
                    >
                        ↺ Undo
                    </button>
                </div>
            </div>
            {expanded && (
                <pre
                    className="font-mono border border-hairline bg-surface-2 text-ink overflow-x-auto"
                    style={{
                        marginTop: 8,
                        marginLeft: 66 + 8 + 118 + 8,
                        padding: 10,
                        borderRadius: 8,
                        fontSize: 12,
                        lineHeight: 1.4,
                        maxHeight: 200,
                    }}
                >
                    {formatPayload(event.payload)}
                </pre>
            )}
            {/* Short notes: optional expand for raw payload */}
            {!longNotes && (
                <div style={{ marginLeft: 66 + 8 + 118 + 8, marginTop: 2 }}>
                    <button
                        type="button"
                        onClick={() => onTogglePayload(uniqueKey)}
                        className="font-mono text-ink-3 bg-transparent border-0 cursor-pointer hover:text-brand"
                        style={{ fontSize: 11.5, padding: 0 }}
                    >
                        {expanded ? 'hide payload ▴' : 'payload ▾'}
                    </button>
                </div>
            )}
        </div>
    );
}

function HubChangeLog({
    events,
    expandedPayload,
    togglePayload,
    setUndoTarget,
}) {
    const groups = useMemo(() => groupEventsByDay(events), [events]);
    const range = formatRangeLabel(events);
    const count = events.length;

    if (count === 0) {
        return (
            <div className="text-center" style={{ padding: '48px 16px' }}>
                <p className="text-ink-3" style={{ fontSize: 13 }}>No changes on this release yet.</p>
            </div>
        );
    }

    return (
        <div>
            <div className="flex items-baseline justify-between flex-wrap" style={{ gap: 8, marginBottom: 4 }}>
                <span className="text-ink-2" style={{ fontSize: 13 }}>
                    <span className="font-semibold text-ink">
                        {count} change{count === 1 ? '' : 's'}
                    </span>
                    {range ? (
                        <span className="text-ink-3">
                            {' · '}{range}
                        </span>
                    ) : null}
                </span>
                <span className="text-ink-3" style={{ fontSize: 11.5 }}>Newest first</span>
            </div>

            {groups.map((group) => (
                <div key={group.key}>
                    <HubDayDivider label={group.label} />
                    {group.events.map((event) => {
                        const uniqueKey = `${event.type}-${event.id}`;
                        return (
                            <HubChangeRow
                                key={uniqueKey}
                                event={event}
                                expanded={!!expandedPayload[uniqueKey]}
                                onTogglePayload={togglePayload}
                                onUndo={setUndoTarget}
                            />
                        );
                    })}
                </div>
            ))}
        </div>
    );
}

export function EventsList({
    submittalId = '',
    jobFilter = '',
    releaseFilter = '',
    selectedDate = '',
    selectedSource = '',
    selectedUser = '',
    limit = 50,
    // 'default' = Events page / EventsModal. 'hub' = Release hub Change Log tab.
    variant = 'default',
}) {
    const isHub = variant === 'hub';
    const effectiveLimit = isHub && limit === 50 ? 100 : limit;

    const [events, setEvents] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [expandedPayload, setExpandedPayload] = useState({});
    const [undoTarget, setUndoTarget] = useState(null);
    const [undoSubmitting, setUndoSubmitting] = useState(false);
    const [undoToast, setUndoToast] = useState(null);

    useEffect(() => {
        fetchEvents();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [selectedDate, effectiveLimit, selectedSource, submittalId, jobFilter, releaseFilter, selectedUser]);

    const fetchEvents = async () => {
        setLoading(true);
        setError(null);
        try {
            const params = { limit: effectiveLimit };
            if (selectedDate) {
                params.start = selectedDate;
                params.end = selectedDate;
            }
            if (selectedSource) {
                params.source = selectedSource;
            }
            if (submittalId) {
                params.submittal_id = String(submittalId).trim();
            }
            if (jobFilter) {
                params.job = parseInt(jobFilter, 10);
            }
            if (releaseFilter) {
                params.release = String(releaseFilter).trim();
            }
            if (selectedUser) {
                params.user_id = selectedUser;
            }
            const response = await axios.get(`${API_BASE_URL}/brain/events`, { params });
            setEvents(response.data.events || []);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const togglePayload = (eventId) => {
        setExpandedPayload(prev => ({
            ...prev,
            [eventId]: !prev[eventId]
        }));
    };

    const submitUndo = async () => {
        if (!undoTarget) return;
        setUndoSubmitting(true);
        const undoUrl = undoTarget.type === 'submittal'
            ? `${API_BASE_URL}/brain/submittal-events/${undoTarget.id}/undo`
            : `${API_BASE_URL}/brain/events/${undoTarget.id}/undo`;
        try {
            await axios.post(undoUrl);
            setUndoTarget(null);
            await fetchEvents();
            setUndoToast({ kind: 'success', message: 'Undo applied.' });
        } catch (err) {
            const status = err?.response?.status;
            const body = err?.response?.data || {};
            if (status === 409) {
                setUndoToast({
                    kind: 'error',
                    message: 'Newer changes exist — refresh and try again.',
                });
                setUndoTarget(null);
                await fetchEvents();
            } else {
                setUndoToast({
                    kind: 'error',
                    message: body.message || body.error || 'Undo failed.',
                });
            }
        } finally {
            setUndoSubmitting(false);
        }
    };

    const undoPortal = (
        <>
            {undoTarget && createPortal(
                <div
                    className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40"
                    onClick={() => !undoSubmitting && setUndoTarget(null)}
                >
                    <div
                        className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl p-6 max-w-md w-full mx-4 border border-gray-200 dark:border-slate-600"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <h2 className="text-lg font-bold text-gray-900 dark:text-slate-100 mb-3">
                            Confirm Undo
                        </h2>
                        {undoTarget.type === 'submittal' ? (() => {
                            const field = dwlPayloadField(undoTarget);
                            const inner = field ? undoTarget.payload[field] : { old: '?', new: '?' };
                            return (
                                <p className="text-sm text-gray-700 dark:text-slate-300 mb-3">
                                    Set <span className="font-semibold">{DWL_FIELD_LABEL[field] || field}</span> on submittal{' '}
                                    <span className="font-mono">{undoTarget.submittal_id}</span> from{' '}
                                    <span className="font-mono bg-gray-100 dark:bg-slate-700 px-1.5 py-0.5 rounded">
                                        {formatPayloadValue(field, inner.new)}
                                    </span>{' '}
                                    back to{' '}
                                    <span className="font-mono bg-gray-100 dark:bg-slate-700 px-1.5 py-0.5 rounded">
                                        {formatPayloadValue(field, inner.old)}
                                    </span>
                                    ?
                                </p>
                            );
                        })() : (
                            <p className="text-sm text-gray-700 dark:text-slate-300 mb-3">
                                Set <span className="font-semibold">{UNDO_ACTION_LABEL[undoTarget.action] || undoTarget.action}</span> on{' '}
                                <span className="font-mono">#{undoTarget.job}-{undoTarget.release}</span> from{' '}
                                <span className="font-mono bg-gray-100 dark:bg-slate-700 px-1.5 py-0.5 rounded">
                                    {formatPayloadValue(undoTarget.action, undoTarget.payload?.to)}
                                </span>{' '}
                                back to{' '}
                                <span className="font-mono bg-gray-100 dark:bg-slate-700 px-1.5 py-0.5 rounded">
                                    {formatPayloadValue(undoTarget.action, undoTarget.payload?.from)}
                                </span>
                                ?
                            </p>
                        )}
                        {(() => {
                            const items = buildLinkedRevertItems(undoTarget);
                            if (items.length === 0) return null;
                            return (
                                <div className="mb-3 px-3 py-2 rounded-lg bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-800">
                                    <p className="text-xs font-semibold text-amber-800 dark:text-amber-200 mb-1">
                                        This will also revert:
                                    </p>
                                    <ul className="text-xs text-amber-900 dark:text-amber-100 space-y-0.5">
                                        {items.map(it => (
                                            <li key={it.key} className="font-mono">
                                                • {it.label}:{' '}
                                                <span className="bg-white/60 dark:bg-slate-800/60 px-1 rounded">
                                                    {formatPayloadValue(null, it.from)}
                                                </span>{' '}
                                                →{' '}
                                                <span className="bg-white/60 dark:bg-slate-800/60 px-1 rounded">
                                                    {formatPayloadValue(null, it.to)}
                                                </span>
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            );
                        })()}
                        <p className="text-xs text-gray-500 dark:text-slate-400 italic mb-5">
                            {UNDO_DISCLAIMER[undoTarget.type] || UNDO_DISCLAIMER.job}
                        </p>
                        <div className="flex justify-end gap-2">
                            <button
                                onClick={() => setUndoTarget(null)}
                                disabled={undoSubmitting}
                                className="px-4 py-2 text-sm font-semibold text-gray-700 dark:text-slate-200 bg-gray-100 dark:bg-slate-700 hover:bg-gray-200 dark:hover:bg-slate-600 rounded-lg transition-colors disabled:opacity-50"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={submitUndo}
                                disabled={undoSubmitting}
                                className="px-4 py-2 text-sm font-semibold text-white bg-accent-600 hover:bg-accent-700 rounded-lg transition-colors disabled:opacity-50"
                            >
                                {undoSubmitting ? 'Undoing…' : 'Undo'}
                            </button>
                        </div>
                    </div>
                </div>,
                document.body
            )}

            {undoToast && createPortal(
                <div className="fixed bottom-6 right-6 z-[70] max-w-sm">
                    <div
                        className={`px-4 py-3 rounded-lg shadow-lg border flex items-start gap-3 ${
                            undoToast.kind === 'success'
                                ? 'bg-green-50 dark:bg-green-900/40 border-green-300 dark:border-green-700 text-green-800 dark:text-green-200'
                                : 'bg-red-50 dark:bg-red-900/40 border-red-300 dark:border-red-700 text-red-800 dark:text-red-200'
                        }`}
                    >
                        <span className="text-sm font-medium flex-1">{undoToast.message}</span>
                        <button
                            onClick={() => setUndoToast(null)}
                            className="text-sm opacity-70 hover:opacity-100"
                            aria-label="Dismiss"
                        >
                            ✕
                        </button>
                    </div>
                </div>,
                document.body
            )}
        </>
    );

    if (loading) {
        return (
            <div className="text-center py-12">
                <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-accent-500 mb-4"></div>
                <p className={isHub ? 'text-ink-3 font-medium' : 'text-gray-600 dark:text-slate-400 font-medium'}>
                    Loading {isHub ? 'changes' : 'events'}…
                </p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="bg-red-50 dark:bg-red-900/30 border-l-4 border-red-500 text-red-700 dark:text-red-200 px-6 py-4 rounded-lg shadow-sm">
                <div className="flex items-center">
                    <span className="text-xl mr-3">⚠️</span>
                    <div>
                        <p className="font-semibold">Error loading events</p>
                        <p className="text-sm mt-1">{error}</p>
                    </div>
                </div>
            </div>
        );
    }

    if (isHub) {
        return (
            <>
                <HubChangeLog
                    events={events}
                    expandedPayload={expandedPayload}
                    togglePayload={togglePayload}
                    setUndoTarget={setUndoTarget}
                />
                {undoPortal}
            </>
        );
    }

    return (
        <>
            <div className="flex-1 min-h-0 flex flex-col overflow-hidden gap-1.5">
                <div className="job-log-table-frame flex-1 min-h-0 flex flex-col">
                    <div className="job-log-table-scroll overflow-auto flex-1 min-h-0">
                        <table className="job-log-table">
                            <thead className="sticky top-0 z-10">
                                <tr>
                                    <th style={{ width: '13%' }} className="px-2 py-1.5 text-center text-jl-head font-bold text-ink bg-head-bg leading-tight">Date</th>
                                    <th style={{ width: '10%' }} className="px-2 py-1.5 text-center text-jl-head font-bold text-ink bg-head-bg leading-tight">Source</th>
                                    <th style={{ width: '9%' }} className="px-2 py-1.5 text-center text-jl-head font-bold text-ink bg-head-bg leading-tight">User</th>
                                    <th style={{ width: '9%' }} className="px-2 py-1.5 text-center text-jl-head font-bold text-ink bg-head-bg leading-tight">Identifier</th>
                                    <th style={{ width: '15%' }} className="px-2 py-1.5 text-center text-jl-head font-bold text-ink bg-head-bg leading-tight">Action</th>
                                    <th style={{ width: '36%' }} className="px-2 py-1.5 text-center text-jl-head font-bold text-ink bg-head-bg leading-tight">Payload</th>
                                    <th style={{ width: '8%' }} className="px-2 py-1.5 text-center text-jl-head font-bold text-ink bg-head-bg leading-tight">Undo</th>
                                </tr>
                            </thead>
                            <tbody>
                                {events.length === 0 ? (
                                    <tr>
                                        <td colSpan="7" className="px-6 py-12 text-center bg-surface">
                                            <div className="text-gray-400 dark:text-slate-500 text-4xl mb-3">📭</div>
                                            <p className="text-gray-500 dark:text-slate-400 font-medium">No events found</p>
                                        </td>
                                    </tr>
                                ) : (
                                    events.map((event, index) => {
                                        const uniqueKey = `${event.type}-${event.id}`;
                                        const bandClass = index % 2 === 0 ? 'jl-band-a' : 'jl-band-b';
                                        return (
                                            <tr
                                                key={uniqueKey}
                                                className={`jl-row ${bandClass}`}
                                            >
                                                <td className="px-2 py-1.5 whitespace-nowrap text-jl font-mono text-center text-ink-2">
                                                    {formatDateTime(event.created_at)}
                                                </td>
                                                <td className="px-2 py-1.5 whitespace-nowrap text-center">
                                                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-jl-2 font-semibold ${getSourceColor(event.source)}`}>
                                                        {event.source}
                                                    </span>
                                                    {isUndoEvent(event) && (
                                                        <span
                                                            className="ml-1.5 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-100 dark:bg-amber-900/50 text-amber-800 dark:text-amber-200 border border-amber-300 dark:border-amber-700"
                                                            title="Undo event"
                                                        >
                                                            ↶ undo
                                                        </span>
                                                    )}
                                                </td>
                                                <td className="px-2 py-1.5 whitespace-nowrap text-jl text-center text-ink-2">
                                                    {event.user_name || '—'}
                                                </td>
                                                <td className="px-2 py-1.5 whitespace-nowrap text-jl font-mono text-center text-ink">
                                                    {event.type === 'job'
                                                        ? `${event.job}-${event.release || 'N/A'}`
                                                        : event.submittal_id || 'N/A'
                                                    }
                                                </td>
                                                <td className="px-2 py-1.5 whitespace-nowrap text-jl font-medium text-center text-ink">
                                                    {event.action}
                                                </td>
                                                <td className="px-2 py-1.5 text-jl">
                                                    {expandedPayload[uniqueKey] ? (
                                                        <div className="space-y-1.5">
                                                            <pre className="bg-surface-2 p-2 rounded text-jl-2 font-mono overflow-x-auto max-w-md border border-hairline text-ink">
                                                                {formatPayload(event.payload)}
                                                            </pre>
                                                            <button
                                                                onClick={() => togglePayload(uniqueKey)}
                                                                className="text-jl-2 text-brand hover:underline font-medium"
                                                            >
                                                                ▲ Collapse
                                                            </button>
                                                        </div>
                                                    ) : (
                                                        <button
                                                            onClick={() => togglePayload(uniqueKey)}
                                                            className="text-jl-2 text-brand hover:underline font-medium"
                                                        >
                                                            ▼ View Payload
                                                        </button>
                                                    )}
                                                </td>
                                                <td className="px-2 py-1.5 whitespace-nowrap text-jl text-center">
                                                    {(() => {
                                                        const { canUndo, reason } = getUndoEligibility(event);
                                                        return (
                                                            <button
                                                                onClick={() => canUndo && setUndoTarget(event)}
                                                                disabled={!canUndo}
                                                                title={canUndo ? 'Revert this change' : reason}
                                                                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-jl-2 font-semibold border transition-colors ${
                                                                    canUndo
                                                                        ? 'bg-white dark:bg-slate-700 text-accent-700 dark:text-accent-300 border-accent-300 dark:border-accent-700 hover:bg-accent-50 dark:hover:bg-slate-600 cursor-pointer'
                                                                        : 'bg-gray-50 dark:bg-slate-800 text-gray-400 dark:text-slate-500 border-gray-200 dark:border-slate-700 cursor-not-allowed'
                                                                }`}
                                                            >
                                                                ↶ Undo
                                                            </button>
                                                        );
                                                    })()}
                                                </td>
                                            </tr>
                                        );
                                    })
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
                <div className="flex items-center gap-2 text-xs font-semibold text-gray-700 dark:text-slate-200 flex-shrink-0">
                    <span>
                        Total: <span className="text-gray-900 dark:text-slate-100 font-bold">{events.length}</span> events
                    </span>
                </div>
            </div>
            {undoPortal}
        </>
    );
}

export default EventsList;
