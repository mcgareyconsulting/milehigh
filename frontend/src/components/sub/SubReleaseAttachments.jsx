/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The Attachments tab of the sub release page as a READER (release-mobile-
 *          recommendations.md §4a): a Drawings section (one row per version, current flagged,
 *          uploader + date, size) and a Photos section (thumbnail rows with the stage tag). A
 *          drawing opens SubDrawingReader; a photo opens a full-screen image view. No upload, no
 *          markup, no Carmen: uploads need an authorship-model change (uploaded_by_user_id is a
 *          NOT NULL users FK) and the rest is desktop-only by the spec's own "what stays desktop".
 * exports:
 *   SubReleaseAttachments: ({ releaseId, code, onCount })
 * imports_from: [react, ../../services/subPortalApi, ./SubDrawingReader]
 * imported_by: [pages/SubcontractorRelease.jsx]
 * invariants:
 *   - All file URLs are the sub-scoped stream routes; nothing here can address a staff route.
 *   - Older versions of a drawing are listed under the current one rather than behind a menu,
 *     because a sub has no "⋯" actions to put there yet.
 */
import { useCallback, useEffect, useState } from 'react';
import { getSubAttachments, subDrawingFileUrl, subPhotoFileUrl } from '../../services/subPortalApi';
import SubDrawingReader from './SubDrawingReader';

const fmtSize = (b) => {
    if (b == null) return '';
    if (b < 1024) return `${b} B`;
    if (b < 1024 * 1024) return `${Math.round(b / 1024)} KB`;
    return `${(b / (1024 * 1024)).toFixed(1)} MB`;
};
const fmtDate = (iso) => {
    if (!iso) return '';
    const d = new Date(iso);
    return isNaN(d) ? '' : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

const ICONS = {
    pdf: <svg viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6M8 13h8M8 17h5" /></svg>,
    back: <svg viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6" /></svg>,
};

function PhotoViewer({ src, title, meta, onClose }) {
    useEffect(() => {
        const onKey = (e) => { if (e.key === 'Escape') onClose(); };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [onClose]);
    return (
        <div className="sub-reader" role="dialog" aria-modal="true" aria-label={title}>
            <div className="sub-reader-head">
                <button type="button" className="sub-iconbtn" aria-label="Back" onClick={onClose}>{ICONS.back}</button>
                <div className="title"><div className="fname">{title}</div>{meta && <div className="fmeta">{meta}</div>}</div>
            </div>
            <div className="sub-reader-body flex items-center justify-center p-2">
                <img src={src} alt={title} style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} />
            </div>
        </div>
    );
}

export default function SubReleaseAttachments({ releaseId, code, onCount }) {
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);
    const [openDrawing, setOpenDrawing] = useState(null);
    const [openPhoto, setOpenPhoto] = useState(null);

    const load = useCallback(async () => {
        try {
            const d = await getSubAttachments(releaseId);
            setData(d);
            setError(null);
            onCount?.((d.drawings?.length || 0) + (d.photos?.length || 0));
        } catch (e) {
            setError(e?.response?.data?.error || 'Could not load attachments');
        }
    }, [releaseId, onCount]);
    useEffect(() => { load(); }, [load]);

    const drawings = data?.drawings || [];
    const photos = data?.photos || [];

    return (
        <div className="flex-1 min-h-0 overflow-y-auto pb-6">
            {error && <p className="px-4 py-3 text-sm text-red-600">{error}</p>}
            {!data && !error && <p className="px-4 py-3 text-sm text-ink-3">Loading…</p>}

            {data && (
                <>
                    <section className="sub-section">
                        <h3 className="sub-section-label">Drawings</h3>
                        {drawings.length === 0 && <p className="sub-quiet">No drawings on this release yet.</p>}
                        {drawings.map((v) => (
                            <button key={v.id} type="button" className="sub-file" onClick={() => setOpenDrawing(v)}>
                                <span className="icon">{ICONS.pdf}</span>
                                <span className="min-w-0 flex-1">
                                    <span className="fname block">{v.original_filename || `Drawing v${v.version_number}`}</span>
                                    <span className="fmeta block">
                                        {[fmtSize(v.file_size_bytes), v.uploaded_by_name, fmtDate(v.uploaded_at)].filter(Boolean).join(' · ')}
                                    </span>
                                    <span className="chips">
                                        <span className={v.is_current ? 'current' : ''}>v{v.version_number}{v.is_current ? ' · current' : ''}</span>
                                        {v.release_label && v.release_label !== code && <span>{v.release_label}</span>}
                                    </span>
                                </span>
                            </button>
                        ))}
                    </section>

                    <section className="sub-section">
                        <h3 className="sub-section-label">Photos</h3>
                        {photos.length === 0 && <p className="sub-quiet">No photos on this release yet.</p>}
                        {photos.map((p) => (
                            <button key={p.id} type="button" className="sub-file" onClick={() => setOpenPhoto(p)}>
                                <span className="icon"><img src={subPhotoFileUrl(releaseId, p.id)} alt="" loading="lazy" /></span>
                                <span className="min-w-0 flex-1">
                                    <span className="fname block">{p.note || p.original_filename || 'Photo'}</span>
                                    <span className="fmeta block">
                                        {[fmtDate(p.uploaded_at), p.uploaded_by_name, p.stage ? `at ${p.stage}` : null].filter(Boolean).join(' · ')}
                                    </span>
                                </span>
                            </button>
                        ))}
                    </section>
                </>
            )}

            {openDrawing && (
                <SubDrawingReader
                    url={subDrawingFileUrl(openDrawing.release_id, openDrawing.id)}
                    title={openDrawing.original_filename || `Drawing v${openDrawing.version_number}`}
                    meta={`v${openDrawing.version_number} · ${openDrawing.release_label || code}`}
                    onClose={() => setOpenDrawing(null)}
                />
            )}
            {openPhoto && (
                <PhotoViewer
                    src={subPhotoFileUrl(releaseId, openPhoto.id)}
                    title={openPhoto.note || openPhoto.original_filename || 'Photo'}
                    meta={[fmtDate(openPhoto.uploaded_at), openPhoto.uploaded_by_name].filter(Boolean).join(' · ')}
                    onClose={() => setOpenPhoto(null)}
                />
            )}
        </div>
    );
}
