/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Detail modal for a vendor pick-up card on the PM Board — shows the assignees and the forwarded vendor email chain as the card description.
 * exports:
 *   PickupCardModal: Portal modal displaying a PickupOrder's identity, assignees, email metadata, and full forwarded body.
 * imports_from: [react, react-dom]
 * imported_by: [frontend/src/components/PMBoardList.jsx]
 * invariants:
 *   - The "Description" section renders pickup.email_body verbatim (whitespace preserved) — the forwarded email chain.
 *   - Closes on backdrop click or the X / Close buttons; renders nothing when no pickup is selected.
 */
import React from 'react';
import { createPortal } from 'react-dom';

const ACCENT = 'rgb(245 158 11)'; // amber — matches the PU card on the board

const CHIP_PALETTE = [
    'rgb(59 130 246)', 'rgb(16 185 129)', 'rgb(245 158 11)',
    'rgb(139 92 246)', 'rgb(236 72 153)', 'rgb(20 184 166)',
];
const chipColor = (key) => {
    let h = 0;
    for (let i = 0; i < (key || '').length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
    return CHIP_PALETTE[h % CHIP_PALETTE.length];
};

const formatDateTime = (val) => {
    if (!val) return '—';
    try {
        const d = new Date(val);
        if (isNaN(d.getTime())) return val;
        return d.toLocaleString('en-US', {
            month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
        });
    } catch {
        return val;
    }
};

export function PickupCardModal({ isOpen, onClose, pickup }) {
    if (!isOpen || !pickup) return null;

    const assignees = pickup.assignees || [];

    const modalContent = (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" onClick={onClose}>
            <div
                className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] flex flex-col overflow-hidden"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="flex-shrink-0 rounded-t-xl px-6 pt-4 pb-3" style={{ backgroundColor: ACCENT }}>
                    <div className="flex items-start justify-between gap-3">
                        <div>
                            <div className="flex items-center gap-2">
                                <span className="bg-white/25 text-white text-[10px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wide">
                                    Pick-Up
                                </span>
                                <h2 className="text-xl font-bold text-white">
                                    {pickup.vendor}: {pickup.job}-{pickup.release}
                                </h2>
                            </div>
                            {pickup.job_name && (
                                <p className="text-white/90 text-sm mt-0.5">{pickup.job_name}</p>
                            )}
                        </div>
                        <button
                            onClick={onClose}
                            className="p-1 rounded text-white/80 hover:text-white transition-colors"
                            aria-label="Close"
                        >
                            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                        </button>
                    </div>
                </div>

                {/* Body */}
                <div className="flex-1 overflow-y-auto px-6 pb-6 pt-4 space-y-5 bg-white dark:bg-slate-800">
                    {/* Assignees */}
                    {assignees.length > 0 && (
                        <div>
                            <h3 className="text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wide mb-2">Members</h3>
                            <div className="flex flex-wrap gap-2">
                                {assignees.map((a) => (
                                    <span key={a.username} className="flex items-center gap-1.5 bg-gray-100 dark:bg-slate-700 rounded-full pl-1 pr-2.5 py-0.5">
                                        <span
                                            className="inline-flex items-center justify-center w-5 h-5 rounded-full text-[9px] font-bold text-white"
                                            style={{ backgroundColor: chipColor(a.initials) }}
                                        >
                                            {a.initials}
                                        </span>
                                        <span className="text-xs font-medium text-gray-800 dark:text-slate-200">{a.name}</span>
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Email metadata */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2">
                        {pickup.email_from && (
                            <div className="flex flex-col">
                                <span className="text-xs text-gray-500 dark:text-slate-400">From</span>
                                <span className="text-sm font-medium text-gray-900 dark:text-slate-100 break-all">{pickup.email_from}</span>
                            </div>
                        )}
                        <div className="flex flex-col">
                            <span className="text-xs text-gray-500 dark:text-slate-400">Received</span>
                            <span className="text-sm font-medium text-gray-900 dark:text-slate-100">{formatDateTime(pickup.email_received_at)}</span>
                        </div>
                        {pickup.email_subject && (
                            <div className="flex flex-col sm:col-span-2">
                                <span className="text-xs text-gray-500 dark:text-slate-400">Subject</span>
                                <span className="text-sm font-medium text-gray-900 dark:text-slate-100">{pickup.email_subject}</span>
                            </div>
                        )}
                    </div>

                    {/* Description = the forwarded email chain */}
                    <div>
                        <h3 className="text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wide mb-1">Description</h3>
                        {pickup.email_body ? (
                            <pre className="text-sm text-gray-800 dark:text-slate-200 whitespace-pre-wrap font-sans bg-gray-50 dark:bg-slate-900/40 border border-gray-200 dark:border-slate-700 rounded-lg p-3 max-h-[40vh] overflow-y-auto">
                                {pickup.email_body}
                            </pre>
                        ) : (
                            <p className="text-sm text-gray-400 dark:text-slate-500 italic">No email body</p>
                        )}
                    </div>
                </div>

                {/* Footer */}
                <div className="flex-shrink-0 flex px-6 py-4" style={{ backgroundColor: ACCENT }}>
                    <button
                        onClick={onClose}
                        className="px-4 py-2 rounded-lg text-sm font-medium hover:opacity-90 transition-opacity ml-auto bg-white/20 text-white hover:bg-white/30"
                    >
                        Close
                    </button>
                </div>
            </div>
        </div>
    );

    return createPortal(modalContent, document.body);
}

export default PickupCardModal;
