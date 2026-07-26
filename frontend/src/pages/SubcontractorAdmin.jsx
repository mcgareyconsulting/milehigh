/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Admin roster page for external subcontractor accounts — invite by email, resend a
 *          pending invite, deactivate/reactivate. Assignment to a specific T&M ticket happens
 *          from TMTicketFormModal.jsx, not here (this page manages the standing roster only).
 * exports:
 *   SubcontractorAdmin: Page component, admin-gated server-side on every route it calls.
 * imports_from: [react, ../services/subcontractorAdminApi]
 * imported_by: [App.jsx]
 * invariants:
 *   - Mirrors TMTickets.jsx's mobile-first card list (below sm:) / table (sm:+) pattern for
 *     visual consistency across the T&M feature area.
 */
import { useState, useEffect, useCallback } from 'react';
import {
    listSubcontractors, inviteSubcontractor, resendInvite,
    deactivateSubcontractor, reactivateSubcontractor,
} from '../services/subcontractorAdminApi';

const inputClass = 'w-full px-3 py-2.5 sm:py-2 text-sm rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-gray-900 dark:text-slate-100';
const labelClass = 'block text-xs font-medium text-gray-600 dark:text-slate-300 mb-1';

function statusOf(sub) {
    if (!sub.is_active) return 'inactive';
    if (!sub.invite_accepted) return 'pending';
    return 'active';
}

const STATUS_BADGE = {
    pending: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
    active: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
    inactive: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
};
const STATUS_LABEL = { pending: 'Pending', active: 'Active', inactive: 'Inactive' };

