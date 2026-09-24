/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The department photo gate (T13) — a focused dialog that requires a photo tagged with
 *   the department's entry stage, or a written reason there is none, before a stage change that
 *   crosses into the next department is applied. Also the place photos get a note, or get
 *   deleted. Split out of the retired PdfVersionHistoryModal; drawings now live in the hybrid
 *   viewer (pdfViewer/PdfViewerPane).
 * exports:
 *   StagePhotoGateModal: props { isOpen, releaseId, title, gateStage, requestedStage, onConfirmStage, onClose }
 * imports_from: [react, react-dom, ../utils/api, ../utils/imageCompress, ./pdfViewer/format]
 * imported_by: [frontend/src/components/JobsTableRow.jsx, frontend/src/components/JobDetailsBody.jsx,
 *   frontend/src/components/GanttChart.jsx]
 * invariants:
 *   - Photos already tagged with gateStage start included. Any other photo on the release
 *     can be included too; Confirm retags those onto gateStage before the stage moves
 *   - Confirm stays disabled until at least one photo is included, OR the "no photo
 *     available" path is open with a non-empty reason and nothing is included
 *   - onConfirmStage receives that reason (trimmed) when words stood in for the photo, else null
 *   - Uploads (file picker or camera) are auto-tagged with the gated stage and join the
 *     included set; the picker takes up to MAX_PER_PICK at once and uploads them one after
 *     another through one queue, each with its own progress bar; a failure marks that photo
 *     Retry and never stops the rest
 *   - Confirm waits for in-flight uploads and for retagging, so the stage never moves ahead
 *     of its evidence
 *   - gateStage is the department's ENTRY stage (what the photo is tagged with); requestedStage
 *     is what the user picked — usually the same, not always (Ship Planning → Complete)
 *   - Notes auto-save on blur, and only when the text actually changed
 *   - Photos land in the release's ordinary photo set — the gate is a forced add into the
 *     existing loadout, not a separate store
 * updated_by_agent: 2026-09-24T00:00:00Z
 */
import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import { API_BASE_URL } from '../utils/api';
import { compressImage } from '../utils/imageCompress';
import { fmtDate, fmtSize } from './pdfViewer/format';

// Comfortable tap targets on a phone (the shop floor's camera), sized back down at
// sm: where a mouse is more likely — same rule as the T&M ticket form.
const touchButtonClass = 'px-4 py-3 sm:py-2 rounded-lg font-semibold';

// One pick from the library is capped here (Daniel, 2026-09-23). The cap is about what a
// phone on LTE can push in one sitting, not about how much evidence a handoff needs —
// pick again for more. Extras beyond the cap are dropped with a message, never silently.
const MAX_PER_PICK = 10;

let uploadSeq = 0;

/** Upload one form body with progress — fetch() has no upload progress, XHR does. */
const postWithProgress = (url, formData, onProgress) =>
    new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', url);
        xhr.withCredentials = true;
        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
        };
        xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) resolve();
            else reject(new Error(`Photo upload failed (${xhr.status}): ${String(xhr.responseText || '').slice(0, 200)}`));
        };
        xhr.onerror = () => reject(new Error('Photo upload failed: network error'));
        xhr.send(formData);
    });

