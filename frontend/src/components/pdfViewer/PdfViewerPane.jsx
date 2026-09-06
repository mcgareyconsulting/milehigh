/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The release's drawing surface — one hybrid viewer. The title itself is the
 *   document/version switcher, the canvas fills the pane, and the right dock carries
 *   Carmen findings, markups, comments and version info. Replaces the old drawings rail.
 * exports:
 *   PdfViewerPane: props { releaseId, label, viewerUrl, initialCommentVersionId,
 *     onOpenVersion, onActionableCount }
 * imports_from: [react, ../PdfReadViewer, ./ViewerDock, ./ProcorePullDialog, ./format,
 *   ../../services/jobsApi,
 *   ../../services/notificationApi, ../../utils/api, ../../utils/auth]
 * imported_by: [frontend/src/components/ReleaseHubModal.jsx,
 *   frontend/src/components/PdfViewerModal.jsx]
 * invariants:
 *   - Newest version is selected on load; picking one from the title menu swaps the canvas
 *   - Markup authoring stays in PdfMarkupModal — "Edit markup" hands off via onOpenVersion
 *   - Escape closes the open title menu without closing the host modal
 *   - Photos are not here; they live on the Details pane and the stage-photo gate
 *   - "Pull from Procore" sits in the top strip for drafters/admins, matching the route —
 *     it is the release-side counterpart to the nightly worker's link-only pass
 * updated_by_agent: 2026-09-05T00:00:00Z
 */
import React, { useEffect, useRef, useState } from 'react';

import { API_BASE_URL } from '../../utils/api';
import { jobsApi } from '../../services/jobsApi';
import { fetchMentionableUsers } from '../../services/notificationApi';
import { checkAuth } from '../../utils/auth';
import { actionableCount } from '../bbReview/urgency';
import { PdfReadViewer } from '../PdfReadViewer';
import { ProcorePullDialog } from './ProcorePullDialog';
import { ViewerDock } from './ViewerDock';
import { fmtDate, fmtSize } from './format';

