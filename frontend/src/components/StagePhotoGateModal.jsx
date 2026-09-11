/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The stage-photo gate — a focused dialog that requires a photo tagged with the
 *   gated stage before the Job Log stage change is applied. Also the place photos get a
 *   note, or get deleted. Split out of the retired PdfVersionHistoryModal; drawings now
 *   live in the hybrid viewer (pdfViewer/PdfViewerPane).
 * exports:
 *   StagePhotoGateModal: props { isOpen, releaseId, title, gateStage, onConfirmStage, onClose }
 * imports_from: [react, react-dom, ../utils/api, ../utils/imageCompress, ./pdfViewer/format]
 * imported_by: [frontend/src/components/JobsTableRow.jsx]
 * invariants:
 *   - Confirm stays disabled until a non-deleted photo tagged with gateStage exists
 *   - Uploads (file picker or camera) are auto-tagged with the gated stage
 *   - Notes auto-save on blur, and only when the text actually changed
 * updated_by_agent: 2026-09-05T00:00:00Z
 */
import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import { API_BASE_URL } from '../utils/api';
import { compressImage } from '../utils/imageCompress';
import { fmtDate, fmtSize } from './pdfViewer/format';

export function StagePhotoGateModal({
    isOpen,
    releaseId,
    title = '',
    gateStage = null,
    onConfirmStage = null,
    onClose,
}) {
    const [photos, setPhotos] = useState([]);
    const [loading, setLoading] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);
    const [noteDrafts, setNoteDrafts] = useState({});
    const fileInputRef = useRef(null);
    const cameraInputRef = useRef(null);

    const loadPhotos = async () => {
        if (!releaseId) return;
        setLoading(true);
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
            setLoading(false);
        }
    };

    useEffect(() => {
        if (!isOpen) return;
        setError(null);
        loadPhotos();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen, releaseId]);

    useEffect(() => {
        if (!isOpen) return undefined;
        const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [isOpen, onClose]);

    const uploadPhoto = async (file) => {
        setBusy(true);
        setError(null);
        try {
            // Shrink phone-camera shots before they hit LTE; see utils/imageCompress.js.
            const payload = await compressImage(file);
            const fd = new FormData();
            fd.append('file', payload);
            if (gateStage) fd.append('stage', gateStage);
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
            setBusy(false);
        }
    };

    const onFileChosen = async (event, ref) => {
        const file = event.target.files?.[0];
        if (!file) return;
        try {
            await uploadPhoto(file);
        } finally {
            if (ref.current) ref.current.value = '';
        }
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
        } catch (err) {
            setError(err?.message || 'Failed to delete photo');
        }
    };

    if (!isOpen) return null;

    const gateSatisfied = !gateStage || photos.some((p) => p.stage === gateStage);

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
                                Required before moving to <strong>{gateStage}</strong>
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

                {gateStage && (
                    <div
                        className="shrink-0 border-b border-hairline"
                        style={{
                            padding: '10px 18px',
                            fontSize: 13,
                            background: gateSatisfied ? 'var(--st-green-bg)' : 'var(--st-amber-bg)',
                            color: gateSatisfied ? 'var(--st-green-fg)' : 'var(--st-amber-fg)',
                        }}
                    >
                        {gateSatisfied
                            ? `✓ Photo for ${gateStage} attached — confirm below to move the stage.`
                            : `A photo is required to move to ${gateStage}. Add one — it is tagged automatically.`}
                    </div>
                )}

                <div className="shrink-0 flex flex-wrap items-center gap-3 border-b border-hairline" style={{ padding: '12px 18px' }}>
                    <input
                        ref={fileInputRef}
                        type="file"
                        accept="image/*"
                        onChange={(e) => onFileChosen(e, fileInputRef)}
                        disabled={busy}
                        className="text-sm"
                    />
                    <button
                        type="button"
                        onClick={() => cameraInputRef.current?.click()}
                        disabled={busy}
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
                        onChange={(e) => onFileChosen(e, cameraInputRef)}
                        className="hidden"
                    />
                    {busy && <span className="text-sm text-ink-3">Uploading…</span>}
                </div>

                {error && (
                    <p className="shrink-0" style={{ padding: '10px 18px 0', fontSize: 13, color: 'var(--fl-red-bg)' }}>
                        {error}
                    </p>
                )}

                <div className="flex-1 min-h-0 overflow-y-auto" style={{ padding: '14px 18px' }}>
                    {loading && <p className="text-sm text-ink-3 italic">Loading…</p>}
                    {!loading && photos.length === 0 && (
                        <p className="text-sm text-ink-3 italic">
                            No photos yet — choose an image above or use “Take photo”.
                        </p>
                    )}
                    <ul className="space-y-4">
                        {photos.map((p) => (
                            <li key={p.id} className="border border-hairline rounded-lg p-3">
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
                                        <div className="flex items-baseline gap-2 flex-wrap">
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
                        ))}
                    </ul>
                </div>

                <div
                    className="shrink-0 flex justify-end gap-3 border-t border-hairline bg-surface-2"
                    style={{ padding: '12px 18px', borderRadius: '0 0 14px 14px' }}
                >
                    <button
                        type="button"
                        onClick={onClose}
                        className="px-4 py-2 border border-hairline-strong bg-surface text-ink-2 rounded-lg font-medium hover:bg-surface-2"
                    >
                        {gateStage ? 'Cancel' : 'Close'}
                    </button>
                    {gateStage && (
                        <button
                            type="button"
                            onClick={() => onConfirmStage?.()}
                            disabled={!gateSatisfied}
                            className="px-4 py-2 bg-accent-600 text-white rounded-lg font-semibold hover:bg-accent-700 disabled:opacity-50 disabled:cursor-not-allowed"
                            title={gateSatisfied ? `Move to ${gateStage}` : `Upload a ${gateStage} photo first`}
                        >
                            Confirm {gateStage}
                        </button>
                    )}
                </div>
            </div>
        </div>,
        document.body,
    );
}

export default StagePhotoGateModal;
