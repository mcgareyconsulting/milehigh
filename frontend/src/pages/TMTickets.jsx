/**
 * @milehigh-header
 * schema_version: 1
 * purpose: T&M tickets page — list field tickets and open the create/edit form. A foreman
 *          creates a digital ticket natively (no paper); drafts are editable, later states view-only.
 * exports:
 *   TMTickets: Page component. Create/edit/void are enforced admin-only server-side.
 * imports_from: [react, ../services/tmApi, ../components/TMTicketFormModal]
 * imported_by: [App.jsx]
 * invariants:
 *   - Status filtering is server-side (status query param); 'all' omits the param.
 *   - The form modal opens in create mode with a null ticket, or edit/view mode with a fetched one.
 */
import { useState, useEffect, useCallback } from 'react';
import { listTickets, getTicket } from '../services/tmApi';
import TMTicketFormModal from '../components/TMTicketFormModal';

const STATUS_TABS = [
    { value: 'all', label: 'All' },
    { value: 'draft', label: 'Draft' },
    { value: 'submitted', label: 'Submitted' },
    { value: 'approved', label: 'Approved' },
    { value: 'void', label: 'Void' },
];

const STATUS_BADGE = {
    draft: 'bg-gray-100 text-gray-700 dark:bg-slate-700 dark:text-slate-300',
    submitted: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300',
    pending_approval: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
    approved: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
    invoiced: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
    void: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
    rejected: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
};
const STATUS_LABEL = {
    draft: 'Draft', submitted: 'Submitted', pending_approval: 'Pending approval',
    approved: 'Approved', co_generated: 'CO generated', co_sent: 'CO sent',
    co_approved: 'CO approved', invoiced: 'Invoiced', rejected: 'Rejected', void: 'Void',
};

