/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Reusable events table with fetch, payload expansion, and undo confirmation. Powers both the Events page and the EventsModal embedded in detail modals.
 * exports:
 *   EventsList: Self-contained events viewer that takes filter props and handles its own data fetching, rendering, and undo flow
 * imports_from: [react, axios, react-dom, ../utils/api]
 * imported_by: [frontend/src/pages/Events.jsx, frontend/src/components/EventsModal.jsx]
 * invariants:
 *   - Refetches whenever any filter prop changes
 *   - Undo POST hits /brain/events/{id}/undo for job events and /brain/submittal-events/{id}/undo for submittal events
 *   - Toast and undo-confirmation render via portal so they sit above any wrapping modal
 */
import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';

import { API_BASE_URL } from '../utils/api';

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

// Build the list of cascaded reverts shown below the primary undo line. Job events
// surface them via `linked_children`; DWL step events embed the swapped neighbor's
// change in `payload.swapped_with` rather than emitting a separate child event.
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

export function EventsList({
    submittalId = '',
    jobFilter = '',
    releaseFilter = '',
    selectedDate = '',
    selectedSource = '',
    selectedUser = '',
    limit = 50,
}) {
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
    }, [selectedDate, limit, selectedSource, submittalId, jobFilter, releaseFilter, selectedUser]);

    const fetchEvents = async () => {
        setLoading(true);
        setError(null);
        try {
            const params = { limit };
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

    if (loading) {
        return (
            <div className="text-center py-12">
                <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-accent-500 mb-4"></div>
                <p className="text-gray-600 dark:text-slate-400 font-medium">Loading events...</p>
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

    return (
        <>
            <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
                <div className="bg-white dark:bg-slate-800 rounded-xl border border-gray-200 dark:border-slate-600 shadow-sm overflow-hidden flex-1 min-h-0 flex flex-col">
                    <div className="overflow-auto flex-1 min-h-0">
                        <table className="w-full">
                            <thead className="bg-gradient-to-r from-gray-50 to-accent-50 dark:from-slate-700 dark:to-slate-700">
                                <tr>
                                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 dark:text-slate-200 uppercase tracking-wider border-b border-gray-200 dark:border-slate-600">Date</th>
                                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 dark:text-slate-200 uppercase tracking-wider border-b border-gray-200 dark:border-slate-600">Source</th>
                                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 dark:text-slate-200 uppercase tracking-wider border-b border-gray-200 dark:border-slate-600">User</th>
                                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 dark:text-slate-200 uppercase tracking-wider border-b border-gray-200 dark:border-slate-600">Identifier</th>
                                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 dark:text-slate-200 uppercase tracking-wider border-b border-gray-200 dark:border-slate-600">Action</th>
                                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 dark:text-slate-200 uppercase tracking-wider border-b border-gray-200 dark:border-slate-600">Payload</th>
                                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 dark:text-slate-200 uppercase tracking-wider border-b border-gray-200 dark:border-slate-600">Undo</th>
                                </tr>
                            </thead>
                            <tbody className="bg-white dark:bg-slate-800 divide-y divide-gray-200 dark:divide-slate-600">
                                {events.length === 0 ? (
                                    <tr>
                                        <td colSpan="7" className="px-6 py-12 text-center">
                                            <div className="text-gray-400 dark:text-slate-500 text-4xl mb-3">📭</div>
                                            <p className="text-gray-500 dark:text-slate-400 font-medium">No events found</p>
                                        </td>
                                    </tr>
                                ) : (
                                    events.map((event, index) => {
                                        const uniqueKey = `${event.type}-${event.id}`;
                                        return (
                                            <tr
                                                key={uniqueKey}
                                                className="hover:bg-accent-50/50 dark:hover:bg-slate-700/50 transition-colors duration-150"
                                                style={{ animationDelay: `${index * 50}ms` }}
                                            >
                                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-slate-300">
                                                    {formatDateTime(event.created_at)}
                                                </td>
                                                <td className="px-6 py-4 whitespace-nowrap">
                                                    <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold ${getSourceColor(event.source)}`}>
                                                        {event.source}
                                                    </span>
                                                    {isUndoEvent(event) && (
                                                        <span
                                                            className="ml-2 inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-100 dark:bg-amber-900/50 text-amber-800 dark:text-amber-200 border border-amber-300 dark:border-amber-700"
                                                            title="Undo event"
                                                        >
                                                            ↶ undo
                                                        </span>
                                                    )}
                                                </td>
                                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-slate-300">
                                                    {event.user_name || '—'}
                                                </td>
                                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-slate-300">
                                                    {event.type === 'job'
                                                        ? `${event.job}-${event.release || 'N/A'}`
                                                        : event.submittal_id || 'N/A'
                                                    }
                                                </td>
                                                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-slate-100">
                                                    {event.action}
                                                </td>
                                                <td className="px-6 py-4 text-sm">
                                                    {expandedPayload[uniqueKey] ? (
                                                        <div className="space-y-2">
                                                            <pre className="bg-gray-50 dark:bg-slate-700 p-3 rounded-lg text-xs overflow-x-auto max-w-md border border-gray-200 dark:border-slate-600 text-gray-900 dark:text-slate-200">
                                                                {formatPayload(event.payload)}
                                                            </pre>
                                                            <button
                                                                onClick={() => togglePayload(uniqueKey)}
                                                                className="text-xs text-accent-600 dark:text-accent-400 hover:text-accent-700 dark:hover:text-accent-300 font-medium"
                                                            >
                                                                ▲ Collapse
                                                            </button>
                                                        </div>
                                                    ) : (
                                                        <button
                                                            onClick={() => togglePayload(uniqueKey)}
                                                            className="text-xs text-accent-600 dark:text-accent-400 hover:text-accent-700 dark:hover:text-accent-300 font-medium"
                                                        >
                                                            ▼ View Payload
                                                        </button>
                                                    )}
                                                </td>
                                                <td className="px-6 py-4 whitespace-nowrap text-sm">
                                                    {(() => {
                                                        const { canUndo, reason } = getUndoEligibility(event);
                                                        return (
                                                            <button
                                                                onClick={() => canUndo && setUndoTarget(event)}
                                                                disabled={!canUndo}
                                                                title={canUndo ? 'Revert this change' : reason}
                                                                className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors ${
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
                <div className="flex items-center justify-between flex-shrink-0 pt-2">
                    <div className="bg-accent-50 dark:bg-accent-900/30 rounded-lg px-4 py-2 border border-accent-200 dark:border-accent-700">
                        <p className="text-sm font-semibold text-accent-700 dark:text-accent-300">
                            Total: <span className="text-accent-900 dark:text-accent-100">{events.length}</span> events
                        </p>
                    </div>
                </div>
            </div>

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
}

export default EventsList;
