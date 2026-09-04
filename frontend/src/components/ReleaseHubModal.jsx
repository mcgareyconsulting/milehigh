/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The single release modal — Details / Attachments / Change Log — opened from the Job
 *   Log table, the card grid, the Timeline, Archive and Subs. Activity rail on Details and
 *   Change Log (hidden on Attachments for the full-width viewer).
 * exports:
 *   ReleaseHubModal: Portal modal shell for a release
 * imports_from: [react, react-dom, ./JobDetailsBody, ./PdfVersionHistoryModal, ./EventsList,
 *   ./ReleaseNotesRail, ./StageIconRow, ../utils/stageTint, ../constants/modalSize]
 * imported_by: [frontend/src/components/JobsTableRow.jsx, frontend/src/components/JobLogCardGrid.jsx,
 *   frontend/src/components/GanttChart.jsx]
 * invariants:
 *   - Renders via createPortal to document.body to escape table overflow clipping
 *   - Leaves a click-out margin around the panel: the backdrop stays reachable on every edge
 *   - A tab pane stays mounted once visited, so drafts and uploads survive tab switching
 *   - Activity rail renders on Details + Change Log only — Attachments takes the full width
 *   - The header owns the stage pill and the compact banana row; both follow an in-pane stage
 *     edit immediately via onStageChange, without waiting for the host's refetch
 * updated_by_agent: 2026-09-03T00:00:00Z
 */
import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import { JobDetailsBody } from './JobDetailsBody';
import { PdfVersionHistoryModal } from './PdfVersionHistoryModal';
import { ReleaseNotesRail } from './ReleaseNotesRail';
import EventsList from './EventsList';
import { StageIconRow } from './StageIconRow';
import { stageTint } from '../utils/stageTint';
import { MODAL_PANEL_SIZE } from '../constants/modalSize';
import { usePersistScroll } from '../hooks/usePersistScroll';

const TABS = [
    { key: 'details', label: 'Details' },
    { key: 'attachments', label: 'Attachments' },
    { key: 'changelog', label: 'Change Log' },
];

/** Map legacy initialTab values from callers that still pass 'drawings'. */
const normalizeTab = (tab) => (tab === 'drawings' ? 'attachments' : tab);

const ACTIVITY_RAIL_WIDTH = 346;

/** Banana row sits in the header now, so it reads at chip scale, not section scale. */
const HEADER_BANANA_ICON_SIZE = 18;

