/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Read-only modal showing the edit history of the Notes field for a single job/release, sourced from /brain/events.
 * exports:
 *   NotesHistoryModal: Portal modal displaying reverse-chronological update_notes events
 * imports_from: [react, react-dom, ../services/jobsApi]
 * imported_by: [frontend/src/components/JobsTableRow.jsx]
 * invariants:
 *   - Renders via createPortal to document.body to escape table overflow clipping
 *   - Filters events client-side to action === 'update_notes' and drops payloads where from === to
 * updated_by_agent: 2026-04-27T00:00:00Z
 */
import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { jobsApi } from '../services/jobsApi';

export function NotesHistoryModal({ isOpen, onClose, job, release, currentNotes }) {
    const [events, setEvents] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (!isOpen || job == null || !release) return;

        let cancelled = false;
        setLoading(true);
        setError(null);

        jobsApi.getNotesHistory(job, release, 200)
            .then((data) => {
                if (cancelled) return;
                const all = Array.isArray(data?.events) ? data.events : [];
                const filtered = all.filter((ev) => {
                    if (ev.action !== 'update_notes') return false;
                    const p = ev.payload || {};
                    return p.from !== p.to;
                });
                setEvents(filtered);
            })
            .catch((err) => {
                if (cancelled) return;
                setError(err.message || 'Failed to load notes history');
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });

        return () => { cancelled = true; };
    }, [isOpen, job, release]);

    useEffect(() => {
        if (!isOpen) return;
        const onKey = (e) => {
            if (e.key === 'Escape') onClose();
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [isOpen, onClose]);

    if (!isOpen) return null;

    const renderValue = (val) => {
        if (val === null || val === undefined || val === '') {
            return <span className="italic text-gray-400 dark:text-slate-500">(empty)</span>;
        }
        return val;
    };

    // Anchor the list with the live cell value. If the most recent event already
    // matches it, the events feed is in sync — no synthetic entry needed.
    // Otherwise prepend a "Current" item so users always see today's note,
    // including for releases whose history predates event tracking.
    const normalizedCurrent = (currentNotes ?? '').toString();
    const latestTo = (events[0]?.payload?.to ?? '').toString();
    const showCurrentSynthetic = normalizedCurrent !== '' && normalizedCurrent !== latestTo;
    const displayItems = showCurrentSynthetic
        ? [{ id: 'current', synthetic: true, value: currentNotes }, ...events]
        : events;

    const modalContent = (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 transition-opacity"
            onClick={onClose}
        >
            <div
                className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl max-w-lg w-full mx-4 max-h-[80vh] flex flex-col transform transition-all"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-6 py-4 rounded-t-xl">
                    <div className="flex items-center justify-between">
                        <h2 className="text-xl font-bold text-white">Notes History</h2>
                        <button
                            onClick={onClose}
                            className="text-white hover:text-gray-200 dark:hover:text-slate-200 transition-colors text-2xl font-bold leading-none"
                            aria-label="Close"
                        >
                            ×
                        </button>
                    </div>
                    <p className="text-sm text-white text-opacity-90 mt-1">
                        Job {job} — Release {release}
                    </p>
                </div>

                <div className="p-6 overflow-y-auto flex-1">
                    {loading && (
                        <p className="text-sm text-gray-500 dark:text-slate-400 italic">
                            Loading…
                        </p>
                    )}
                    {error && !loading && (
                        <p className="text-sm text-red-600 dark:text-red-400">
                            {error}
                        </p>
                    )}
                    {!loading && !error && displayItems.length === 0 && (
                        <p className="text-sm text-gray-500 dark:text-slate-400 italic">
                            No prior notes for this release.
                        </p>
                    )}
                    {!loading && !error && displayItems.length > 0 && (
                        <ul className="space-y-4">
                            {displayItems.map((item) => {
                                if (item.synthetic) {
                                    return (
                                        <li
                                            key={item.id}
                                            className="border-l-2 border-accent-500 pl-3"
                                        >
                                            <div className="flex flex-wrap items-baseline gap-x-2 mb-1">
                                                <span className="text-xs font-semibold text-gray-700 dark:text-slate-200">
                                                    Current
                                                </span>
                                            </div>
                                            <p className="text-sm text-gray-900 dark:text-slate-100 whitespace-pre-wrap break-words">
                                                {renderValue(item.value)}
                                            </p>
                                        </li>
                                    );
                                }
                                const p = item.payload || {};
                                return (
                                    <li
                                        key={item.id}
                                        className="border-l-2 border-accent-500 pl-3"
                                    >
                                        <div className="flex flex-wrap items-baseline gap-x-2 mb-1">
                                            <span className="text-xs font-semibold text-gray-700 dark:text-slate-200">
                                                {item.created_at}
                                            </span>
                                            <span className="text-xs text-gray-500 dark:text-slate-400">
                                                {item.source || '—'}
                                            </span>
                                        </div>
                                        <p className="text-sm text-gray-900 dark:text-slate-100 whitespace-pre-wrap break-words">
                                            {renderValue(p.to)}
                                        </p>
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </div>

                <div className="bg-gray-50 dark:bg-slate-700 px-6 py-4 rounded-b-xl border-t border-gray-200 dark:border-slate-600">
                    <button
                        onClick={onClose}
                        className="w-full px-4 py-2 bg-gray-200 dark:bg-slate-600 text-gray-700 dark:text-slate-200 rounded-lg font-medium hover:bg-gray-300 dark:hover:bg-slate-500 transition-colors"
                    >
                        Close
                    </button>
                </div>
            </div>
        </div>
    );

    return createPortal(modalContent, document.body);
}
