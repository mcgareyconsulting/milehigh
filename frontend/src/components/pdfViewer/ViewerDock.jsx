/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Right dock of the hybrid PDF viewer — Review (Carmen findings) · Markups
 *   (saved markup versions) · Comments (@mention thread) · Info (version metadata),
 *   collapsible to a 30px rail so the canvas takes the width.
 * exports:
 *   ViewerDock: the 380px dock (tabs: review · markups · comments · info)
 * imports_from: [react, ./ReviewTab, ./format, ../shared/MentionInput]
 * imported_by: [frontend/src/components/pdfViewer/PdfViewerPane.jsx]
 * invariants:
 *   - Every tab is scoped to the open version; switching versions reloads its data
 *   - Tabs stay mounted while the dock is open, so a comment draft survives a tab switch
 *   - A markup is a whole saved PDF version (release_drawing_versions), not an
 *     annotation record — the Markups tab lists versions, and jumping means opening one
 * updated_by_agent: 2026-09-05T00:00:00Z
 */
import React from 'react';

import MentionInput from '../shared/MentionInput';
import { ReviewTab } from './ReviewTab';
import { fmtDate, fmtSize, renderCommentBody } from './format';

const CountBadge = ({ n }) => (
    n > 0 ? (
        <span
            className="font-bold"
            style={{ fontSize: 11, padding: '0 5px', borderRadius: 999, background: '#fef3c7', color: '#b45309' }}
        >
            {n}
        </span>
    ) : null
);

const PenIcon = () => (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </svg>
);

const ChatIcon = () => (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2Z" />
    </svg>
);

const InfoIcon = () => (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" />
    </svg>
);