export function PdfViewerPane({
    releaseId,
    /** Job-release label ("340-666"), shown on the Procore pull dialog. */
    label = '',
    viewerUrl = '',
    /** Land on this version's comment thread (notification bell click-through). */
    initialCommentVersionId = null,
    /** (versionId, mode) => void — hands off to PdfMarkupModal. Hidden when absent. */
    onOpenVersion = null,
    /** (count:number) => void — actionable Carmen findings, for the hub tab badge. */
    onActionableCount = null,
}) {
    const [versions, setVersions] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [uploading, setUploading] = useState(false);
    const [viewingVersionId, setViewingVersionId] = useState(null);
    const [menuOpen, setMenuOpen] = useState(false);
    const [numPages, setNumPages] = useState(0);
    const [citePage, setCitePage] = useState(null);
    const [citeRuleId, setCiteRuleId] = useState(null);
    const [dockTab, setDockTab] = useState('review');
    const [dockCollapsed, setDockCollapsed] = useState(false);
    const [pullOpen, setPullOpen] = useState(false);
    const [canReview, setCanReview] = useState(false);
    // versionId → actionable finding count (hub Attachments badge).
    const [flagsByVersion, setFlagsByVersion] = useState({});
    const [commentsByVersion, setCommentsByVersion] = useState({});
    const [commentDrafts, setCommentDrafts] = useState({});
    const [commentBusy, setCommentBusy] = useState({});
    const [mentionableUsers, setMentionableUsers] = useState([]);
    const pdfInputRef = useRef(null);
    const menuRef = useRef(null);

    const loadVersions = async () => {
        if (!releaseId) return;
        setLoading(true);
        setError(null);
        try {
            const resp = await fetch(`${API_BASE_URL}/brain/releases/${releaseId}/drawing/versions`, {
                credentials: 'include',
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            setVersions(data?.versions ?? []);
        } catch (err) {
            setError(err?.message || 'Failed to load versions');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadVersions();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [releaseId]);

    useEffect(() => {
        if (mentionableUsers.length > 0) return;
        fetchMentionableUsers().then(setMentionableUsers).catch(() => {});
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // Carmen review loop: admin OR drafter (backend: drafter_or_admin_required).
    useEffect(() => {
        checkAuth()
            .then((u) => setCanReview(!!(u?.is_admin || u?.is_drafter)))
            .catch(() => setCanReview(false));
    }, []);

    // Newest drawing wins once versions land, unless the bell pointed at one.
    useEffect(() => {
        if (!versions.length) return;
        setViewingVersionId((cur) => {
            if (cur != null && versions.some((v) => v.id === cur)) return cur;
            if (initialCommentVersionId != null
                && versions.some((v) => v.id === initialCommentVersionId)) {
                return initialCommentVersionId;
            }
            return versions[0].id;
        });
    }, [versions, initialCommentVersionId]);

    // A notification click-through lands on the comment thread it mentioned.
    useEffect(() => {
        if (initialCommentVersionId != null) setDockTab('comments');
    }, [initialCommentVersionId]);

    // Sum actionable flags → hub Attachments tab badge.
    useEffect(() => {
        if (!onActionableCount) return;
        const total = Object.values(flagsByVersion).reduce((s, n) => s + (Number(n) || 0), 0);
        onActionableCount(total);
    }, [flagsByVersion, onActionableCount]);

    // Prefetch every version's review so the badge and the menu chips are right
    // before the reviewer opens the Review tab.
    useEffect(() => {
        if (!canReview || !releaseId || !versions.length) return undefined;
        let cancelled = false;
        (async () => {
            const next = {};
            await Promise.all(versions.map(async (v) => {
                try {
                    const r = await jobsApi.getBBReview(releaseId, v.id);
                    next[v.id] = r?.status === 'complete' ? actionableCount(r.findings || []) : 0;
                } catch {
                    next[v.id] = 0;
                }
            }));
            if (!cancelled) setFlagsByVersion((prev) => ({ ...prev, ...next }));
        })();
        return () => { cancelled = true; };
    }, [canReview, releaseId, versions]);

    // Comments are per version — load the open one's thread so the tab count is real.
    useEffect(() => {
        if (!releaseId || viewingVersionId == null) return;
        if (commentsByVersion[viewingVersionId] !== undefined) return;
        let cancelled = false;
        jobsApi.getVersionComments(releaseId, viewingVersionId)
            .then((comments) => {
                if (!cancelled) {
                    setCommentsByVersion((prev) => ({ ...prev, [viewingVersionId]: comments }));
                }
            })
            .catch(() => {
                if (!cancelled) setCommentsByVersion((prev) => ({ ...prev, [viewingVersionId]: [] }));
            });
        return () => { cancelled = true; };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [releaseId, viewingVersionId]);

    // Escape closes the title menu only — the host modal owns Escape otherwise, so
    // this runs in the capture phase and stops there when the menu is what's open.
    useEffect(() => {
        if (!menuOpen) return undefined;
        const onKey = (e) => {
            if (e.key !== 'Escape') return;
            e.stopPropagation();
            setMenuOpen(false);
        };
        window.addEventListener('keydown', onKey, true);
        return () => window.removeEventListener('keydown', onKey, true);
    }, [menuOpen]);

    // Click-out closes the menu.
    useEffect(() => {
        if (!menuOpen) return undefined;
        const onDown = (e) => {
            if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false);
        };
        document.addEventListener('mousedown', onDown);
        return () => document.removeEventListener('mousedown', onDown);
    }, [menuOpen]);

    const uploadDrawing = async (file) => {
        setUploading(true);
        setError(null);
        try {
            const fd = new FormData();
            fd.append('file', file);
            const latest = versions[0];
            if (latest) fd.append('source_version_id', String(latest.id));
            const resp = await fetch(`${API_BASE_URL}/brain/releases/${releaseId}/drawing`, {
                method: 'POST',
                body: fd,
                credentials: 'include',
            });
            if (!resp.ok) {
                const errBody = await resp.text();
                throw new Error(`Upload failed (${resp.status}): ${errBody.slice(0, 200)}`);
            }
            const created = await resp.json().catch(() => null);
            await loadVersions();
            const newId = created?.version?.id ?? created?.id ?? null;
            if (newId != null) selectVersion(newId);
        } catch (err) {
            setError(err?.message || 'Upload failed');
        } finally {
            setUploading(false);
        }
    };

    const selectVersion = (versionId) => {
        setViewingVersionId(versionId);
        setMenuOpen(false);
        setCitePage(null);
        setCiteRuleId(null);
        setNumPages(0);
    };

    const submitComment = async () => {
        const versionId = viewingVersionId;
        const body = (commentDrafts[versionId] || '').trim();
        if (!versionId || !body || commentBusy[versionId]) return;
        setCommentBusy((prev) => ({ ...prev, [versionId]: true }));
        try {
            const comment = await jobsApi.addVersionComment(releaseId, versionId, body);
            setCommentsByVersion((prev) => ({
                ...prev,
                [versionId]: [...(prev[versionId] || []), comment],
            }));
            setCommentDrafts((prev) => ({ ...prev, [versionId]: '' }));
        } catch (err) {
            setError(err?.message || 'Failed to add comment');
        } finally {
            setCommentBusy((prev) => ({ ...prev, [versionId]: false }));
        }
    };

    const viewing = versions.find((v) => v.id === viewingVersionId) || null;
    const fileUrl = viewing
        ? `${API_BASE_URL}/brain/releases/${releaseId}/drawing/versions/${viewing.id}/file`
        : null;
    const fileName = viewing
        ? (viewing.original_filename || `Drawing v${viewing.version_number}`)
        : 'No drawing';

    // One hidden input for the whole pane — the menu pill and the strip button
    // both trigger it, so the ref stays single.
    const uploadPill = (
        <button
            type="button"
            onClick={() => pdfInputRef.current?.click()}
            disabled={uploading}
            className="font-semibold border-0 cursor-pointer disabled:opacity-50"
            style={{
                fontSize: 11.5,
                padding: '4px 10px',
                borderRadius: 999,
                background: 'var(--accent-soft)',
                color: 'var(--accent)',
            }}
        >
            {uploading ? 'Uploading…' : '+ Upload PDF'}
        </button>
    );

    return (
        <div className="flex-1 min-h-0 flex flex-col bg-surface">
            {/* Top strip: title-as-switcher + meta + markup hand-off */}
            <div
                className="shrink-0 flex items-center border-b border-hairline bg-surface"
                style={{ gap: 10, padding: '8px 14px', minHeight: 44 }}
            >
                <div className="relative" ref={menuRef}>
                    <button
                        type="button"
                        onClick={() => setMenuOpen((o) => !o)}
                        aria-haspopup="menu"
                        aria-expanded={menuOpen}
                        className="inline-flex items-center border border-hairline-strong bg-surface cursor-pointer"
                        style={{ height: 30, padding: '0 10px', borderRadius: 7, gap: 7, maxWidth: 420 }}
                    >
                        <span className="font-semibold text-ink truncate" style={{ fontSize: 13 }}>
                            {fileName}
                        </span>
                        {viewing && (
                            <span
                                className="font-bold"
                                style={{
                                    fontSize: 11,
                                    padding: '1px 7px',
                                    borderRadius: 999,
                                    background: 'var(--accent-soft)',
                                    color: 'var(--accent)',
                                }}
                            >
                                v{viewing.version_number}
                            </span>
                        )}
                        <span className="text-ink-3" style={{ fontSize: 12 }} aria-hidden="true">▾</span>
                    </button>

                    {menuOpen && (
                        <div
                            role="menu"
                            className="absolute bg-surface border border-hairline-strong"
                            style={{
                                top: 36,
                                left: 0,
                                width: 360,
                                borderRadius: 10,
                                boxShadow: 'var(--shadow, 0 24px 60px rgba(15,26,48,.22))',
                                zIndex: 30,
                                overflow: 'hidden',
                            }}
                        >
                            <div
                                className="flex items-center justify-between border-b border-hairline bg-surface-2"
                                style={{ padding: '8px 12px' }}
                            >
                                <span
                                    className="font-bold uppercase text-ink-3"
                                    style={{ fontSize: 12, letterSpacing: '.06em' }}
                                >
                                    Drawings
                                </span>
                                {uploadPill}
                            </div>
                            <div style={{ maxHeight: 320, overflowY: 'auto' }}>
                                {loading && (
                                    <p className="text-ink-3 italic" style={{ padding: '10px 12px', fontSize: 12.5 }}>
                                        Loading…
                                    </p>
                                )}
                                {!loading && versions.length === 0 && (
                                    <p className="text-ink-3" style={{ padding: '10px 12px', fontSize: 12.5 }}>
                                        No drawings yet — upload a PDF to create v1.
                                    </p>
                                )}
                                {versions.map((v) => {
                                    const active = v.id === viewingVersionId;
                                    const flags = flagsByVersion[v.id] || 0;
                                    return (
                                        <button
                                            key={v.id}
                                            type="button"
                                            role="menuitem"
                                            onClick={() => selectVersion(v.id)}
                                            className="w-full text-left border-0 border-b border-hairline cursor-pointer"
                                            style={{
                                                padding: '9px 12px',
                                                background: active ? 'var(--accent-soft)' : 'var(--surface)',
                                            }}
                                        >
                                            <div className="flex items-center gap-2">
                                                <span className="font-semibold text-ink truncate" style={{ fontSize: 13 }}>
                                                    {v.original_filename || `Drawing v${v.version_number}`}
                                                </span>
                                                <span className="text-ink-3" style={{ fontSize: 11 }}>
                                                    v{v.version_number}
                                                </span>
                                                {flags > 0 && (
                                                    <span
                                                        className="font-semibold"
                                                        style={{
                                                            fontSize: 10.5,
                                                            padding: '1px 6px',
                                                            borderRadius: 999,
                                                            background: '#fef3c7',
                                                            color: '#b45309',
                                                        }}
                                                    >
                                                        ⚠ {flags} to confirm
                                                    </span>
                                                )}
                                                {active && (
                                                    <span className="ml-auto font-bold" style={{ color: 'var(--accent)' }}>✓</span>
                                                )}
                                            </div>
                                            <p className="text-ink-3" style={{ fontSize: 11.5, marginTop: 2 }}>
                                                {fmtDate(v.uploaded_at)}
                                                {v.uploaded_by?.name ? ` · ${v.uploaded_by.name}` : ''}
                                                {v.file_size_bytes ? ` · ${fmtSize(v.file_size_bytes)}` : ''}
                                            </p>
                                        </button>
                                    );
                                })}
                            </div>
                        </div>
                    )}
                </div>

                <span className="text-ink-3 truncate" style={{ fontSize: 11.5 }}>
                    {viewing
                        ? `${numPages || '—'} pages${viewing.file_size_bytes ? ` · ${fmtSize(viewing.file_size_bytes)}` : ''}`
                        : 'No drawing uploaded yet'}
                </span>

                <div className="flex-1" />

                {error && (
                    <span className="truncate" style={{ fontSize: 12, color: 'var(--fl-red-bg)', maxWidth: 320 }}>
                        {error}
                    </span>
                )}

                {canReview && (
                    <button
                        type="button"
                        onClick={() => setPullOpen(true)}
                        className="inline-flex items-center gap-1.5 border border-hairline-strong bg-surface text-ink-2 font-semibold hover:bg-surface-2"
                        style={{ height: 28, padding: '0 11px', fontSize: 13, borderRadius: 7 }}
                        title="Pull the Final PDF Pack from Procore into this release"
                    >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M12 3v12" /><path d="M7 10l5 5 5-5" /><path d="M4 21h16" />
                        </svg>
                        Pull from Procore
                    </button>
                )}

                {!loading && versions.length === 0 && (
                    <button
                        type="button"
                        onClick={() => pdfInputRef.current?.click()}
                        disabled={uploading}
                        className="inline-flex items-center gap-1.5 bg-accent-600 text-white font-semibold disabled:opacity-50"
                        style={{ height: 28, padding: '0 11px', fontSize: 13, borderRadius: 7, border: 0 }}
                    >
                        {uploading ? 'Uploading…' : '+ Upload PDF'}
                    </button>
                )}

                {viewing && onOpenVersion && (
                    <button
                        type="button"
                        onClick={() => onOpenVersion(viewing.id, 'edit')}
                        className="inline-flex items-center gap-1.5 border border-hairline-strong bg-surface text-ink-2 font-semibold hover:bg-surface-2"
                        style={{ height: 28, padding: '0 11px', fontSize: 13, borderRadius: 7 }}
                    >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
                        </svg>
                        Edit markup
                    </button>
                )}
            </div>

            {/* Canvas + dock */}
            <div className="flex-1 min-h-0 flex">
                <PdfReadViewer
                    fileUrl={fileUrl}
                    citePage={citePage}
                    citeRuleId={citeRuleId}
                    onClearCite={() => { setCitePage(null); setCiteRuleId(null); }}
                    onNumPages={setNumPages}
                />
                <ViewerDock
                    releaseId={releaseId}
                    version={viewing}
                    versions={versions}
                    numPages={numPages}
                    viewerUrl={viewerUrl}
                    canReview={canReview}
                    tab={dockTab}
                    onTab={setDockTab}
                    collapsed={dockCollapsed}
                    onToggleCollapse={() => setDockCollapsed((c) => !c)}
                    comments={viewing ? commentsByVersion[viewing.id] : []}
                    commentDraft={viewing ? (commentDrafts[viewing.id] || '') : ''}
                    commentBusy={viewing ? !!commentBusy[viewing.id] : false}
                    mentionableUsers={mentionableUsers}
                    onCommentDraft={(val) => setCommentDrafts((prev) => (
                        viewing ? { ...prev, [viewing.id]: val } : prev
                    ))}
                    onSubmitComment={submitComment}
                    flags={viewing ? (flagsByVersion[viewing.id] || 0) : 0}
                    onCite={(page, ruleId) => { setCitePage(page); setCiteRuleId(ruleId); }}
                    onFlagsChange={(n) => setFlagsByVersion((prev) => (
                        !viewing || prev[viewing.id] === n ? prev : { ...prev, [viewing.id]: n }
                    ))}
                    onOpenVersion={onOpenVersion}
                />
            </div>

            <ProcorePullDialog
                isOpen={pullOpen}
                releaseId={releaseId}
                label={label}
                onClose={() => setPullOpen(false)}
                onPulled={async (version) => {
                    await loadVersions();
                    if (version?.id != null) selectVersion(version.id);
                }}
            />

            <input
                ref={pdfInputRef}
                type="file"
                accept="application/pdf,.pdf"
                className="hidden"
                onChange={async (e) => {
                    const file = e.target.files?.[0];
                    if (file) await uploadDrawing(file);
                    if (pdfInputRef.current) pdfInputRef.current.value = '';
                }}
            />
        </div>
    );
}

export default PdfViewerPane;
