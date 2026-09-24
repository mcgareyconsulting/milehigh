/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The subcontractor portal's empty state — icon well, headline, one line of explanation —
 *          per the Option A spec (§7). Shared by the To-Dos, Mentions, Job Log and T&M pages so an
 *          empty screen looks the same everywhere.
 * exports:
 *   SubEmpty: ({ icon: 'check'|'bell'|'calendar'|'file', title, body })
 * imports_from: [react]
 * imported_by: [pages/SubcontractorTodos.jsx, pages/SubcontractorJobLog.jsx, pages/SubcontractorTicketList.jsx]
 */
const ICONS = {
    check: <svg viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="3" /><path d="M8 12l3 3 5-6" /></svg>,
    bell: <svg viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.7 21a2 2 0 0 1-3.4 0" /></svg>,
    calendar: <svg viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="17" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" /></svg>,
    file: <svg viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6M8 13h8M8 17h5" /></svg>,
};

export default function SubEmpty({ icon = 'check', title, body }) {
    return (
        <div className="sub-empty">
            <div className="well">{ICONS[icon] || ICONS.check}</div>
            <h2>{title}</h2>
            {body && <p>{body}</p>}
        </div>
    );
}