export function ViewerDock({
    releaseId,
    version = null,
    versions = [],
    numPages = 0,
    viewerUrl = '',
    canReview = false,
    tab = 'review',
    onTab,
    collapsed = false,
    onToggleCollapse,
    // Comments
    comments,                 // undefined = loading, [] = none
    commentDraft = '',
    commentBusy = false,
    mentionableUsers = [],
    onCommentDraft,
    onSubmitComment,
    // Findings
    flags = 0,
    onCite,
    onFlagsChange,
    // Markups
    onOpenVersion = null,
}) {
    const commentCount = Array.isArray(comments) ? comments.length : 0;
    // Every saved markup lands as its own version derived from another one.
    const markups = versions.filter((v) => v.source_version_id != null);

    if (collapsed) {
        return (
            <div
                className="shrink-0 flex flex-col items-center border-l border-hairline bg-surface-2"
                style={{ width: 30 }}
            >
                <button
                    type="button"
                    onClick={onToggleCollapse}
                    className="bg-transparent border-0 cursor-pointer text-ink-3"
                    style={{ height: 34, width: 30, fontSize: 13 }}
                    aria-label="Expand panel"
                    title="Expand panel"
                >
                    ‹
                </button>
                {flags > 0 && (
                    <span
                        className="font-bold"
                        style={{ fontSize: 10.5, padding: '1px 4px', borderRadius: 999, background: '#fef3c7', color: '#b45309' }}
                    >
                        {flags}
                    </span>
                )}
            </div>
        );
    }

    const tabBtn = (key, label, icon, count) => {
        const active = tab === key;
        return (
            <button
                key={key}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => onTab?.(key)}
                className="flex-1 inline-flex items-center justify-center gap-1 border-0 cursor-pointer"
                style={{
                    padding: '9px 0',
                    fontSize: 12.5,
                    fontWeight: active ? 700 : 500,
                    color: active ? 'var(--text)' : 'var(--text-2)',
                    background: active ? 'var(--surface)' : 'transparent',
                    boxShadow: active ? 'inset 0 -2px 0 0 var(--accent)' : 'none',
                }}
            >
                {icon}
                {label}
                <CountBadge n={count} />
            </button>
        );
    };

    return (
        <div
            className="shrink-0 flex flex-col min-h-0 border-l border-hairline bg-surface"
            style={{ width: 380 }}
        >
            {/* Tab row */}
            <div className="shrink-0 flex items-stretch border-b border-hairline bg-surface-2" role="tablist">
                {tabBtn(
                    'review',
                    'Review',
                    <span
                        className="grid place-items-center text-white font-bold"
                        style={{ width: 17, height: 17, borderRadius: '50%', background: '#264093', fontSize: 7 }}
                        aria-hidden="true"
                    >
                        CM
                    </span>,
                    flags,
                )}
                {tabBtn('markups', 'Markups', <PenIcon />, markups.length)}
                {tabBtn('comments', 'Comments', <ChatIcon />, commentCount)}
                {tabBtn('info', 'Info', <InfoIcon />, 0)}
                <button
                    type="button"
                    onClick={onToggleCollapse}
                    className="shrink-0 border-0 border-l border-hairline bg-transparent cursor-pointer text-ink-3"
                    style={{ width: 30, fontSize: 13 }}
                    aria-label="Collapse panel"
                    title="Collapse panel"
                >
                    ›
                </button>
            </div>

            {/* Context chip */}
            <div
                className="shrink-0 flex items-center gap-1.5 border-b border-hairline bg-surface-2 text-ink-2"
                style={{ padding: '7px 12px', fontSize: 12.5 }}
            >
                <span aria-hidden="true">📄</span>
                <span className="truncate">
                    {version
                        ? `${version.original_filename || `Drawing v${version.version_number}`} v${version.version_number} · markups, comments & findings`
                        : 'No drawing selected'}
                </span>
            </div>

            <div className="flex-1 min-h-0 flex flex-col">
                {!version && (
                    <p className="text-ink-3" style={{ padding: '14px 12px', fontSize: 12.5 }}>
                        Upload a PDF to start a drawing history for this release.
                    </p>
                )}

                <div className={version && tab === 'review' ? 'flex-1 min-h-0 flex flex-col' : 'hidden'}>
                    {version && (
                    <ReviewTab
                        releaseId={releaseId}
                        versionId={version.id}
                        enabled={canReview}
                        onCite={onCite}
                        onFlagsChange={onFlagsChange}
                    />
                    )}
                </div>

                <div className={version && tab === 'markups' ? 'flex-1 min-h-0 overflow-y-auto' : 'hidden'} style={{ padding: '10px 12px' }}>
                        {markups.length === 0 && (
                            <p className="text-ink-3" style={{ fontSize: 12.5 }}>
                                No markups saved yet. “Edit markup” opens the editor; each save lands
                                here as its own version.
                            </p>
                        )}
                        <ul className="space-y-2">
                            {markups.map((m) => (
                                <li
                                    key={m.id}
                                    className="border border-hairline bg-surface"
                                    style={{ borderRadius: 8, padding: '8px 10px' }}
                                >
                                    <div className="flex items-baseline gap-2">
                                        <span className="font-semibold text-ink" style={{ fontSize: 13 }}>
                                            v{m.version_number}
                                        </span>
                                        <span className="text-ink-3" style={{ fontSize: 11.5 }}>
                                            {m.uploaded_by?.name || '—'}
                                        </span>
                                        <span className="text-ink-3 ml-auto" style={{ fontSize: 11.5 }}>
                                            {fmtSize(m.file_size_bytes)}
                                        </span>
                                    </div>
                                    <p className="text-ink-3" style={{ fontSize: 11.5, marginTop: 2 }}>
                                        {fmtDate(m.uploaded_at)} · from v-id {m.source_version_id}
                                    </p>
                                    {m.note && (
                                        <p className="text-ink-2 break-words" style={{ fontSize: 12.5, marginTop: 4 }}>
                                            {m.note}
                                        </p>
                                    )}
                                    {onOpenVersion && (
                                        <button
                                            type="button"
                                            onClick={() => onOpenVersion(m.id, 'view')}
                                            className="bg-transparent border-0 cursor-pointer text-brand font-semibold"
                                            style={{ fontSize: 12, marginTop: 6 }}
                                        >
                                            Open in markup editor
                                        </button>
                                    )}
                                </li>
                            ))}
                        </ul>
                </div>

                <div className={version && tab === 'comments' ? 'flex-1 min-h-0 flex flex-col' : 'hidden'}>
                        <div className="flex-1 min-h-0 overflow-y-auto space-y-2" style={{ padding: '10px 12px' }}>
                            {comments === undefined && <p className="text-xs text-ink-3 italic">Loading…</p>}
                            {Array.isArray(comments) && comments.length === 0 && (
                                <p className="text-ink-3" style={{ fontSize: 12.5 }}>
                                    No comments on this version yet.
                                </p>
                            )}
                            {Array.isArray(comments) && comments.map((c) => (
                                <div key={c.id} className="text-sm">
                                    <div className="flex items-baseline gap-2">
                                        <span className="font-semibold text-ink">{c.author_name}</span>
                                        <span className="text-xs text-ink-3">{fmtDate(c.created_at)}</span>
                                    </div>
                                    <p className="text-ink-2 break-words whitespace-pre-wrap">
                                        {renderCommentBody(c.body)}
                                    </p>
                                </div>
                            ))}
                        </div>
                        <div className="shrink-0 border-t border-hairline flex items-end gap-2" style={{ padding: '8px 10px 12px' }}>
                            <MentionInput
                                value={commentDraft}
                                onChange={(val) => onCommentDraft?.(val)}
                                onSubmit={() => onSubmitComment?.()}
                                users={mentionableUsers}
                                placeholder="Add a comment… @ to tag"
                                multiline
                                disabled={commentBusy}
                            />
                            <button
                                type="button"
                                onClick={() => onSubmitComment?.()}
                                disabled={commentBusy || !commentDraft.trim()}
                                className="px-3 py-1.5 text-xs bg-accent-600 text-white rounded-md font-semibold disabled:opacity-50 shrink-0"
                            >
                                Post
                            </button>
                        </div>
                </div>

                <div className={version && tab === 'info' ? 'flex-1 min-h-0 overflow-y-auto' : 'hidden'} style={{ padding: '12px' }}>
                        {version && (
                        <dl className="space-y-2" style={{ fontSize: 12.5 }}>
                            {[
                                ['File', version.original_filename || `Drawing v${version.version_number}`],
                                ['Version', `v${version.version_number}`],
                                ['Uploaded', fmtDate(version.uploaded_at)],
                                ['Uploaded by', version.uploaded_by?.name || '—'],
                                ['Size', fmtSize(version.file_size_bytes) || '—'],
                                ['Pages', numPages || '—'],
                                ['Derived from', version.source_version_id != null ? `v-id ${version.source_version_id}` : 'original upload'],
                                ['Note', version.note || '—'],
                            ].map(([k, v]) => (
                                <div key={k} className="flex gap-2">
                                    <dt className="text-ink-3 shrink-0" style={{ width: 96 }}>{k}</dt>
                                    <dd className="text-ink-2 break-words min-w-0">{v}</dd>
                                </div>
                            ))}
                        </dl>
                        )}
                        {viewerUrl && viewerUrl.trim() !== '' && (
                            <a
                                href={viewerUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center border border-hairline-strong rounded-[7px] bg-surface text-ink-2 font-semibold hover:bg-surface-2"
                                style={{ height: 28, padding: '0 11px', fontSize: 13, marginTop: 12 }}
                            >
                                ↗ View in Procore
                            </a>
                        )}
                </div>
            </div>
        </div>
    );
}

export default ViewerDock;
