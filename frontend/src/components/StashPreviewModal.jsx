/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Preview the queued edits for a stash session before they are applied as a batch, with conflict indicators and per-row remove controls.
 * exports:
 *   StashPreviewModal: Modal dialog that fetches /brain/stash-sessions/<id>/preview and exposes Apply / Discard / Close.
 * imports_from: [react, ../services/jobsApi]
 * imported_by: [../pages/JobLog.jsx]
 * invariants:
 *   - Conflict rows are flagged but still applyable; server-side apply skips them with a diagnostic.
 *   - Apply and Discard are single-shot; the modal disables its buttons while a request is in flight.
 */
import React, { useEffect, useState, useCallback } from 'react';
import { jobsApi } from '../services/jobsApi';

const FIELD_LABEL = {
    stage: 'Stage',
    fab_order: 'Fab Order',
    notes: 'Notes',
    job_comp: 'Job Comp',
    invoiced: 'Invoiced',
    start_install: 'Start Install',
};

function formatValue(field, value) {
    if (value === null || value === undefined) return <span className="text-gray-400">—</span>;
    if (field === 'start_install') {
        if (typeof value === 'object') {
            if (value.action === 'clear') return <em className="text-gray-500">clear hard date</em>;
            if (value.date) return value.date;
            return <span className="text-gray-400">—</span>;
        }
        return String(value);
    }
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
}

