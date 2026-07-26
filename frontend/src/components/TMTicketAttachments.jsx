/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Photo/video field-evidence attachments for an EXISTING T&M ticket — pick, capture,
 *          view full size, and delete. Uploads immediately on file-select (the ticket already
 *          has an id). For the create-flow (no id yet), TMTicketFormModal stages files locally
 *          instead of using this component — see its uploadStagedAttachments.
 * exports:
 *   TMTicketAttachments: Self-contained attachment manager. Props: ticketId, readOnly.
 * imports_from: [react, ../services/tmApi]
 * imported_by: [components/TMTicketFormModal.jsx]
 * invariants:
 *   - Owns its own fetch/state; does not depend on the parent ticket payload for live updates.
 *   - Add/Camera/Delete are hidden when readOnly (ticket is no longer a draft); viewing always works.
 *   - Mirrors components/board/BoardPhotos.jsx, minus drag-drop/clipboard-paste (desktop
 *     affordances not relevant to a mobile-first field form), plus video support.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
    listTicketAttachments,
    uploadTicketAttachment,
    deleteTicketAttachment,
    ticketAttachmentFileUrl,
} from '../services/tmApi';

const isMediaFile = (file) => {
    const type = (file?.type || '').toLowerCase();
    if (type.startsWith('image/') || type.startsWith('video/')) return true;
    return /\.(png|jpe?g|gif|webp|bmp|heic|heif|tiff?|mp4|mov|webm|3gp|m4v)$/i.test(file?.name || '');
};

