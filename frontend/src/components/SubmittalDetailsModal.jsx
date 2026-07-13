/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Per-document BB review workspace for a Procore submittal — lists drawing documents,
 *   drives pull → review → findings/feedback per document, and keeps the Rel-assignment and
 *   Events history controls (demoted into a collapsible Details strip).
 * exports:
 *   SubmittalDetailsModal: Review workspace modal for a single submittal record
 * imports_from: [react, react-dom, ./EventsModal, ./bbReview/DocumentRow, ../services/draftingWorkLoadApi]
 * imported_by: [components/SubmittalCardGrid.jsx, components/TableRow.jsx, components/SubmittalRowList.jsx]
 * invariants:
 *   - Exported name and props ({ isOpen, onClose, submittal, canEditRel, onRelAssigned }) are stable so call sites need no edits.
 *   - The BB/documents section is gated on canEditRel && a present submittal id.
 * updated_by_agent: 2026-07-10T00:00:00Z
 */
import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';

import { EventsModal } from './EventsModal';
import DocumentRow from './bbReview/DocumentRow';
import { PdfMarkupModal } from './PdfMarkupModal';
import { draftingWorkLoadApi } from '../services/draftingWorkLoadApi';
import { API_BASE_URL } from '../utils/api';

const DRR_TYPE = 'Drafting Release Review';
const PHASES = ['GC', 'DRR', 'FC'];

// Model choice is sticky for the browser session (survives modal open/close), default sonnet.
let sessionModel = 'sonnet';

function PhasePipeline({ phase }) {
    return (
        <div className="flex items-center gap-1.5">
            {PHASES.map((p, i) => {
                const active = p === phase;
                return (
                    <React.Fragment key={p}>
                        <span
                            className={`flex items-center gap-1 text-[10px] font-semibold ${
                                active ? 'text-white' : 'text-white/50'
                            }`}
                        >
                            <span className={`inline-block rounded-full ${active ? 'w-2.5 h-2.5 bg-white' : 'w-1.5 h-1.5 bg-white/40'}`} />
                            {p}
                        </span>
                        {i < PHASES.length - 1 && <span className="text-white/30 text-[10px]">→</span>}
                    </React.Fragment>
                );
            })}
        </div>
    );
}

