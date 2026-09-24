/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The phone's department photo gate (T13). When a stage change answers 422
 *          photo_required, this bottom sheet says which handoff photo is owed and offers the two
 *          exits the desktop StagePhotoGateModal has: take / upload a photo (tagged with the gate
 *          stage, then the stage change is retried) or "No photo available" with a written reason
 *          (sent as gate_exception_note). Phone-shaped and adapter-driven, so it serves both the
 *          sub portal and the employee shell.
 * exports:
 *   SubStageGateSheet: ({ gateStage, requestedStage, releaseId, api, onSatisfied, onClose })
 *     onSatisfied({ gateExceptionNote? }) is called after a tagged photo lands (no note) or when
 *     the user submits a reason (note set); the caller retries the stage change.
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
    const cameraRef = useRef(null);
    const libraryRef = useRef(null);

    useEffect(() => {
        const onKey = (e) => { if (e.key === 'Escape') onClose(); };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [onClose]);

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

    return (
        <>
            <div className="sub-scrim" onClick={onClose} aria-hidden="true" />
            <section className="sub-sheet" role="dialog" aria-modal="true" aria-label="Photo required">
                <div className="grab" />
                <h2>Photo required</h2>
                <p className="sub-note">
                    Moving to <b>{requestedStage}</b> needs a handoff photo tagged <b>{gateStage}</b>.
                    Take one now, or say why there is none.
                </p>
                {error && <p className="text-sm text-red-600 mb-2">{error}</p>}

                {mode === 'photo' ? (
                    <>
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
                        <button type="button" className="row" onClick={() => setMode('reason')} disabled={busy}>
                            No photo available…
                        </button>
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
        </>
    );
}
