/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The Details tab of the sub release page — the desktop's three columns collapsed to one
 *          scroll in field order (release-mobile-recommendations.md §3): action pair, then
 *          Schedule and Details as 44px key/value rows, then the sub's to-dos on this release.
 *          Every value is read-only here: the sub payload is an allowlist and stage / installer /
 *          crew edits remain staff actions.
 * exports:
 *   SubReleaseDetails: ({ rel, todos, onAddNote, onSeeAttachments })
 * imports_from: [react, ../installSchedule/DatePill]
 * imported_by: [pages/SubcontractorRelease.jsx]
 * invariants:
 *   - Empty sections show one muted line, never a bare section header.
 *   - No fab hours / fab order / paint / invoicing: absent from the payload, so absent here.
 */
import { DatePill } from '../installSchedule/DatePill';

const fmtDate = (iso) => {
    if (!iso) return null;
    const d = new Date(String(iso).length <= 10 ? `${iso}T00:00:00` : iso);
    return isNaN(d) ? String(iso) : d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
};

function dateKind(rel) {
    if (!rel?.['Start install']) return null;
    if (rel.start_install_no_color) return 'neutral';
    if (rel.start_install_formulaTF) return 'projected';
    return rel.start_install_asap ? 'asap' : 'hard';
}

function Row({ k, v, muted }) {
    return (
        <div className="sub-kv">
            <span className="k">{k}</span>
            <span className={`v${v == null || v === '' ? ' muted' : ''}${muted ? ' muted' : ''}`}>{v == null || v === '' ? '—' : v}</span>
        </div>
    );
}

const ICONS = {
    note: <svg viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></svg>,
    clip: <svg viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21.4 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.2-9.19a4 4 0 1 1 5.65 5.66l-9.2 9.19a2 2 0 0 1-2.82-2.83l8.49-8.48" /></svg>,
};

export default function SubReleaseDetails({ rel, todos = [], onAddNote, onSeeAttachments }) {
    const kind = dateKind(rel);
    const start = fmtDate(rel['Start install']);
    return (
        <div className="flex-1 min-h-0 overflow-y-auto pb-6">
            <div className="sub-actions">
                <button type="button" className="sub-btn primary" onClick={onAddNote}>{ICONS.note} Add note</button>
                <button type="button" className="sub-btn" onClick={onSeeAttachments}>{ICONS.clip} Attachments</button>
            </div>

            <section className="sub-section">
                <h3 className="sub-section-label">Schedule</h3>
                <div className="sub-kv">
                    <span className="k">Start install</span>
                    <span className="v flex items-center gap-2 justify-end">
                        {start || '—'}
                        {kind && <DatePill kind={kind} />}
                    </span>
                </div>
                <Row k="Install complete" v={fmtDate(rel.comp_eta_effective || rel['Comp. ETA'])} />
                <Row k="Ship date" v={fmtDate(rel['Ship Date'])} />
                <Row k="Install hours" v={rel['Install HRS'] != null ? `${rel['Install HRS']} h` : null} />
                <Row k="Crew size" v={rel.num_guys != null ? String(rel.num_guys) : null} />
            </section>

            <section className="sub-section">
                <h3 className="sub-section-label">Details</h3>
                <Row k="Stage" v={rel.Stage} />
                <Row k="Crew" v={rel.installer} />
                <Row k="PM" v={rel.PM} />
                <Row k="Detailed by" v={rel.BY} />
                {rel.release_tag && <Row k="Tag" v={rel.release_tag} />}
                <Row k="Complete" v={rel['Job Comp'] === 'X' ? 'Yes' : 'No'} muted={rel['Job Comp'] !== 'X'} />
            </section>

            <section className="sub-section">
                <h3 className="sub-section-label">Your to-dos here</h3>
                {todos.length === 0 ? (
                    <p className="sub-quiet">No to-dos on this release.</p>
                ) : (
                    <ul className="flex flex-col">
                        {todos.map((t) => (
                            <li key={t.id} className={`sub-kv ${t.status === 'done' ? 'opacity-60' : ''}`}>
                                <span className={`k ${t.status === 'done' ? 'line-through' : ''}`}>{t.title}</span>
                                {t.due_date && <span className="v muted">due {fmtDate(t.due_date)}</span>}
                            </li>
                        ))}
                    </ul>
                )}
            </section>
        </div>
    );
}
