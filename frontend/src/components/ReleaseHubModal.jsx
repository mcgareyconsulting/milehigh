/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The single release modal — Details / Attachments / Issues / Splices / Change Log — opened from the Job
 *   Log table, the card grid, the Timeline, Archive and Subs. Activity rail on Details and
 *   Change Log (hidden on Attachments for the full-width viewer).
 * exports:
 *   ReleaseHubModal: Portal modal shell for a release
 * imports_from: [react, react-dom, ./JobDetailsBody, ./pdfViewer/PdfViewerPane, ./EventsList,
 *   ./ReleaseNotesRail, ./StageIconRow, ./releaseIssues/ReleaseIssuesPane, ./SplicesPane,
 *   ../services/jobsApi, ../utils/stageTint, ../utils/auth, ../constants/modalSize, ../hooks/useBreakpoint]
 * imported_by: [frontend/src/components/JobsTableRow.jsx, frontend/src/components/JobLogCardGrid.jsx,
 *   frontend/src/components/GanttChart.jsx]
 * invariants:
 *   - Renders via createPortal to document.body to escape table overflow clipping
 *   - Leaves a click-out margin around the panel: the backdrop stays reachable on every edge
 *   - A tab pane stays mounted once visited, so drafts and uploads survive tab switching
 *   - Activity rail renders on Details + Change Log only — Attachments takes the full width
 *   - ON A PHONE THE RAIL IS A TAB, not a column. It is a FIXED 346px beside a `minmax(0,1fr)` pane,
 *     so on a 390px screen the pane collapsed to a ~40px ribbon of single-letter lines with the rail
 *     overflowing across it — the two read as one broken, overlapping surface. Below `md` it becomes
 *     a fourth tab and takes the full width instead. Nothing is lost by moving it: the rail already
 *     unmounts when Attachments is selected, so it has never survived a tab switch anyway.
 *   - The header's right cluster (bananas / Procore / Trello / close) must NEVER be `shrink-0` on a
 *     phone. It was, and at ~330px it starved the `min-w-0` title block down to about 28px — which is
 *     why the job-release label wrapped one number per line — while pushing the CLOSE BUTTON off the
 *     panel entirely, leaving no way out of the modal but the backdrop.
 *   - The header owns the stage pill and the compact banana row; both follow an in-pane stage
 *     edit immediately via onStageChange, without waiting for the host's refetch
 *   - Header identity is ONE line: label, job, description, stage, then PM/detailer
 *   - Issues (Release Issue Register, T11) is ADMIN-ONLY in v1 and needs the release id; the
 *     server gates every issue route regardless, the tab check is presentation only
 *   - Splices (T9) is a tab for everyone with a release id. Opening another release of the splice
 *     group swaps the hub to that row IN PLACE (mirror-card style): the host's `job` is the root, the
 *     opened rows are a stack, and the header's back button returns to the previous row on the tab
 *     you left it from. Panes are keyed by release id so nothing from the previous row leaks across.
 *     Edits on an opened row refetch that row (GET get-all-jobs?release_id) as well as the host list.
 * updated_by_agent: 2026-09-16T00:00:00Z
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import { JobDetailsBody } from './JobDetailsBody';
import { PdfViewerPane } from './pdfViewer/PdfViewerPane';
import { ReleaseNotesRail } from './ReleaseNotesRail';
import EventsList from './EventsList';
import { StageIconRow } from './StageIconRow';
import { ReleaseIssuesPane } from './releaseIssues/ReleaseIssuesPane';
import { SplicesPane } from './SplicesPane';
import { jobsApi } from '../services/jobsApi';
import { stageTint } from '../utils/stageTint';
import { checkAuth, readCachedRoleFlags } from '../utils/auth';
import { MODAL_PANEL_SIZE } from '../constants/modalSize';
import { usePersistScroll } from '../hooks/usePersistScroll';
import { useBreakpoint } from '../hooks/useBreakpoint';

