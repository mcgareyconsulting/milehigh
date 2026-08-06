/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Single modal for a release — details, drawings/photos and change log behind tabs, with a threaded notes rail. Styled to the Aug 2026 redesign handoff §4.
 * exports:
 *   ReleaseHubModal: Portal modal with Details / Drawings & Photos / Change Log tabs
 * imports_from: [react, react-dom, ./JobDetailsBody, ./PdfVersionHistoryModal, ./EventsList, ./ReleaseNotesRail, ../utils/stageTint]
 * imported_by: [frontend/src/components/JobsTableRow.jsx, frontend/src/components/JobLogCardGrid.jsx, frontend/src/components/GanttChart.jsx]
 * invariants:
 *   - Renders via createPortal to document.body to escape table overflow clipping
 *   - Leaves a click-out margin around the panel: the backdrop stays reachable on every edge
 *   - A tab pane stays mounted once visited, so drafts and uploads survive tab switching
 *   - The notes rail sits OUTSIDE the tab panes — notes stay readable whichever tab is open
 * updated_by_agent: 2026-08-06T00:00:00Z
 */
import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

import { JobDetailsBody } from './JobDetailsBody';
import { PdfVersionHistoryModal } from './PdfVersionHistoryModal';
import { ReleaseNotesRail } from './ReleaseNotesRail';
import EventsList from './EventsList';
import { stageTint } from '../utils/stageTint';

const TABS = [
    { key: 'details', label: 'Details' },
    { key: 'drawings', label: 'Drawings & Photos' },
    { key: 'changelog', label: 'Change Log' },
];

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
}) {
    const [activeTab, setActiveTab] = useState(initialTab);
    // Panes render once activated and then stay mounted (hidden) so an
    // in-progress comment or note draft isn't thrown away by a tab switch.
    const [visited, setVisited] = useState(() => ({ [initialTab]: true }));

    useEffect(() => {
        if (!isOpen) return;
        setActiveTab(initialTab);
        setVisited((prev) => ({ ...prev, [initialTab]: true }));
    }, [isOpen, initialTab]);

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
    const stage = job['Stage'] || job.stage || '';
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
    const linkStyle = { height: 28, padding: '0 11px', fontSize: 12 };
    const deadStyle = { ...linkStyle, opacity: 0.45, cursor: 'not-allowed' };

    const context = [jobName, pm ? `PM ${pm}` : null, by ? `Detailed by ${by}` : null]
        .filter(Boolean).join(' · ');

    const content = (
        <div
            className="fixed inset-0 z-50 dc-fade flex items-center justify-center p-4"
            style={{ background: 'rgba(10,16,28,.55)', backdropFilter: 'blur(2px)' }}
            onClick={onClose}
        >
            <div
                className="dc-pop bg-surface border border-hairline-strong flex flex-col overflow-hidden"
                style={{
                    width: 'min(1180px, 94vw)',
                    height: 'min(760px, 92vh)',
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
                            <div className="flex items-center gap-2.5 flex-wrap">
                                <span
                                    className="font-mono font-semibold text-brand bg-brand-soft"
                                    style={{ fontSize: 12, padding: '3px 8px', borderRadius: 5 }}
                                >
                                    {label}
                                </span>
                                <span className="font-bold text-ink truncate" style={{ fontSize: 17, letterSpacing: '-.3px' }}>
                                    {description || '—'}
                                </span>
                                {stage && (
                                    <span
                                        className="inline-block font-semibold"
                                        style={{ padding: '3px 9px', borderRadius: 5, fontSize: 11.5, background: tint.bg, color: tint.fg }}
                                    >
                                        {stage}
                                    </span>
                                )}
                            </div>
                            {context && (
                                <div className="text-jl text-ink-2 truncate" style={{ marginTop: 3 }} title={context}>
                                    {context}
                                </div>
                            )}
                        </div>
                        <div className="flex-1" />
                        <div className="flex items-center gap-1.5 shrink-0">
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
                        {/* Drawings needs the release row's id to fetch versions/photos;
                            without it the pane would just render 404s, so drop the tab. */}
                        {TABS.filter((tab) => tab.key !== 'drawings' || releaseId != null).map((tab) => {
                            const active = tab.key === activeTab;
                            return (
                                <button
                                    key={tab.key}
                                    type="button"
                                    onClick={() => selectTab(tab.key)}
                                    aria-selected={active}
                                    role="tab"
                                    className="bg-transparent border-0 cursor-pointer"
                                    style={{
                                        padding: '8px 0 9px',
                                        fontSize: 13,
                                        fontWeight: active ? 700 : 500,
                                        color: active ? 'var(--text)' : 'var(--text-2)',
                                        boxShadow: active ? 'inset 0 -2px 0 0 var(--accent)' : 'none',
                                    }}
                                >
                                    {tab.label}
                                </button>
                            );
                        })}
                    </div>
                </div>

                {/* Body: pane | notes rail. The rail is a sibling of the panes, not
                    inside one, so notes stay visible on every tab. */}
                <div className="flex-1 min-h-0 grid" style={{ gridTemplateColumns: 'minmax(0,1fr) 372px' }}>
                    <div className="min-w-0 relative">
                        {visited.details && (
                            <div
                                className={`absolute inset-0 overflow-auto ${activeTab === 'details' ? '' : 'hidden'}`}
                                style={{ padding: '16px 18px 22px' }}
                                role="tabpanel"
                            >
                                <JobDetailsBody
                                    job={job}
                                    scrollToMaterials={scrollToMaterials}
                                    onOrdersChanged={onOrdersChanged}
                                />
                            </div>
                        )}

                        {visited.drawings && releaseId != null && (
                            <div
                                className={`absolute inset-0 flex flex-col ${activeTab === 'drawings' ? '' : 'hidden'}`}
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
                                />
                            </div>
                        )}

                        {visited.changelog && (
                            <div
                                className={`absolute inset-0 overflow-auto ${activeTab === 'changelog' ? '' : 'hidden'}`}
                                style={{ padding: '16px 18px 22px' }}
                                role="tabpanel"
                            >
                                <EventsList jobFilter={jobNumber} releaseFilter={releaseNumber} />
                            </div>
                        )}
                    </div>

                    <ReleaseNotesRail
                        job={jobNumber}
                        release={releaseNumber}
                        currentNotes={job['Notes'] ?? job.notes}
                    />
                </div>
            </div>
        </div>
    );

    return createPortal(content, document.body);
}

export default ReleaseHubModal;
