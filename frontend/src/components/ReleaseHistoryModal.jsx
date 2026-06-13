/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Read-only, billing-friendly modal showing a single release's full change history and
 *   its live header data (stage, install, invoiced). Opened from the invoicing report's release rows.
 * exports:
 *   ReleaseHistoryModal: Portal modal that fetches GET /api/jobs/<job>/<release>/history and renders
 *     a clean vertical event timeline — no raw payloads, no undo.
 * imports_from: [react, react-dom, ../services/invoicingApi, ../utils/invoicingFormat]
 * imported_by: [pages/InvoicingReport.jsx]
 * invariants:
 *   - Renders via createPortal; Escape and backdrop click close only this modal.
 *   - Fetches the full (not month-bounded) history whenever the release prop changes while open.
 */
import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

import { invoicingApi } from '../services/invoicingApi';
import Badge from './Badge';
import { actionLabel, actionTint, stageTint, prettyDate, prettyTime } from '../utils/invoicingFormat';

export function ReleaseHistoryModal({ isOpen, onClose, release }) {
    const [history, setHistory] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (!isOpen) return;
        const handleKey = (e) => {
            if (e.key === 'Escape') {
                e.stopPropagation();
                onClose();
            }
        };
        document.addEventListener('keydown', handleKey);
        return () => document.removeEventListener('keydown', handleKey);
    }, [isOpen, onClose]);

    useEffect(() => {
        if (!isOpen || !release) return;
        let cancelled = false;
        setLoading(true);
        setError(null);
        invoicingApi
            .fetchReleaseHistory({ job: release.job, release: release.release })
            .then((data) => {
                if (!cancelled) setHistory(data.history || []);
            })
            .catch((err) => {
                if (!cancelled) setError(err.message);
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => { cancelled = true; };
    }, [isOpen, release]);

    if (!isOpen || !release) return null;

    const r = release;
    const label = `${r.release}${r.description ? ` — ${r.description}` : ''}`;

    const modal = (
        <div
            className="fixed inset-0 z-[55] flex items-center justify-center bg-black bg-opacity-50 p-4"
            onClick={onClose}
        >
            <div
                className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl w-full max-w-3xl h-[85vh] flex flex-col"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header — release identity + live data */}
                <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-6 py-4 rounded-t-xl flex-shrink-0">
                    <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                            <h2 className="text-xl font-bold text-white truncate" title={label}>{label}</h2>
                            {r.pm && <p className="text-sm text-white/80 mt-0.5">{r.pm}</p>}
                        </div>
                        <button
                            onClick={onClose}
                            className="text-white hover:text-gray-200 transition-colors text-2xl font-bold leading-none flex-shrink-0"
                            aria-label="Close"
                        >
                            ×
                        </button>
                    </div>
                    <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 mt-3 text-sm text-white/90">
                        {r.stage && <Badge tint={stageTint(r.stage)}>{r.stage}</Badge>}
                        {r.stage_entered_at && (
                            <span>Since <span className="font-semibold">{prettyDate(r.stage_entered_at)}</span></span>
                        )}
                        <span>Install <span className="font-semibold">{r.install_prog || '—'}</span></span>
                        <span>Invoiced <span className="font-semibold">{r.invoiced || '—'}</span></span>
                    </div>
                </div>

                {/* Body — full event timeline */}
                <div className="p-6 flex-1 min-h-0 overflow-auto">
                    {loading && (
                        <div className="text-center py-12 text-gray-500 dark:text-slate-400">Loading history…</div>
                    )}
                    {error && !loading && (
                        <div className="py-4 px-5 rounded-xl bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-200 text-base ring-1 ring-red-200/60 dark:ring-red-500/30">
                            {error}
                        </div>
                    )}
                    {!loading && !error && history.length === 0 && (
                        <p className="text-sm text-gray-400 dark:text-slate-500 italic">No change history for this release.</p>
                    )}
                    {!loading && !error && history.length > 0 && (
                        <table className="w-full text-sm border-collapse">
                            <thead>
                                <tr className="text-left text-xs uppercase tracking-wide text-gray-600 dark:text-slate-300 border-b-2 border-gray-300 dark:border-slate-600">
                                    <th className="px-3 py-2 font-semibold w-40">Change Type</th>
                                    <th className="px-3 py-2 font-semibold">Detail</th>
                                    <th className="px-3 py-2 font-semibold w-36">Date</th>
                                    <th className="px-3 py-2 font-semibold w-28">Source</th>
                                </tr>
                            </thead>
                            <tbody>
                                {history.map((ev) => (
                                    <tr key={ev.id} className="border-b border-gray-200 dark:border-slate-700 hover:bg-gray-50 dark:hover:bg-slate-700/40">
                                        <td className="px-3 py-2.5 align-top whitespace-nowrap">
                                            <Badge tint={actionTint(ev.action)}>{actionLabel(ev.action)}</Badge>
                                        </td>
                                        <td className="px-3 py-2.5 align-top text-gray-800 dark:text-slate-100 break-words">
                                            {ev.new_value || <span className="text-gray-400 dark:text-slate-500">—</span>}
                                        </td>
                                        <td className="px-3 py-2.5 align-top whitespace-nowrap text-gray-700 dark:text-slate-200">
                                            {prettyDate(ev.created_at)}
                                            <span className="block text-xs text-gray-400 dark:text-slate-500">{prettyTime(ev.created_at)}</span>
                                        </td>
                                        <td className="px-3 py-2.5 align-top whitespace-nowrap text-gray-700 dark:text-slate-200">
                                            {ev.source || '—'}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
            </div>
        </div>
    );

    return createPortal(modal, document.body);
}

export default ReleaseHistoryModal;
