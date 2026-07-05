/**
 * @milehigh-header
 * schema_version: 1
 * purpose: T&M ticket ingestion page — upload a photographed/scanned ticket, watch it get
 *          read by the extractor, then review/confirm or reject it against the original document.
 * exports:
 *   TMTickets: Page component. Upload/confirm/reject are enforced admin-only server-side.
 * imports_from: [react, ../services/tmApi, ../components/TMReviewModal]
 * imported_by: [App.jsx]
 * invariants:
 *   - The upload POST takes ~10-30s (LLM extraction); a spinner state covers that window.
 *   - Status filtering is server-side (status query param); 'all' omits the param.
 *   - On upload success the review modal opens immediately with the response payload.
 */
import { useState, useEffect, useCallback } from 'react';
import { listTickets, getTicket, uploadTicket } from '../services/tmApi';
import TMReviewModal from '../components/TMReviewModal';

const STATUS_TABS = [
    { value: 'all', label: 'All' },
    { value: 'pending_review', label: 'Pending review' },
    { value: 'confirmed', label: 'Confirmed' },
    { value: 'rejected', label: 'Rejected' },
];

const STATUS_BADGE = {
    pending_review: 'bg-gray-100 text-gray-700 dark:bg-slate-700 dark:text-slate-300',
    confirmed: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
    rejected: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
};
const STATUS_LABEL = {
    pending_review: 'Pending review',
    confirmed: 'Confirmed',
    rejected: 'Rejected',
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
    const [status, setStatus] = useState('pending_review');
    const [tickets, setTickets] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [uploading, setUploading] = useState(false);
    const [uploadError, setUploadError] = useState(null);
    const [modalTicket, setModalTicket] = useState(null);
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

    const handleFileChange = async (e) => {
        const file = e.target.files?.[0];
        e.target.value = ''; // allow re-selecting the same file
        if (!file) return;
        setUploadError(null);
        setUploading(true);
        try {
            const data = await uploadTicket(file);
            setModalTicket(data.ticket);
            setModalCandidates(data.release_candidates || []);
            await load();
        } catch (err) {
            setUploadError(err?.response?.data?.error || 'Failed to upload ticket');
        } finally {
            setUploading(false);
        }
    };

    const openTicket = async (id) => {
        setError(null);
        try {
            const d = await getTicket(id);
            setModalTicket(d.ticket);
            setModalCandidates(d.release_candidates || []);
        } catch {
            setError('Failed to load ticket');
        }
    };

    const closeModal = () => { setModalTicket(null); setModalCandidates([]); };

    return (
        <div className="flex-1 p-4 md:p-6 max-w-[1200px] mx-auto w-full">
            <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
                <h1 className="text-xl font-bold text-gray-900 dark:text-slate-100">T&amp;M Tickets</h1>
                <div className="flex items-center gap-3">
                    {uploading && (
                        <span className="inline-flex items-center gap-2 text-sm text-gray-500 dark:text-slate-400">
                            <span className="inline-block w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                            Reading ticket…
                        </span>
                    )}
                    <label
                        htmlFor="tm-ticket-upload"
                        className={`px-3 py-1.5 text-sm font-medium rounded-lg text-white transition-colors ${uploading
                            ? 'bg-accent-400 opacity-60 cursor-not-allowed pointer-events-none'
                            : 'bg-accent-500 hover:bg-accent-600 cursor-pointer'
                            }`}
                    >
                        + Upload ticket
                    </label>
                    <input
                        id="tm-ticket-upload"
                        type="file"
                        accept="application/pdf,image/*"
                        className="hidden"
                        disabled={uploading}
                        onChange={handleFileChange}
                    />
                </div>
            </div>

            {uploadError && (
                <div className="mb-3 px-3 py-2 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300 text-sm">{uploadError}</div>
            )}
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
                    No tickets here yet. Upload one to get started.
                </div>
            ) : (
                <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800">
                    <table className="min-w-full text-sm">
                        <thead className="bg-gray-50 dark:bg-slate-900/40">
                            <tr>
                                <th className="px-3 py-2 text-left font-semibold text-gray-500 dark:text-slate-400">ID</th>
                                <th className="px-3 py-2 text-left font-semibold text-gray-500 dark:text-slate-400">Job</th>
                                <th className="px-3 py-2 text-left font-semibold text-gray-500 dark:text-slate-400">Release</th>
                                <th className="px-3 py-2 text-left font-semibold text-gray-500 dark:text-slate-400">Date of work</th>
                                <th className="px-3 py-2 text-left font-semibold text-gray-500 dark:text-slate-400">Customer</th>
                                <th className="px-3 py-2 text-left font-semibold text-gray-500 dark:text-slate-400">Status</th>
                                <th className="px-3 py-2 text-left font-semibold text-gray-500 dark:text-slate-400">Uploaded by</th>
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
                                        <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${STATUS_BADGE[t.status] || STATUS_BADGE.pending_review}`}>
                                            {STATUS_LABEL[t.status] || t.status}
                                        </span>
                                    </td>
                                    <td className="px-3 py-2 text-gray-700 dark:text-slate-300">{t.uploaded_by || '—'}</td>
                                    <td className="px-3 py-2 text-gray-500 dark:text-slate-400">{fmtDateTime(t.created_at)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            <TMReviewModal
                isOpen={!!modalTicket}
                ticket={modalTicket}
                releaseCandidates={modalCandidates}
                onClose={closeModal}
                onSaved={load}
            />
        </div>
    );
}
