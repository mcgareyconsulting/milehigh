/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Displays a filterable audit trail of job and submittal events so admins can investigate what changed and when.
 * exports:
 *   Events: Page component rendering event table with date, source, user, and identifier filters
 * imports_from: [react, react-router-dom, axios, ../utils/api]
 * imported_by: [App.jsx]
 * invariants:
 *   - URL search params (submittal_id, job, release) pre-populate filters on mount and sync bidirectionally
 *   - Payload expansion is tracked per-event using a composite key of type + id
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
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

// SubmittalEvents (DWL) undo: action is always 'updated' and the operation is
// keyed by which whitelisted field appears in the payload. The Procore-bound
// `status` is intentionally excluded.
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

// Identify the DWL field this event targets, if any. Returns the field name or null.
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

// Returns { canUndo, reason } for the row. `reason` populates the disabled-state tooltip.
function getUndoEligibility(event) {
    const payload = event.payload || {};

    // Undo events themselves aren't undoable, regardless of type.
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

function Events() {
    const [searchParams, setSearchParams] = useSearchParams();
    const [events, setEvents] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [selectedDate, setSelectedDate] = useState('');
    const [availableDates, setAvailableDates] = useState([]);
    const [selectedSource, setSelectedSource] = useState('');
    const [availableSources, setAvailableSources] = useState([]);
    const [selectedUser, setSelectedUser] = useState('');
    const [availableUsers, setAvailableUsers] = useState([]);
    const [limit, setLimit] = useState(50);
    const [expandedPayload, setExpandedPayload] = useState({});
    const [submittalId, setSubmittalId] = useState(searchParams.get('submittal_id') || '');
    const [jobFilter, setJobFilter] = useState(searchParams.get('job') || '');
    const [releaseFilter, setReleaseFilter] = useState(searchParams.get('release') || '');
    const [undoTarget, setUndoTarget] = useState(null);
    const [undoSubmitting, setUndoSubmitting] = useState(false);
    const [undoToast, setUndoToast] = useState(null);

    useEffect(() => {
        // Update filters from URL params
        const urlSubmittalId = searchParams.get('submittal_id') || '';
        const urlJob = searchParams.get('job') || '';
        const urlRelease = searchParams.get('release') || '';
        setSubmittalId(urlSubmittalId);
        setJobFilter(urlJob);
        setReleaseFilter(urlRelease);
    }, [searchParams]);

    useEffect(() => {
        fetchFilters();
    }, []);

    useEffect(() => {
        fetchEvents();
    }, [selectedDate, limit, selectedSource, submittalId, jobFilter, releaseFilter, selectedUser]);

    const fetchFilters = async () => {
        try {
            const response = await axios.get(`${API_BASE_URL}/brain/events/filters`);
            const dates = [...new Set(
                response.data.dates
            )].sort().reverse();
            setAvailableDates(dates);
            const sources = response.data.sources;
            setAvailableSources(sources);
            setAvailableUsers(response.data.users || []);
        } catch (err) {
            console.error('Error fetching filters:', err);
        }
    }

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

    const formatDateTime = (dateString) => {
        if (!dateString) return '—';
        return new Date(dateString).toLocaleString();
    };

    const formatPayload = (payload) => {
        if (!payload) return '—';
        if (typeof payload === 'string') {
            try {
                payload = JSON.parse(payload);
            } catch {
                return payload;
            }
        }
        return JSON.stringify(payload, null, 2);
    };

    const togglePayload = (eventId) => {
        setExpandedPayload(prev => ({
            ...prev,
            [eventId]: !prev[eventId]
        }));
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

    const formatUserDisplay = (event) => event.user_name || '—';

    const resetFilters = () => {
        setSelectedDate('');
        setSelectedSource('');
        setSelectedUser('');
        setLimit(50);
        setSubmittalId('');
        setJobFilter('');
        setReleaseFilter('');
        // Clear all filters from URL
        const newParams = new URLSearchParams(searchParams);
        newParams.delete('submittal_id');
        newParams.delete('job');
        newParams.delete('release');
        setSearchParams(newParams);
    };

    const clearSubmittalIdFilter = () => {
        setSubmittalId('');
        const newParams = new URLSearchParams(searchParams);
        newParams.delete('submittal_id');
        setSearchParams(newParams);
    };

    // An undo event is identified by the `undone_event_id` field in its payload
    // (set by the /brain/events/<id>/undo endpoint). Source stays as 'Brain' so
    // undos still roll up under the normal Brain source filter.
    const isUndoEvent = (event) => event?.payload?.undone_event_id != null;

    const formatPayloadValue = (action, value) => {
        if (value === null || value === undefined || value === '') return '∅';
        return String(value);
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

    const clearJobReleaseFilter = () => {
        setJobFilter('');
        setReleaseFilter('');
        const newParams = new URLSearchParams(searchParams);
        newParams.delete('job');
        newParams.delete('release');
        setSearchParams(newParams);
    };

    return (
        <div className="w-full h-full flex flex-col bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50 dark:from-slate-900 dark:via-slate-800 dark:to-slate-900" style={{ width: '100%', minWidth: '100%' }}>
            <div className="flex-1 min-h-0 max-w-full mx-auto w-full py-2 px-2 flex flex-col" style={{ width: '100%' }}>
                <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-xl overflow-hidden flex flex-col flex-1 min-h-0">
                    {/* Title bar - matches DWL / Job Log */}
                    <div className="flex-shrink-0 px-4 py-3 bg-gradient-to-r from-accent-500 to-accent-600">
                        <div className="flex items-center justify-between">
                            <h1 className="text-3xl font-bold text-white">Job Events</h1>
                        </div>
                    </div>

                    <div className="p-2 flex flex-col flex-1 min-h-0 space-y-2">
                        <div className="bg-gradient-to-r from-gray-50 to-accent-50 dark:from-slate-700 dark:to-slate-700 rounded-xl p-3 border border-gray-200 dark:border-slate-600 shadow-sm flex-shrink-0">
                            <div className="flex flex-wrap gap-3 items-end">
                                <div className="flex-1 min-w-[200px]">
                                    <label className="block text-sm font-semibold text-gray-700 dark:text-slate-200 mb-2">
                                        📅 Filter by Date
                                    </label>
                                    <select
                                        value={selectedDate}
                                        onChange={(e) => setSelectedDate(e.target.value)}
                                        className="w-full px-4 py-2.5 border border-gray-300 dark:border-slate-500 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent bg-white dark:bg-slate-600 dark:text-slate-100 shadow-sm transition-all"
                                    >
                                        <option value="">All Dates</option>
                                        {availableDates.map(date => (
                                            <option key={date} value={date}>{date}</option>
                                        ))}
                                    </select>
                                </div>
                                <div className="flex-1 min-w-[200px]">
                                    <label className="block text-sm font-semibold text-gray-700 dark:text-slate-200 mb-2">
                                        🔗 Filter by Source
                                    </label>
                                    <select
                                        value={selectedSource}
                                        onChange={(e) => setSelectedSource(e.target.value)}
                                        className="w-full px-4 py-2.5 border border-gray-300 dark:border-slate-500 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent bg-white dark:bg-slate-600 dark:text-slate-100 shadow-sm transition-all"
                                    >
                                        <option value="">All Sources</option>
                                        {availableSources.map(source => (
                                            <option key={source} value={source}>{source}</option>
                                        ))}
                                    </select>
                                </div>
                                <div className="flex-1 min-w-[200px]">
                                    <label className="block text-sm font-semibold text-gray-700 dark:text-slate-200 mb-2">
                                        👤 Filter by User
                                    </label>
                                    <select
                                        value={selectedUser}
                                        onChange={(e) => setSelectedUser(e.target.value)}
                                        className="w-full px-4 py-2.5 border border-gray-300 dark:border-slate-500 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent bg-white dark:bg-slate-600 dark:text-slate-100 shadow-sm transition-all"
                                    >
                                        <option value="">All Users</option>
                                        {availableUsers.map(user => (
                                            <option key={user.id} value={user.id}>{user.name}</option>
                                        ))}
                                    </select>
                                </div>
                                <div className="min-w-[150px]">
                                    <label className="block text-sm font-semibold text-gray-700 dark:text-slate-200 mb-2">
                                        🔢 Results Limit
                                    </label>
                                    <input
                                        type="number"
                                        min="1"
                                        max="200"
                                        value={limit}
                                        onChange={(e) => {
                                            const value = e.target.value;
                                            if (value === '') {
                                                setLimit(50);
                                            } else {
                                                const parsed = parseInt(value, 10);
                                                if (!isNaN(parsed)) {
                                                    setLimit(Math.max(1, Math.min(200, parsed)));
                                                }
                                            }
                                        }}
                                        className="w-full px-4 py-2.5 border border-gray-300 dark:border-slate-500 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent bg-white dark:bg-slate-600 dark:text-slate-100 shadow-sm transition-all"
                                    />
                                </div>
                                <div className="flex items-end">
                                    <button
                                        onClick={resetFilters}
                                        className="px-6 py-2.5 bg-gray-200 dark:bg-slate-600 hover:bg-gray-300 dark:hover:bg-slate-500 text-gray-700 dark:text-slate-200 font-semibold rounded-lg text-sm transition-colors duration-150 shadow-sm hover:shadow border border-gray-300 dark:border-slate-500 flex items-center gap-2"
                                    >
                                        <span>🔄</span>
                                        Reset Filters
                                    </button>
                                </div>
                            </div>
                            {submittalId && (
                                <div className="mt-2 bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800 rounded-lg px-3 py-2 flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                        <span className="text-blue-700 dark:text-blue-300 font-semibold">Filtered by Submittal ID:</span>
                                        <span className="text-blue-900 dark:text-blue-100 font-mono text-sm">{submittalId}</span>
                                    </div>
                                    <button
                                        onClick={clearSubmittalIdFilter}
                                        className="text-blue-700 dark:text-blue-300 hover:text-blue-900 dark:hover:text-blue-100 font-medium text-sm underline"
                                    >
                                        Clear
                                    </button>
                                </div>
                            )}
                            {(jobFilter || releaseFilter) && (
                                <div className="mt-2 bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 rounded-lg px-3 py-2 flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                        <span className="text-green-700 dark:text-green-300 font-semibold">Filtered by Job:</span>
                                        <span className="text-green-900 dark:text-green-100 font-mono text-sm">
                                            {jobFilter}{releaseFilter ? `-${releaseFilter}` : ''}
                                        </span>
                                    </div>
                                    <button
                                        onClick={clearJobReleaseFilter}
                                        className="text-green-700 dark:text-green-300 hover:text-green-900 dark:hover:text-green-100 font-medium text-sm underline"
                                    >
                                        Clear
                                    </button>
                                </div>
                            )}
                        </div>

                        {loading && (
                            <div className="text-center py-12">
                                <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-accent-500 mb-4"></div>
                                <p className="text-gray-600 dark:text-slate-400 font-medium">Loading events...</p>
                            </div>
                        )}
                        {error && (
                            <div className="bg-red-50 dark:bg-red-900/30 border-l-4 border-red-500 text-red-700 dark:text-red-200 px-6 py-4 rounded-lg mb-6 shadow-sm">
                                <div className="flex items-center">
                                    <span className="text-xl mr-3">⚠️</span>
                                    <div>
                                        <p className="font-semibold">Error loading events</p>
                                        <p className="text-sm mt-1">{error}</p>
                                    </div>
                                </div>
                            </div>
                        )}

                        {!loading && !error && (
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
                                                                    {formatUserDisplay(event)}
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
                        )}
                    </div>
                </div>
            </div>

            {undoTarget && (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
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
                            // Build the list of linked reverts to show. For job events, this
                            // comes from `linked_children` (events stamped with parent_event_id).
                            // For DWL step events, it comes from `payload.swapped_with` —
                            // the step route embeds the neighbor's change in the parent payload
                            // rather than emitting a separate event.
                            const items = [];
                            if (undoTarget.linked_children && undoTarget.linked_children.length > 0) {
                                for (const c of undoTarget.linked_children) {
                                    items.push({
                                        key: `child-${c.id}`,
                                        label: UNDO_ACTION_LABEL[c.action] || c.action,
                                        from: c.to,    // displayed reversed (revert direction)
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
                            {undoTarget.type === 'submittal'
                                ? 'Reverts the database value only — no Procore update is sent.'
                                : 'Undo reverts this row only. Cascaded changes outside this row (scheduling for other releases, other rows in the same stash session) are not rolled back.'}
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
                </div>
            )}

            {undoToast && (
                <div className="fixed bottom-6 right-6 z-50 max-w-sm">
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
                </div>
            )}
        </div>
    );
}

export default Events;
