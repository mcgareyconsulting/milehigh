/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Centered, read-only detail modal for a release, opened by clicking a timeline bar.
 *   Seeds core release fields instantly from the passed job row, then lazy-loads enrichment
 *   (active to-dos + meeting notes, photos, drawing versions) and quick links (Trello/Procore/viewer).
 * exports:
 *   ReleaseDetailModal: Portal modal showing a release's core fields, to-dos, meeting notes,
 *     attachments, and external links. Read-only.
 * imports_from: [react, react-dom, ../services/jobsApi, ../utils/api, ../utils/auth, ./Badge, ./PdfVersionHistoryModal, ./PdfMarkupModal]
 * imported_by: [frontend/src/components/GanttChart.jsx]
 * invariants:
 *   - READ-ONLY for release/scheduling data — GET fetches only; never PATCHes or mutates the release. Edits live in Job Log.
 *   - The Drawing button opens the internal drawing hub (PdfVersionHistoryModal → PdfMarkupModal), the same
 *     path as ReleaseNumberLink; it is NOT a Procore link. The separate Procore button links to the submittal tool.
 *     (Drawing markup/upload via the hub is its own feature, gated by canMarkup, and is not part of the read-only invariant.)
 *   - Renders via createPortal to document.body to escape the timeline's scroll/overflow clipping.
 *   - Core fields render from the `release` prop with no fetch; enrichment fetches fill in async.
 * updated_by_agent: 2026-06-17 (new: timeline detail modal)
 */
import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

import { jobsApi } from '../services/jobsApi';
import { API_BASE_URL } from '../utils/api';
import { checkAuth } from '../utils/auth';
import { Badge } from './Badge';
import { PdfVersionHistoryModal } from './PdfVersionHistoryModal';
import { PdfMarkupModal } from './PdfMarkupModal';
import { BBReviewReport } from './bbReview/report';

// item_type → Badge tint (mirrors the checklist item_type vocabulary).
const ITEM_TYPE_TINT = {
    action: 'blue',
    needs_gc_update: 'amber',
    decision: 'violet',
    risk: 'red',
    fyi: 'slate',
};

const STATUS_TINT = { accepted: 'amber', done: 'emerald' };

