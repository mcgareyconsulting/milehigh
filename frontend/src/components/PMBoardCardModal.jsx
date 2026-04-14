/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Shows a color-coded detail modal for a single release card on the PM Kanban board with links to events.
 * exports:
 *   PMBoardCardModal: Portal modal displaying release fields styled by stage color
 * imports_from: [react, react-dom, react-router-dom]
 * imported_by: [frontend/src/components/PMBoardList.jsx]
 * invariants:
 *   - Falls back to a default blue stage color when stageColor prop is not provided
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import React from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';

const RELEASE_FIELDS = [
    { key: 'Job #', label: 'Job #' },
    { key: 'Release #', label: 'Release #' },
    { key: 'Job', label: 'Project' },
    { key: 'Description', label: 'Description' },
    { key: 'Stage', label: 'Stage' },
    { key: 'Fab Order', label: 'Fab Order' },
    { key: 'PM', label: 'PM' },
    { key: 'BY', label: 'BY' },
    { key: 'Released', label: 'Released', format: 'date' },
    { key: 'Fab Hrs', label: 'Fab Hrs' },
    { key: 'Install HRS', label: 'Install HRS' },
    { key: 'Paint color', label: 'Paint color' },
    { key: 'Start install', label: 'Start install', format: 'date' },
    { key: 'Comp. ETA', label: 'Comp. ETA', format: 'date' },
    { key: 'Job Comp', label: 'Install Prog' },
    { key: 'Invoiced', label: 'Invoiced' },
    { key: 'Urgency', label: 'Urgency' },
    { key: 'Notes', label: 'Notes' },
];

const DEFAULT_STAGE_COLOR = {
    light: 'rgb(219 234 254)',
    base: 'rgb(59 130 246)',
    text: 'rgb(30 64 175)',
    border: 'rgb(147 197 253)',
};

export function PMBoardCardModal({ isOpen, onClose, job, stageColor }) {
    const navigate = useNavigate();
    const colors = stageColor || DEFAULT_STAGE_COLOR;

    if (!isOpen || !job) return null;

    const jobNumber = job['Job #'] || job.job;
    const releaseNumber = job['Release #'] || job.release;

    const formatDate = (val) => {
        if (!val) return '—';
        try {
            const d = new Date(val);
            if (isNaN(d.getTime())) return val;
            return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        } catch (e) {
            return val;
        }
    };

    const formatValue = (field, value) => {
        if (value == null || value === '') return '—';
        if (field.format === 'date') return formatDate(value);
        return String(value);
    };

    const handleEventsClick = () => {
        if (jobNumber && releaseNumber) {
            navigate(`/events?job=${jobNumber}&release=${releaseNumber}`);
            onClose();
        }
    };

    const modalContent = (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
            onClick={onClose}
        >
            <div
                className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] flex flex-col overflow-hidden"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header accent */}
                <div
                    className="flex-shrink-0 rounded-t-xl px-6 pt-4 pb-3"
                    style={{ backgroundColor: colors.base }}
                >
                    <div className="flex items-start justify-between gap-3">
                        <h2 className="text-xl font-bold text-white">
                            {job['Job'] || 'Untitled'} ({jobNumber}-{releaseNumber})
                        </h2>
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

                {/* Main content - default styling */}
                <div className="flex-1 overflow-y-auto px-6 pb-6 space-y-6 bg-white dark:bg-slate-800">
                    {/* Labels row */}
                    <div className="flex flex-wrap gap-2">
                        {job['Stage'] && (
                            <span
                                className="px-2 py-0.5 rounded text-xs font-medium"
                                style={{ backgroundColor: colors.base, color: 'white' }}
                            >
                                {job['Stage']}
                            </span>
                        )}
                        {job['Urgency'] && (
                            <span className="px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800 dark:bg-slate-700 dark:text-slate-200">
                                {job['Urgency']}
                            </span>
                        )}
                        {job['Fab Order'] != null && job['Fab Order'] !== '' && (
                            <span className="px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800 dark:bg-slate-700 dark:text-slate-200">
                                Fab #{job['Fab Order']}
                            </span>
                        )}
                    </div>

                    {/* Description */}
                    {job['Description'] && (
                        <div>
                            <h3 className="text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wide mb-1">Description</h3>
                            <p className="text-sm text-gray-800 dark:text-slate-200 whitespace-pre-wrap">{job['Description']}</p>
                        </div>
                    )}

                    {/* Details grid */}
                    <div>
                        <h3 className="text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wide mb-3">Details</h3>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3">
                            {RELEASE_FIELDS.filter(f => f.key !== 'Description' && job[f.key] != null && job[f.key] !== '').map(({ key, label, format }) => (
                                <div key={key} className="flex flex-col">
                                    <span className="text-xs text-gray-500 dark:text-slate-400">{label}</span>
                                    <span className="text-sm font-medium text-gray-900 dark:text-slate-100">
                                        {formatValue({ format }, job[key])}
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Notes */}
                    {job['Notes'] && (
                        <div>
                            <h3 className="text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wide mb-1">Notes</h3>
                            <p className="text-sm text-gray-800 dark:text-slate-200 whitespace-pre-wrap">{job['Notes']}</p>
                        </div>
                    )}
                </div>

                {/* Footer accent */}
                <div
                    className="flex-shrink-0 flex gap-3 px-6 py-4"
                    style={{ backgroundColor: colors.base }}
                >
                    {jobNumber && releaseNumber && (
                        <button
                            onClick={handleEventsClick}
                            className="px-4 py-2 bg-white text-gray-900 rounded-lg text-sm font-medium hover:bg-gray-100 transition-colors"
                        >
                            View Events
                        </button>
                    )}
                    {job.trello_card_id && (
                        <a
                            href={`https://trello.com/c/${job.trello_card_id}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="px-4 py-2 bg-white text-gray-900 rounded-lg text-sm font-medium hover:bg-gray-100 transition-colors"
                        >
                            Open in Trello
                        </a>
                    )}
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
