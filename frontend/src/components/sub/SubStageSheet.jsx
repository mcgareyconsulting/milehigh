/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The stage picker for the sub release page (release-mobile-recommendations.md §6): a
 *          bottom sheet listing the stages a subcontractor may set, in workflow order, current one
 *          checked. Tapping a stage saves immediately through the sub stage route (which runs the
 *          full UpdateStageCommand cascade server-side) and closes.
 * exports:
 *   SubStageSheet: ({ current, options, onPick, onClose, busy })
 * imports_from: [react]
 * imported_by: [pages/SubcontractorRelease.jsx]
 * invariants:
 *   - `options` comes from the server (stage_options on the release payload); nothing here can
 *     offer a shop stage. If the current stage is outside the list it is shown, checked and
 *     disabled, so the sheet never lies about where the release is.
 *   - Closes on scrim tap and Escape.
 */
import { useEffect } from 'react';

const CHECK = <svg viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20 6L9 17l-5-5" /></svg>;

export default function SubStageSheet({ current, options = [], onPick, onClose, busy = false }) {
    useEffect(() => {
        const onKey = (e) => { if (e.key === 'Escape') onClose(); };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [onClose]);

    const rows = options.includes(current) || !current ? options : [current, ...options];

    return (
        <>
            <div className="sub-scrim" onClick={onClose} aria-hidden="true" />
            <section className="sub-sheet" role="dialog" aria-modal="true" aria-label="Change stage">
                <div className="grab" />
                <h2>Stage</h2>
                <p className="sub-note">Field stages only. Shop stages are set by MHMW.</p>
                {rows.map((stage) => {
                    const isCurrent = stage === current;
                    const allowed = options.includes(stage);
                    return (
                        <button key={stage} type="button" className="sub-stage-row"
                            disabled={busy || isCurrent || !allowed}
                            onClick={() => onPick(stage)}
                            aria-current={isCurrent ? 'true' : undefined}>
                            <span>{stage}{!allowed ? ' · current, set by MHMW' : ''}</span>
                            {isCurrent && <span className="check">{CHECK}</span>}
                        </button>
                    );
                })}
            </section>
        </>
    );
}
