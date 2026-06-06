/**
 * Attachment hub for a release, split into two columns:
 *   - Drawings: the saved PDF version history. Each row offers View (read-only)
 *     and Edit (opens the markup modal seeded from that version).
 *   - Photos: a flat list of image attachments, each with an editable optional
 *     note. A "Take photo" button captures straight from the device camera.
 *
 * The single "Choose file" picker lives above both columns: PDFs are routed to
 * the Drawings flow (next version), images are routed to the Photos flow.
 */
import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { API_BASE_URL } from '../utils/api';

const isPdfFile = (file) =>
    (file?.type || '').toLowerCase() === 'application/pdf' ||
    (file?.name || '').toLowerCase().endsWith('.pdf');

const isImageFile = (file) =>
    (file?.type || '').toLowerCase().startsWith('image/') ||
    /\.(png|jpe?g|gif|webp|bmp|heic|heif|tiff?)$/i.test(file?.name || '');

export function PdfVersionHistoryModal({
    isOpen,
    releaseId,
    onClose,
    onOpenVersion,
    viewerUrl = '',
}) {
    const [versions, setVersions] = useState([]);
    const [photos, setPhotos] = useState([]);
    const [loading, setLoading] = useState(false);
    const [photosLoading, setPhotosLoading] = useState(false);
    const [error, setError] = useState(null);
    const [uploading, setUploading] = useState(false);
    const [photoBusy, setPhotoBusy] = useState(false);
    const [noteDrafts, setNoteDrafts] = useState({});
    const fileInputRef = useRef(null);
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

    useEffect(() => {
        if (!isOpen) return;
        const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [isOpen, onClose]);

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

    const uploadPhoto = async (file) => {
        setPhotoBusy(true);
        setError(null);
        try {
            const fd = new FormData();
            fd.append('file', file);
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
                await uploadPhoto(file);
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
            await uploadPhoto(file);
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

    return createPortal(
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"
            onClick={onClose}
        >
            <div
                className="bg-white rounded-xl shadow-2xl w-full max-w-5xl mx-4 max-h-[85vh] flex flex-col"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-6 py-4 rounded-t-xl flex items-center justify-between gap-3">
                    <h2 className="text-xl font-bold text-white">Attachments</h2>
                    <div className="flex items-center gap-3">
                        {viewerUrl && viewerUrl.trim() !== '' ? (
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

                {/* Choose file — lives outside the two columns; routes by file type. */}
                <div className="px-6 py-4 border-b border-gray-200 flex flex-wrap items-center gap-3">
                    <input
                        ref={fileInputRef}
                        type="file"
                        accept="application/pdf,.pdf,image/*"
                        onChange={handleFileChosen}
                        disabled={uploading || photoBusy}
                        className="text-sm"
                    />
                    <span className="text-xs text-gray-500">
                        PDFs go to Drawings; images go to Photos.
                    </span>
                    {(uploading || photoBusy) && <span className="text-sm text-gray-500">Uploading…</span>}
                </div>

                {error && (
                    <div className="px-6 pt-3">
                        <p className="text-sm text-red-600">{error}</p>
                    </div>
                )}

                <div className="px-6 py-4 overflow-y-auto flex-1 grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* ── Drawings column ───────────────────────────────────── */}
                    <section className="min-w-0">
                        <h3 className="text-sm font-bold text-gray-800 uppercase tracking-wide mb-3 pb-2 border-b border-gray-200">
                            Drawings
                        </h3>
                        {loading && <p className="text-sm text-gray-500 italic">Loading…</p>}
                        {!loading && versions.length === 0 && (
                            <p className="text-sm text-gray-500 italic">
                                No drawings yet — choose a PDF above to create v1.
                            </p>
                        )}
                        {!loading && versions.length > 0 && (
                            <ul className="space-y-3">
                                {versions.map((v) => (
                                    <li
                                        key={v.id}
                                        className="border border-gray-200 rounded-lg p-3 flex items-center gap-3"
                                    >
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-baseline gap-2 flex-wrap">
                                                <span className="font-semibold text-gray-900">v{v.version_number}</span>
                                                <span className="text-xs text-gray-500">{fmtDate(v.uploaded_at)}</span>
                                                <span className="text-xs text-gray-500">
                                                    {v.uploaded_by?.name || '—'}
                                                </span>
                                                <span className="text-xs text-gray-400 ml-auto">{fmtSize(v.file_size_bytes)}</span>
                                            </div>
                                            {v.note && (
                                                <p className="text-sm text-gray-700 mt-1 break-words">{v.note}</p>
                                            )}
                                            {v.source_version_id != null && (
                                                <p className="text-xs text-gray-400 mt-1">from v-id {v.source_version_id}</p>
                                            )}
                                        </div>
                                        <button
                                            type="button"
                                            onClick={() => onOpenVersion?.(v.id, 'view')}
                                            className="px-3 py-2 text-sm border border-gray-300 rounded-md hover:bg-gray-50"
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
                                    </li>
                                ))}
                            </ul>
                        )}
                    </section>

                    {/* ── Photos column ─────────────────────────────────────── */}
                    <section className="min-w-0">
                        <div className="flex items-center justify-between mb-3 pb-2 border-b border-gray-200">
                            <h3 className="text-sm font-bold text-gray-800 uppercase tracking-wide">
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
                        {photosLoading && <p className="text-sm text-gray-500 italic">Loading…</p>}
                        {!photosLoading && photos.length === 0 && (
                            <p className="text-sm text-gray-500 italic">
                                No photos yet — choose an image above or use “Take photo”.
                            </p>
                        )}
                        {!photosLoading && photos.length > 0 && (
                            <ul className="space-y-4">
                                {photos.map((p) => (
                                    <li
                                        key={p.id}
                                        className="border border-gray-200 rounded-lg p-3"
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
                                                    className="w-24 h-24 object-cover rounded-md border border-gray-200 bg-gray-50"
                                                />
                                            </a>
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-baseline gap-2 flex-wrap">
                                                    <span className="text-xs text-gray-500">{fmtDate(p.uploaded_at)}</span>
                                                    <span className="text-xs text-gray-500">{p.uploaded_by?.name || '—'}</span>
                                                    <span className="text-xs text-gray-400 ml-auto">{fmtSize(p.file_size_bytes)}</span>
                                                </div>
                                                <textarea
                                                    value={noteDrafts[p.id] ?? ''}
                                                    onChange={(e) =>
                                                        setNoteDrafts((prev) => ({ ...prev, [p.id]: e.target.value }))
                                                    }
                                                    onBlur={() => saveNote(p.id)}
                                                    placeholder="Optional notes…"
                                                    rows={2}
                                                    className="mt-2 w-full text-sm border border-gray-300 rounded-md px-2 py-1 resize-y focus:outline-none focus:ring-1 focus:ring-accent-500"
                                                />
                                                <div className="flex items-center gap-2 mt-2">
                                                    <button
                                                        type="button"
                                                        onClick={() => deletePhoto(p.id)}
                                                        className="px-3 py-1 text-xs border border-gray-300 text-gray-600 rounded-md hover:bg-gray-50"
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

                <div className="bg-gray-50 px-6 py-4 rounded-b-xl border-t border-gray-200 flex justify-end">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg font-medium hover:bg-gray-300"
                    >
                        Close
                    </button>
                </div>
            </div>
        </div>,
        document.body,
    );
}

export default PdfVersionHistoryModal;