export default function StashPreviewModal({ sessionId, onClose, onApply, onDiscard, onRemove }) {
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [data, setData] = useState(null);
    const [inFlight, setInFlight] = useState(false);
    const [applySummary, setApplySummary] = useState(null);
    const [confirmPending, setConfirmPending] = useState(null); // 'apply' | 'discard' | null

    const refresh = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const d = await jobsApi.getStashPreview(sessionId);
            setData(d);
        } catch (err) {
            setError(err.message || 'Failed to load preview');
        } finally {
            setLoading(false);
        }
    }, [sessionId]);

    useEffect(() => {
        refresh();
    }, [refresh]);

    const handleRemove = async (changeId) => {
        try {
            await onRemove(changeId);
            await refresh();
        } catch (err) {
            alert(err.message || 'Failed to remove change');
        }
    };

    const handleApply = async () => {
        setInFlight(true);
        try {
            const result = await onApply();
            setApplySummary(result?.summary || null);
        } catch (err) {
            alert(err.message || 'Failed to apply');
        } finally {
            setInFlight(false);
        }
    };

    const handleDiscard = async () => {
        setInFlight(true);
        try {
            await onDiscard();
        } catch (err) {
            alert(err.message || 'Failed to discard');
            setInFlight(false);
        }
    };

    const changes = data?.changes || [];
    const conflicts = changes.filter(c => c.conflict).length;

    return (
        <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 overflow-y-auto">
            <div className="bg-white dark:bg-slate-800 rounded-lg shadow-xl w-full max-w-5xl mt-8">
                <div className="px-5 py-3 border-b border-gray-200 dark:border-slate-600 flex items-center justify-between">
                    <div>
                        <h2 className="text-base font-semibold text-gray-900 dark:text-slate-100">
                            Review Session Preview
                        </h2>
                        <p className="text-xs text-gray-500 dark:text-slate-400">
                            {changes.length} queued change{changes.length === 1 ? '' : 's'}
                            {conflicts > 0 && (
                                <span className="ml-2 text-amber-600 dark:text-amber-400 font-medium">
                                    ({conflicts} conflict{conflicts === 1 ? '' : 's'})
                                </span>
                            )}
                        </p>
                    </div>
                    <button
                        onClick={onClose}
                        disabled={inFlight}
                        className="text-gray-500 hover:text-gray-700 dark:text-slate-400 dark:hover:text-slate-200 text-2xl leading-none disabled:opacity-50"
                    >
                        ×
                    </button>
                </div>

                <div className="p-5">
                    {loading && <div className="text-sm text-gray-500">Loading preview…</div>}
                    {error && <div className="text-sm text-red-600">{error}</div>}

                    {applySummary && (
                        <div className="mb-4 p-3 bg-emerald-50 dark:bg-emerald-900/30 border border-emerald-200 dark:border-emerald-800 rounded text-sm">
                            <strong>Apply complete.</strong>{' '}
                            applied={applySummary.applied}{' '}
                            no-op={applySummary.no_op}{' '}
                            conflicts={applySummary.conflicts}{' '}
                            failed={applySummary.failed}
                        </div>
                    )}

                    {!loading && !error && changes.length === 0 && (
                        <div className="text-sm text-gray-500">
                            No changes queued. Discard the session or close and add some edits.
                        </div>
                    )}

                    {!loading && !error && changes.length > 0 && (
                        <div className="overflow-x-auto">
                            <table className="w-full text-xs">
                                <thead className="bg-gray-100 dark:bg-slate-700">
                                    <tr>
                                        <th className="px-2 py-1 text-left font-semibold">Job</th>
                                        <th className="px-2 py-1 text-left font-semibold">Rel.</th>
                                        <th className="px-2 py-1 text-left font-semibold">Field</th>
                                        <th className="px-2 py-1 text-left font-semibold">Baseline</th>
                                        <th className="px-2 py-1 text-left font-semibold">Current</th>
                                        <th className="px-2 py-1 text-left font-semibold">New</th>
                                        <th className="px-2 py-1 text-left font-semibold">Status</th>
                                        <th className="px-2 py-1"></th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {changes.map((c) => (
                                        <tr
                                            key={c.id}
                                            className={`border-t border-gray-200 dark:border-slate-600 ${c.conflict ? 'bg-amber-50 dark:bg-amber-900/20' : ''}`}
                                        >
                                            <td className="px-2 py-1">{c.job}</td>
                                            <td className="px-2 py-1">{c.release}</td>
                                            <td className="px-2 py-1 font-medium">{FIELD_LABEL[c.field] || c.field}</td>
                                            <td className="px-2 py-1 text-gray-600 dark:text-slate-300">{formatValue(c.field, c.baseline_value)}</td>
                                            <td className="px-2 py-1 text-gray-600 dark:text-slate-300">{formatValue(c.field, c.current_value)}</td>
                                            <td className="px-2 py-1 font-semibold text-emerald-700 dark:text-emerald-400">{formatValue(c.field, c.new_value)}</td>
                                            <td className="px-2 py-1">
                                                {c.conflict ? (
                                                    <span className="inline-block px-1.5 py-0.5 text-[10px] font-semibold rounded bg-amber-200 text-amber-900">
                                                        CONFLICT
                                                    </span>
                                                ) : c.status === 'applied' ? (
                                                    <span className="inline-block px-1.5 py-0.5 text-[10px] font-semibold rounded bg-emerald-200 text-emerald-900">
                                                        applied
                                                    </span>
                                                ) : c.status === 'failed' ? (
                                                    <span className="inline-block px-1.5 py-0.5 text-[10px] font-semibold rounded bg-red-200 text-red-900" title={c.error}>
                                                        failed
                                                    </span>
                                                ) : c.status === 'no_op' ? (
                                                    <span className="inline-block px-1.5 py-0.5 text-[10px] font-semibold rounded bg-gray-200 text-gray-700">
                                                        no-op
                                                    </span>
                                                ) : (
                                                    <span className="inline-block px-1.5 py-0.5 text-[10px] font-semibold rounded bg-blue-100 text-blue-800">
                                                        pending
                                                    </span>
                                                )}
                                            </td>
                                            <td className="px-2 py-1 text-right">
                                                <button
                                                    onClick={() => handleRemove(c.id)}
                                                    disabled={inFlight || !!applySummary}
                                                    className="text-red-600 hover:underline disabled:opacity-30"
                                                    title="Remove this queued change"
                                                >
                                                    Remove
                                                </button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>

                <div className="px-5 py-3 border-t border-gray-200 dark:border-slate-600 flex items-center justify-between">
                    {confirmPending ? (
                        <div className="flex items-center gap-3 w-full">
                            <span className="text-sm text-gray-700 dark:text-slate-300">
                                {confirmPending === 'discard'
                                    ? 'Discard all queued edits?'
                                    : 'Apply all queued changes? This cannot be undone.'}
                            </span>
                            <button
                                onClick={() => {
                                    setConfirmPending(null);
                                    if (confirmPending === 'discard') handleDiscard();
                                    else handleApply();
                                }}
                                className="px-3 py-1.5 text-sm font-semibold rounded bg-red-600 text-white hover:bg-red-700"
                            >
                                Yes
                            </button>
                            <button
                                onClick={() => setConfirmPending(null)}
                                className="px-3 py-1.5 text-sm font-semibold rounded bg-gray-200 text-gray-800 hover:bg-gray-300"
                            >
                                Cancel
                            </button>
                        </div>
                    ) : (
                        <>
                            <button
                                onClick={() => setConfirmPending('discard')}
                                disabled={inFlight || !!applySummary}
                                className="px-3 py-1.5 text-sm font-semibold rounded bg-red-100 text-red-800 hover:bg-red-200 disabled:opacity-50"
                            >
                                Discard Session
                            </button>
                            <div className="flex items-center gap-2">
                                <button
                                    onClick={onClose}
                                    disabled={inFlight}
                                    className="px-3 py-1.5 text-sm font-semibold rounded bg-gray-200 text-gray-800 hover:bg-gray-300 disabled:opacity-50"
                                >
                                    {applySummary ? 'Close' : 'Back'}
                                </button>
                                {!applySummary && (
                                    <button
                                        onClick={() => setConfirmPending('apply')}
                                        disabled={inFlight || changes.length === 0}
                                        className="px-3 py-1.5 text-sm font-semibold rounded bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
                                    >
                                        {inFlight ? 'Applying…' : 'Apply All'}
                                    </button>
                                )}
                            </div>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}