function fmtDate(value) {
    if (!value) return '—';
    const d = new Date(String(value).length <= 10 ? value + 'T00:00:00' : value);
    if (isNaN(d)) return String(value);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function Field({ label, children }) {
    return (
        <div>
            <dt className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-slate-500">{label}</dt>
            <dd className="text-sm text-gray-800 dark:text-slate-200">{children || '—'}</dd>
        </div>
    );
}

function SectionSpinner() {
    return (
        <div className="flex items-center gap-2 text-xs text-gray-400 dark:text-slate-500 py-2">
            <span className="inline-block animate-spin rounded-full h-3.5 w-3.5 border-b-2 border-accent-500" />
            Loading…
        </div>
    );
}

export function ReleaseDetailModal({ isOpen, onClose, release }) {
    const [enrichment, setEnrichment] = useState({ todos: [], meetings: [] });
    const [photos, setPhotos] = useState([]);
    const [drawings, setDrawings] = useState([]);
    const [bbReport, setBbReport] = useState(null);   // PM-facing BB review report, or null
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    // Internal drawing hub (version history → markup), mirroring ReleaseNumberLink.
    const [canMarkup, setCanMarkup] = useState(false);
    const [drawingHubOpen, setDrawingHubOpen] = useState(false);
    const [markupOpen, setMarkupOpen] = useState(false);
    const [markupVersionId, setMarkupVersionId] = useState(null);
    const [markupMode, setMarkupMode] = useState('view');
    const [hasDrawingLocal, setHasDrawingLocal] = useState(false);

    const releaseId = release?.id;

    // Escape-to-close.
    useEffect(() => {
        if (!isOpen) return;
        const onKey = (e) => { if (e.key === 'Escape') onClose(); };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [isOpen, onClose]);

    // Drafters/admins can open versions in edit mode; everyone else views read-only.
    useEffect(() => {
        if (!isOpen) return;
        let cancelled = false;
        checkAuth()
            .then((u) => { if (!cancelled) setCanMarkup(!!(u?.is_admin || u?.is_drafter)); })
            .catch(() => {});
        return () => { cancelled = true; };
    }, [isOpen]);

    // Seed the local has-drawing flag from the release row (the modal can flip it true
    // after an upload via PdfMarkupModal.onSaved).
    useEffect(() => {
        setHasDrawingLocal(Boolean(release?.has_drawing));
    }, [release]);

    // Three parallel enrichment fetches (no waterfall); core fields come from the prop.
    useEffect(() => {
        if (!isOpen || !releaseId) return;
        let cancelled = false;
        setLoading(true);
        setError(null);
        setEnrichment({ todos: [], meetings: [] });
        setPhotos([]);
        setDrawings([]);
        setBbReport(null);
        Promise.allSettled([
            jobsApi.getReleaseChecklist(releaseId),
            jobsApi.getReleasePhotos(releaseId),
            jobsApi.getReleaseDrawings(releaseId),
            // 403 (not admin/PM for this release) or no review → null; never blocks the modal.
            jobsApi.getBBReviewReport(releaseId).catch(() => null),
        ]).then(([checklist, photoList, drawingList, bbReviewReport]) => {
            if (cancelled) return;
            if (checklist.status === 'fulfilled') {
                setEnrichment({
                    todos: checklist.value?.todos || [],
                    meetings: checklist.value?.meetings || [],
                });
            }
            if (photoList.status === 'fulfilled') setPhotos(photoList.value || []);
            if (drawingList.status === 'fulfilled') setDrawings(drawingList.value || []);
            if (bbReviewReport.status === 'fulfilled') setBbReport(bbReviewReport.value || null);
            if (checklist.status === 'rejected' && photoList.status === 'rejected' && drawingList.status === 'rejected') {
                setError('Failed to load release details.');
            }
            setLoading(false);
        });
        return () => { cancelled = true; };
    }, [isOpen, releaseId]);

    if (!isOpen || !release) return null;

    const job = release['Job #'] ?? release.job;
    const rel = release['Release #'] ?? release.release;
    const jobName = release['Job'] || release.job_name || '';
    const description = release['Description'] || release.description || '';
    const stage = release['Stage'] || release.stage;
    const stageGroup = release['Stage Group'] || release.stage_group;
    const startInstall = release['Start install'] || release.start_install;
    const compEta = release['comp_eta_effective'] || release['Comp. ETA'] || release.comp_eta;
    const installer = release.installer;
    const pm = release['PM'] || release.pm;
    const by = release['BY'] || release.by;
    const installHrs = release['Install HRS'] ?? release.install_hrs;
    const numGuys = release.num_guys;
    const notes = release['Notes'] || release.notes;

    const projectId = release.procore_project_id || '';
    const submittalId = release.procore_submittal_id || '';
    const procoreUrl = projectId && submittalId
        ? `https://app.procore.com/webclients/host/companies/18521/projects/${projectId}/tools/submittals/${submittalId}`
        : null;
    const trelloUrl = release.trello_card_id ? `https://trello.com/c/${release.trello_card_id}` : null;
    const viewerUrl = release.viewer_url || null;

    const { todos, meetings } = enrichment;

    const modalContent = (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 transition-opacity"
            onClick={onClose}
        >
            <div
                className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl max-w-3xl w-full mx-4 flex flex-col max-h-[85vh] transform transition-all"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-6 py-4 rounded-t-xl shrink-0">
                    <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                            <h2 className="text-xl font-bold text-white truncate">
                                Job {job}-{rel}{jobName ? ` · ${jobName}` : ''}
                            </h2>
                            {description && (
                                <p className="text-sm text-white/80 mt-0.5 line-clamp-2">{description}</p>
                            )}
                        </div>
                        <button
                            onClick={onClose}
                            className="text-white hover:text-gray-200 transition-colors text-2xl font-bold leading-none shrink-0"
                            aria-label="Close"
                        >
                            ×
                        </button>
                    </div>
                </div>

                {/* Body */}
                <div className="p-6 space-y-6 overflow-y-auto">
                    {/* Core fields */}
                    <section>
                        <dl className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-3">
                            <Field label="Stage">
                                {stage ? <Badge tint="slate">{stage}</Badge> : '—'}
                            </Field>
                            <Field label="Stage Group">{stageGroup}</Field>
                            <Field label="Installer">{installer}</Field>
                            <Field label="Start Install">{fmtDate(startInstall)}</Field>
                            <Field label="Comp. ETA">{fmtDate(compEta)}</Field>
                            <Field label="Crew">{numGuys != null ? `${numGuys} guys` : '—'}</Field>
                            <Field label="Install Hrs">{installHrs != null ? installHrs : '—'}</Field>
                            <Field label="PM">{pm}</Field>
                            <Field label="BY">{by}</Field>
                        </dl>
                        {notes && (
                            <div className="mt-4">
                                <dt className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-slate-500 mb-1">Notes</dt>
                                <p className="text-sm text-gray-700 dark:text-slate-300 whitespace-pre-wrap bg-gray-50 dark:bg-slate-700/50 rounded p-2.5 border border-gray-100 dark:border-slate-600">
                                    {notes}
                                </p>
                            </div>
                        )}
                    </section>

                    {error && (
                        <div className="text-xs text-red-600 dark:text-red-400">{error}</div>
                    )}

                    {/* Active to-dos */}
                    <section>
                        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-slate-400 mb-2">Active To-dos</h3>
                        {loading && todos.length === 0 ? <SectionSpinner /> : todos.length === 0 ? (
                            <p className="text-xs text-gray-400 dark:text-slate-500">No active to-dos.</p>
                        ) : (
                            <ul className="space-y-2">
                                {todos.map((t) => (
                                    <li key={t.id} className="rounded-lg border border-gray-100 dark:border-slate-600 bg-white dark:bg-slate-700/40 px-3 py-2">
                                        <div className="flex items-start justify-between gap-2">
                                            <span className="text-sm text-gray-800 dark:text-slate-200">{t.title}</span>
                                            <Badge tint={STATUS_TINT[t.status] || 'slate'} className="shrink-0">{t.status}</Badge>
                                        </div>
                                        <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-gray-500 dark:text-slate-400">
                                            <Badge tint={ITEM_TYPE_TINT[t.item_type] || 'slate'}>{t.item_type}</Badge>
                                            {t.owner_name && <span>👤 {t.owner_name}</span>}
                                            {t.due_date && <span>📅 {fmtDate(t.due_date)}</span>}
                                            {t.meeting_title && <span className="italic truncate">from “{t.meeting_title}”</span>}
                                        </div>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </section>

                    {/* Meeting notes */}
                    <section>
                        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-slate-400 mb-2">Meeting Notes</h3>
                        {loading && meetings.length === 0 ? <SectionSpinner /> : meetings.length === 0 ? (
                            <p className="text-xs text-gray-400 dark:text-slate-500">No linked meetings.</p>
                        ) : (
                            <div className="space-y-3">
                                {meetings.map((m) => (
                                    <div key={m.id} className="rounded-lg border border-gray-100 dark:border-slate-600 bg-gray-50 dark:bg-slate-700/40 px-3 py-2">
                                        <div className="flex items-center justify-between gap-2 mb-1">
                                            <span className="text-sm font-medium text-gray-800 dark:text-slate-200 truncate">{m.title}</span>
                                            <span className="text-[11px] text-gray-400 dark:text-slate-500 shrink-0">{fmtDate(m.occurred_at)}</span>
                                        </div>
                                        {m.summary ? (
                                            <p className="text-xs text-gray-600 dark:text-slate-300 whitespace-pre-wrap">{m.summary}</p>
                                        ) : (
                                            <p className="text-xs text-gray-400 dark:text-slate-500 italic">No summary.</p>
                                        )}
                                    </div>
                                ))}
                            </div>
                        )}
                    </section>

                    {/* Attachments */}
                    <section>
                        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-slate-400 mb-2">Attachments</h3>
                        {loading && photos.length === 0 && drawings.length === 0 ? <SectionSpinner /> : (
                            <>
                                {photos.length === 0 && drawings.length === 0 && (
                                    <p className="text-xs text-gray-400 dark:text-slate-500">No photos or drawings.</p>
                                )}
                                {photos.length > 0 && (
                                    <div className="grid grid-cols-3 sm:grid-cols-4 gap-2 mb-3">
                                        {photos.map((p) => (
                                            <a
                                                key={p.id}
                                                href={`${API_BASE_URL}/brain/releases/${releaseId}/photos/${p.id}/file`}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                title={p.note || p.original_filename}
                                                className="block aspect-square rounded overflow-hidden border border-gray-200 dark:border-slate-600 bg-gray-100 dark:bg-slate-700"
                                            >
                                                <img
                                                    src={`${API_BASE_URL}/brain/releases/${releaseId}/photos/${p.id}/file`}
                                                    alt={p.original_filename}
                                                    loading="lazy"
                                                    className="w-full h-full object-cover"
                                                />
                                            </a>
                                        ))}
                                    </div>
                                )}
                                {drawings.length > 0 && (
                                    <ul className="space-y-1">
                                        {drawings.map((v) => (
                                            <li key={v.id}>
                                                <a
                                                    href={`${API_BASE_URL}/brain/releases/${releaseId}/drawing/versions/${v.id}/file`}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="text-sm text-accent-600 dark:text-accent-400 hover:underline inline-flex items-center gap-2"
                                                >
                                                    📄 v{v.version_number} · {v.original_filename}
                                                    <span className="text-[11px] text-gray-400 dark:text-slate-500">{fmtDate(v.uploaded_at)}</span>
                                                </a>
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </>
                        )}
                    </section>

                    {/* Banana Boy code-compliance review (PM-facing; only when a report exists) */}
                    {bbReport && (
                        <section>
                            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-slate-400 mb-2">
                                🍌 BB Review
                            </h3>
                            <BBReviewReport report={bbReport} />
                        </section>
                    )}
                </div>

                {/* Footer links */}
                <div className="bg-gray-50 dark:bg-slate-700 px-6 py-4 rounded-b-xl border-t border-gray-200 dark:border-slate-600 flex gap-3 shrink-0">
                    {(canMarkup || hasDrawingLocal) ? (
                        // Internal drawing hub (version history + markup), surfaces Procore inside.
                        <button
                            onClick={() => setDrawingHubOpen(true)}
                            className="flex-1 px-4 py-2 bg-accent-600 text-white rounded-lg font-medium hover:bg-accent-700 transition-colors text-center">
                            Drawing
                        </button>
                    ) : viewerUrl ? (
                        // No internal drawing and no markup rights → fall back to the Procore FC viewer.
                        <a href={viewerUrl} target="_blank" rel="noopener noreferrer"
                            className="flex-1 px-4 py-2 bg-accent-600 text-white rounded-lg font-medium hover:bg-accent-700 transition-colors text-center">
                            Drawing
                        </a>
                    ) : (
                        <button disabled className="flex-1 px-4 py-2 bg-gray-300 dark:bg-slate-500 text-white rounded-lg font-medium cursor-not-allowed">Drawing</button>
                    )}
                    {procoreUrl ? (
                        <a href={procoreUrl} target="_blank" rel="noopener noreferrer"
                            className="flex-1 px-4 py-2 bg-purple-600 text-white rounded-lg font-medium hover:bg-purple-700 transition-colors text-center">
                            Procore
                        </a>
                    ) : (
                        <button disabled className="flex-1 px-4 py-2 bg-gray-300 dark:bg-slate-500 text-white rounded-lg font-medium cursor-not-allowed">Procore</button>
                    )}
                    {trelloUrl ? (
                        <a href={trelloUrl} target="_blank" rel="noopener noreferrer"
                            className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors text-center">
                            Trello
                        </a>
                    ) : (
                        <button disabled className="flex-1 px-4 py-2 bg-gray-300 dark:bg-slate-500 text-white rounded-lg font-medium cursor-not-allowed">Trello</button>
                    )}
                </div>
            </div>
        </div>
    );

    return (
        <>
            {createPortal(modalContent, document.body)}
            <PdfVersionHistoryModal
                isOpen={drawingHubOpen}
                releaseId={releaseId}
                title={`${job}-${rel}`}
                viewerUrl={viewerUrl || ''}
                onClose={() => setDrawingHubOpen(false)}
                onOpenVersion={(vid, mode) => {
                    setDrawingHubOpen(false);
                    setMarkupVersionId(vid);
                    setMarkupMode(canMarkup ? mode : 'view');
                    setMarkupOpen(true);
                }}
            />
            <PdfMarkupModal
                isOpen={markupOpen}
                releaseId={releaseId}
                versionId={markupVersionId}
                mode={markupMode}
                onClose={() => setMarkupOpen(false)}
                onSaved={() => setHasDrawingLocal(true)}
            />
        </>
    );
}

export default ReleaseDetailModal;
