/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The read-only release detail a subcontractor sees when they tap a card — a phone
 *          BOTTOM SHEET showing the allowlisted fields the server returns for their crew's
 *          release (scope, stage, install window, hours, crew size, ship date, PM) plus the
 *          sub's own to-dos on that release. This is deliberately NOT the staff ReleaseHubModal:
 *          every endpoint behind that modal is @login_required, and the sub's payload is an
 *          allowlist (app/brain/sub_portal/service.py) — fab hours never reach this component.
 * exports:
 *   SubReleaseSheet: ({ releaseId, onClose, todos }) — fetches the release itself; null id = closed.
 * imports_from: [react, ../../services/subPortalApi, ../installSchedule/DatePill]
 * imported_by: [pages/SubcontractorJobLog.jsx, pages/SubcontractorTodos.jsx]
 * invariants:
 *   - Read-only. No write control renders here; when subs get notes / photos those land as
 *     their own sub-scoped endpoints, not by reusing staff ones.
 *   - Dismiss by the handle/close button, the backdrop, or Escape. The sheet is portal-free
 *     (fixed positioning) so it works inside the sub shell without a modal root.
 */
import { useEffect, useState } from 'react';
import { getSubRelease } from '../../services/subPortalApi';
import { DatePill } from '../installSchedule/DatePill';

const fmtDate = (iso) => {
    if (!iso) return '—';
    const d = new Date(String(iso).length <= 10 ? `${iso}T00:00:00` : iso);
    return isNaN(d) ? String(iso) : d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
};

function dateKind(rel) {
    if (!rel?.['Start install']) return null;
    if (rel.start_install_no_color) return 'neutral';
    if (rel.start_install_formulaTF) return 'projected';
    return rel.start_install_asap ? 'asap' : 'hard';
}

function Row({ label, children }) {
    return (
        <div className="flex items-baseline justify-between gap-3 py-2 border-b border-hairline last:border-b-0">
            <span className="text-xs text-ink-3 shrink-0">{label}</span>
            <span className="text-sm text-ink text-right break-words min-w-0">{children ?? '—'}</span>
        </div>
    );
}

export default function SubReleaseSheet({ releaseId, onClose, todos = [] }) {
    const open = releaseId != null;
    const [rel, setRel] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (!open) return undefined;
        let cancelled = false;
        setRel(null); setError(null);
        getSubRelease(releaseId)
            .then((r) => { if (!cancelled) setRel(r); })
            .catch((e) => { if (!cancelled) setError(e?.response?.status === 404 ? 'This release is not on your crew.' : 'Could not load the release.'); });
        return () => { cancelled = true; };
    }, [open, releaseId]);

    useEffect(() => {
        if (!open) return undefined;
        const onKey = (e) => { if (e.key === 'Escape') onClose(); };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [open, onClose]);

    if (!open) return null;

    const code = rel ? `${rel['Job #']}-${rel['Release #']}` : '';
    const mine = todos.filter((t) => t.release_id === releaseId);

    return (
        <div className="fixed inset-0 z-50 flex flex-col justify-end" role="dialog" aria-modal="true" aria-label="Release details">
            <div className="absolute inset-0 bg-black/40" onClick={onClose} aria-hidden="true" />
            <div
                className="relative bg-surface rounded-t-2xl shadow-2xl max-h-[88vh] flex flex-col"
                style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
            >
                <div className="flex items-center justify-between px-4 pt-2 pb-1">
                    <span className="w-10 h-1.5 rounded-full bg-hairline-strong mx-auto absolute left-1/2 -translate-x-1/2 top-2" aria-hidden="true" />
                    <span />
                    <button type="button" onClick={onClose} aria-label="Close"
                        className="w-9 h-9 -mr-2 flex items-center justify-center rounded-full text-ink-2 active:bg-surface-2 text-xl leading-none">
                        ×
                    </button>
                </div>

                <div className="overflow-y-auto px-4 pb-4">
                    {error && <p className="py-6 text-center text-sm text-red-600 dark:text-red-400">{error}</p>}
                    {!error && !rel && <p className="py-6 text-center text-sm text-ink-3">Loading…</p>}
                    {rel && (
                        <>
                            <div className="flex items-start justify-between gap-2">
                                <div className="min-w-0">
                                    <div className="font-mono text-lg font-bold text-accent-600 dark:text-accent-400">{code}</div>
                                    <div className="text-sm font-semibold text-ink break-words">{rel.Job}</div>
                                </div>
                                {dateKind(rel) && <DatePill kind={dateKind(rel)} />}
                            </div>
                            {rel.Description && (
                                <p className="mt-2 text-sm text-ink-2 break-words">{rel.Description}</p>
                            )}

                            <div className="mt-3">
                                <Row label="Stage">{rel.Stage}</Row>
                                <Row label="Start install">{fmtDate(rel['Start install'])}</Row>
                                <Row label="Install complete">{fmtDate(rel.comp_eta_effective || rel['Comp. ETA'])}</Row>
                                <Row label="Install hours">{rel['Install HRS'] != null ? `${rel['Install HRS']} h` : '—'}</Row>
                                <Row label="Crew size">{rel.num_guys != null ? `${rel.num_guys}` : '—'}</Row>
                                <Row label="Ship date">{fmtDate(rel['Ship Date'])}</Row>
                                <Row label="Crew">{rel.installer}</Row>
                                <Row label="PM">{rel.PM}</Row>
                                {rel.release_tag && <Row label="Tag">{rel.release_tag}</Row>}
                            </div>

                            {mine.length > 0 && (
                                <div className="mt-4">
                                    <h3 className="text-xs font-bold uppercase tracking-wide text-ink-3 mb-1">Your to-dos here</h3>
                                    <ul className="flex flex-col gap-1">
                                        {mine.map((t) => (
                                            <li key={t.id} className={`text-sm rounded-lg border border-hairline px-3 py-2 ${t.status === 'done' ? 'text-ink-3 line-through' : 'text-ink'}`}>
                                                {t.title}{t.due_date ? <span className="text-ink-3"> · due {fmtDate(t.due_date)}</span> : null}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}
