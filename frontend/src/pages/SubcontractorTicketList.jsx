/**
 * @milehigh-header
 * schema_version: 1
 * purpose: A subcontractor's list of T&M tickets shared with them — the /sub/tickets landing
 *          page. Mirrors TMTickets.jsx's card-list styling but without status-tab filtering
 *          (a subcontractor typically has few tickets, unlike the admin roster).
 * exports:
 *   SubcontractorTicketList: Page component, rendered inside SubcontractorShell's Outlet.
 * imports_from: [react, react-router-dom, ../services/subcontractorTmApi]
 * imported_by: [App.jsx]
 */
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { listAssignedTickets } from '../services/subcontractorTmApi';

const STATUS_BADGE = {
    draft: 'bg-gray-100 text-gray-700 dark:bg-slate-700 dark:text-slate-300',
    submitted: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300',
    pending_approval: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
    approved: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
    invoiced: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
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

    return (
        <div className="flex-1 p-4 md:p-6 max-w-[800px] mx-auto w-full">
            <h1 className="text-xl font-bold text-gray-900 dark:text-slate-100 mb-4">Your T&amp;M Tickets</h1>

            {error && (
                <div className="mb-3 px-3 py-2 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300 text-sm">{error}</div>
            )}

            {loading ? (
                <div className="flex items-center justify-center py-16">
                    <span className="text-gray-500 dark:text-slate-400">Loading…</span>
                </div>
            ) : tickets.length === 0 ? (
                <div className="rounded-xl border border-dashed border-gray-300 dark:border-slate-700 p-12 text-center text-sm text-gray-400 dark:text-slate-500">
                    No tickets have been shared with you yet.
                </div>
            ) : (
                <div className="space-y-2">
                    {tickets.map(t => (
                        <button
                            key={t.id} onClick={() => navigate(`/sub/tickets/${t.id}`)}
                            className="w-full text-left rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-3 active:bg-gray-50 dark:active:bg-slate-700/50"
                        >
                            <div className="flex items-center justify-between gap-2 mb-1.5">
                                <span className="text-sm font-semibold text-gray-900 dark:text-slate-100">
                                    {t.release ? `${t.release.job}-${t.release.release}` : (t.job ?? `Ticket #${t.id}`)}
                                </span>
                                <span className={`shrink-0 px-2 py-0.5 text-xs font-medium rounded-full ${STATUS_BADGE[t.status] || STATUS_BADGE.draft}`}>
                                    {STATUS_LABEL[t.status] || t.status}
                                </span>
                            </div>
                            <div className="flex items-center justify-between gap-2 text-xs text-gray-500 dark:text-slate-400">
                                <span>{t.location || t.customer || '—'}</span>
                                <span>{fmtDate(t.date_of_work)}</span>
                            </div>
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}