export function ReleaseHubModal({
    isOpen,
    onClose,
    job,
    releaseId,
    viewerUrl = '',
    initialTab = 'details',
    scrollToMaterials = false,
    onOrdersChanged = null,
    initialCommentVersionId = null,
    onOpenVersion = null,
    /** Actionable Carmen findings count for the Attachments tab badge (0 = hidden). */
    attachmentsBadgeCount = 0,
    onAttachmentsBadgeCount = null,
    /** Called after Activity rail overwrites Job Log notes (parent can refresh row). */
    onNotesChanged = null,
    /** Refetch hook for the host list — every write in the Details pane calls it. */
    onJobUpdate = null,
}) {
    const startTab = normalizeTab(initialTab);
    const [activeTab, setActiveTab] = useState(startTab);
    const detailsScrollStore = useRef(0);
    const changelogScrollStore = useRef(0);
    const detailsScroll = usePersistScroll(detailsScrollStore);
    const changelogScroll = usePersistScroll(changelogScrollStore);
    // Panes render once activated and then stay mounted (hidden) so an
    // in-progress comment or note draft isn't thrown away by a tab switch.
    const [visited, setVisited] = useState(() => ({ [startTab]: true }));
    // Local badge can be lifted from the Attachments pane once reviews load.
    const [badgeFromPane, setBadgeFromPane] = useState(0);
    // Stage the header renders. Seeded from the row, then owned by the Details
    // pane's select until the host's refetch brings a fresh row in.
    const [liveStage, setLiveStage] = useState(null);

    useEffect(() => {
        if (!isOpen) return;
        const tab = normalizeTab(initialTab);
        setActiveTab(tab);
        setVisited((prev) => ({ ...prev, [tab]: true }));
        setBadgeFromPane(0);
        setLiveStage(null);
        detailsScrollStore.current = 0;
        changelogScrollStore.current = 0;
    }, [isOpen, initialTab, job?.id]);

    useEffect(() => {
        if (!isOpen) return;
        const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [isOpen, onClose]);

    if (!isOpen || !job) return null;

    const jobNumber = job['Job #'] || job.job;
    const releaseNumber = job['Release #'] || job.release;
    const jobName = job['Job'] || job.job_name || '';
    const description = (job['Description'] || job.description || '').toString().trim();
    const stage = liveStage ?? (job['Stage'] || job.stage || '');
    const pm = job['PM'] || job.pm;
    const by = job['BY'] || job.by;
    const label = `${jobNumber ?? ''}${releaseNumber ? `-${releaseNumber}` : ''}`;
    const tint = stageTint(stage);

    const selectTab = (key) => {
        setActiveTab(key);
        setVisited((prev) => ({ ...prev, [key]: true }));
    };

    const procoreUrl = job.procore_project_id && job.procore_submittal_id
        ? `https://app.procore.com/webclients/host/companies/18521/projects/${job.procore_project_id}/tools/submittals/${job.procore_submittal_id}`
        : (viewerUrl && viewerUrl.trim() !== '' ? viewerUrl : null);
    const trelloUrl = job.trello_card_id ? `https://trello.com/c/${job.trello_card_id}` : null;

    const linkCls = 'inline-flex items-center border border-hairline-strong rounded-[7px] bg-surface text-ink-2 font-semibold hover:bg-surface-2 hover:text-ink transition-colors';
    const linkStyle = { height: 28, padding: '0 11px', fontSize: 13 };
    const deadStyle = { ...linkStyle, opacity: 0.45, cursor: 'not-allowed' };

    // Row 2. The job name now leads row 1, so this is attribution only.
    const context = [pm ? `PM ${pm}` : null, by ? `Detailed by ${by}` : null]
        .filter(Boolean).join(' · ');

    const showActivityRail = activeTab === 'details' || activeTab === 'changelog';
    const badgeCount = Math.max(0, Number(attachmentsBadgeCount) || 0, Number(badgeFromPane) || 0);

    const reportBadge = (n) => {
        const count = Math.max(0, Number(n) || 0);
        setBadgeFromPane(count);
        onAttachmentsBadgeCount?.(count);
    };

    const content = (
        <div
            className="fixed inset-0 z-50 dc-fade flex items-center justify-center p-4"
            style={{ background: 'rgba(10,16,28,.55)', backdropFilter: 'blur(2px)' }}
            onClick={onClose}
        >
            <div
                className="dc-pop bg-surface border border-hairline-strong flex flex-col overflow-hidden"
                style={{
                    // Shared with the DWL submittal modal — see constants/modalSize.js
                    // (that file carries the dvh/BUG-14 note).
                    ...MODAL_PANEL_SIZE,
                    borderRadius: 14,
                    boxShadow: 'var(--shadow)',
                }}
                onClick={(e) => e.stopPropagation()}
                role="dialog"
                aria-modal="true"
                aria-label={`${label} ${jobName}`.trim()}
            >
                <div className="shrink-0 border-b border-hairline bg-surface-2" style={{ padding: '14px 18px 0' }}>
                    <div className="flex items-start gap-3.5">
                        <div className="min-w-0">
                            <div className="flex items-center flex-wrap" style={{ gap: 12 }}>
                                <span
                                    className="font-mono"
                                    style={{
                                        fontWeight: 700,
                                        fontSize: 15,
                                        padding: '4px 10px',
                                        borderRadius: 6,
                                        color: 'var(--accent)',
                                        background: 'var(--accent-soft)',
                                    }}
                                >
                                    {label}
                                </span>
                                <span
                                    className="text-ink truncate"
                                    style={{ fontWeight: 700, fontSize: 20, letterSpacing: '-.3px' }}
                                >
                                    {jobName || '—'}
                                </span>
                                {description && (
                                    <span className="text-ink-2 truncate" style={{ fontWeight: 500, fontSize: 17 }}>
                                        {description}
                                    </span>
                                )}
                                {stage && (
                                    <span
                                        className="inline-block font-semibold"
                                        style={{ padding: '4px 11px', borderRadius: 6, fontSize: 13.5, background: tint.bg, color: tint.fg }}
                                    >
                                        {stage}
                                    </span>
                                )}
                            </div>
                            {context && (
                                <div className="text-ink-2 truncate" style={{ fontSize: 13.5, marginTop: 4 }} title={context}>
                                    {context}
                                </div>
                            )}
                        </div>
                        <div className="flex-1" />
                        <div className="flex items-center gap-1.5 shrink-0">
                            {/* Stage progress, compacted out of the Details pane and into the
                                header — it reads as identity, not as a section. */}
                            {stage && (
                                <span
                                    className="inline-flex items-center bg-surface border border-hairline"
                                    style={{ padding: '4px 8px', borderRadius: 8, marginRight: 4 }}
                                    title={stage}
                                >
                                    <StageIconRow stage={stage} iconSize={HEADER_BANANA_ICON_SIZE} />
                                </span>
                            )}
                            {procoreUrl ? (
                                <a href={procoreUrl} target="_blank" rel="noopener noreferrer" className={linkCls} style={linkStyle}>
                                    Procore
                                </a>
                            ) : (
                                <span className={linkCls} style={deadStyle} title="No Procore link on this release">Procore</span>
                            )}
                            {trelloUrl ? (
                                <a href={trelloUrl} target="_blank" rel="noopener noreferrer" className={linkCls} style={linkStyle}>
                                    Trello
                                </a>
                            ) : (
                                <span className={linkCls} style={deadStyle} title="No Trello card on this release">Trello</span>
                            )}
                            <button
                                onClick={onClose}
                                className="grid place-items-center border border-hairline-strong rounded-[7px] bg-surface text-ink-2 hover:text-ink"
                                style={{ width: 28, height: 28, marginLeft: 4 }}
                                aria-label="Close"
                            >
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                                    <path d="M6 6l12 12 M18 6L6 18" />
                                </svg>
                            </button>
                        </div>
                    </div>

                    <div className="flex items-center" style={{ gap: 18, marginTop: 12 }}>
                        {/* Attachments needs the release row's id to fetch versions/photos;
                            without it the pane would just render 404s, so drop the tab. */}
                        {TABS.filter((tab) => tab.key !== 'attachments' || releaseId != null).map((tab) => {
                            const active = tab.key === activeTab;
                            const showBadge = tab.key === 'attachments' && badgeCount > 0;
                            return (
                                <button
                                    key={tab.key}
                                    type="button"
                                    onClick={() => selectTab(tab.key)}
                                    aria-selected={active}
                                    role="tab"
                                    className="bg-transparent border-0 cursor-pointer inline-flex items-center gap-1.5"
                                    style={{
                                        padding: '8px 0 9px',
                                        fontSize: 13,
                                        fontWeight: active ? 700 : 500,
                                        color: active ? 'var(--text)' : 'var(--text-2)',
                                        boxShadow: active ? 'inset 0 -2px 0 0 var(--accent)' : 'none',
                                    }}
                                >
                                    {tab.label}
                                    {showBadge && (
                                        <span
                                            className="font-mono font-semibold"
                                            style={{
                                                fontSize: 11.5,
                                                padding: '1px 6px',
                                                borderRadius: 999,
                                                background: '#fef3c7',
                                                color: '#b45309',
                                                lineHeight: 1.3,
                                            }}
                                            aria-label={`${badgeCount} findings to confirm`}
                                        >
                                            {badgeCount}
                                        </span>
                                    )}
                                </button>
                            );
                        })}
                    </div>
                </div>

                {/* Body: pane | activity rail (rail only on Details + Change Log). */}
                <div
                    className="flex-1 min-h-0 grid"
                    style={{
                        gridTemplateColumns: showActivityRail
                            ? `minmax(0,1fr) ${ACTIVITY_RAIL_WIDTH}px`
                            : 'minmax(0,1fr)',
                    }}
                >
                    <div className="min-w-0 relative">
                        {visited.details && (
                            <div
                                ref={detailsScroll.ref}
                                onScroll={detailsScroll.onScroll}
                                className={`absolute inset-0 overflow-auto ${activeTab === 'details' ? '' : 'hidden'}`}
                                style={{ padding: '16px 18px 22px' }}
                                role="tabpanel"
                            >
                                <JobDetailsBody
                                    job={job}
                                    releaseId={releaseId}
                                    scrollToMaterials={scrollToMaterials}
                                    onOrdersChanged={onOrdersChanged}
                                    onJobUpdate={onJobUpdate}
                                    onStageChange={setLiveStage}
                                />
                            </div>
                        )}

                        {visited.attachments && releaseId != null && (
                            <div
                                className={`absolute inset-0 flex flex-col ${activeTab === 'attachments' ? '' : 'hidden'}`}
                                role="tabpanel"
                            >
                                <PdfVersionHistoryModal
                                    embedded
                                    isOpen
                                    releaseId={releaseId}
                                    title={label}
                                    viewerUrl={viewerUrl}
                                    initialCommentVersionId={initialCommentVersionId}
                                    onClose={onClose}
                                    onOpenVersion={onOpenVersion}
                                    onActionableCount={reportBadge}
                                />
                            </div>
                        )}

                        {visited.changelog && (
                            <div
                                ref={changelogScroll.ref}
                                onScroll={changelogScroll.onScroll}
                                className={`absolute inset-0 overflow-auto ${activeTab === 'changelog' ? '' : 'hidden'}`}
                                style={{ padding: '16px 18px 22px' }}
                                role="tabpanel"
                            >
                                <EventsList
                                    jobFilter={jobNumber}
                                    releaseFilter={releaseNumber}
                                    variant="hub"
                                />
                            </div>
                        )}
                    </div>

                    {showActivityRail && (
                        <ReleaseNotesRail
                            job={jobNumber}
                            release={releaseNumber}
                            currentNotes={job['Notes'] ?? job.notes}
                            onNotesChanged={onNotesChanged}
                        />
                    )}
                </div>
            </div>
        </div>
    );

    return createPortal(content, document.body);
}

export default ReleaseHubModal;
