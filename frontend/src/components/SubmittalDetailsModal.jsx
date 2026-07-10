/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Displays a read-only detail modal for a Procore submittal with links to events history and the Procore web UI.
 * exports:
 *   SubmittalDetailsModal: Detail modal for a single submittal record
 * imports_from: [react, react-router-dom]
 * imported_by: []
 * invariants:
 *   - Procore URL is only rendered when both projectId and submittalId are present
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';

import { EventsModal } from './EventsModal';
import { draftingWorkLoadApi } from '../services/draftingWorkLoadApi';

const DRR_TYPE = 'Drafting Release Review';

// Verdict → badge styling for inline BB findings.
const VERDICT_STYLE = {
    violation: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
    needs_field_verification: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
    ok: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
};

export function SubmittalDetailsModal({ isOpen, onClose, submittal, canEditRel = false, onRelAssigned }) {
    const [eventsOpen, setEventsOpen] = useState(false);
    const [relInput, setRelInput] = useState('');
    const [relSaving, setRelSaving] = useState(false);
    const [relError, setRelError] = useState(null);
    const [relSuccess, setRelSuccess] = useState(false);
    const [bbBusy, setBbBusy] = useState(false);
    const [bbPullOnly, setBbPullOnly] = useState(false);
    const [bbResult, setBbResult] = useState(null);
    const [bbError, setBbError] = useState(null);
    const [bbModel, setBbModel] = useState('sonnet'); // 'sonnet' = lighter/faster, 'opus' = deep

    const submittalId = (submittal?.submittal_id || submittal?.['Submittals Id'] || '');
    const isDRR = (submittal?.type ?? submittal?.['TYPE']) === DRR_TYPE;
    const currentRel = submittal?.rel ?? submittal?.['Rel'] ?? null;

    // Prefill the Rel input when the popup opens on a DRR: the current value if
    // one is set, otherwise the server-suggested next available number.
    useEffect(() => {
        if (!isOpen) {
            setRelError(null);
            setRelSuccess(false);
            setBbBusy(false);
            setBbResult(null);
            setBbError(null);
            return;
        }
        if (!isDRR || !canEditRel) return;
        setRelError(null);
        setRelSuccess(false);
        if (currentRel != null) {
            setRelInput(String(currentRel));
            return;
        }
        let cancelled = false;
        draftingWorkLoadApi.fetchNextRel(submittalId)
            .then((n) => { if (!cancelled && n != null) setRelInput(String(n)); })
            .catch(() => { /* leave blank on failure */ });
        return () => { cancelled = true; };
    }, [isOpen, isDRR, canEditRel, currentRel, submittalId]);

    const handleAssignRel = async () => {
        setRelError(null);
        setRelSuccess(false);
        const n = parseInt(relInput, 10);
        if (Number.isNaN(n) || n < 101 || n > 998) {
            setRelError('Rel must be a whole number from 101 to 998.');
            return;
        }
        setRelSaving(true);
        try {
            await draftingWorkLoadApi.updateRel(submittalId, n);
            setRelSuccess(true);
            if (onRelAssigned) onRelAssigned(true);
        } catch (err) {
            setRelError(err?.message || 'Failed to assign Rel.');
        } finally {
            setRelSaving(false);
        }
    };

    const runBB = async (pullOnly) => {
        setBbError(null);
        setBbResult(null);
        setBbPullOnly(pullOnly);
        setBbBusy(true);
        try {
            const data = await draftingWorkLoadApi.runProcoreBBReview(submittalId, { pullOnly, model: bbModel });
            setBbResult(data);
        } catch (err) {
            setBbError(err?.message || 'BB review failed');
        } finally {
            setBbBusy(false);
        }
    };

    if (!isOpen || !submittal) return null;
    const projectId = submittal.procore_project_id || submittal['Project Id'] || '';
    const procoreUrl = projectId && submittalId
        ? `https://app.procore.com/webclients/host/companies/18521/projects/${projectId}/tools/submittals/${submittalId}`
        : null;

    const handleEventsClick = () => {
        if (submittalId) {
            setEventsOpen(true);
        }
    };

    const formatDateTime = (dateString) => {
        if (!dateString) return 'N/A';
        try {
            const date = new Date(dateString);
            return date.toLocaleString('en-US', {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: true
            });
        } catch {
            return dateString;
        }
    };

    const createdAt = submittal.created_at || submittal['Created At'];

    const modalContent = (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 transition-opacity"
            onClick={onClose}
        >
            <div
                className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl max-w-md w-full mx-4 transform transition-all"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-6 py-4 rounded-t-xl">
                    <div className="flex items-center justify-between">
                        <h2 className="text-xl font-bold text-white">Submittal Details</h2>
                        <button
                            onClick={onClose}
                            className="text-white hover:text-gray-200 dark:hover:text-slate-200 transition-colors text-2xl font-bold leading-none"
                            aria-label="Close"
                        >
                            ×
                        </button>
                    </div>
                </div>

                <div className="p-6 space-y-4">
                    <div>
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                            {submittal.title || submittal['Title'] || 'N/A'}
                        </h3>
                        <p className="text-sm text-gray-600 dark:text-slate-300">
                            Submittal ID: {submittal.submittal_id || submittal['Submittals Id'] || 'N/A'}
                        </p>
                    </div>

                    <div className="border-t border-gray-200 dark:border-slate-600 pt-4 space-y-4">
                        <div>
                            <div className="flex items-center gap-2 mb-1">
                                <span className="text-sm font-semibold text-gray-700 dark:text-slate-200">Created At:</span>
                            </div>
                            <p className="text-sm text-gray-600 dark:text-slate-300 pl-4">
                                {formatDateTime(createdAt)}
                            </p>
                        </div>

                        {submittal.ball_in_court || submittal['Ball In Court'] ? (
                            <div>
                                <div className="flex items-center gap-2 mb-1">
                                    <span className="text-sm font-semibold text-gray-700 dark:text-slate-200">Current Ball In Court:</span>
                                </div>
                                <p className="text-sm text-gray-600 dark:text-slate-300 pl-4">
                                    {submittal.ball_in_court || submittal['Ball In Court']}
                                </p>
                            </div>
                        ) : null}

                        <div>
                            <div className="flex items-center gap-2 mb-1">
                                <span className="text-sm font-semibold text-gray-700 dark:text-slate-200">Release (Rel):</span>
                                <span className="text-sm text-gray-600 dark:text-slate-300">
                                    {currentRel != null ? currentRel : '—'}
                                </span>
                            </div>
                            <div className="flex items-center gap-2 pl-4">
                                <input
                                    type="text"
                                    inputMode="numeric"
                                    value={relInput}
                                    onChange={(e) => setRelInput(e.target.value.replace(/[^0-9]/g, ''))}
                                    disabled={!isDRR || !canEditRel || relSaving}
                                    placeholder="101–998"
                                    className="w-24 px-2 py-1 text-sm rounded border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-900 dark:text-slate-100 disabled:bg-gray-100 dark:disabled:bg-slate-700 disabled:cursor-not-allowed"
                                />
                                {isDRR && canEditRel ? (
                                    <button
                                        onClick={handleAssignRel}
                                        disabled={relSaving}
                                        className="px-3 py-1 text-sm font-medium bg-accent-600 text-white rounded hover:bg-accent-700 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
                                    >
                                        {relSaving ? 'Saving…' : (currentRel != null ? 'Update Rel' : 'Assign Rel')}
                                    </button>
                                ) : (
                                    <button
                                        disabled
                                        title={!isDRR
                                            ? 'Rel can only be assigned to Drafting Release Review submittals'
                                            : 'You do not have permission to assign a Rel'}
                                        className="px-3 py-1 text-sm font-medium bg-gray-400 dark:bg-slate-500 text-white rounded cursor-not-allowed"
                                    >
                                        {currentRel != null ? 'Update Rel' : 'Assign Rel'}
                                    </button>
                                )}
                            </div>
                            {relError ? (
                                <p className="text-sm text-red-600 dark:text-red-400 pl-4 mt-1">{relError}</p>
                            ) : null}
                            {relSuccess ? (
                                <p className="text-sm text-green-600 dark:text-green-400 pl-4 mt-1">Rel saved.</p>
                            ) : null}
                        </div>
                    </div>

                    {canEditRel && submittalId && projectId ? (
                        <div className="border-t border-gray-200 dark:border-slate-600 pt-4">
                            <div className="text-sm font-semibold text-gray-700 dark:text-slate-200 mb-2">
                                🍌 Banana Boy Review
                            </div>
                            <div className="flex items-center gap-2 flex-wrap">
                                <button
                                    onClick={() => runBB(false)}
                                    disabled={bbBusy}
                                    className="px-3 py-1.5 text-sm font-medium bg-yellow-500 text-white rounded hover:bg-yellow-600 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
                                >
                                    {bbBusy && !bbPullOnly ? 'Pulling & reviewing…' : 'Pull & BB Review'}
                                </button>
                                <button
                                    onClick={() => runBB(true)}
                                    disabled={bbBusy}
                                    className="px-3 py-1.5 text-sm font-medium bg-gray-200 dark:bg-slate-600 text-gray-700 dark:text-slate-200 rounded hover:bg-gray-300 dark:hover:bg-slate-500 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
                                >
                                    {bbBusy && bbPullOnly ? 'Pulling…' : 'Pull only'}
                                </button>
                                <select
                                    value={bbModel}
                                    onChange={(e) => setBbModel(e.target.value)}
                                    disabled={bbBusy}
                                    title="Reviewing model"
                                    className="ml-auto px-2 py-1 text-xs rounded border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-700 dark:text-slate-200 disabled:opacity-60"
                                >
                                    <option value="sonnet">Sonnet (lighter)</option>
                                    <option value="opus">Opus (deep)</option>
                                </select>
                            </div>
                            {bbBusy && !bbPullOnly ? (
                                <p className="text-xs text-gray-500 dark:text-slate-400 mt-2">
                                    Review can take a few minutes — keep this modal open.
                                </p>
                            ) : null}
                            {bbError ? (
                                <p className="text-sm text-red-600 dark:text-red-400 mt-2">{bbError}</p>
                            ) : null}
                            {bbResult ? (
                                <div className="mt-3 text-sm">
                                    {bbResult.pulled ? (
                                        <p className="text-gray-600 dark:text-slate-300">
                                            Pulled <span className="font-medium">{bbResult.pulled.filename || 'drawing.pdf'}</span>
                                            {bbResult.pulled.size_bytes
                                                ? ` (${Math.round(bbResult.pulled.size_bytes / 1024)} KB${bbResult.pulled.source ? `, ${bbResult.pulled.source}` : ''})`
                                                : ''}
                                        </p>
                                    ) : null}
                                    {Array.isArray(bbResult.findings) ? (
                                        bbResult.findings.length === 0 ? (
                                            <p className="text-green-600 dark:text-green-400 mt-1">
                                                No findings — clear against BB's rules.
                                            </p>
                                        ) : (
                                            <div className="mt-2 space-y-2 max-h-64 overflow-y-auto pr-1">
                                                <p className="text-gray-700 dark:text-slate-200 font-medium">
                                                    {bbResult.findings.length} finding{bbResult.findings.length === 1 ? '' : 's'}
                                                </p>
                                                {bbResult.findings.map((f, i) => (
                                                    <div key={i} className="rounded border border-gray-200 dark:border-slate-600 p-2">
                                                        <div className="flex items-center gap-2 mb-1">
                                                            <span className={`px-1.5 py-0.5 rounded text-xs font-semibold ${VERDICT_STYLE[f.verdict] || 'bg-gray-100 text-gray-600 dark:bg-slate-600 dark:text-slate-300'}`}>
                                                                {(f.verdict || '').replace(/_/g, ' ')}
                                                            </span>
                                                            {f.severity ? (
                                                                <span className="text-xs text-gray-500 dark:text-slate-400">{f.severity}</span>
                                                            ) : null}
                                                            {f.rule_id ? (
                                                                <span className="text-xs text-gray-400 dark:text-slate-500 ml-auto">{f.rule_id}</span>
                                                            ) : null}
                                                        </div>
                                                        <p className="text-gray-700 dark:text-slate-200">{f.issue}</p>
                                                        {f.computation ? (
                                                            <p className="text-xs text-gray-500 dark:text-slate-400 mt-1 font-mono">{f.computation}</p>
                                                        ) : null}
                                                        {f.location ? (
                                                            <p className="text-xs text-gray-400 dark:text-slate-500 mt-0.5">{f.location}</p>
                                                        ) : null}
                                                    </div>
                                                ))}
                                            </div>
                                        )
                                    ) : null}
                                </div>
                            ) : null}
                        </div>
                    ) : null}
                </div>

                <div className="bg-gray-50 dark:bg-slate-700 px-6 py-4 rounded-b-xl border-t border-gray-200 dark:border-slate-600 space-y-3">
                    <div className="flex gap-3">
                        {procoreUrl ? (
                            <a
                                href={procoreUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex-1 px-4 py-2 bg-purple-600 text-white rounded-lg font-medium hover:bg-purple-700 transition-colors text-center"
                            >
                                Procore
                            </a>
                        ) : (
                            <button
                                disabled
                                className="flex-1 px-4 py-2 bg-gray-400 dark:bg-slate-500 text-white rounded-lg font-medium cursor-not-allowed text-center"
                            >
                                Procore
                            </button>
                        )}
                        {submittalId ? (
                            <button
                                onClick={handleEventsClick}
                                className="flex-1 px-4 py-2 bg-accent-600 text-white rounded-lg font-medium hover:bg-accent-700 transition-colors"
                            >
                                Events
                            </button>
                        ) : (
                            <button
                                disabled
                                className="flex-1 px-4 py-2 bg-gray-400 dark:bg-slate-500 text-white rounded-lg font-medium cursor-not-allowed"
                            >
                                Events
                            </button>
                        )}
                    </div>
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

    return (
        <>
            {createPortal(modalContent, document.body)}
            <EventsModal
                isOpen={eventsOpen}
                onClose={() => setEventsOpen(false)}
                title={`Events — Submittal ${submittalId}`}
                submittalId={submittalId ? String(submittalId).trim() : ''}
            />
        </>
    );
}

