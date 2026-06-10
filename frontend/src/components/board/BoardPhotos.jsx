/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Photo/screenshot attachments section for a board (bug tracker) item — paste, pick, drop, or capture multiple images, view full size, and delete.
 * exports:
 *   BoardPhotos: Self-contained photo manager rendered inside BoardDetail for a single board item.
 * imports_from: [react, ../../services/boardApi]
 * imported_by: [components/board/BoardDetail.jsx]
 * invariants:
 *   - Owns its own photo state/fetch; does not depend on the item payload for live updates.
 *   - Clipboard paste is captured at the document level only while this component is mounted (i.e. a card is open).
 *   - Photos carry no per-photo caption; context lives in the card body.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
    fetchBoardPhotos,
    uploadBoardPhoto,
    deleteBoardPhoto,
    boardPhotoFileUrl,
} from '../../services/boardApi';

const isImageFile = (file) =>
    (file?.type || '').toLowerCase().startsWith('image/') ||
    /\.(png|jpe?g|gif|webp|bmp|heic|heif|tiff?)$/i.test(file?.name || '');

function fmtSize(bytes) {
    if (!bytes && bytes !== 0) return '';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function BoardPhotos({ itemId }) {
    const [photos, setPhotos] = useState([]);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);
    const [dragOver, setDragOver] = useState(false);
    const [lightboxId, setLightboxId] = useState(null);

    const fileInputRef = useRef(null);
    const cameraInputRef = useRef(null);

    const load = useCallback(async () => {
        try {
            const list = await fetchBoardPhotos(itemId);
            setPhotos(list);
        } catch {
            setError('Failed to load photos.');
        } finally {
            setLoading(false);
        }
    }, [itemId]);

    useEffect(() => {
        setLoading(true);
        load();
    }, [load]);

    const uploadFiles = useCallback(async (files) => {
        const images = Array.from(files || []).filter(isImageFile);
        if (images.length === 0) return;
        setBusy(true);
        setError(null);
        try {
            // Upload sequentially so the server assigns stable, ordered ids.
            for (const file of images) {
                await uploadBoardPhoto(itemId, file);
            }
            await load();
        } catch (err) {
            setError(err?.response?.data?.error || err?.message || 'Upload failed.');
        } finally {
            setBusy(false);
        }
    }, [itemId, load]);

    // Capture clipboard pastes while a card is open (key affordance for screenshots).
    useEffect(() => {
        const onPaste = (e) => {
            const items = e.clipboardData?.items;
            if (!items) return;
            const files = [];
            for (const it of items) {
                if (it.kind === 'file') {
                    const f = it.getAsFile();
                    if (f && isImageFile(f)) files.push(f);
                }
            }
            if (files.length) {
                e.preventDefault();
                uploadFiles(files);
            }
        };
        document.addEventListener('paste', onPaste);
        return () => document.removeEventListener('paste', onPaste);
    }, [uploadFiles]);

    const handleDrop = (e) => {
        e.preventDefault();
        setDragOver(false);
        if (e.dataTransfer?.files?.length) uploadFiles(e.dataTransfer.files);
    };

    const handleFilePick = (e) => {
        if (e.target.files?.length) uploadFiles(e.target.files);
        e.target.value = '';
    };

    const handleDelete = async (photoId) => {
        if (!window.confirm('Delete this photo?')) return;
        try {
            await deleteBoardPhoto(itemId, photoId);
            setPhotos((prev) => prev.filter((p) => p.id !== photoId));
        } catch {
            setError('Failed to delete photo.');
        }
    };

    const lightboxPhoto = photos.find((p) => p.id === lightboxId);

    return (
        <div
            className="shrink-0 mb-2"
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
        >
            <div className="flex items-center gap-2 mb-1.5">
                <h4 className="text-[11px] font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider">
                    Photos{photos.length > 0 ? ` (${photos.length})` : ''}
                </h4>
                <div className="ml-auto flex items-center gap-1.5">
                    <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        disabled={busy}
                        className="px-2 py-0.5 text-[11px] font-medium text-gray-600 dark:text-slate-300 bg-gray-100 dark:bg-slate-700 hover:bg-gray-200 dark:hover:bg-slate-600 rounded disabled:opacity-50"
                    >
                        Add
                    </button>
                    <button
                        type="button"
                        onClick={() => cameraInputRef.current?.click()}
                        disabled={busy}
                        className="px-2 py-0.5 text-[11px] font-medium text-gray-600 dark:text-slate-300 bg-gray-100 dark:bg-slate-700 hover:bg-gray-200 dark:hover:bg-slate-600 rounded disabled:opacity-50 sm:hidden"
                    >
                        Camera
                    </button>
                </div>
                <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    multiple
                    onChange={handleFilePick}
                    className="hidden"
                />
                <input
                    ref={cameraInputRef}
                    type="file"
                    accept="image/*"
                    capture="environment"
                    onChange={handleFilePick}
                    className="hidden"
                />
            </div>

            <div className={`rounded-lg border border-dashed px-2.5 py-2 transition-colors ${
                dragOver
                    ? 'border-accent-500 bg-accent-50 dark:bg-accent-900/20'
                    : 'border-gray-200 dark:border-slate-600'
            }`}>
                {error && (
                    <div className="text-[11px] text-red-600 dark:text-red-400 mb-1.5">{error}</div>
                )}
                {busy && (
                    <div className="text-[11px] text-gray-400 dark:text-slate-500 mb-1.5">Uploading…</div>
                )}
                {loading ? (
                    <div className="text-[11px] text-gray-400 dark:text-slate-500 py-1">Loading…</div>
                ) : photos.length === 0 ? (
                    <div className="text-[11px] text-gray-400 dark:text-slate-500 py-1">
                        Paste a screenshot, drop an image, or use Add.
                    </div>
                ) : (
                    <div className="grid grid-cols-3 gap-2">
                        {photos.map((p) => (
                            <div key={p.id} className="group relative">
                                <button
                                    type="button"
                                    onClick={() => setLightboxId(p.id)}
                                    className="block w-full"
                                    title="View full size"
                                >
                                    <img
                                        src={boardPhotoFileUrl(itemId, p.id)}
                                        alt={p.original_filename || 'photo'}
                                        className="w-full h-20 object-cover rounded-md border border-gray-200 dark:border-slate-600 bg-gray-50 dark:bg-slate-700"
                                    />
                                </button>
                                <button
                                    type="button"
                                    onClick={() => handleDelete(p.id)}
                                    className="absolute top-1 right-1 w-5 h-5 flex items-center justify-center rounded-full bg-black/50 text-white text-xs opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-600"
                                    title="Delete"
                                >
                                    &times;
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {lightboxPhoto && (
                <div
                    className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
                    onClick={() => setLightboxId(null)}
                >
                    <div className="max-w-full max-h-full flex flex-col items-center gap-2" onClick={(e) => e.stopPropagation()}>
                        <img
                            src={boardPhotoFileUrl(itemId, lightboxPhoto.id)}
                            alt={lightboxPhoto.original_filename || 'photo'}
                            className="max-w-full max-h-[80vh] object-contain rounded-lg"
                        />
                        <div className="flex items-center gap-3 text-xs text-gray-200">
                            <span className="text-gray-400">
                                {lightboxPhoto.uploaded_by?.name || '—'} · {fmtSize(lightboxPhoto.file_size_bytes)}
                            </span>
                            <a
                                href={boardPhotoFileUrl(itemId, lightboxPhoto.id)}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-accent-400 hover:text-accent-300"
                            >
                                Open in tab
                            </a>
                            <button
                                type="button"
                                onClick={() => setLightboxId(null)}
                                className="text-gray-300 hover:text-white"
                            >
                                Close
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
