/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The Details tab of the sub release page — the desktop's three columns collapsed to one
 *          scroll in field order (release-mobile-recommendations.md §3): Schedule and Details as
 *          44px key/value rows, then the sub's to-dos on this release. The spec's action pair is
 *          NOT here by decision: Add note lives on the Activity tab and photos on Attachments.
 *          Every value is read-only here: the sub payload is an allowlist and stage / installer /
 *          crew edits remain staff actions.
 * exports:
 *   SubReleaseDetails: ({ rel, todos })
 * imports_from: [react, ../installSchedule/DatePill]
 * imported_by: [pages/SubcontractorRelease.jsx]
 * invariants:
 *   - Empty sections show one muted line, never a bare section header.
 *   - No fab hours / fab order / paint / invoicing: absent from the payload, so absent here.
 */
import { DatePill } from '../installSchedule/DatePill';
import { fmtDay as fmtDate } from '../mobile/format';

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

export default function SubReleaseDetails({ rel, todos = [] }) {
    const kind = dateKind(rel);
    const start = fmtDate(rel['Start install']);
    return (
        <div className="flex-1 min-h-0 overflow-y-auto pb-6">

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
