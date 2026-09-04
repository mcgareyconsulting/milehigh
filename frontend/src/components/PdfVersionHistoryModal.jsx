/**
 * Attachment hub for a release:
 *   - Standalone modal: two-column drawings + photos (legacy layout).
 *   - Embedded in ReleaseHubModal: left rail (drawings/findings) + thin
 *     read-only PDF viewer on the right with finding cite jumps.
 *
 * PDFs → drawing versions; images → photos. Markup authoring stays in PdfMarkupModal.
 */
import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { API_BASE_URL } from '../utils/api';
import { jobsApi } from '../services/jobsApi';
import { fetchMentionableUsers } from '../services/notificationApi';
import { checkAuth } from '../utils/auth';
import { BBReviewPanel } from './BBReviewPanel';
import { PdfReadViewer } from './PdfReadViewer';
import { actionableCount } from './bbReview/urgency';
import MentionInput from './shared/MentionInput';
import { compressImage } from '../utils/imageCompress';

const isPdfFile = (file) =>
    (file?.type || '').toLowerCase() === 'application/pdf' ||
    (file?.name || '').toLowerCase().endsWith('.pdf');

const isImageFile = (file) =>
    (file?.type || '').toLowerCase().startsWith('image/') ||
    /\.(png|jpe?g|gif|webp|bmp|heic|heif|tiff?)$/i.test(file?.name || '');

/** Render @FirstName mentions in bold accent (mirrors board comment rendering). */
function renderCommentBody(body) {
    return (body || '').split(/(@\w+)/g).map((part, i) =>
        part.startsWith('@')
            ? <span key={i} className="font-semibold text-accent-500">{part}</span>
            : part
    );
}