const TABS = [
    { key: 'details', label: 'Details' },
    { key: 'attachments', label: 'Attachments' },
    { key: 'issues', label: 'Issues', adminOnly: true },
    { key: 'splices', label: 'Splices' },
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
    job: hostJob,
    releaseId: hostReleaseId,
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
    /** Opens the Issues tab on this issue (notification click-through). */
    initialIssueId = null,
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
    // Phones get the Activity rail as a tab rather than a column (see invariants).
    const { isMobile } = useBreakpoint();
    // Stage the header renders. Seeded from the row, then owned by the Details
    // pane's select until the host's refetch brings a fresh row in.
    const [liveStage, setLiveStage] = useState(null);
    // Issues tab is admin-only. Cached role flags paint first; checkAuth confirms.
    const [isAdmin, setIsAdmin] = useState(() => readCachedRoleFlags().isAdmin);
    const [openIssueCount, setOpenIssueCount] = useState(0);
    const [spliceCount, setSpliceCount] = useState(0);
    // Splice-group navigation: rows opened from the Splices tab, stacked over the host's row.
    // Each frame remembers the tab it was opened from so Back lands where you were.
    const [frames, setFrames] = useState([]);
    const [navBusy, setNavBusy] = useState(false);
    const [navError, setNavError] = useState(null);
    const pendingTabRef = useRef(null);

    const topFrame = frames.length ? frames[frames.length - 1] : null;
    const job = topFrame ? topFrame.job : hostJob;
    const releaseId = topFrame ? topFrame.job?.id : hostReleaseId;

    // A new host row (or reopening) starts a fresh stack.
    useEffect(() => {
        setFrames([]);
        setNavError(null);
    }, [isOpen, hostJob?.id]);

    useEffect(() => {
        if (!isOpen) return;
        let cancelled = false;
        checkAuth().then((u) => { if (!cancelled) setIsAdmin(!!u?.is_admin); });
        return () => { cancelled = true; };
    }, [isOpen]);

    useEffect(() => {
        if (!isOpen) return;
        const pending = pendingTabRef.current;
        pendingTabRef.current = null;
        const tab = pending || normalizeTab(initialTab);
        setActiveTab(tab);
        // Moving across the splice group starts the new row's panes fresh.
        setVisited((prev) => (pending ? { [tab]: true } : { ...prev, [tab]: true }));
        setBadgeFromPane(0);
        setOpenIssueCount(0);
        setLiveStage(null);
        detailsScrollStore.current = 0;
        changelogScrollStore.current = 0;
    }, [isOpen, initialTab, job?.id, initialIssueId]);

    // Splice count for the tab badge; the pane refreshes it after a create.
    useEffect(() => {
        if (!isOpen || releaseId == null) { setSpliceCount(0); return undefined; }
        let cancelled = false;
        // Promise-wrapped so a throw of any kind only costs the badge.
        Promise.resolve()
            .then(() => jobsApi.getSplices(releaseId))
            .then((data) => { if (!cancelled) setSpliceCount(data?.splices?.length || 0); })
            .catch(() => { if (!cancelled) setSpliceCount(0); });
        return () => { cancelled = true; };
    }, [isOpen, releaseId]);

    const openRelease = useCallback(async (id) => {
        if (id == null || id === releaseId) return;
        setNavError(null);
        // Already in the chain (the host row or an earlier frame): unwind to it.
        if (id === hostReleaseId || id === hostJob?.id) {
            pendingTabRef.current = 'details';
            setFrames([]);
            return;
        }
        const idx = frames.findIndex((f) => f.job?.id === id);
        if (idx >= 0) {
            pendingTabRef.current = 'details';
            setFrames(frames.slice(0, idx + 1));
            return;
        }
        setNavBusy(true);
        try {
            const row = await jobsApi.getRelease(id);
            if (!row) throw new Error('That release no longer exists');
            pendingTabRef.current = 'details';
            setFrames((prev) => [...prev, { job: row, returnTab: activeTab }]);
        } catch (err) {
            setNavError(err.message || 'Could not open that release');
        } finally {
            setNavBusy(false);
        }
    }, [releaseId, hostReleaseId, hostJob?.id, frames, activeTab]);

    const goBack = () => {
        if (!topFrame) return;
        pendingTabRef.current = topFrame.returnTab || 'details';
        setNavError(null);
        setFrames((prev) => prev.slice(0, -1));
    };

    // Edits on an opened (non-host) row: refetch that row too, since the host only owns its own.
    const refreshTopFrame = useCallback(async () => {
        const id = topFrame?.job?.id;
        if (id == null) return;
        try {
            const row = await jobsApi.getRelease(id);
            if (row) setFrames((prev) => prev.map((f) => (f.job?.id === id ? { ...f, job: row } : f)));
        } catch { /* keep the row we have */ }
    }, [topFrame?.job?.id]);

    const handleJobUpdate = useCallback((...args) => {
        onJobUpdate?.(...args);
        if (topFrame) refreshTopFrame();
    }, [onJobUpdate, topFrame, refreshTopFrame]);

    const handleNotesChanged = (notes) => {
        if (topFrame) {
            setFrames((prev) => prev.map((f, i) => (
                i === prev.length - 1 ? { ...f, job: { ...f.job, Notes: notes, notes } } : f
            )));
            onJobUpdate?.();
            return;
        }
        onNotesChanged?.(notes);
    };

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
    const backJob = frames.length > 1 ? frames[frames.length - 2].job : hostJob;
    const backLabel = backJob
        ? `${backJob['Job #'] || backJob.job || ''}-${backJob['Release #'] || backJob.release || ''}`
        : '';
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

    // Attachments needs the release row's id to fetch versions/photos; without it the pane would
    // just render 404s, so that tab drops out. Activity is a tab only where the rail cannot fit.
    const tabs = [
        ...TABS.filter((tab) => {
            if (tab.key === 'attachments' || tab.key === 'issues' || tab.key === 'splices') {
                if (releaseId == null) return false;
            }
            return !tab.adminOnly || isAdmin;
        }),
        ...(isMobile ? [{ key: 'activity', label: 'Activity' }] : []),
    ];
    const showActivityRail = !isMobile && (activeTab === 'details' || activeTab === 'changelog');
    const badgeCount = Math.max(0, Number(attachmentsBadgeCount) || 0, Number(badgeFromPane) || 0);

    const reportBadge = (n) => {
        const count = Math.max(0, Number(n) || 0);
        setBadgeFromPane(count);
        onAttachmentsBadgeCount?.(count);
    };

    const content = (
        <div
            className="fixed inset-0 z-50 dc-fade flex items-center justify-center p-2 sm:p-4"
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
                <div className="shrink-0 border-b border-hairline bg-surface-2 px-3 sm:px-[18px]" style={{ paddingTop: 12 }}>
                    <div className="flex items-start gap-2 sm:gap-3.5 flex-wrap">
                        {/* Full width on a phone: sharing the row is what collapsed this block to
                            28px and wrapped "170-561" one number per line. */}
                        <div className="min-w-0 w-full sm:w-auto order-2 sm:order-1">
                            <div className="flex items-center flex-wrap gap-x-2 gap-y-1 sm:gap-3">
                                {topFrame && (
                                    <button
                                        type="button"
                                        onClick={goBack}
                                        className="inline-flex items-center gap-1 border border-hairline-strong rounded-[7px] bg-surface text-ink-2 font-semibold hover:bg-surface-2 hover:text-ink whitespace-nowrap"
                                        style={{ height: 28, padding: '0 9px', fontSize: 13 }}
                                        title="Back to the previous release"
                                    >
                                        <span aria-hidden="true">←</span>
                                        <span className="font-mono">{backLabel}</span>
                                    </button>
                                )}
                                <span
                                    className="font-mono whitespace-nowrap text-[13px] sm:text-[15px]"
                                    style={{
                                        fontWeight: 700,
                                        padding: '4px 10px',
                                        borderRadius: 6,
                                        color: 'var(--accent)',
                                        background: 'var(--accent-soft)',
                                    }}
                                >
                                    {label}
                                </span>
                                <span
                                    className="text-ink truncate text-base sm:text-xl"
                                    style={{ fontWeight: 700, letterSpacing: '-.3px' }}
                                >
                                    {jobName || '—'}
                                </span>
                                {description && (
                                    <span className="text-ink-2 truncate text-[13px] sm:text-[17px]" style={{ fontWeight: 500 }}>
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
                                {/* Attribution rides the identity line rather than owning a
                                    second row — the header costs one line, not two. */}
                                {context && (
                                    <span className="text-ink-3 truncate" style={{ fontSize: 13.5 }} title={context}>
                                        {context}
                                    </span>
                                )}
                            </div>
                        </div>
                        {/* order-1 so it sorts AFTER the title block (sm:order-1, later in DOM)
                            and before the link cluster (order-2). At order 0 it sorted first
                            and pushed the whole title block to the right. */}
                        <div className="hidden sm:block flex-1 sm:order-1" />
                        {/* Never shrink-0 on a phone: at ~330px this cluster starved the title block
                            and pushed the close button off the panel. */}
                        <div className="flex items-center gap-1.5 ml-auto shrink-0 order-1 sm:order-2">
                            {/* Stage progress, compacted out of the Details pane and into the
                                header — it reads as identity, not as a section. Hidden on a phone:
                                seven bananas is ~360px of decoration on a 390px screen. */}
                            {stage && (
                                <span
                                    className="hidden sm:inline-flex items-center bg-surface border border-hairline"
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
                        {tabs.map((tab) => {
                            const active = tab.key === activeTab;
                            const showBadge = tab.key === 'attachments' && badgeCount > 0;
                            const showIssueCount = tab.key === 'issues' && openIssueCount > 0;
                            const showSpliceCount = tab.key === 'splices' && spliceCount > 0;
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
                                    {showIssueCount && (
                                        <span
                                            className="font-mono font-semibold"
                                            style={{
                                                fontSize: 11.5,
                                                padding: '1px 6px',
                                                borderRadius: 999,
                                                background: 'var(--accent-soft)',
                                                color: 'var(--accent)',
                                                lineHeight: 1.3,
                                            }}
                                            aria-label={`${openIssueCount} open issues`}
                                        >
                                            {openIssueCount}
                                        </span>
                                    )}
                                    {showSpliceCount && (
                                        <span
                                            className="font-mono font-semibold"
                                            style={{
                                                fontSize: 11.5,
                                                padding: '1px 6px',
                                                borderRadius: 999,
                                                background: 'var(--surface-2)',
                                                color: 'var(--text-2)',
                                                lineHeight: 1.3,
                                            }}
                                            aria-label={`${spliceCount} splices`}
                                        >
                                            {spliceCount}
                                        </span>
                                    )}
                                </button>
                            );
                        })}
                        {(navBusy || navError) && (
                            <span
                                className="text-jl-2 ml-auto"
                                style={{ color: navError ? 'var(--fl-red-fg)' : 'var(--text-3)' }}
                                role={navError ? 'alert' : undefined}
                            >
                                {navError || 'Opening…'}
                            </span>
                        )}
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
                                    key={releaseId ?? 'no-id'}
                                    job={job}
                                    releaseId={releaseId}
                                    scrollToMaterials={scrollToMaterials}
                                    onOrdersChanged={onOrdersChanged}
                                    onJobUpdate={handleJobUpdate}
                                    onStageChange={setLiveStage}
                                />
                            </div>
                        )}

                        {visited.attachments && releaseId != null && (
                            <div
                                className={`absolute inset-0 flex flex-col ${activeTab === 'attachments' ? '' : 'hidden'}`}
                                role="tabpanel"
                            >
                                <PdfViewerPane
                                    key={releaseId}
                                    releaseId={releaseId}
                                    label={label}
                                    viewerUrl={viewerUrl}
                                    initialCommentVersionId={initialCommentVersionId}
                                    onOpenVersion={onOpenVersion}
                                    onActionableCount={reportBadge}
                                />
                            </div>
                        )}

                        {isAdmin && visited.issues && releaseId != null && (
                            <div
                                className={`absolute inset-0 ${activeTab === 'issues' ? '' : 'hidden'}`}
                                role="tabpanel"
                            >
                                <ReleaseIssuesPane
                                    key={releaseId}
                                    releaseId={releaseId}
                                    initialIssueId={initialIssueId}
                                    onSummary={(s) => setOpenIssueCount(s?.open_count || 0)}
                                />
                            </div>
                        )}

                        {visited.splices && releaseId != null && (
                            <div
                                className={`absolute inset-0 overflow-auto ${activeTab === 'splices' ? '' : 'hidden'}`}
                                style={{ padding: '16px 18px 22px' }}
                                role="tabpanel"
                            >
                                <SplicesPane
                                    releaseId={releaseId}
                                    onOpenRelease={openRelease}
                                    onChanged={handleJobUpdate}
                                    onCount={setSpliceCount}
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
                                    key={releaseId ?? label}
                                    jobFilter={jobNumber}
                                    releaseFilter={releaseNumber}
                                    variant="hub"
                                />
                            </div>
                        )}

                        {/* Phone only: the rail as a full-width pane. Same component the desktop
                            column renders, so notes behave identically either way. */}
                        {isMobile && visited.activity && (
                            <div
                                className={`absolute inset-0 flex flex-col ${activeTab === 'activity' ? '' : 'hidden'}`}
                                role="tabpanel"
                            >
                                <ReleaseNotesRail
                                    key={label}
                                    job={jobNumber}
                                    release={releaseNumber}
                                    currentNotes={job['Notes'] ?? job.notes}
                                    onNotesChanged={handleNotesChanged}
                                />
                            </div>
                        )}
                    </div>

                    {showActivityRail && (
                        <ReleaseNotesRail
                            key={label}
                            job={jobNumber}
                            release={releaseNumber}
                            currentNotes={job['Notes'] ?? job.notes}
                            onNotesChanged={handleNotesChanged}
                        />
                    )}
                </div>
            </div>
        </div>
    );

    return createPortal(content, document.body);
}

export default ReleaseHubModal;