function fmtSize(bytes) {
    if (!bytes && bytes !== 0) return '';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function TMTicketAttachments({ ticketId, readOnly }) {
    const [attachments, setAttachments] = useState([]);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);
    const [lightboxId, setLightboxId] = useState(null);

    const fileInputRef = useRef(null);
    const cameraInputRef = useRef(null);

    const load = useCallback(async () => {
        try {
            const d = await listTicketAttachments(ticketId);
            setAttachments(d.attachments || []);
        } catch {
            setError('Failed to load attachments.');
        } finally {
            setLoading(false);
        }
    }, [ticketId]);

    useEffect(() => { setLoading(true); load(); }, [load]);

    const uploadFiles = async (files) => {
        const media = Array.from(files || []).filter(isMediaFile);
        if (media.length === 0) return;
        setBusy(true);
        setError(null);
        try {
            // Sequential so the server assigns stable, ordered ids.
            for (const file of media) {
                await uploadTicketAttachment(ticketId, file);
            }
            await load();
        } catch (err) {
            setError(err?.response?.data?.error || err?.message || 'Upload failed.');
        } finally {
            setBusy(false);
        }
    };

    const handleFilePick = (e) => {
        if (e.target.files?.length) uploadFiles(e.target.files);
        e.target.value = '';
    };

    const handleDelete = async (attachmentId) => {
        if (!window.confirm('Delete this attachment?')) return;
        try {
            await deleteTicketAttachment(ticketId, attachmentId);
            setAttachments((prev) => prev.filter((a) => a.id !== attachmentId));
        } catch {
            setError('Failed to delete attachment.');
        }
    };

    const lightboxItem = attachments.find((a) => a.id === lightboxId);

    return (
        <div>
            <div className="flex items-center gap-2 mb-1.5">
                <h4 className="text-xs font-semibold text-gray-600 dark:text-slate-300">
                    Photos &amp; videos{attachments.length > 0 ? ` (${attachments.length})` : ''}
                </h4>
                {!readOnly && (
                    <div className="ml-auto flex items-center gap-1.5">
                        <button type="button" onClick={() => fileInputRef.current?.click()} disabled={busy}
                            className="text-xs px-3 py-1.5 rounded-md border border-gray-300 dark:border-slate-600 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700 disabled:opacity-50">
                            + Add
                        </button>
                        <button type="button" onClick={() => cameraInputRef.current?.click()} disabled={busy}
                            className="sm:hidden text-xs px-3 py-1.5 rounded-md border border-gray-300 dark:border-slate-600 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700 disabled:opacity-50">
                            Camera
                        </button>
                    </div>
                )}
                <input ref={fileInputRef} type="file" accept="image/*,video/*" multiple
                    onChange={handleFilePick} className="hidden" />
                <input ref={cameraInputRef} type="file" accept="image/*,video/*" capture="environment"
                    onChange={handleFilePick} className="hidden" />
            </div>

            {error && (
                <div className="mb-1.5 text-xs text-red-600 dark:text-red-400">{error}</div>
            )}
            {busy && (
                <div className="mb-1.5 text-xs text-gray-400 dark:text-slate-500">Uploading…</div>
            )}

            {loading ? (
                <div className="text-xs text-gray-400 dark:text-slate-500 py-1">Loading…</div>
            ) : attachments.length === 0 ? (
                <div className="rounded-lg border border-dashed border-gray-200 dark:border-slate-700 px-3 py-3 text-center text-xs text-gray-400 dark:text-slate-500">
                    {readOnly ? 'No photos or videos.' : 'No photos or videos yet. Use Add or Camera.'}
                </div>
            ) : (
                <div className="grid grid-cols-3 gap-2">
                    {attachments.map((a) => (
                        <div key={a.id} className="group relative">
                            <button type="button" onClick={() => setLightboxId(a.id)} className="block w-full" title="View full size">
                                {a.is_video ? (
                                    <div className="w-full h-20 flex flex-col items-center justify-center gap-0.5 rounded-md border border-gray-200 dark:border-slate-600 bg-gray-50 dark:bg-slate-700">
                                        <span className="text-lg">▶</span>
                                        <span className="text-[10px] text-gray-500 dark:text-slate-400 truncate max-w-full px-1">
                                            {a.original_filename || 'video'}
                                        </span>
                                    </div>
                                ) : (
                                    <img
                                        src={ticketAttachmentFileUrl(ticketId, a.id)}
                                        alt={a.original_filename || 'photo'}
                                        className="w-full h-20 object-cover rounded-md border border-gray-200 dark:border-slate-600 bg-gray-50 dark:bg-slate-700"
                                    />
                                )}
                            </button>
                            {!readOnly && (
                                <button type="button" onClick={() => handleDelete(a.id)}
                                    className="absolute top-1 right-1 w-6 h-6 flex items-center justify-center rounded-full bg-black/60 text-white text-sm hover:bg-red-600"
                                    title="Delete">
                                    &times;
                                </button>
                            )}
                        </div>
                    ))}
                </div>
            )}

            {lightboxItem && (
                <div className="fixed inset-0 z-[60] bg-black/80 flex items-center justify-center p-4" onClick={() => setLightboxId(null)}>
                    <div className="max-w-full max-h-full flex flex-col items-center gap-2" onClick={(e) => e.stopPropagation()}>
                        {lightboxItem.is_video ? (
                            <video src={ticketAttachmentFileUrl(ticketId, lightboxItem.id)} controls autoPlay
                                className="max-w-full max-h-[80vh] rounded-lg" />
                        ) : (
                            <img src={ticketAttachmentFileUrl(ticketId, lightboxItem.id)}
                                alt={lightboxItem.original_filename || 'photo'}
                                className="max-w-full max-h-[80vh] object-contain rounded-lg" />
                        )}
                        <div className="flex items-center gap-3 text-xs text-gray-200">
                            <span className="text-gray-400">
                                {lightboxItem.uploaded_by?.name || '—'} · {fmtSize(lightboxItem.file_size_bytes)}
                            </span>
                            <a href={ticketAttachmentFileUrl(ticketId, lightboxItem.id)} target="_blank" rel="noopener noreferrer"
                                className="text-accent-400 hover:text-accent-300">
                                Open in tab
                            </a>
                            <button type="button" onClick={() => setLightboxId(null)} className="text-gray-300 hover:text-white">
                                Close
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
