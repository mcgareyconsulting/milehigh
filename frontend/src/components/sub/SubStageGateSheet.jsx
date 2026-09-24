/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The phone's department photo gate (T13). When a stage change answers 422
 *          photo_required, this bottom sheet says which handoff photo is owed. The crew
 *          can reuse photos already on the release (retagging them onto the gate stage),
 *          take or upload a new one, or say why there is none. Phone-shaped and
 *          adapter-driven, so it serves both the sub portal and the employee shell.
 * exports:
 *   SubStageGateSheet: ({ gateStage, requestedStage, releaseId, api, onSatisfied, onClose })
 *     onSatisfied({ gateExceptionNote? }) is called after evidence is in place (no note)
 *     or when the user submits a reason (note set); the caller retries the stage change.
 * imports_from: [react]
 * imported_by: [components/mobile/MobileReleasePage.jsx]
 */
import { useEffect, useRef, useState } from 'react';

const ICONS = {
    camera: <svg viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" /><circle cx="12" cy="13" r="4" /></svg>,
    upload: <svg viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><path d="M17 8l-5-5-5 5M12 3v12" /></svg>,
};

export default function SubStageGateSheet({ gateStage, requestedStage, releaseId, api, onSatisfied, onClose }) {
    const [mode, setMode] = useState('photo'); // 'photo' | 'reason'
    const [reason, setReason] = useState('');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);
    const [photos, setPhotos] = useState(null);
    const [selected, setSelected] = useState(() => new Set());
    const [viewing, setViewing] = useState(null);
    const cameraRef = useRef(null);
    const libraryRef = useRef(null);

    useEffect(() => {
        const onKey = (e) => { if (e.key === 'Escape') onClose(); };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [onClose]);

    useEffect(() => {
        let cancelled = false;
        api.getAttachments(releaseId).then((d) => {
            if (cancelled) return;
            const list = d?.photos || [];
            setPhotos(list);
            setSelected(new Set(list.filter((p) => p.stage === gateStage).map((p) => p.id)));
        }).catch((err) => {
            if (!cancelled) setError(err?.response?.data?.error || 'Could not load photos');
        });
        return () => { cancelled = true; };
    }, [api, releaseId, gateStage]);

    const toggle = (id) => {
        setSelected((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    const tagSelected = async () => {
        const pending = (photos || []).filter((p) => selected.has(p.id) && p.stage !== gateStage);
        await Promise.all(pending.map((p) => api.tagPhoto(releaseId, p.id, gateStage)));
    };

    const onFile = async (e) => {
        const file = e.target.files?.[0];
        e.target.value = '';
        if (!file) return;
        setBusy(true);
        setError(null);
        try {
            await api.uploadPhoto(releaseId, file, { stage: gateStage });
            await onSatisfied({});
        } catch (err) {
            setError(err?.response?.data?.error || 'Could not upload the photo');
            setBusy(false);
        }
    };

    const useSelected = async () => {
        if (!selected.size || busy) return;
        setBusy(true);
        setError(null);
        try {
            await tagSelected();
            await onSatisfied({});
        } catch (err) {
            setError(err?.response?.data?.error || err?.message || 'Could not use these photos');
            setBusy(false);
        }
    };

    const submitReason = async () => {
        if (!reason.trim()) return;
        setBusy(true);
        setError(null);
        try {
            await onSatisfied({ gateExceptionNote: reason.trim() });
        } catch (err) {
            setError(err?.response?.data?.error || 'Could not change the stage');
            setBusy(false);
        }
    };

    const taggedAlready = (photos || []).some((p) => p.stage === gateStage);

    return (
        <>
            <div className="sub-scrim" onClick={onClose} aria-hidden="true" />
            <section className="sub-sheet" role="dialog" aria-modal="true" aria-label="Photo required">
                <div className="grab" />
                <h2>Photo required</h2>
                <p className="sub-note">
                    Moving to <b>{requestedStage}</b> needs a handoff photo tagged <b>{gateStage}</b>.
                    Use one already on this release, take a new one, or say why there is none.
                </p>
                {error && <p className="text-sm text-red-600 mb-2">{error}</p>}

                {mode === 'photo' ? (
                    <>
                        <div style={{ maxHeight: '38vh', overflowY: 'auto' }}>
                            {photos == null && !error && <p className="sub-quiet">Loading photos…</p>}
                            {photos && photos.length === 0 && (
                                <p className="sub-quiet">No photos on this release yet.</p>
                            )}
                            {photos && photos.map((p) => (
                                <div key={p.id} className="sub-file">
                                    <button
                                        type="button"
                                        className="icon"
                                        onClick={() => setViewing(p)}
                                        aria-label={`View ${p.original_filename || 'photo'}`}
                                        style={{ padding: 0, border: 0, background: 'none' }}
                                    >
                                        <img src={api.photoFileUrl(releaseId, p.id)} alt="" />
                                    </button>
                                    <label className="min-w-0 flex-1" style={{ display: 'block' }}>
                                        <span className="fname block">{p.note || p.original_filename || 'Photo'}</span>
                                        <span className="fmeta block">
                                            {p.stage && p.stage !== gateStage
                                                ? `Tagged ${p.stage}. Including it tags it for ${gateStage}.`
                                                : (p.uploaded_by_name || 'On this release')}
                                        </span>
                                        <span className="inline-flex items-center gap-2 mt-1 text-sm font-semibold">
                                            <input
                                                type="checkbox"
                                                checked={selected.has(p.id)}
                                                onChange={() => toggle(p.id)}
                                                aria-label={`Use for ${gateStage}`}
                                            />
                                            Use for {gateStage}
                                        </span>
                                    </label>
                                </div>
                            ))}
                        </div>

                        {selected.size > 0 && (
                            <div className="sub-actions" style={{ padding: '8px 0 0' }}>
                                <button type="button" className="sub-btn primary" disabled={busy} onClick={useSelected}>
                                    {busy ? 'Saving…' : `Move to ${requestedStage}`}
                                </button>
                            </div>
                        )}

                        <input ref={cameraRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={onFile} />
                        <input ref={libraryRef} type="file" accept="image/*" className="hidden" onChange={onFile} />
                        <div className="sub-actions" style={{ padding: '8px 0 4px' }}>
                            <button type="button" className="sub-btn primary" disabled={busy} onClick={() => cameraRef.current?.click()}>
                                {ICONS.camera} {busy ? 'Uploading…' : `Take ${gateStage} photo`}
                            </button>
                            <button type="button" className="sub-btn" disabled={busy} onClick={() => libraryRef.current?.click()}>
                                {ICONS.upload} Upload
                            </button>
                        </div>
                        {!taggedAlready && selected.size === 0 && (
                            <button type="button" className="row" onClick={() => setMode('reason')} disabled={busy}>
                                No photo available…
                            </button>
                        )}
                    </>
                ) : (
                    <>
                        <textarea
                            value={reason}
                            onChange={(e) => setReason(e.target.value)}
                            placeholder={`Why is there no ${gateStage} photo?`}
                            rows={3}
                            className="w-full mt-2 px-3 py-2 rounded-xl border border-hairline bg-canvas text-ink text-[15px]"
                            aria-label="Reason there is no photo"
                        />
                        <div className="sub-actions" style={{ padding: '10px 0 4px' }}>
                            <button type="button" className="sub-btn" disabled={busy} onClick={() => setMode('photo')}>Back</button>
                            <button type="button" className="sub-btn primary" disabled={busy || !reason.trim()} onClick={submitReason}>
                                {busy ? 'Saving…' : `Move to ${requestedStage}`}
                            </button>
                        </div>
                    </>
                )}
            </section>
            {viewing && (
                <div className="sub-reader" role="dialog" aria-modal="true" aria-label="Photo">
                    <div className="sub-reader-head">
                        <button type="button" className="sub-iconbtn" onClick={() => setViewing(null)}>Back</button>
                        <div className="title">
                            <div className="fname">{viewing.note || viewing.original_filename || 'Photo'}</div>
                        </div>
                    </div>
                    <div className="sub-reader-body flex items-center justify-center p-2">
                        <img
                            src={api.photoFileUrl(releaseId, viewing.id)}
                            alt={viewing.original_filename || 'Photo'}
                            style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }}
                        />
                    </div>
                </div>
            )}
        </>
    );
}