export function StagePhotoGateModal({
    isOpen,
    releaseId,
    title = '',
    gateStage = null,
    requestedStage = null,
    onConfirmStage = null,
    onClose,
}) {
    const [photos, setPhotos] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [noteDrafts, setNoteDrafts] = useState({});
    // The "no photo available" exit: open the reason box, and the reason itself.
    const [noPhoto, setNoPhoto] = useState(false);
    const [exceptionNote, setExceptionNote] = useState('');
    // The upload strip: one entry per picked file, from pick to landed (or failed).
    //   { key, file, name, previewUrl, status: 'queued'|'uploading'|'done'|'failed', pct, error }
    const [uploads, setUploads] = useState([]);
    const [notice, setNotice] = useState(null);           // the over-the-cap message
    // Photos included with this handoff. Already-tagged ones start included; checking
    // another photo on the release retags it on Confirm.
    const [selectedIds, setSelectedIds] = useState(() => new Set());
    const [tagging, setTagging] = useState(false);
    const fileInputRef = useRef(null);
    const cameraInputRef = useRef(null);
    // Ids we have already offered. A later reload auto-includes only new gate-tagged
    // photos (the ones an upload just landed), so unchecking an old one sticks.
    const seenIdsRef = useRef(new Set());
    // Every upload joins one chain, so two quick picks (or a retry mid-batch) still go
    // one at a time — steady progress on LTE instead of five stalled requests.
    const queueRef = useRef(Promise.resolve());

    const busy = uploads.some((u) => u.status === 'queued' || u.status === 'uploading');

    const loadPhotos = async ({ quiet = false, resetSelection = false } = {}) => {
        if (!releaseId) return;
        if (!quiet) setLoading(true);
        try {
            const resp = await fetch(`${API_BASE_URL}/brain/releases/${releaseId}/photos`, {
                credentials: 'include',
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            const list = data?.photos ?? [];
            setPhotos(list);
            setNoteDrafts(Object.fromEntries(list.map((p) => [p.id, p.note || ''])));
            if (gateStage) {
                const seen = seenIdsRef.current;
                const live = new Set(list.map((p) => p.id));
                setSelectedIds((prev) => {
                    const next = resetSelection ? new Set() : new Set(prev);
                    list.forEach((p) => {
                        if (p.stage === gateStage && (resetSelection || !seen.has(p.id))) next.add(p.id);
                    });
                    return new Set([...next].filter((id) => live.has(id)));
                });
                seenIdsRef.current = live;
            }
        } catch (err) {
            setError(err?.message || 'Failed to load photos');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (!isOpen) return;
        setError(null);
        setNotice(null);
        setNoPhoto(false);
        setExceptionNote('');
        setSelectedIds(new Set());
        seenIdsRef.current = new Set();
        setUploads((prev) => { prev.forEach((u) => URL.revokeObjectURL(u.previewUrl)); return []; });
        loadPhotos({ resetSelection: true });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen, releaseId]);

    // Once a batch has fully landed, its tiles have become real photos in the list below;
    // give the checkmarks a beat, then clear the strip. Failed tiles stay until retried.
    useEffect(() => {
        if (busy || !uploads.some((u) => u.status === 'done')) return undefined;
        const t = setTimeout(() => {
            setUploads((prev) => {
                prev.filter((u) => u.status === 'done').forEach((u) => URL.revokeObjectURL(u.previewUrl));
                return prev.filter((u) => u.status !== 'done');
            });
        }, 1200);
        return () => clearTimeout(t);
    }, [busy, uploads]);

    useEffect(() => () => { uploads.forEach((u) => URL.revokeObjectURL(u.previewUrl)); },
        // eslint-disable-next-line react-hooks/exhaustive-deps
        []);

    useEffect(() => {
        if (!isOpen) return undefined;
        const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [isOpen, onClose]);

    const patchUpload = (key, patch) =>
        setUploads((prev) => prev.map((u) => (u.key === key ? { ...u, ...patch } : u)));

    // One file, start to finish. A failure lands on the tile (Retry), not on the modal's
    // error line, and never touches the files queued behind it.
    const uploadOne = async (entry) => {
        patchUpload(entry.key, { status: 'uploading', pct: 0, error: null });
        try {
            // Shrink phone-camera shots before they hit LTE; see utils/imageCompress.js.
            const payload = await compressImage(entry.file);
            const fd = new FormData();
            fd.append('file', payload);
            if (gateStage) fd.append('stage', gateStage);
            await postWithProgress(
                `${API_BASE_URL}/brain/releases/${releaseId}/photos`,
                fd,
                (pct) => patchUpload(entry.key, { pct }),
            );
            patchUpload(entry.key, { status: 'done', pct: 100 });
            await loadPhotos({ quiet: true });
        } catch (err) {
            patchUpload(entry.key, { status: 'failed', error: err?.message || 'Photo upload failed' });
        }
    };

    const enqueue = (entries) => {
        entries.forEach((entry) => {
            queueRef.current = queueRef.current.then(() => uploadOne(entry));
        });
    };

    // Several at once from the library (Bill's §5.4.2 "multi-photo"), capped at
    // MAX_PER_PICK; the camera input hands over one shot at a time by nature.
    const onFileChosen = (event, ref) => {
        const picked = Array.from(event.target.files || []);
        if (ref.current) ref.current.value = '';
        if (picked.length === 0) return;
        const files = picked.slice(0, MAX_PER_PICK);
        setNotice(picked.length > MAX_PER_PICK
            ? `${MAX_PER_PICK} at a time — the first ${MAX_PER_PICK} were added. Pick again for the other ${picked.length - MAX_PER_PICK}.`
            : null);
        const entries = files.map((file) => ({
            key: `u${uploadSeq += 1}`,
            file,
            name: file.name,
            previewUrl: URL.createObjectURL(file),
            status: 'queued',
            pct: 0,
            error: null,
        }));
        setUploads((prev) => [...prev, ...entries]);
        enqueue(entries);
    };

    const retryUpload = (entry) => {
        patchUpload(entry.key, { status: 'queued', error: null });
        enqueue([entry]);
    };
    const retryAllFailed = () => uploads.filter((u) => u.status === 'failed').forEach(retryUpload);

    const toggleSelected = (photoId) => {
        setSelectedIds((prev) => {
            const next = new Set(prev);
            if (next.has(photoId)) next.delete(photoId);
            else next.add(photoId);
            return next;
        });
    };

    // Include an existing photo in this handoff by tagging it with the entry stage.
    const tagPhoto = async (photoId) => {
        const resp = await fetch(`${API_BASE_URL}/brain/releases/${releaseId}/photos/${photoId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ stage: gateStage }),
            credentials: 'include',
        });
        if (!resp.ok) {
            const errBody = await resp.text();
            throw new Error(`Could not tag photo (${resp.status}): ${String(errBody || '').slice(0, 200)}`);
        }
        return resp.json();
    };

    // Auto-saved on blur; no-op when the note is unchanged.
    const saveNote = async (photoId) => {
        const draft = noteDrafts[photoId] ?? '';
        const current = photos.find((p) => p.id === photoId)?.note || '';
        if (draft === current) return;
        setError(null);
        try {
            const resp = await fetch(`${API_BASE_URL}/brain/releases/${releaseId}/photos/${photoId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ note: draft }),
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
            setSelectedIds((prev) => {
                if (!prev.has(photoId)) return prev;
                const next = new Set(prev);
                next.delete(photoId);
                return next;
            });
            seenIdsRef.current.delete(photoId);
        } catch (err) {
            setError(err?.message || 'Failed to delete photo');
        }
    };

    if (!isOpen) return null;

    const destination = requestedStage || gateStage;
    const uploadTotal = uploads.length;
    const uploadFinished = uploads.filter((u) => u.status === 'done' || u.status === 'failed').length;
    const uploadFailed = uploads.filter((u) => u.status === 'failed').length;
    const taggedOnRelease = !!gateStage && photos.some((p) => p.stage === gateStage);
    const selectedCount = gateStage ? selectedIds.size : 0;
    const selectionSatisfied = selectedCount > 0;
    const reason = exceptionNote.trim();
    // Words stand in only when this handoff has no photo in the included set and none
    // already tagged. A tagged photo the user unchecked still blocks the exception.
    const reasonSatisfied = !!gateStage && !selectionSatisfied && !taggedOnRelease && noPhoto && reason.length > 0;
    const gateSatisfied = !gateStage || selectionSatisfied || reasonSatisfied;

    const confirm = async () => {
        if (!gateSatisfied || busy || tagging) return;
        if (selectionSatisfied) {
            const pending = photos.filter((p) => selectedIds.has(p.id) && p.stage !== gateStage);
            if (pending.length === 0) {
                onConfirmStage?.(null);
                return;
            }
            setTagging(true);
            setError(null);
            try {
                const updated = await Promise.all(pending.map((p) => tagPhoto(p.id)));
                const byId = new Map(updated.filter((p) => p && p.id != null).map((p) => [p.id, p]));
                if (byId.size) setPhotos((prev) => prev.map((p) => byId.get(p.id) || p));
                onConfirmStage?.(null);
            } catch (err) {
                setError(err?.message || 'Could not tag the selected photos');
            } finally {
                setTagging(false);
            }
            return;
        }
        onConfirmStage?.(reason);
    };

    let bannerText;
    if (!gateStage) bannerText = null;
    else if (selectionSatisfied) {
        bannerText = selectedCount === 1
            ? `✓ ${gateStage} photo attached — confirm below to move the stage.`
            : `✓ ${selectedCount} ${gateStage} photos attached — confirm below to move the stage.`;
    } else if (reasonSatisfied) bannerText = `Moving without a photo — your reason is recorded on the stage change.`;
    else if (noPhoto) bannerText = `Say why there is no ${gateStage} photo, then confirm.`;
    else bannerText = `A ${gateStage} photo is required to move to ${destination}. Choose one already on this release, upload, or take a new one.`;

    return createPortal(
        <div
            className="fixed inset-0 z-50 flex items-center justify-center"
            style={{ background: 'rgba(10,16,28,.55)', backdropFilter: 'blur(2px)' }}
            onClick={onClose}
        >
            <div
                className="bg-surface flex flex-col border border-hairline-strong"
                onClick={(e) => e.stopPropagation()}
                style={{
                    width: 'min(720px, 94vw)',
                    maxHeight: 'min(860px, 92dvh, 92vh)',
                    borderRadius: 14,
                    boxShadow: 'var(--shadow, 0 24px 60px rgba(15,26,48,.22))',
                }}
            >
                <div
                    className="shrink-0 flex items-center justify-between border-b border-hairline bg-surface-2"
                    style={{ padding: '14px 18px', borderRadius: '14px 14px 0 0' }}
                >
                    <div className="min-w-0">
                        <h2 className="font-bold text-ink truncate" style={{ fontSize: 17 }}>
                            {title ? `${title} Photos` : 'Photos'}
                        </h2>
                        {gateStage && (
                            <p className="text-ink-2" style={{ fontSize: 12.5, marginTop: 2 }}>
                                Required before moving to <strong>{destination}</strong>
                                {destination !== gateStage && (
                                    <> — the <strong>{gateStage}</strong> handoff</>
                                )}
                            </p>
                        )}
                    </div>
                    <button
                        type="button"
                        onClick={onClose}
                        className="grid place-items-center border border-hairline-strong rounded-[7px] bg-surface text-ink-2 hover:text-ink"
                        style={{ width: 28, height: 28 }}
                        aria-label="Close"
                    >
                        ×
                    </button>
                </div>

                {bannerText && (
                    <div
                        className="shrink-0 border-b border-hairline"
                        style={{
                            padding: '10px 18px',
                            fontSize: 13,
                            background: gateSatisfied ? 'var(--st-green-bg)' : 'var(--st-amber-bg)',
                            color: gateSatisfied ? 'var(--st-green-fg)' : 'var(--st-amber-fg)',
                        }}
                    >
                        {bannerText}
                    </div>
                )}

                <div className="shrink-0 border-b border-hairline" style={{ padding: '12px 18px' }}>
                    <div className="flex gap-2">
                        <button
                            type="button"
                            onClick={() => fileInputRef.current?.click()}
                            disabled={busy || tagging}
                            className={`flex-1 inline-flex items-center justify-center gap-1 text-sm border border-accent-600 text-accent-700 bg-surface disabled:opacity-50 ${touchButtonClass}`}
                        >
                            Upload photos
                        </button>
                        <button
                            type="button"
                            onClick={() => cameraInputRef.current?.click()}
                            disabled={busy || tagging}
                            className={`flex-1 inline-flex items-center justify-center gap-1 text-sm bg-accent-600 text-white disabled:opacity-50 ${touchButtonClass}`}
                            title="Capture a photo with your device camera"
                        >
                            {/* The camera returns one shot at a time, so the loop is the affordance:
                                shoot, land back here, shoot again. */}
                            📷 {photos.length > 0 || uploads.length > 0 ? 'Take another' : 'Take photo'}
                        </button>
                    </div>
                    <p className="text-ink-3" style={{ fontSize: 12, marginTop: 8 }}>
                        Upload can add several photos. Take photo adds one shot each time you use it. Or include photos already on this release.
                    </p>
                    <input
                        ref={fileInputRef}
                        type="file"
                        accept="image/*"
                        multiple
                        onChange={(e) => onFileChosen(e, fileInputRef)}
                        className="hidden"
                        aria-label="Upload photos"
                    />
                    <input
                        ref={cameraInputRef}
                        type="file"
                        accept="image/*"
                        capture="environment"
                        onChange={(e) => onFileChosen(e, cameraInputRef)}
                        className="hidden"
                        aria-label="Take a photo with the camera"
                    />
                </div>

                {/* The upload strip: a tile per picked file, alive from pick to landed. The bar
                    on the in-flight tile is real bytes (XHR progress), not a spinner guessing. */}
                {uploads.length > 0 && (
                    <div className="shrink-0 border-b border-hairline" style={{ padding: '10px 18px' }}>
                        <div className="flex items-center justify-between gap-3" style={{ fontSize: 12.5, marginBottom: 8 }}>
                            <span className="text-ink-2" aria-live="polite">
                                {busy
                                    ? `Uploading ${Math.min(uploadFinished + 1, uploadTotal)} of ${uploadTotal}…`
                                    : uploadFailed > 0
                                        ? `${uploadFailed} of ${uploadTotal} didn't upload`
                                        : `${uploadTotal} uploaded`}
                            </span>
                            {uploadFailed > 0 && !busy && (
                                <button
                                    type="button"
                                    onClick={retryAllFailed}
                                    className="text-xs font-semibold text-accent-700 hover:underline"
                                >
                                    Retry failed
                                </button>
                            )}
                        </div>
                        <ul className="flex flex-wrap gap-2">
                            {uploads.map((u) => (
                                <li
                                    key={u.key}
                                    className="relative w-16 h-16 rounded-md overflow-hidden border border-hairline bg-surface-2"
                                    title={u.status === 'failed' ? `${u.name} — ${u.error}` : u.name}
                                >
                                    <img
                                        src={u.previewUrl}
                                        alt=""
                                        className="w-full h-full object-cover"
                                        style={{ opacity: u.status === 'done' ? 1 : 0.55 }}
                                    />
                                    {u.status === 'queued' && (
                                        <span className="absolute inset-0 grid place-items-center text-[10px] font-semibold text-white bg-black/35">
                                            queued
                                        </span>
                                    )}
                                    {u.status === 'uploading' && (
                                        <>
                                            <span
                                                className="absolute top-1 right-1 w-4 h-4 rounded-full border-2 border-white/40 border-t-white animate-spin"
                                                aria-hidden="true"
                                            />
                                            <div className="absolute inset-x-0 bottom-0 h-1.5 bg-black/30">
                                                <div className="h-full bg-accent-500 transition-[width] duration-150" style={{ width: `${u.pct}%` }} />
                                            </div>
                                        </>
                                    )}
                                    {u.status === 'done' && (
                                        <span className="absolute top-1 right-1 w-4 h-4 rounded-full bg-emerald-600 text-white text-[10px] grid place-items-center">
                                            ✓
                                        </span>
                                    )}
                                    {u.status === 'failed' && (
                                        <button
                                            type="button"
                                            onClick={() => retryUpload(u)}
                                            className="absolute inset-0 grid place-items-center text-[11px] font-semibold text-white bg-red-600/80"
                                        >
                                            Retry
                                        </button>
                                    )}
                                </li>
                            ))}
                        </ul>
                    </div>
                )}

                {notice && (
                    <p className="shrink-0 text-ink-2" style={{ padding: '10px 18px 0', fontSize: 12.5 }}>
                        {notice}
                    </p>
                )}
                {error && (
                    <p className="shrink-0" style={{ padding: '10px 18px 0', fontSize: 13, color: 'var(--fl-red-bg)' }}>
                        {error}
                    </p>
                )}

                <div className="flex-1 min-h-0 overflow-y-auto" style={{ padding: '14px 18px' }}>
                    {loading && <p className="text-sm text-ink-3 italic">Loading…</p>}
                    {gateStage && !loading && photos.length > 0 && (
                        <p className="text-sm font-semibold text-ink" style={{ marginBottom: 8 }}>
                            Already on this release
                        </p>
                    )}
                    {!loading && photos.length === 0 && (
                        <p className="text-sm text-ink-3 italic">
                            No photos on this release yet. Upload photos you already have, or take new ones.
                        </p>
                    )}
                    <ul className="space-y-4">
                        {photos.map((p) => {
                            const selected = gateStage ? selectedIds.has(p.id) : false;
                            return (
                            <li
                                key={p.id}
                                className="border border-hairline rounded-lg p-3"
                                style={selected ? { borderColor: 'var(--accent)', boxShadow: '0 0 0 1px var(--accent)' } : undefined}
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
                                            className="w-24 h-24 object-cover rounded-md border border-hairline bg-surface-2"
                                        />
                                    </a>
                                    <div className="flex-1 min-w-0">
                                        {gateStage && (
                                            <label className="inline-flex items-center gap-2 text-sm font-medium text-ink cursor-pointer">
                                                <input
                                                    type="checkbox"
                                                    checked={selected}
                                                    onChange={() => toggleSelected(p.id)}
                                                />
                                                Include with {gateStage}
                                            </label>
                                        )}
                                        {gateStage && p.stage && p.stage !== gateStage && (
                                            <p className="text-ink-3" style={{ fontSize: 11, marginTop: 4 }}>
                                                Tagged {p.stage}. Including it tags it for {gateStage}.
                                            </p>
                                        )}
                                        <div className="flex items-baseline gap-2 flex-wrap" style={{ marginTop: gateStage ? 6 : 0 }}>
                                            {p.stage && (
                                                <span
                                                    className="font-semibold uppercase"
                                                    style={{
                                                        fontSize: 10,
                                                        letterSpacing: '.04em',
                                                        padding: '1px 6px',
                                                        borderRadius: 4,
                                                        background: 'var(--accent-soft)',
                                                        color: 'var(--accent)',
                                                    }}
                                                >
                                                    {p.stage}
                                                </span>
                                            )}
                                            <span className="text-xs text-ink-3">{fmtDate(p.uploaded_at)}</span>
                                            <span className="text-xs text-ink-3">{p.uploaded_by?.name || '—'}</span>
                                            <span className="text-xs text-ink-3 ml-auto">{fmtSize(p.file_size_bytes)}</span>
                                        </div>
                                        {p.last_edited_by && (
                                            <p className="text-ink-3 italic" style={{ fontSize: 11, marginTop: 4 }}>
                                                Note edited by {p.last_edited_by.name || '—'} · {fmtDate(p.last_edited_at)}
                                            </p>
                                        )}
                                        <textarea
                                            value={noteDrafts[p.id] ?? ''}
                                            onChange={(e) => setNoteDrafts((prev) => ({ ...prev, [p.id]: e.target.value }))}
                                            onBlur={() => saveNote(p.id)}
                                            placeholder="Optional notes…"
                                            rows={2}
                                            className="mt-2 w-full text-sm border border-hairline-strong bg-surface text-ink rounded-md px-2 py-1 resize-y focus:outline-none focus:ring-1 focus:ring-accent-500"
                                        />
                                        <button
                                            type="button"
                                            onClick={() => deletePhoto(p.id)}
                                            className="mt-2 px-3 py-1 text-xs border border-hairline-strong text-ink-2 rounded-md hover:bg-surface-2"
                                        >
                                            Delete
                                        </button>
                                    </div>
                                </div>
                            </li>
                            );
                        })}
                    </ul>

                    {/* The exit for the ship-plate case: nothing to photograph, so the
                        reason takes the photo's place and rides on the stage event. */}
                    {gateStage && !selectionSatisfied && !taggedOnRelease && (
                        <div className="mt-4 border-t border-hairline pt-3">
                            <label className="inline-flex items-center gap-2 text-sm text-ink-2 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={noPhoto}
                                    onChange={(e) => setNoPhoto(e.target.checked)}
                                />
                                No photo available
                            </label>
                            {noPhoto && (
                                <textarea
                                    value={exceptionNote}
                                    onChange={(e) => setExceptionNote(e.target.value)}
                                    placeholder={`Why is there no ${gateStage} photo? (required)`}
                                    rows={3}
                                    autoFocus
                                    className="mt-2 w-full text-sm border border-hairline-strong bg-surface text-ink rounded-md px-2 py-1.5 resize-y focus:outline-none focus:ring-1 focus:ring-accent-500"
                                />
                            )}
                        </div>
                    )}
                </div>

                <div
                    className="shrink-0 flex justify-end gap-3 border-t border-hairline bg-surface-2"
                    style={{ padding: '12px 18px', borderRadius: '0 0 14px 14px' }}
                >
                    <button
                        type="button"
                        onClick={onClose}
                        className={`border border-hairline-strong bg-surface text-ink-2 hover:bg-surface-2 ${touchButtonClass}`}
                    >
                        {gateStage ? 'Cancel' : 'Close'}
                    </button>
                    {gateStage && (
                        <button
                            type="button"
                            onClick={confirm}
                            disabled={!gateSatisfied || busy || tagging}
                            className={`bg-accent-600 text-white hover:bg-accent-700 disabled:opacity-50 disabled:cursor-not-allowed ${touchButtonClass}`}
                            title={
                                busy
                                    ? 'Wait for the uploads to finish'
                                    : tagging
                                        ? 'Saving photo tags'
                                        : gateSatisfied
                                            ? `Move to ${destination}`
                                            : `Choose a ${gateStage} photo, upload one, or say why there is none`
                            }
                        >
                            {tagging ? 'Saving photos…' : `Confirm ${destination}`}
                        </button>
                    )}
                </div>
            </div>
        </div>,
        document.body,
    );
}

export default StagePhotoGateModal;