function fmtDateTime(value) {
    if (!value) return '—';
    const s = /([zZ]|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`;
    const d = new Date(s);
    if (isNaN(d)) return String(value);
    return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

export default function SubcontractorAdmin() {
    const [subs, setSubs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [formOpen, setFormOpen] = useState(false);
    const [companyName, setCompanyName] = useState('');
    const [contactName, setContactName] = useState('');
    const [email, setEmail] = useState('');
    const [saving, setSaving] = useState(false);
    const [busyId, setBusyId] = useState(null);

    const load = useCallback(async () => {
        setError(null);
        try {
            const d = await listSubcontractors();
            setSubs(d.subcontractors || []);
        } catch {
            setError('Failed to load subcontractors');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { setLoading(true); load(); }, [load]);

    const handleInvite = async (e) => {
        e.preventDefault();
        setSaving(true); setError(null);
        try {
            await inviteSubcontractor({ company_name: companyName, contact_name: contactName, email });
            setCompanyName(''); setContactName(''); setEmail('');
            setFormOpen(false);
            await load();
        } catch (err) {
            setError(err?.response?.data?.error || 'Failed to invite subcontractor');
        } finally {
            setSaving(false);
        }
    };

    const withBusy = async (id, fn) => {
        setBusyId(id); setError(null);
        try {
            await fn();
            await load();
        } catch (err) {
            setError(err?.response?.data?.error || 'Action failed');
        } finally {
            setBusyId(null);
        }
    };

    const renderActions = (sub) => (
        <div className="flex flex-wrap gap-2">
            {statusOf(sub) === 'pending' && (
                <button onClick={() => withBusy(sub.id, () => resendInvite(sub.id))} disabled={busyId === sub.id}
                    className="text-xs px-3 py-1.5 rounded-md border border-gray-300 dark:border-slate-600 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700 disabled:opacity-50">
                    Resend invite
                </button>
            )}
            {sub.is_active ? (
                <button onClick={() => withBusy(sub.id, () => deactivateSubcontractor(sub.id))} disabled={busyId === sub.id}
                    className="text-xs px-3 py-1.5 rounded-md border border-red-200 dark:border-red-900/50 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50">
                    Deactivate
                </button>
            ) : (
                <button onClick={() => withBusy(sub.id, () => reactivateSubcontractor(sub.id))} disabled={busyId === sub.id}
                    className="text-xs px-3 py-1.5 rounded-md border border-green-200 dark:border-green-900/50 text-green-600 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-900/20 disabled:opacity-50">
                    Reactivate
                </button>
            )}
        </div>
    );

    return (
        <div className="flex-1 p-4 md:p-6 max-w-[1200px] mx-auto w-full">
            <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
                <h1 className="text-xl font-bold text-gray-900 dark:text-slate-100">Subcontractors</h1>
                <button
                    onClick={() => setFormOpen(v => !v)}
                    className="px-4 py-2.5 sm:py-1.5 text-sm font-medium rounded-lg text-white bg-accent-500 hover:bg-accent-600 transition-colors"
                >
                    {formOpen ? 'Cancel' : '+ Invite subcontractor'}
                </button>
            </div>

            {error && (
                <div className="mb-3 px-3 py-2 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300 text-sm">{error}</div>
            )}

            {formOpen && (
                <form onSubmit={handleInvite} className="mb-4 p-4 rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 space-y-3">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div className="min-w-0">
                            <label className={labelClass}>Company name</label>
                            <input required value={companyName} onChange={e => setCompanyName(e.target.value)} className={inputClass} />
                        </div>
                        <div className="min-w-0">
                            <label className={labelClass}>Contact name</label>
                            <input required value={contactName} onChange={e => setContactName(e.target.value)} className={inputClass} />
                        </div>
                    </div>
                    <div>
                        <label className={labelClass}>Email</label>
                        <input required type="email" value={email} onChange={e => setEmail(e.target.value)} className={inputClass} />
                        <p className="mt-1 text-[11px] text-gray-400 dark:text-slate-500">
                            They'll get an email with a link to set a password and log in.
                        </p>
                    </div>
                    <button type="submit" disabled={saving}
                        className="px-4 py-2.5 sm:py-2 text-sm font-medium rounded-lg bg-green-600 hover:bg-green-700 text-white disabled:opacity-50">
                        {saving ? 'Sending invite…' : 'Send invite'}
                    </button>
                </form>
            )}

            {loading ? (
                <div className="flex items-center justify-center py-16">
                    <span className="text-gray-500 dark:text-slate-400">Loading…</span>
                </div>
            ) : subs.length === 0 ? (
                <div className="rounded-xl border border-dashed border-gray-300 dark:border-slate-700 p-12 text-center text-sm text-gray-400 dark:text-slate-500">
                    No subcontractors yet. Invite one to get started.
                </div>
            ) : (
                <>
                    <div className="sm:hidden space-y-2">
                        {subs.map(sub => (
                            <div key={sub.id} className="rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-3">
                                <div className="flex items-center justify-between gap-2 mb-1.5">
                                    <span className="text-sm font-semibold text-gray-900 dark:text-slate-100">{sub.company_name}</span>
                                    <span className={`shrink-0 px-2 py-0.5 text-xs font-medium rounded-full ${STATUS_BADGE[statusOf(sub)]}`}>
                                        {STATUS_LABEL[statusOf(sub)]}
                                    </span>
                                </div>
                                <div className="text-xs text-gray-700 dark:text-slate-300">{sub.contact_name}</div>
                                <div className="text-xs text-gray-500 dark:text-slate-400 mb-2">{sub.email}</div>
                                {renderActions(sub)}
                            </div>
                        ))}
                    </div>

                    <div className="hidden sm:block overflow-x-auto rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800">
                        <table className="min-w-full text-sm">
                            <thead className="bg-gray-50 dark:bg-slate-900/40">
                                <tr>
                                    <th className="px-3 py-2 text-left font-semibold text-gray-500 dark:text-slate-400">Company</th>
                                    <th className="px-3 py-2 text-left font-semibold text-gray-500 dark:text-slate-400">Contact</th>
                                    <th className="px-3 py-2 text-left font-semibold text-gray-500 dark:text-slate-400">Email</th>
                                    <th className="px-3 py-2 text-left font-semibold text-gray-500 dark:text-slate-400">Status</th>
                                    <th className="px-3 py-2 text-left font-semibold text-gray-500 dark:text-slate-400">Invited</th>
                                    <th className="px-3 py-2 text-left font-semibold text-gray-500 dark:text-slate-400">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {subs.map(sub => (
                                    <tr key={sub.id} className="border-t border-gray-100 dark:border-slate-800">
                                        <td className="px-3 py-2 text-gray-900 dark:text-slate-100">{sub.company_name}</td>
                                        <td className="px-3 py-2 text-gray-700 dark:text-slate-300">{sub.contact_name}</td>
                                        <td className="px-3 py-2 text-gray-700 dark:text-slate-300">{sub.email}</td>
                                        <td className="px-3 py-2">
                                            <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${STATUS_BADGE[statusOf(sub)]}`}>
                                                {STATUS_LABEL[statusOf(sub)]}
                                            </span>
                                        </td>
                                        <td className="px-3 py-2 text-gray-500 dark:text-slate-400">{fmtDateTime(sub.invited_at)}</td>
                                        <td className="px-3 py-2">{renderActions(sub)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </>
            )}
        </div>
    );
}
