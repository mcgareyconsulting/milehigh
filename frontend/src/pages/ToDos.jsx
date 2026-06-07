/**
 * @milehigh-header
 * schema_version: 1
 * purpose: To-Do page. Admins see every assigned to-do (filter by status + owner); non-admins
 *          see only what's assigned to them. Owner/admin can check items done. Assignments arrive
 *          via the notification bell (created when a meeting checklist item is accepted).
 * exports:
 *   ToDos: Page component (any authenticated user).
 * imports_from: [react, ../utils/auth, ../services/todosApi, ../services/meetingsApi]
 * imported_by: [App.jsx]
 * invariants:
 *   - Server enforces scoping; non-admins can only ever see/modify their own items.
 */
import { useState, useEffect, useCallback } from 'react';
import { checkAuth } from '../utils/auth';
import { fetchTodos, setTodoStatus } from '../services/todosApi';
import { fetchAssignableUsers } from '../services/meetingsApi';

const STATUS_TABS = [
    { value: 'open', label: 'Open' },
    { value: 'done', label: 'Done' },
    { value: 'all', label: 'All' },
];

const COMPANY_TZ = 'America/Denver';
const todayDenver = () => new Intl.DateTimeFormat('en-CA', { timeZone: COMPANY_TZ }).format(new Date());
const fmtDue = (iso) => {
    if (!iso) return '';
    const d = new Date(`${iso}T00:00:00`);
    return isNaN(d) ? iso : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

export default function ToDos() {
    const [loading, setLoading] = useState(true);
    const [authed, setAuthed] = useState(false);
    const [isAdmin, setIsAdmin] = useState(false);
    const [todos, setTodos] = useState([]);
    const [status, setStatus] = useState('open');
    const [owner, setOwner] = useState('');
    const [users, setUsers] = useState([]);
    const [busy, setBusy] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        checkAuth().then(u => { setAuthed(!!u); setIsAdmin(u?.is_admin || false); setLoading(false); });
    }, []);

    const load = useCallback(async () => {
        setError(null);
        try {
            const d = await fetchTodos({ status, owner: owner || undefined });
            setTodos(d.todos);
            setIsAdmin(d.is_admin);
        } catch { setError('Failed to load to-dos'); }
    }, [status, owner]);

    useEffect(() => { if (authed) load(); }, [authed, load]);
    useEffect(() => { if (isAdmin) fetchAssignableUsers().then(setUsers).catch(() => {}); }, [isAdmin]);

    const toggleDone = async (it) => {
        const next = it.status === 'done' ? 'accepted' : 'done';
        setBusy(it.id); setError(null);
        try {
            const updated = await setTodoStatus(it.id, next);
            setTodos(prev => {
                const mapped = prev.map(t => (t.id === it.id ? { ...t, status: updated.status } : t));
                if (status === 'open') return mapped.filter(t => t.status === 'accepted');
                if (status === 'done') return mapped.filter(t => t.status === 'done');
                return mapped;
            });
        } catch { setError('Failed to update to-do'); }
        finally { setBusy(null); }
    };

    if (loading) return <div className="flex-1 flex items-center justify-center"><span className="text-gray-500 dark:text-slate-400">Loading…</span></div>;
    if (!authed) return <div className="flex-1 flex items-center justify-center"><span className="text-gray-500 dark:text-slate-400">Please log in to see your to-dos.</span></div>;

    const today = todayDenver();
    const isOverdue = (it) => it.due_date && it.status !== 'done' && it.due_date < today;

    return (
        <div className="flex-1 p-4 md:p-6 max-w-[1100px] mx-auto w-full">
            <div className="flex items-center justify-between gap-3 mb-4">
                <h1 className="text-xl font-bold text-gray-900 dark:text-slate-100">
                    To-Dos
                    {!isAdmin && <span className="ml-2 text-sm font-normal text-gray-400 dark:text-slate-500">assigned to you</span>}
                </h1>
            </div>
            {error && <div className="mb-3 px-3 py-2 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300 text-sm">{error}</div>}

            {/* Filters */}
            <div className="flex items-center gap-2 mb-4 flex-wrap">
                <div className="inline-flex rounded-lg border border-gray-200 dark:border-slate-700 overflow-hidden">
                    {STATUS_TABS.map(t => (
                        <button key={t.value} onClick={() => setStatus(t.value)}
                            className={`px-3 py-1.5 text-sm ${status === t.value
                                ? 'bg-accent-500 text-white'
                                : 'bg-white dark:bg-slate-800 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700'}`}>
                            {t.label}
                        </button>
                    ))}
                </div>
                {isAdmin && (
                    <select value={owner} onChange={e => setOwner(e.target.value)}
                        className="px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-gray-700 dark:text-slate-200">
                        <option value="">All owners</option>
                        {users.map(u => <option key={u.id} value={u.id}>{u.first_name} {u.last_name}</option>)}
                    </select>
                )}
            </div>

            {/* List */}
            {todos.length === 0 ? (
                <div className="rounded-xl border border-dashed border-gray-300 dark:border-slate-700 p-12 text-center text-sm text-gray-400 dark:text-slate-500">
                    {status === 'done' ? 'No completed to-dos.' : 'No to-dos here. Accepted meeting action items show up as to-dos.'}
                </div>
            ) : (
                <ul className="space-y-2">
                    {todos.map(it => (
                        <li key={it.id}
                            className="flex items-center gap-3 rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-3">
                            <input
                                type="checkbox" checked={it.status === 'done'} disabled={busy === it.id}
                                onChange={() => toggleDone(it)}
                                className="h-4 w-4 shrink-0 accent-accent-500 cursor-pointer disabled:opacity-50"
                                title={it.status === 'done' ? 'Reopen' : 'Mark done'}
                            />
                            <div className="flex-1 min-w-0">
                                <div className={`text-sm truncate ${it.status === 'done' ? 'line-through text-gray-400 dark:text-slate-500' : 'text-gray-900 dark:text-slate-100'}`}>
                                    {it.title}
                                </div>
                                <div className="text-[11px] text-gray-400 dark:text-slate-500 truncate">
                                    {isAdmin && it.owner_name ? `${it.owner_name}` : ''}
                                    {isAdmin && it.owner_name && it.meeting_title ? ' · ' : ''}
                                    {it.meeting_title || ''}
                                    {it.matched_job_name ? ` · ${it.matched_job_name}` : (it.matched_job_number ? ` · job ${it.matched_job_number}` : '')}
                                </div>
                            </div>
                            {it.due_date && (
                                <span className={`shrink-0 text-[11px] whitespace-nowrap ${isOverdue(it) ? 'text-red-600 dark:text-red-400 font-medium' : 'text-gray-500 dark:text-slate-400'}`}>
                                    {isOverdue(it) ? 'overdue · ' : 'due '}{fmtDue(it.due_date)}
                                </span>
                            )}
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}