export function PdfVersionHistoryModal({
    isOpen,
    releaseId,
    onClose,
    onOpenVersion,
    // Job-release label (e.g. "170-345") shown in the header so the attachments
    // hub reads "170-345 Attachments" instead of a bare "Attachments".
    title = '',
    // When set, that version's comment thread is auto-expanded on open (used by
    // the notification bell to land directly on the mentioned drawing comment).
    initialCommentVersionId = null,
    viewerUrl = '',
    // When set (e.g. "Welded QC" / "Paint Complete"), the modal is in stage-gate
    // mode: it requires a photo tagged with this stage before the stage change
    // can be confirmed. Photo uploads are auto-tagged with this stage.
    gateStage = null,
    onConfirmStage,
    // Embedded mode drops this component's own dialog chrome (backdrop, panel,
    // header, Close button) so the hub modal can host the body inside a tab.
    // The host owns closing; only the gate-confirm action survives in the footer.
    embedded = false,
    // Optional: report total actionable Carmen findings for the hub tab badge.
    // Wired fully when reviews are prefetched; safe no-op until then.
    onActionableCount = null,
}) {
    const [versions, setVersions] = useState([]);
    const [photos, setPhotos] = useState([]);
    const [loading, setLoading] = useState(false);
    const [photosLoading, setPhotosLoading] = useState(false);
    const [error, setError] = useState(null);
    const [uploading, setUploading] = useState(false);
    const [photoBusy, setPhotoBusy] = useState(false);
    const [noteDrafts, setNoteDrafts] = useState({});
    // Per-version comment threads (lazy-loaded on expand).
    const [expandedComments, setExpandedComments] = useState({});      // versionId -> bool
    const [commentsByVersion, setCommentsByVersion] = useState({});    // versionId -> comment[]
    const [commentDrafts, setCommentDrafts] = useState({});            // versionId -> string
    const [commentBusy, setCommentBusy] = useState({});               // versionId -> bool
    const [mentionableUsers, setMentionableUsers] = useState([]);
    // Carmen review loop: admin OR drafter (backend: drafter_or_admin_required).
    const [canReview, setCanReview] = useState(false);
    // Embedded hub: which version is in the right-pane viewer + cite bar.
    const [viewingVersionId, setViewingVersionId] = useState(null);
    const [citePage, setCitePage] = useState(null);
    const [citeRuleId, setCiteRuleId] = useState(null);
    // versionId → actionable finding count (for hub tab badge).
    const [flagsByVersion, setFlagsByVersion] = useState({});
    const fileInputRef = useRef(null);
    const pdfInputRef = useRef(null);
    const cameraInputRef = useRef(null);

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

    const loadPhotos = async () => {
        if (!releaseId) return;
        setPhotosLoading(true);
        try {
            const resp = await fetch(`${API_BASE_URL}/brain/releases/${releaseId}/photos`, {
                credentials: 'include',
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            const list = data?.photos ?? [];
            setPhotos(list);
            setNoteDrafts(Object.fromEntries(list.map((p) => [p.id, p.note || ''])));
        } catch (err) {
            setError(err?.message || 'Failed to load photos');
        } finally {
            setPhotosLoading(false);
        }
    };

    useEffect(() => {
        if (!isOpen) return;
        loadVersions();
        loadPhotos();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen, releaseId]);

    // Mentionable users for the comment typeahead — loaded once when the modal opens.
    useEffect(() => {
        if (!isOpen || mentionableUsers.length > 0) return;
        fetchMentionableUsers().then(setMentionableUsers).catch(() => {});
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen]);

    // Admin or drafter may run/view Carmen reviews on a version.
    useEffect(() => {
        if (!isOpen) return;
        checkAuth()
            .then((u) => setCanReview(!!(u?.is_admin || u?.is_drafter)))
            .catch(() => setCanReview(false));
    }, [isOpen]);

    // Default the embedded viewer to the newest drawing once versions load.
    useEffect(() => {
        if (!embedded || !versions.length) return;
        setViewingVersionId((cur) => {
            if (cur != null && versions.some((v) => v.id === cur)) return cur;
            return versions[0].id;
        });
    }, [embedded, versions]);

    // Sum actionable flags → hub Attachments tab badge.
    useEffect(() => {
        if (!onActionableCount) return;
        const total = Object.values(flagsByVersion).reduce((s, n) => s + (Number(n) || 0), 0);
        onActionableCount(total);
    }, [flagsByVersion, onActionableCount]);

    // Prefetch reviews for badge when reviewer can access Carmen.
    useEffect(() => {
        if (!isOpen || !canReview || !releaseId || !versions.length) return;
        let cancelled = false;
        (async () => {
            const next = {};
            await Promise.all(versions.map(async (v) => {
                try {
                    const r = await jobsApi.getBBReview(releaseId, v.id);
                    if (r?.status === 'complete') {
                        next[v.id] = actionableCount(r.findings || []);
                    } else {
                        next[v.id] = 0;
                    }
                } catch {
                    next[v.id] = 0;
                }
            }));
            if (!cancelled) setFlagsByVersion((prev) => ({ ...prev, ...next }));
        })();
        return () => { cancelled = true; };
    }, [isOpen, canReview, releaseId, versions]);

    // Auto-expand the version a notification pointed at, once it appears.
    useEffect(() => {
        if (!isOpen || !initialCommentVersionId) return;
        setExpandedComments((prev) => ({ ...prev, [initialCommentVersionId]: true }));
        if (commentsByVersion[initialCommentVersionId] === undefined) {
            loadComments(initialCommentVersionId);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen, initialCommentVersionId]);

    const loadComments = async (versionId) => {
        try {
            const comments = await jobsApi.getVersionComments(releaseId, versionId);
            setCommentsByVersion((prev) => ({ ...prev, [versionId]: comments }));
        } catch {
            setCommentsByVersion((prev) => ({ ...prev, [versionId]: [] }));
        }
    };

    const toggleComments = (versionId) => {
        setExpandedComments((prev) => {
            const next = !prev[versionId];
            if (next && commentsByVersion[versionId] === undefined) loadComments(versionId);
            return { ...prev, [versionId]: next };
        });
    };

    const submitComment = async (versionId) => {
        const body = (commentDrafts[versionId] || '').trim();
        if (!body || commentBusy[versionId]) return;
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

    useEffect(() => {
        // Embedded: the host modal owns Escape, so binding here would close both.
        if (!isOpen || embedded) return;
        const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [isOpen, embedded, onClose]);

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
            await loadVersions();
        } catch (err) {
            setError(err?.message || 'Upload failed');
        } finally {
            setUploading(false);
        }
    };

    const uploadPhoto = async (file, stageTag = null) => {
        setPhotoBusy(true);
        setError(null);
        try {
            // Shrink phone-camera shots before they hit LTE; see utils/imageCompress.js.
            const payload = await compressImage(file);
            const fd = new FormData();
            fd.append('file', payload);
            if (stageTag) fd.append('stage', stageTag);
            const resp = await fetch(`${API_BASE_URL}/brain/releases/${releaseId}/photos`, {
                method: 'POST',
                body: fd,
                credentials: 'include',
            });
            if (!resp.ok) {
                const errBody = await resp.text();
                throw new Error(`Photo upload failed (${resp.status}): ${errBody.slice(0, 200)}`);
            }
            await loadPhotos();
        } catch (err) {
            setError(err?.message || 'Photo upload failed');
        } finally {
            setPhotoBusy(false);
        }
    };

    // Top "Choose file" picker — routes PDFs to Drawings, images to Photos.
    const handleFileChosen = async (event) => {
        const file = event.target.files?.[0];
        if (!file) return;
        try {
            if (isPdfFile(file)) {
                await uploadDrawing(file);
            } else if (isImageFile(file)) {
                await uploadPhoto(file, gateStage);
            } else {
                setError('Unsupported file type — choose a PDF (drawing) or an image (photo).');
            }
        } finally {
            if (fileInputRef.current) fileInputRef.current.value = '';
        }
    };

    const handleCameraCapture = async (event) => {
        const file = event.target.files?.[0];
        if (!file) return;
        try {
            await uploadPhoto(file, gateStage);
        } finally {
            if (cameraInputRef.current) cameraInputRef.current.value = '';
        }
    };

    // Auto-saved on blur. No-op when the note is unchanged so leaving the
    // textarea without edits doesn't fire a request.
    const saveNote = async (photoId) => {
        const draft = noteDrafts[photoId] ?? '';
        const current = photos.find((p) => p.id === photoId)?.note || '';
        if (draft === current) return;
        setError(null);
        try {
            const resp = await fetch(`${API_BASE_URL}/brain/releases/${releaseId}/photos/${photoId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ note: noteDrafts[photoId] ?? '' }),
                credentials: 'include',
            });
            if (!resp.ok) throw new Error(`Save failed (${resp.status})`);
            const updated = await resp.json();
            setPhotos((prev) => prev.map((p) => (p.id === photoId ? updated : p)));
        } catch (err) {
            setError(err?.message || 'Failed to save note');
        }
    };

    const deletePhoto = async (photoId) => {
        if (!window.confirm('Delete this photo?')) return;
        setError(null);
        try {
            const resp = await fetch(`${API_BASE_URL}/brain/releases/${releaseId}/photos/${photoId}`, {
                method: 'DELETE',
                credentials: 'include',
            });
            if (!resp.ok) throw new Error(`Delete failed (${resp.status})`);
            setPhotos((prev) => prev.filter((p) => p.id !== photoId));
        } catch (err) {
            setError(err?.message || 'Failed to delete photo');
        }
    };

    if (!isOpen) return null;

    // In gate mode, the stage change is only allowed once a non-deleted photo
    // tagged with the gated stage exists.
    const gateSatisfied = !gateStage || photos.some((p) => p.stage === gateStage);

    const fmtDate = (iso) => {
        if (!iso) return '—';
        try {
            return new Date(iso).toLocaleString();
        } catch {
            return iso;
        }
    };

    const fmtSize = (bytes) => {
        if (!bytes) return '';
        const kb = bytes / 1024;
        if (kb < 1024) return `${kb.toFixed(0)} KB`;
        return `${(kb / 1024).toFixed(1)} MB`;
    };

    const hasViewerUrl = Boolean(viewerUrl && viewerUrl.trim() !== '');

    const body = (
        <>
                {/* Choose file — lives outside the two columns; routes by file type. */}
                <div className="px-6 py-4 border-b border-gray-200 dark:border-slate-600 flex flex-wrap items-center gap-3">
                    <input
                        ref={fileInputRef}
                        type="file"
                        accept="application/pdf,.pdf,image/*"
                        onChange={handleFileChosen}
                        disabled={uploading || photoBusy}
                        className="text-sm"
                    />
                    <span className="text-xs text-gray-500 dark:text-slate-400">
                        PDFs go to Drawings; images go to Photos.
                    </span>
                    {(uploading || photoBusy) && <span className="text-sm text-gray-500 dark:text-slate-400">Uploading…</span>}
                    {/* Embedded hub: Procore lives on the ReleaseHub header — no duplicate link. */}
                </div>

                {gateStage && (
                    <div className={`px-6 py-3 border-b text-sm flex items-center gap-2 ${gateSatisfied
                        ? 'bg-green-50 border-green-200 text-green-800 dark:bg-green-900/30 dark:border-green-800 dark:text-green-200'
                        : 'bg-amber-50 border-amber-200 text-amber-800 dark:bg-amber-900/30 dark:border-amber-800 dark:text-amber-200'}`}>
                        {gateSatisfied ? (
                            <span>✓ Photo for <strong>{gateStage}</strong> attached — confirm below to move the stage.</span>
                        ) : (
                            <span>A photo is required to move to <strong>{gateStage}</strong>. Upload an image or use “Take photo” — it will be tagged automatically.</span>
                        )}
                    </div>
                )}

                {error && (
                    <div className="px-6 pt-3">
                        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
                    </div>
                )}

                <div className="px-6 py-4 overflow-y-auto flex-1 grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* ── Drawings column ───────────────────────────────────── */}
                    <section className="min-w-0">
                        <h3 className="text-sm font-bold text-gray-800 dark:text-slate-100 uppercase tracking-wide mb-3 pb-2 border-b border-gray-200 dark:border-slate-600">
                            Drawings
                        </h3>
                        {loading && <p className="text-sm text-gray-500 dark:text-slate-400 italic">Loading…</p>}
                        {!loading && versions.length === 0 && (
                            <p className="text-sm text-gray-500 dark:text-slate-400 italic">
                                No drawings yet — choose a PDF above to create v1.
                            </p>
                        )}
                        {!loading && versions.length > 0 && (
                            <ul className="space-y-3">
                                {versions.map((v) => {
                                    const comments = commentsByVersion[v.id];
                                    const expanded = !!expandedComments[v.id];
                                    return (
                                    <li
                                        key={v.id}
                                        className="border border-gray-200 dark:border-slate-600 rounded-lg p-3"
                                    >
                                        <div className="flex items-center gap-3">
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-baseline gap-2 flex-wrap">
                                                    <span className="font-semibold text-gray-900 dark:text-slate-100">v{v.version_number}</span>
                                                    <span className="text-xs text-gray-500 dark:text-slate-400">{fmtDate(v.uploaded_at)}</span>
                                                    <span className="text-xs text-gray-500 dark:text-slate-400">
                                                        {v.uploaded_by?.name || '—'}
                                                    </span>
                                                    <span className="text-xs text-gray-400 dark:text-slate-500 ml-auto">{fmtSize(v.file_size_bytes)}</span>
                                                </div>
                                                {v.note && (
                                                    <p className="text-sm text-gray-700 dark:text-slate-200 mt-1 break-words">{v.note}</p>
                                                )}
                                                {v.source_version_id != null && (
                                                    <p className="text-xs text-gray-400 dark:text-slate-500 mt-1">from v-id {v.source_version_id}</p>
                                                )}
                                            </div>
                                            <button
                                                type="button"
                                                onClick={() => onOpenVersion?.(v.id, 'view')}
                                                className="px-3 py-2 text-sm border border-gray-300 dark:border-slate-500 rounded-md hover:bg-gray-50 dark:hover:bg-slate-600"
                                            >
                                                View
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => onOpenVersion?.(v.id, 'edit')}
                                                className="px-3 py-2 text-sm bg-accent-600 text-white rounded-md font-semibold"
                                            >
                                                Edit
                                            </button>
                                        </div>

                                        {/* Comments / @mentions thread for this version */}
                                        <div className="mt-2 pt-2 border-t border-gray-100 dark:border-slate-700">
                                            <button
                                                type="button"
                                                onClick={() => toggleComments(v.id)}
                                                className="text-xs font-medium text-accent-600 hover:text-accent-700 flex items-center gap-1"
                                            >
                                                <span>{expanded ? '▾' : '▸'}</span>
                                                <span>
                                                    Comments
                                                    {comments?.length ? ` (${comments.length})` : ''}
                                                </span>
                                            </button>
                                            {expanded && (
                                                <div className="mt-2 space-y-2">
                                                    {comments === undefined && (
                                                        <p className="text-xs text-gray-400 dark:text-slate-500 italic">Loading…</p>
                                                    )}
                                                    {comments?.length === 0 && (
                                                        <p className="text-xs text-gray-400 dark:text-slate-500 italic">No comments yet.</p>
                                                    )}
                                                    {comments?.map((c) => (
                                                        <div key={c.id} className="text-sm">
                                                            <div className="flex items-baseline gap-2">
                                                                <span className="font-semibold text-gray-800 dark:text-slate-100">{c.author_name}</span>
                                                                <span className="text-xs text-gray-400 dark:text-slate-500">{fmtDate(c.created_at)}</span>
                                                            </div>
                                                            <p className="text-gray-700 dark:text-slate-200 break-words whitespace-pre-wrap">
                                                                {renderCommentBody(c.body)}
                                                            </p>
                                                        </div>
                                                    ))}
                                                    <div className="flex items-end gap-2 pt-1">
                                                        <MentionInput
                                                            value={commentDrafts[v.id] || ''}
                                                            onChange={(val) => setCommentDrafts((prev) => ({ ...prev, [v.id]: val }))}
                                                            onSubmit={() => submitComment(v.id)}
                                                            users={mentionableUsers}
                                                            placeholder="Add a comment… use @ to tag a teammate"
                                                            multiline
                                                            disabled={!!commentBusy[v.id]}
                                                        />
                                                        <button
                                                            type="button"
                                                            onClick={() => submitComment(v.id)}
                                                            disabled={!!commentBusy[v.id] || !(commentDrafts[v.id] || '').trim()}
                                                            className="px-3 py-1.5 text-xs bg-accent-600 text-white rounded-md font-semibold disabled:opacity-50 shrink-0"
                                                        >
                                                            Post
                                                        </button>
                                                    </div>
                                                </div>
                                            )}
                                        </div>

                                        {/* Carmen review — admin or drafter */}
                                        <BBReviewPanel
                                            releaseId={releaseId}
                                            versionId={v.id}
                                            enabled={canReview}
                                        />
                                    </li>
                                    );
                                })}
                            </ul>
                        )}
                    </section>

                    {/* ── Photos column ─────────────────────────────────────── */}
                    <section className="min-w-0">
                        <div className="flex items-center justify-between mb-3 pb-2 border-b border-gray-200 dark:border-slate-600">
                            <h3 className="text-sm font-bold text-gray-800 dark:text-slate-100 uppercase tracking-wide">
                                Photos
                            </h3>
                            <button
                                type="button"
                                onClick={() => cameraInputRef.current?.click()}
                                disabled={photoBusy}
                                className="inline-flex items-center gap-1 px-3 py-1.5 text-sm bg-accent-600 text-white rounded-md font-semibold disabled:opacity-50"
                                title="Capture a photo with your device camera"
                            >
                                📷 Take photo
                            </button>
                            <input
                                ref={cameraInputRef}
                                type="file"
                                accept="image/*"
                                capture="environment"
                                onChange={handleCameraCapture}
                                className="hidden"
                            />
                        </div>
                        {photosLoading && <p className="text-sm text-gray-500 dark:text-slate-400 italic">Loading…</p>}
                        {!photosLoading && photos.length === 0 && (
                            <p className="text-sm text-gray-500 dark:text-slate-400 italic">
                                No photos yet — choose an image above or use “Take photo”.
                            </p>
                        )}
                        {!photosLoading && photos.length > 0 && (
                            <ul className="space-y-4">
                                {photos.map((p) => (
                                    <li
                                        key={p.id}
                                        className="border border-gray-200 dark:border-slate-600 rounded-lg p-3"
                                    >
                                        <div className="flex gap-3">
                                            <a
                                                href={`${API_BASE_URL}/brain/releases/${releaseId}/photos/${p.id}/file`}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="shrink-0"
                                                title="Open full size"
                                            >
                                                <img
                                                    src={`${API_BASE_URL}/brain/releases/${releaseId}/photos/${p.id}/file`}
                                                    alt={p.original_filename || 'photo'}
                                                    className="w-24 h-24 object-cover rounded-md border border-gray-200 dark:border-slate-600 bg-gray-50 dark:bg-slate-700"
                                                />
                                            </a>
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-baseline gap-2 flex-wrap">
                                                    {p.stage && (
                                                        <span className="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300">
                                                            {p.stage}
                                                        </span>
                                                    )}
                                                    <span className="text-xs text-gray-500 dark:text-slate-400">{fmtDate(p.uploaded_at)}</span>
                                                    <span className="text-xs text-gray-500 dark:text-slate-400">{p.uploaded_by?.name || '—'}</span>
                                                    <span className="text-xs text-gray-400 dark:text-slate-500 ml-auto">{fmtSize(p.file_size_bytes)}</span>
                                                </div>
                                                {p.last_edited_by && (
                                                    <p className="text-[11px] text-gray-400 dark:text-slate-500 mt-1 italic">
                                                        Note edited by {p.last_edited_by.name || '—'} · {fmtDate(p.last_edited_at)}
                                                    </p>
                                                )}
                                                <textarea
                                                    value={noteDrafts[p.id] ?? ''}
                                                    onChange={(e) =>
                                                        setNoteDrafts((prev) => ({ ...prev, [p.id]: e.target.value }))
                                                    }
                                                    onBlur={() => saveNote(p.id)}
                                                    placeholder="Optional notes…"
                                                    rows={2}
                                                    className="mt-2 w-full text-sm border border-gray-300 dark:border-slate-500 dark:bg-slate-700 dark:text-slate-100 dark:placeholder-slate-400 rounded-md px-2 py-1 resize-y focus:outline-none focus:ring-1 focus:ring-accent-500"
                                                />
                                                <div className="flex items-center gap-2 mt-2">
                                                    <button
                                                        type="button"
                                                        onClick={() => deletePhoto(p.id)}
                                                        className="px-3 py-1 text-xs border border-gray-300 dark:border-slate-500 text-gray-600 dark:text-slate-300 rounded-md hover:bg-gray-50 dark:hover:bg-slate-600"
                                                    >
                                                        Delete
                                                    </button>
                                                </div>
                                            </div>
                                        </div>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </section>
                </div>

                {/* Embedded with no gate to confirm, the footer would hold nothing
                    but a duplicate Close — the host modal already has one. */}
                {(!embedded || gateStage) && (
                    <div className="bg-gray-50 dark:bg-slate-700 px-6 py-4 rounded-b-xl border-t border-gray-200 dark:border-slate-600 flex justify-end gap-3">
                        {!embedded && (
                            <button
                                onClick={onClose}
                                className="px-4 py-2 bg-gray-200 dark:bg-slate-600 text-gray-700 dark:text-slate-200 rounded-lg font-medium hover:bg-gray-300 dark:hover:bg-slate-500"
                            >
                                {gateStage ? 'Cancel' : 'Close'}
                            </button>
                        )}
                        {gateStage && (
                            <button
                                onClick={() => onConfirmStage?.()}
                                disabled={!gateSatisfied}
                                className="px-4 py-2 bg-accent-600 text-white rounded-lg font-semibold hover:bg-accent-700 disabled:opacity-50 disabled:cursor-not-allowed"
                                title={gateSatisfied ? `Move to ${gateStage}` : `Upload a ${gateStage} photo first`}
                            >
                                Confirm {gateStage}
                            </button>
                        )}
                    </div>
                )}
        </>
    );

    // ── Embedded hub: left rail + thin read viewer ─────────────────────────
    if (embedded) {
        const viewing = versions.find((v) => v.id === viewingVersionId) || null;
        const fileUrl = viewing
            ? `${API_BASE_URL}/brain/releases/${releaseId}/drawing/versions/${viewing.id}/file`
            : null;
        const fileName = viewing
            ? (viewing.original_filename || `v${viewing.version_number}.pdf`)
            : '';

        const openInViewer = (versionId) => {
            setViewingVersionId(versionId);
            setCitePage(null);
            setCiteRuleId(null);
        };

        const handleCite = (page, ruleId) => {
            setCitePage(page);
            setCiteRuleId(ruleId);
        };

        const pillBtn = {
            fontSize: 11.5,
            padding: '4px 10px',
            borderRadius: 999,
            border: 0,
            cursor: 'pointer',
            fontWeight: 600,
        };

        return (
            <div className="flex flex-1 min-h-0 bg-surface">
                {/* Left rail */}
                <div
                    className="shrink-0 flex flex-col min-h-0 border-r border-hairline bg-surface overflow-hidden"
                    style={{ width: 404 }}
                >
                    <div className="flex-1 min-h-0 overflow-y-auto" style={{ padding: '12px 14px 18px' }}>
                        {error && (
                            <p className="text-sm mb-2" style={{ color: 'var(--fl-red-bg)' }}>{error}</p>
                        )}

                        {/* DRAWINGS */}
                        <div className="flex items-center justify-between gap-2" style={{ marginBottom: 10 }}>
                            <span className="text-jl-label font-bold uppercase text-ink-3">Drawings</span>
                            <div className="flex items-center gap-1.5">
                                <button
                                    type="button"
                                    onClick={() => pdfInputRef.current?.click()}
                                    disabled={uploading}
                                    style={{
                                        ...pillBtn,
                                        background: 'var(--accent-soft)',
                                        color: 'var(--accent)',
                                        opacity: uploading ? 0.5 : 1,
                                    }}
                                >
                                    {uploading ? 'Uploading…' : '+ Upload PDF'}
                                </button>
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
                        </div>

                        {loading && <p className="text-jl-2 text-ink-3 italic">Loading…</p>}
                        {!loading && versions.length === 0 && (
                            <p className="text-jl-2 text-ink-3 italic" style={{ marginBottom: 16 }}>
                                No drawings yet — upload a PDF to create v1.
                            </p>
                        )}
                        {!loading && versions.length > 0 && (
                            <ul className="space-y-2.5" style={{ marginBottom: 18 }}>
                                {versions.map((v) => {
                                    const active = v.id === viewingVersionId;
                                    const flags = flagsByVersion[v.id] || 0;
                                    return (
                                        <li
                                            key={v.id}
                                            className="border border-hairline bg-surface"
                                            style={{
                                                borderRadius: 10,
                                                padding: 12,
                                                boxShadow: active ? 'inset 0 0 0 1.5px var(--accent)' : undefined,
                                            }}
                                        >
                                            <div className="flex items-baseline gap-2 flex-wrap">
                                                <span className="font-semibold text-ink truncate" style={{ fontSize: 13 }}>
                                                    {v.original_filename || `Drawing v${v.version_number}`}
                                                </span>
                                                <span className="font-mono text-ink-3" style={{ fontSize: 11 }}>
                                                    v{v.version_number}
                                                </span>
                                                <span className="text-ink-3 ml-auto" style={{ fontSize: 11 }}>
                                                    {fmtSize(v.file_size_bytes)}
                                                </span>
                                            </div>
                                            <p className="text-ink-3" style={{ fontSize: 11.5, marginTop: 3 }}>
                                                {fmtDate(v.uploaded_at)}
                                                {v.uploaded_by?.name ? ` · ${v.uploaded_by.name}` : ''}
                                            </p>
                                            {flags > 0 && (
                                                <span
                                                    className="inline-block font-mono font-semibold"
                                                    style={{
                                                        marginTop: 6,
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
                                            <div className="flex items-center flex-wrap" style={{ gap: 8, marginTop: 8 }}>
                                                <button
                                                    type="button"
                                                    onClick={() => openInViewer(v.id)}
                                                    className="text-brand font-semibold bg-transparent border-0 cursor-pointer"
                                                    style={{ fontSize: 12 }}
                                                >
                                                    View
                                                </button>
                                                <button
                                                    type="button"
                                                    onClick={() => onOpenVersion?.(v.id, 'edit')}
                                                    className="text-ink-2 font-semibold bg-transparent border-0 cursor-pointer"
                                                    style={{ fontSize: 12 }}
                                                >
                                                    Edit markup
                                                </button>
                                            </div>
                                            {canReview && (
                                                <BBReviewPanel
                                                    releaseId={releaseId}
                                                    versionId={v.id}
                                                    enabled
                                                    autoLoad
                                                    defaultOpen={active && flags > 0}
                                                    onCite={(page, ruleId) => {
                                                        openInViewer(v.id);
                                                        handleCite(page, ruleId);
                                                    }}
                                                    onFlagsChange={(n) => {
                                                        setFlagsByVersion((prev) => (
                                                            prev[v.id] === n ? prev : { ...prev, [v.id]: n }
                                                        ));
                                                    }}
                                                />
                                            )}
                                            {/* Comments still available */}
                                            <div className="mt-2 pt-2 border-t border-hairline">
                                                <button
                                                    type="button"
                                                    onClick={() => toggleComments(v.id)}
                                                    className="text-xs font-medium text-brand bg-transparent border-0 cursor-pointer flex items-center gap-1"
                                                >
                                                    <span>{expandedComments[v.id] ? '▾' : '▸'}</span>
                                                    Comments
                                                    {commentsByVersion[v.id]?.length
                                                        ? ` (${commentsByVersion[v.id].length})`
                                                        : ''}
                                                </button>
                                                {expandedComments[v.id] && (
                                                    <div className="mt-2 space-y-2">
                                                        {commentsByVersion[v.id] === undefined && (
                                                            <p className="text-xs text-ink-3 italic">Loading…</p>
                                                        )}
                                                        {commentsByVersion[v.id]?.map((c) => (
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
                                                        <div className="flex items-end gap-2 pt-1">
                                                            <MentionInput
                                                                value={commentDrafts[v.id] || ''}
                                                                onChange={(val) => setCommentDrafts((prev) => ({ ...prev, [v.id]: val }))}
                                                                onSubmit={() => submitComment(v.id)}
                                                                users={mentionableUsers}
                                                                placeholder="Add a comment… @ to tag"
                                                                multiline
                                                                disabled={!!commentBusy[v.id]}
                                                            />
                                                            <button
                                                                type="button"
                                                                onClick={() => submitComment(v.id)}
                                                                disabled={!!commentBusy[v.id] || !(commentDrafts[v.id] || '').trim()}
                                                                className="px-3 py-1.5 text-xs bg-accent-600 text-white rounded-md font-semibold disabled:opacity-50 shrink-0"
                                                            >
                                                                Post
                                                            </button>
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        </li>
                                    );
                                })}
                            </ul>
                        )}

                        {/* Photos moved to the hub's Details pane (the shipping-guy click
                            path); this rail is drawings + PDF review only. The standalone
                            modal below still shows photos — that is where note editing,
                            deletes and the stage-photo gate live. */}

                        {gateStage && (
                            <div
                                className="mt-4 p-3 rounded-lg text-sm border"
                                style={{
                                    background: gateSatisfied ? 'var(--st-green-bg)' : 'var(--st-amber-bg)',
                                    color: gateSatisfied ? 'var(--st-green-fg)' : 'var(--st-amber-fg)',
                                    borderColor: 'var(--border)',
                                }}
                            >
                                {gateSatisfied
                                    ? `✓ Photo for ${gateStage} attached.`
                                    : `A photo is required to move to ${gateStage}.`}
                                {gateSatisfied && (
                                    <button
                                        type="button"
                                        onClick={() => onConfirmStage?.()}
                                        className="mt-2 block font-semibold underline bg-transparent border-0 cursor-pointer"
                                        style={{ color: 'inherit' }}
                                    >
                                        Confirm {gateStage}
                                    </button>
                                )}
                            </div>
                        )}
                    </div>
                </div>

                {/* Right: read viewer */}
                <PdfReadViewer
                    fileUrl={fileUrl}
                    fileName={fileName}
                    citePage={citePage}
                    citeRuleId={citeRuleId}
                    onClearCite={() => { setCitePage(null); setCiteRuleId(null); }}
                />
            </div>
        );
    }

    return createPortal(
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"
            onClick={onClose}
        >
            <div
                className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl w-full max-w-5xl mx-4 max-h-[85vh] flex flex-col"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-6 py-4 rounded-t-xl flex items-center justify-between gap-3">
                    <h2 className="text-xl font-bold text-white">{title ? `${title} Attachments` : 'Attachments'}</h2>
                    <div className="flex items-center gap-3">
                        {hasViewerUrl ? (
                            <a
                                href={viewerUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md text-xs font-semibold bg-white/90 text-accent-700 hover:bg-white whitespace-nowrap"
                                title="Open this drawing in Procore"
                            >
                                ↗ View in Procore
                            </a>
                        ) : (
                            <span
                                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md text-xs font-semibold bg-white/30 text-white/60 cursor-help select-none whitespace-nowrap"
                                title="No FC link found"
                                aria-disabled="true"
                            >
                                ↗ View in Procore
                            </span>
                        )}
                        <button
                            onClick={onClose}
                            className="text-white hover:text-gray-200 text-2xl font-bold leading-none"
                            aria-label="Close"
                        >
                            ×
                        </button>
                    </div>
                </div>
                {body}
            </div>
        </div>,
        document.body,
    );
}

export default PdfVersionHistoryModal;
