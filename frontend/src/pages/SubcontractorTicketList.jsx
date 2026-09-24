/**
 * @milehigh-header
 * schema_version: 1
 * purpose: A subcontractor's list of T&M tickets shared with them — the T&M tab of the sub
 *          portal. Option A styling (subs-mobile-option-a.md §6): a title row with the crew and
 *          draft count, then one .sub-card per ticket. No status-tab filtering (a subcontractor
 *          typically has few tickets, unlike the admin roster). No FAB: subs cannot create tickets
 *          today (the sub T&M routes are list / view / edit-draft / submit), so a "+" would lead
 *          nowhere.
 * exports:
 *   SubcontractorTicketList: Page component, rendered inside SubcontractorShell's Outlet.
 * imports_from: [react, react-router-dom, ../services/subcontractorTmApi]
 * imported_by: [App.jsx]
 */
import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import { listAssignedTickets } from '../services/subcontractorTmApi';
import SubEmpty from '../components/sub/SubEmpty';

const STATUS_BADGE = {
    draft: '',
    submitted: '!bg-indigo-100 text-indigo-800',
    pending_approval: '!bg-amber-100 text-amber-800',
    approved: '!bg-blue-100 text-blue-800',
    invoiced: '!bg-green-100 text-green-800',
};
const STATUS_LABEL = {
    draft: 'Draft', submitted: 'Submitted', pending_approval: 'Pending approval',
    approved: 'Approved', co_generated: 'CO generated', co_sent: 'CO sent',
    co_approved: 'CO approved', invoiced: 'Invoiced',
};

function fmtDate(value) {
    if (!value) return '—';
    const d = new Date(String(value).length <= 10 ? `${value}T00:00:00` : value);
    if (isNaN(d)) return String(value);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

export default function SubcontractorTicketList() {
    const [tickets, setTickets] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const navigate = useNavigate();
    const { subcontractor } = useOutletContext();
    const crew = subcontractor?.installer_team;

    const load = useCallback(async () => {
        setError(null);
        try {
            const d = await listAssignedTickets();
            setTickets(d.tickets || []);
        } catch {
            setError('Failed to load tickets');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { load(); }, [load]);

    const drafts = tickets.filter(t => t.status === 'draft').length;
    const ctx = [crew, drafts > 0 ? `${drafts} ${drafts === 1 ? 'draft' : 'drafts'}` : null].filter(Boolean).join(' · ');

    return (
        <div className="flex-1 min-h-0 flex flex-col">
            <div className="sub-page-head">
                <h1>T&amp;M</h1>
                {ctx && <div className="sub-ctx">{ctx}</div>}
            </div>

            {error && (
                <div className="mx-4 mb-3 px-3 py-2 rounded-lg bg-red-50 text-red-700 text-sm">{error}</div>
            )}

            {loading ? (
                <div className="text-ink-3 text-sm px-4 py-2">Loading…</div>
            ) : tickets.length === 0 ? (
                <SubEmpty icon="file" title="No tickets yet" body="When MHMW shares a T&M ticket with you, it shows up here." />
            ) : (
                <div className="flex flex-col gap-2.5 px-4 pb-4">
                    {tickets.map(t => (
                        <button
                            key={t.id} onClick={() => navigate(`/sub/tickets/${t.id}`)}
                            className="sub-card w-full text-left p-4 flex flex-col gap-2 active:scale-[0.995]"
                        >
                            <div className="flex items-center justify-between gap-2">
                                <span className="num">
                                    {t.release ? `${t.release.job}-${t.release.release}` : (t.job ?? `Ticket #${t.id}`)}
                                </span>
                                <span className={`sub-pill ${STATUS_BADGE[t.status] || STATUS_BADGE.draft}`}>
                                    {STATUS_LABEL[t.status] || t.status}
                                </span>
                            </div>
                            <div className="flex items-center justify-between gap-2 text-sm text-ink-3">
                                <span className="truncate">{t.location || t.customer || '—'}</span>
                                <span className="shrink-0">{fmtDate(t.date_of_work)}</span>
                            </div>
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}