function fmtDate(value) {
    if (!value) return '—';
    const d = new Date(String(value).length <= 10 ? `${value}T00:00:00` : value);
    if (isNaN(d)) return String(value);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function fmtDateTime(value) {
    if (!value) return '—';
    // Backend timestamps are naive UTC (no offset) — append 'Z' so they parse as UTC.
    const s = /([zZ]|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`;
    const d = new Date(s);
    if (isNaN(d)) return String(value);
    return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

export default function TMTickets() {
    const [status, setStatus] = useState('draft');
    const [tickets, setTickets] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [modalOpen, setModalOpen] = useState(false);
    const [modalTicket, setModalTicket] = useState(null);      // null = create mode
    const [modalCandidates, setModalCandidates] = useState([]);

    const load = useCallback(async () => {
        setError(null);
        try {
            const d = await listTickets(status === 'all' ? undefined : status);
            setTickets(d.tickets || []);
        } catch {
            setError('Failed to load tickets');
        } finally {
            setLoading(false);
        }
    }, [status]);

    useEffect(() => { setLoading(true); load(); }, [load]);

    const openNew = () => { setModalTicket(null); setModalCandidates([]); setModalOpen(true); };

    const openTicket = async (id) => {
        setError(null);
        try {
            const d = await getTicket(id);
            setModalTicket(d.ticket);
            setModalCandidates(d.release_candidates || []);
            setModalOpen(true);
        } catch {
            setError('Failed to load ticket');
        }
    };

    const closeModal = () => { setModalOpen(false); setModalTicket(null); setModalCandidates([]); };

    return (
        <div className="flex-1 p-4 md:p-6 max-w-[1200px] mx-auto w-full">
            <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
                <h1 className="text-xl font-bold text-gray-900 dark:text-slate-100">T&amp;M Tickets</h1>
                <button
                    onClick={openNew}
                    className="px-4 py-2.5 sm:py-1.5 text-sm font-medium rounded-lg text-white bg-accent-500 hover:bg-accent-600 transition-colors"
                >
                    + New ticket
                </button>
            </div>

            {error && (
                <div className="mb-3 px-3 py-2 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300 text-sm">{error}</div>
            )}

            <div className="flex items-center gap-1.5 flex-wrap mb-4">
                {STATUS_TABS.map(t => (
                    <button
                        key={t.value} onClick={() => setStatus(t.value)}
                        className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${status === t.value
                            ? 'bg-accent-500 border-accent-500 text-white'
                            : 'bg-white dark:bg-slate-800 border-gray-200 dark:border-slate-700 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700'}`}
                    >
                        {t.label}
                    </button>
                ))}
            </div>

            {loading ? (
                <div className="flex items-center justify-center py-16">
                    <span className="text-gray-500 dark:text-slate-400">Loading…</span>
                </div>
            ) : tickets.length === 0 ? (
                <div className="rounded-xl border border-dashed border-gray-300 dark:border-slate-700 p-12 text-center text-sm text-gray-400 dark:text-slate-500">
                    No tickets here yet. Create one to get started.
                </div>
            ) : (
                <>
                    {/* Below sm: (~375-430px portrait phones), an 8-column table forces
                        horizontal scroll that's awkward on a touchscreen even scoped to its
                        own box — so list as tappable cards instead. Table returns at sm:+. */}
                    <div className="sm:hidden space-y-2">
                        {tickets.map(t => (
                            <button
                                key={t.id} onClick={() => openTicket(t.id)}
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
                                    <span>{t.customer || '—'}</span>
                                    <span>{fmtDate(t.date_of_work)}</span>
                                </div>
                                <div className="mt-1 text-[11px] text-gray-400 dark:text-slate-500">
                                    {t.created_by ? `${t.created_by} · ` : ''}{fmtDateTime(t.created_at)}
                                </div>
                            </button>
                        ))}
                    </div>

                    <div className="hidden sm:block overflow-x-auto rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800">
                        <table className="min-w-full text-sm">
                            <thead className="bg-gray-50 dark:bg-slate-900/40">
                                <tr>
                                    <th className="px-3 py-2 text-left font-semibold text-gray-500 dark:text-slate-400">ID</th>
                                    <th className="px-3 py-2 text-left font-semibold text-gray-500 dark:text-slate-400">Job</th>
                                    <th className="px-3 py-2 text-left font-semibold text-gray-500 dark:text-slate-400">Release</th>
                                    <th className="px-3 py-2 text-left font-semibold text-gray-500 dark:text-slate-400">Date of work</th>
                                    <th className="px-3 py-2 text-left font-semibold text-gray-500 dark:text-slate-400">Customer</th>
                                    <th className="px-3 py-2 text-left font-semibold text-gray-500 dark:text-slate-400">Status</th>
                                    <th className="px-3 py-2 text-left font-semibold text-gray-500 dark:text-slate-400">Created by</th>
                                    <th className="px-3 py-2 text-left font-semibold text-gray-500 dark:text-slate-400">Created</th>
                                </tr>
                            </thead>
                            <tbody>
                                {tickets.map(t => (
                                    <tr
                                        key={t.id} onClick={() => openTicket(t.id)}
                                        className="border-t border-gray-100 dark:border-slate-800 hover:bg-gray-50 dark:hover:bg-slate-700/50 cursor-pointer"
                                    >
                                        <td className="px-3 py-2 text-gray-500 dark:text-slate-400">#{t.id}</td>
                                        <td className="px-3 py-2 text-gray-900 dark:text-slate-100">{t.job ?? '—'}</td>
                                        <td className="px-3 py-2 text-gray-900 dark:text-slate-100">
                                            {t.release ? `${t.release.job}-${t.release.release}` : '—'}
                                        </td>
                                        <td className="px-3 py-2 text-gray-700 dark:text-slate-300">{fmtDate(t.date_of_work)}</td>
                                        <td className="px-3 py-2 text-gray-700 dark:text-slate-300">{t.customer || '—'}</td>
                                        <td className="px-3 py-2">
                                            <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${STATUS_BADGE[t.status] || STATUS_BADGE.draft}`}>
                                                {STATUS_LABEL[t.status] || t.status}
                                            </span>
                                        </td>
                                        <td className="px-3 py-2 text-gray-700 dark:text-slate-300">{t.created_by || '—'}</td>
                                        <td className="px-3 py-2 text-gray-500 dark:text-slate-400">{fmtDateTime(t.created_at)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </>
            )}

            <TMTicketFormModal
                isOpen={modalOpen}
                ticket={modalTicket}
                releaseCandidates={modalCandidates}
                onClose={closeModal}
                onSaved={load}
            />
        </div>
    );
}
