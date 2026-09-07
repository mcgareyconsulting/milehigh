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
 *   - The Markups tab groups markups by the version each first appeared in, and reports
 *     the PAGES they sit on; a row scrolls the canvas to that page
 * updated_by_agent: 2026-09-05T00:00:00Z
 */
import React from 'react';

import MentionInput from '../shared/MentionInput';
import { ReviewTab } from './ReviewTab';
import { fmtDate, fmtSize, renderCommentBody } from './format';

//: pdf.js annotation subtypes, in the reviewer's words.
const MARKUP_TYPE_LABEL = { Ink: 'Pen / shape', FreeText: 'Text', Stamp: 'Stamp' };

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

const Chevron = ({ dir = 'right', size = 18 }) => {
    const path = {
        right: 'M9 6l6 6-6 6',
        left: 'M15 6l-6 6 6 6',
        down: 'M6 9l6 6 6-6',
    }[dir];
    return (
        <svg
            width={size} height={size} viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"
            aria-hidden="true"
        >
            <path d={path} />
        </svg>
    );
};

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
    // Markups — the annotations on the open version (Option 4c), not the version list.
    markups = [],
    markupDirty = false,
    onJumpToPage = null,
}) {
    const [expandedGroup, setExpandedGroup] = React.useState(null);   // null = newest only
    const [collapsedOverride, setCollapsedOverride] = React.useState(() => new Set());

    const commentCount = Array.isArray(comments) ? comments.length : 0;

    // One group per version that introduced markup. Annotations carry over between
    // versions, so `versionNumber` is the version a shape FIRST appeared in — that is the
    // session a reviewer thinks in, and it is what the flat list failed to convey.
    const versionMeta = new Map(versions.map((v) => [v.version_number, v]));
    const markupGroups = [];
    const groupIndex = new Map();
    markups.forEach((m) => {
        const key = m.versionNumber == null ? 'unsaved' : `v${m.versionNumber}`;
        if (!groupIndex.has(key)) {
            const meta = versionMeta.get(m.versionNumber);
            groupIndex.set(key, markupGroups.length);
            markupGroups.push({
                key,
                versionNumber: m.versionNumber ?? null,
                subtitle: meta
                    ? [meta.uploaded_by?.name, fmtDate(meta.uploaded_at)].filter(Boolean).join(' · ')
                    : 'not yet saved',
                items: [],
                byPage: new Map(),
                pages: [],
            });
        }
        const group = markupGroups[groupIndex.get(key)];
        group.items.push(m);
        group.byPage.set(m.page, (group.byPage.get(m.page) || 0) + 1);
    });
    // Which pages carry markup — not how many are on each. Presence is the signal.
    markupGroups.forEach((g) => { g.pages = [...g.byPage.keys()].sort((a, b) => a - b); });
    // Newest first; anything not yet saved leads.
    markupGroups.sort((a, b) => (b.versionNumber ?? Infinity) - (a.versionNumber ?? Infinity));

    // By default only the newest group is open: at v10 the history should be ten lines,
    // not ten open lists. Clicking a header toggles that group.
    const newestKey = markupGroups[0]?.key;
    const collapsedGroups = new Set(
        markupGroups
            .filter((g) => (g.key === newestKey
                ? collapsedOverride.has(g.key)
                : g.key !== expandedGroup))
            .map((g) => g.key),
    );
    const toggleGroup = (key) => {
        if (key === newestKey) {
            setCollapsedOverride((prev) => {
                const next = new Set(prev);
                if (next.has(key)) next.delete(key); else next.add(key);
                return next;
            });
            return;
        }
        setExpandedGroup((prev) => (prev === key ? null : key));
    };
    // The version list lives in the title menu; this tab is about the markups themselves.
    const savedMarkupVersions = versions.filter((v) => v.source_version_id != null);

    if (collapsed) {
        return (
            <div
                className="shrink-0 flex flex-col items-center border-l border-hairline bg-surface-2"
                style={{ width: 30 }}
            >
                <button
                    type="button"
                    onClick={onToggleCollapse}
                    className="grid place-items-center bg-transparent border-0 cursor-pointer text-ink-2 hover:text-ink"
                    style={{ height: 44, width: 30 }}
                    aria-label="Expand panel"
                    title="Expand panel"
                >
                    <Chevron dir="left" />
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
                {tabBtn('markups', 'Markups', <PenIcon />, markups.length || savedMarkupVersions.length)}
                {tabBtn('comments', 'Comments', <ChatIcon />, commentCount)}
                {tabBtn('info', 'Info', <InfoIcon />, 0)}
                <button
                    type="button"
                    onClick={onToggleCollapse}
                    className="shrink-0 grid place-items-center border-0 border-l border-hairline bg-transparent cursor-pointer text-ink-2 hover:text-ink"
                    style={{ width: 32 }}
                    aria-label="Collapse panel"
                    title="Collapse panel"
                >
                    <Chevron dir="right" />
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
                        ? `${version.original_filename || `Drawing v${version.version_number}`} v${version.version_number} · marking up`
                        : 'No drawing selected'}
                </span>
                {markupDirty && (
                    <span className="ml-auto shrink-0 font-semibold" style={{ fontSize: 12, color: '#b45309' }}>
                        unsaved
                    </span>
                )}
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
                                No markups on this version yet. Pick a tool from the pill and
                                draw; Save version commits them.
                            </p>
                        )}

                        {/* One line per version, then the pages it touched — a version with
                            12 shapes on two sheets is two page chips, not twelve rows. */}
                        <div className="space-y-1.5">
                            {markupGroups.map((group) => {
                                const open = !collapsedGroups.has(group.key);
                                return (
                                    <section
                                        key={group.key}
                                        className="border border-hairline bg-surface"
                                        style={{ borderRadius: 8 }}
                                    >
                                        <button
                                            type="button"
                                            onClick={() => toggleGroup(group.key)}
                                            aria-expanded={open}
                                            className="w-full flex items-center gap-2 bg-transparent border-0 cursor-pointer text-left"
                                            style={{ padding: '8px 10px' }}
                                        >
                                            <span
                                                className="text-ink-3 shrink-0 grid place-items-center"
                                                style={{ width: 16, height: 16 }}
                                            >
                                                <Chevron dir={open ? 'down' : 'right'} size={15} />
                                            </span>
                                            <span className="font-bold text-ink shrink-0" style={{ fontSize: 13 }}>
                                                {group.versionNumber != null ? `v${group.versionNumber}` : 'Unsaved'}
                                            </span>
                                            <span className="text-ink-3 truncate" style={{ fontSize: 11.5 }}>
                                                {group.subtitle}
                                            </span>
                                            <span className="text-ink-3 shrink-0 ml-auto" style={{ fontSize: 11.5 }}>
                                                {group.pages.length} page{group.pages.length === 1 ? '' : 's'}
                                            </span>
                                        </button>

                                        {open && (
                                            <div className="border-t border-hairline">
                                                {group.pages.map((page) => (
                                                    <button
                                                        key={page}
                                                        type="button"
                                                        onClick={() => onJumpToPage?.(page)}
                                                        className="w-full flex items-center gap-2 bg-transparent border-0 cursor-pointer text-left hover:bg-surface-2"
                                                        style={{ padding: '8px 10px' }}
                                                        title={`Scroll to page ${page}`}
                                                    >
                                                        <span className="font-semibold text-ink" style={{ fontSize: 12.5 }}>
                                                            Page {page}
                                                        </span>
                                                        <span className="ml-auto text-ink-3 shrink-0 grid place-items-center">
                                                            <Chevron dir="right" size={14} />
                                                        </span>
                                                    </button>
                                                ))}
                                            </div>
                                        )}
                                    </section>
                                );
                            })}
                        </div>
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
                        <div className="shrink-0 border-t border-hairline flex items-end gap-2" style={{ padding: '10px 12px 12px' }}>
                            {/* MentionInput defaults to rows=1 + text-xs, which collapses to a
                                sliver on this dock — give it a real composer's shape. */}
                            <MentionInput
                                value={commentDraft}
                                onChange={(val) => onCommentDraft?.(val)}
                                onSubmit={() => onSubmitComment?.()}
                                users={mentionableUsers}
                                placeholder="Add a comment… @ to tag"
                                multiline
                                rows={3}
                                className="w-full resize-none overflow-y-auto max-h-40 px-3 py-2 text-sm leading-snug border border-hairline-strong rounded-[10px] bg-surface text-ink placeholder:text-ink-3 focus:outline-none focus:ring-1 focus:ring-accent-500 focus:border-transparent"
                                disabled={commentBusy}
                            />
                            <button
                                type="button"
                                onClick={() => onSubmitComment?.()}
                                disabled={commentBusy || !commentDraft.trim()}
                                className="px-3 text-sm bg-accent-600 text-white rounded-lg font-semibold disabled:opacity-50 shrink-0"
                                style={{ height: 34 }}
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