export function SubmittalDetailsModal({ isOpen, onClose, submittal, canEditRel = false, onRelAssigned }) {
    const [eventsOpen, setEventsOpen] = useState(false);
    const [relInput, setRelInput] = useState('');
    const [relSaving, setRelSaving] = useState(false);
    const [relError, setRelError] = useState(null);
    const [relSuccess, setRelSuccess] = useState(false);
    const [relValue, setRelValue] = useState(null);

    const [model, setModel] = useState(sessionModel);
    const [detailsOpen, setDetailsOpen] = useState(false);

    const [cite, setCite] = useState(null); // { doc, page, nonce } — active drawing shown in the right pane
    const openCite = (doc, page = 1) => setCite({ doc, page: page || 1, nonce: Date.now() });
    const [docs, setDocs] = useState(null);        // array | null (null = not loaded)
    const [meta, setMeta] = useState(null);        // documents.submittal (enriched metadata)
    const [docsLoading, setDocsLoading] = useState(false);
    const [docsError, setDocsError] = useState(null);

    const submittalId = (submittal?.submittal_id || submittal?.['Submittals Id'] || '');
    const isDRR = (submittal?.type ?? submittal?.['TYPE']) === DRR_TYPE;
    const currentRel = submittal?.rel ?? submittal?.['Rel'] ?? null;
    const phase = meta?.phase || (isDRR ? 'DRR' : 'other');
    const bbEnabled = canEditRel && !!submittalId;

    // Keep the model dropdown sticky across opens within a session.
    const handleModelChange = (m) => { setModel(m); sessionModel = m; };

    // Prefill the Rel input when the popup opens on a DRR.
    useEffect(() => {
        if (!isOpen) {
            setRelError(null);
            setRelSuccess(false);
            setDetailsOpen(false);
            return;
        }
        setRelValue(currentRel);
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

    // Load the documents for this submittal on open.
    useEffect(() => {
        if (!isOpen || !bbEnabled) {
            setDocs(null);
            setMeta(null);
            setDocsError(null);
            return;
        }
        let cancelled = false;
        setDocsLoading(true);
        setDocsError(null);
        draftingWorkLoadApi.fetchProcoreDocuments(submittalId)
            .then((data) => {
                if (cancelled) return;
                setDocs(Array.isArray(data?.documents) ? data.documents : []);
                setMeta(data?.submittal || null);
                if (data?.submittal?.rel != null) setRelValue(data.submittal.rel);
            })
            .catch((err) => { if (!cancelled) setDocsError(err?.message || 'Failed to load documents'); })
            .finally(() => { if (!cancelled) setDocsLoading(false); });
        return () => { cancelled = true; };
    }, [isOpen, bbEnabled, submittalId]);

    const patchDoc = (attachmentId, patch) => {
        setDocs((prev) => (prev || []).map((d) => (d.attachment_id === attachmentId ? { ...d, ...patch } : d)));
    };

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
            setRelValue(n);
            setRelSuccess(true);
            if (onRelAssigned) onRelAssigned(true);
        } catch (err) {
            setRelError(err?.message || 'Failed to assign Rel.');
        } finally {
            setRelSaving(false);
        }
    };

    if (!isOpen || !submittal) return null;

    const title = submittal.title || submittal['Title'] || 'Submittal';
    const status = meta?.status || submittal.status || submittal['Status'] || null;
    const ballInCourt = meta?.ball_in_court || submittal.ball_in_court || submittal['Ball In Court'] || null;
    const projectId = meta?.project_id || submittal.procore_project_id || submittal['Project Id'] || '';
    const procoreUrl = meta?.procore_url || (projectId && submittalId
        ? `https://app.procore.com/webclients/host/companies/18521/projects/${projectId}/tools/submittals/${submittalId}`
        : null);
    const canAssignRel = isDRR && canEditRel;

    const formatDateTime = (dateString) => {
        if (!dateString) return 'N/A';
        try {
            return new Date(dateString).toLocaleString('en-US', {
                year: 'numeric', month: 'short', day: 'numeric',
                hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true,
            });
        } catch {
            return dateString;
        }
    };
    const createdAt = submittal.created_at || submittal['Created At'];

    const chip = 'text-[11px] font-medium px-2 py-0.5 rounded-full';

    const modalContent = (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 transition-opacity p-4"
            onClick={onClose}
        >
            <div
                className={`bg-white dark:bg-slate-800 rounded-xl shadow-2xl w-full max-h-[85vh] flex flex-col transform transition-all ${cite ? 'max-w-6xl' : 'max-w-2xl'}`}
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-6 py-4 rounded-t-xl shrink-0">
                    <div className="flex items-start justify-between gap-3">
                        <h2 className="text-lg font-bold text-white leading-snug min-w-0">{title}</h2>
                        <button
                            onClick={onClose}
                            className="text-white hover:text-gray-200 transition-colors text-2xl font-bold leading-none shrink-0"
                            aria-label="Close"
                        >
                            ×
                        </button>
                    </div>
                    <div className="mt-2 flex items-center gap-1.5 flex-wrap">
                        {phase !== 'other' && (
                            <span className={`${chip} bg-white text-accent-600 font-semibold`}>{phase}</span>
                        )}
                        {status && <span className={`${chip} bg-white/20 text-white`}>{status}</span>}
                        {ballInCourt && <span className={`${chip} bg-white/20 text-white`}>BIC · {ballInCourt}</span>}
                        {relValue != null ? (
                            <span className={`${chip} bg-white/20 text-white`}>Rel {relValue} ✓</span>
                        ) : canAssignRel ? (
                            <button
                                onClick={() => setDetailsOpen(true)}
                                className={`${chip} bg-white/20 text-white hover:bg-white/30 transition-colors`}
                            >
                                Assign Rel
                            </button>
                        ) : null}
                        {procoreUrl && (
                            <a
                                href={procoreUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className={`${chip} bg-white/20 text-white hover:bg-white/30 transition-colors ml-auto`}
                            >
                                Procore ↗
                            </a>
                        )}
                    </div>
                    <div className="mt-2">
                        <PhasePipeline phase={phase} />
                    </div>
                </div>

                {/* Body (internal scroll region) — splits into a two-pane layout when a cite is active */}
                <div className={cite ? 'flex-1 min-h-0 flex flex-row' : 'flex-1 overflow-y-auto'}>
                    <div className={cite ? 'md:w-[440px] md:flex-none w-full overflow-y-auto p-6 space-y-4 min-w-0' : 'p-6 space-y-4'}>
                    {bbEnabled ? (
                        <div>
                            <div className="flex items-center justify-between gap-2 mb-2">
                                <h3 className="text-sm font-semibold text-gray-700 dark:text-slate-200">🍌 Documents</h3>
                                <label className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-slate-400">
                                    Reviewing with:
                                    <select
                                        value={model}
                                        onChange={(e) => handleModelChange(e.target.value)}
                                        className="px-1.5 py-0.5 text-xs rounded border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-700 dark:text-slate-200"
                                    >
                                        <option value="sonnet">Sonnet</option>
                                        <option value="opus">Opus</option>
                                    </select>
                                </label>
                            </div>

                            {docsLoading ? (
                                <p className="text-sm text-gray-500 dark:text-slate-400">Loading documents…</p>
                            ) : docsError ? (
                                <p className="text-sm text-red-600 dark:text-red-400">{docsError}</p>
                            ) : docs && docs.length === 0 ? (
                                <p className="text-sm text-gray-500 dark:text-slate-400 border border-dashed border-gray-300 dark:border-slate-600 rounded-lg p-4 text-center">
                                    No drawings on this submittal yet.
                                </p>
                            ) : docs ? (
                                <div className="border border-gray-200 dark:border-slate-600 rounded-lg divide-y divide-gray-200 dark:divide-slate-600 overflow-hidden">
                                    {docs.map((d) => (
                                        <DocumentRow
                                            key={d.attachment_id}
                                            submittalId={submittalId}
                                            doc={d}
                                            model={model}
                                            onUpdate={patchDoc}
                                            onView={(doc) => openCite(doc, 1)}
                                            onCiteSource={(doc, finding) => openCite(doc, finding?.page)}
                                            activeAttachmentId={cite?.doc?.attachment_id}
                                        />
                                    ))}
                                </div>
                            ) : null}
                        </div>
                    ) : (
                        <p className="text-sm text-gray-500 dark:text-slate-400">
                            Submittal ID: {submittalId || 'N/A'}
                        </p>
                    )}

                    {/* Details (demoted, collapsible) */}
                    <div className="border-t border-gray-200 dark:border-slate-600 pt-3">
                        <button
                            onClick={() => setDetailsOpen((o) => !o)}
                            className="flex items-center gap-1.5 text-sm font-medium text-gray-600 dark:text-slate-300 hover:text-gray-900 dark:hover:text-white transition-colors"
                        >
                            Details {detailsOpen ? '▾' : '▸'}
                        </button>
                        {detailsOpen && (
                            <div className="mt-3 space-y-4">
                                <div>
                                    <span className="text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wide">Created At</span>
                                    <p className="text-sm text-gray-700 dark:text-slate-200">{formatDateTime(createdAt)}</p>
                                </div>
                                {ballInCourt && (
                                    <div>
                                        <span className="text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wide">Ball In Court</span>
                                        <p className="text-sm text-gray-700 dark:text-slate-200">{ballInCourt}</p>
                                    </div>
                                )}
                                <div>
                                    <span className="text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wide">Release (Rel)</span>
                                    {canAssignRel && relValue == null ? (
                                        <div className="mt-1 flex items-center gap-2">
                                            <input
                                                type="text"
                                                inputMode="numeric"
                                                value={relInput}
                                                onChange={(e) => setRelInput(e.target.value.replace(/[^0-9]/g, ''))}
                                                disabled={relSaving}
                                                placeholder="101–998"
                                                className="w-24 px-2 py-1 text-sm rounded border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-900 dark:text-slate-100 disabled:bg-gray-100 dark:disabled:bg-slate-700 disabled:cursor-not-allowed"
                                            />
                                            <button
                                                onClick={handleAssignRel}
                                                disabled={relSaving}
                                                className="px-3 py-1 text-sm font-medium bg-accent-600 text-white rounded hover:bg-accent-700 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
                                            >
                                                {relSaving ? 'Saving…' : 'Assign Rel'}
                                            </button>
                                        </div>
                                    ) : canAssignRel ? (
                                        <div className="mt-1 flex items-center gap-2">
                                            <span className="inline-block text-sm font-medium px-2 py-0.5 rounded bg-gray-100 dark:bg-slate-700 text-gray-700 dark:text-slate-200">
                                                Rel {relValue}
                                            </span>
                                            <input
                                                type="text"
                                                inputMode="numeric"
                                                value={relInput}
                                                onChange={(e) => setRelInput(e.target.value.replace(/[^0-9]/g, ''))}
                                                disabled={relSaving}
                                                placeholder="101–998"
                                                className="w-24 px-2 py-1 text-sm rounded border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-900 dark:text-slate-100 disabled:bg-gray-100 dark:disabled:bg-slate-700 disabled:cursor-not-allowed"
                                            />
                                            <button
                                                onClick={handleAssignRel}
                                                disabled={relSaving}
                                                className="px-3 py-1 text-sm font-medium bg-accent-600 text-white rounded hover:bg-accent-700 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
                                            >
                                                {relSaving ? 'Saving…' : 'Update Rel'}
                                            </button>
                                        </div>
                                    ) : (
                                        <p className="text-sm text-gray-700 dark:text-slate-200">
                                            {relValue != null ? `Rel ${relValue}` : '—'}
                                        </p>
                                    )}
                                    {relError && <p className="text-sm text-red-600 dark:text-red-400 mt-1">{relError}</p>}
                                    {relSuccess && <p className="text-sm text-green-600 dark:text-green-400 mt-1">Rel saved.</p>}
                                </div>
                                {submittalId && (
                                    <button
                                        onClick={() => setEventsOpen(true)}
                                        className="px-3 py-1.5 text-sm font-medium bg-accent-600 text-white rounded hover:bg-accent-700 transition-colors"
                                    >
                                        Events
                                    </button>
                                )}
                            </div>
                        )}
                    </div>
                    </div>
                    {cite && (
                        <div className="flex-1 min-w-0 min-h-0 border-l border-gray-200 dark:border-slate-600 flex flex-col">
                            <PdfMarkupModal
                                isOpen
                                inline
                                mode="view"
                                title={cite.doc?.name || 'Drawing'}
                                fileUrl={`${API_BASE_URL}/brain/procore-submittals/${encodeURIComponent(submittalId)}/documents/${encodeURIComponent(cite.doc.attachment_id)}/file`}
                                initialPage={cite.page}
                                citeNonce={cite.nonce}
                                onClose={() => setCite(null)}
                            />
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="bg-gray-50 dark:bg-slate-700 px-6 py-3 rounded-b-xl border-t border-gray-200 dark:border-slate-600 shrink-0">
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
