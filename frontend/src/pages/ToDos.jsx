/**
 * @milehigh-header
 * schema_version: 1
 * purpose: To-Do page. Admins see every assigned to-do (filter by status + owner + due bucket +
 *          item type + job + text); non-admins see only what's assigned to them. Owner/admin can
 *          check items done. Items are grouped into collapsible due-urgency sections for scanning.
 *          Assignments arrive via the notification bell (created when a meeting checklist item is accepted).
 * exports:
 *   ToDos: Page component (any authenticated user).
 * imports_from: [react, ../utils/auth, ../services/todosApi, ../services/meetingsApi, ../components/Badge, ../components/Dropdown]
 * imported_by: [App.jsx]
 * invariants:
 *   - Server enforces scoping; non-admins can only ever see/modify their own items.
 *   - Status + owner filter server-side; due-bucket / item-type / job / text filter client-side.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { checkAuth } from '../utils/auth';
import { fetchTodos, setTodoStatus } from '../services/todosApi';
import { fetchAssignableUsers } from '../services/meetingsApi';
import { Badge } from '../components/Badge';
import Dropdown, { DropdownItem } from '../components/Dropdown';

const STATUS_TABS = [
    { value: 'open', label: 'Open' },
    { value: 'done', label: 'Done' },
    { value: 'all', label: 'All' },
];

// Item type → friendly label + Badge tint family (keys verified in utils/invoicingFormat.js).
const ITEM_TYPE_META = {
    action: { label: 'Action', tint: 'blue' },
    needs_gc_update: { label: 'GC update', tint: 'amber' },
    decision: { label: 'Decision', tint: 'violet' },
    risk: { label: 'Risk', tint: 'red' },
    fyi: { label: 'FYI', tint: 'slate' },
};
const ITEM_TYPE_ORDER = ['action', 'needs_gc_update', 'decision', 'risk', 'fyi'];
const typeMeta = (t) => ITEM_TYPE_META[t] || { label: t, tint: 'slate' };

// Due-urgency buckets. 'done' is terminal so completed items never read as "overdue".
const BUCKETS = [
    { key: 'overdue', label: 'Overdue' },
    { key: 'today', label: 'Due today' },
    { key: 'week', label: 'This week' },
    { key: 'later', label: 'Later' },
    { key: 'nodate', label: 'No date' },
    { key: 'done', label: 'Done' },
];
const BUCKET_LABEL = Object.fromEntries(BUCKETS.map(b => [b.key, b.label]));
// Chips exclude 'done' (the status tabs already control completed visibility).
const DUE_CHIPS = [{ key: 'all', label: 'All' }, ...BUCKETS.filter(b => b.key !== 'done')];

const COMPANY_TZ = 'America/Denver';
const todayDenver = () => new Intl.DateTimeFormat('en-CA', { timeZone: COMPANY_TZ }).format(new Date());
const addDays = (iso, n) => {
    const d = new Date(`${iso}T00:00:00`);
    d.setDate(d.getDate() + n);
    return new Intl.DateTimeFormat('en-CA').format(d);
};
const fmtDue = (iso) => {
    if (!iso) return '';
    const d = new Date(`${iso}T00:00:00`);
    return isNaN(d) ? iso : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

const jobLabel = (it) =>
    it.matched_job_name || (it.matched_job_number ? `job ${it.matched_job_number}` : null);

const userName = (u) => `${u.first_name || ''} ${u.last_name || ''}`.trim() || u.username || 'Unknown';
const initials = (u) =>
    (`${(u.first_name || '')[0] || ''}${(u.last_name || '')[0] || ''}`.toUpperCase()
        || (u.username || '?')[0].toUpperCase());

function Avatar({ user, size = 20 }) {
    return (
        <span
            className="inline-flex items-center justify-center shrink-0 rounded-full bg-accent-100 text-accent-700 dark:bg-accent-500/25 dark:text-accent-200 font-semibold"
            style={{ width: size, height: size, fontSize: Math.round(size * 0.45) }}
        >
            {initials(user)}
        </span>
    );
}

const bucketOf = (it, today, weekOut) => {
    if (it.status === 'done') return 'done';
    if (!it.due_date) return 'nodate';
    if (it.due_date < today) return 'overdue';
    if (it.due_date === today) return 'today';
    if (it.due_date <= weekOut) return 'week';
    return 'later';
};

export default function ToDos() {
    const [loading, setLoading] = useState(true);
    const [authed, setAuthed] = useState(false);
    const [isAdmin, setIsAdmin] = useState(false);
    const [todos, setTodos] = useState([]);
    // Server-side filters
    const [status, setStatus] = useState('open');
    const [owner, setOwner] = useState('');
    const [users, setUsers] = useState([]);
    // Client-side filters
    const [dueFilter, setDueFilter] = useState('all');
    const [itemType, setItemType] = useState('all');
    const [job, setJob] = useState('all');
    const [q, setQ] = useState('');
    const [collapsed, setCollapsed] = useState(() => new Set());
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

    const today = todayDenver();
    const weekOut = addDays(today, 7);

    // Distinct item types / jobs present in the loaded set, for the filter controls.
    const typeOptions = useMemo(() => {
        const present = new Set(todos.map(t => t.item_type).filter(Boolean));
        return ITEM_TYPE_ORDER.filter(t => present.has(t));
    }, [todos]);
    const jobOptions = useMemo(() => {
        const present = new Set(todos.map(jobLabel).filter(Boolean));
        return [...present].sort((a, b) => a.localeCompare(b));
    }, [todos]);

    // Reset client filters that no longer have a matching option (e.g. after a reload).
    useEffect(() => { if (itemType !== 'all' && !typeOptions.includes(itemType)) setItemType('all'); }, [typeOptions, itemType]);
    useEffect(() => { if (job !== 'all' && !jobOptions.includes(job)) setJob('all'); }, [jobOptions, job]);

    const filtered = useMemo(() => {
        const needle = q.trim().toLowerCase();
        return todos.filter(it => {
            if (itemType !== 'all' && it.item_type !== itemType) return false;
            if (job !== 'all' && jobLabel(it) !== job) return false;
            if (dueFilter !== 'all' && bucketOf(it, today, weekOut) !== dueFilter) return false;
            if (needle) {
                const hay = `${it.title || ''} ${it.detail || ''}`.toLowerCase();
                if (!hay.includes(needle)) return false;
            }
            return true;
        });
    }, [todos, itemType, job, dueFilter, q, today, weekOut]);

    // Group the filtered set into ordered, non-empty buckets.
    const groups = useMemo(() => {
        const by = {};
        for (const it of filtered) {
            const b = bucketOf(it, today, weekOut);
            (by[b] ||= []).push(it);
        }
        return BUCKETS.filter(b => by[b.key]?.length).map(b => ({ ...b, items: by[b.key] }));
    }, [filtered, today, weekOut]);

    const toggleCollapse = (key) => setCollapsed(prev => {
        const next = new Set(prev);
        next.has(key) ? next.delete(key) : next.add(key);
        return next;
    });

    if (loading) return <div className="flex-1 flex items-center justify-center"><span className="text-gray-500 dark:text-slate-400">Loading…</span></div>;
    if (!authed) return <div className="flex-1 flex items-center justify-center"><span className="text-gray-500 dark:text-slate-400">Please log in to see your to-dos.</span></div>;

    const isOverdue = (it) => it.due_date && it.status !== 'done' && it.due_date < today;
    const hasActiveFilters = dueFilter !== 'all' || itemType !== 'all' || job !== 'all' || q.trim();
    const chipBase = 'px-3 py-1.5 text-sm rounded-lg border transition-colors';

    return (
        <div className="flex-1 p-4 md:p-6 max-w-[1100px] mx-auto w-full">
            <div className="flex items-center justify-between gap-3 mb-4">
                <h1 className="text-xl font-bold text-gray-900 dark:text-slate-100">
                    To-Dos
                    {!isAdmin && <span className="ml-2 text-sm font-normal text-gray-400 dark:text-slate-500">assigned to you</span>}
                </h1>
                <span className="text-sm text-gray-400 dark:text-slate-500">{filtered.length} shown</span>
            </div>
            {error && <div className="mb-3 px-3 py-2 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300 text-sm">{error}</div>}

            {/* Filters */}
            <div className="space-y-2 mb-5">
                {/* Row 1 — status (server) + owner (server, admin) + text search */}
                <div className="flex items-center gap-2 flex-wrap">
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
                    {isAdmin && (() => {
                        const selected = users.find(u => String(u.id) === String(owner));
                        return (
                            <Dropdown
                                menuWidth={220}
                                icon={selected
                                    ? <Avatar user={selected} size={20} />
                                    : <span className="inline-flex items-center justify-center shrink-0 h-5 w-5 rounded-full bg-gray-100 text-gray-500 dark:bg-slate-600 dark:text-slate-300 text-[10px] font-semibold">All</span>}
                                label={<span className="ml-1.5">{selected ? userName(selected) : 'All owners'}</span>}
                                active={!!owner}
                                buttonClassName={`px-2.5 py-1.5 text-sm rounded-lg border inline-flex items-center gap-1 whitespace-nowrap transition-colors ${owner
                                    ? 'bg-accent-50 dark:bg-accent-500/15 border-accent-300 dark:border-accent-500/40 text-accent-700 dark:text-accent-200'
                                    : 'bg-white dark:bg-slate-900 border-gray-300 dark:border-slate-600 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-800'}`}
                            >
                                <DropdownItem
                                    onClick={() => setOwner('')}
                                    active={!owner}
                                    icon={<span className="inline-flex items-center justify-center shrink-0 h-5 w-5 rounded-full bg-gray-100 text-gray-500 dark:bg-slate-600 dark:text-slate-300 text-[10px] font-semibold">All</span>}
                                >
                                    All owners
                                </DropdownItem>
                                {users.map(u => (
                                    <DropdownItem
                                        key={u.id}
                                        onClick={() => setOwner(String(u.id))}
                                        active={String(u.id) === String(owner)}
                                        icon={<Avatar user={u} size={20} />}
                                    >
                                        {userName(u)}
                                    </DropdownItem>
                                ))}
                            </Dropdown>
                        );
                    })()}
                    <div className="relative flex-1 min-w-[180px] max-w-xs">
                        <input
                            type="text" value={q} onChange={e => setQ(e.target.value)} placeholder="Search to-dos…"
                            className="w-full px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-gray-700 dark:text-slate-200 placeholder-gray-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-accent-500/40 focus:border-accent-400"
                        />
                        {q && (
                            <button onClick={() => setQ('')} title="Clear search"
                                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-slate-300 text-sm leading-none">×</button>
                        )}
                    </div>
                </div>

                {/* Row 2 — due-urgency bucket chips */}
                <div className="flex items-center gap-1.5 flex-wrap">
                    {DUE_CHIPS.map(c => {
                        const active = dueFilter === c.key;
                        const danger = c.key === 'overdue';
                        return (
                            <button key={c.key} onClick={() => setDueFilter(c.key)}
                                className={`${chipBase} ${active
                                    ? (danger ? 'bg-red-500 border-red-500 text-white' : 'bg-accent-500 border-accent-500 text-white')
                                    : `bg-white dark:bg-slate-800 border-gray-200 dark:border-slate-700 hover:bg-gray-50 dark:hover:bg-slate-700 ${danger ? 'text-red-600 dark:text-red-400' : 'text-gray-600 dark:text-slate-300'}`}`}>
                                {c.label}
                            </button>
                        );
                    })}
                </div>

                {/* Row 3 — admin: item-type chips + job select (only when options exist) */}
                {isAdmin && (typeOptions.length > 1 || jobOptions.length > 0) && (
                    <div className="flex items-center gap-1.5 flex-wrap">
                        {typeOptions.length > 1 && (
                            <>
                                <button onClick={() => setItemType('all')}
                                    className={`${chipBase} ${itemType === 'all'
                                        ? 'bg-accent-500 border-accent-500 text-white'
                                        : 'bg-white dark:bg-slate-800 border-gray-200 dark:border-slate-700 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700'}`}>
                                    All types
                                </button>
                                {typeOptions.map(t => (
                                    <button key={t} onClick={() => setItemType(t)}
                                        className={`${chipBase} ${itemType === t
                                            ? 'bg-accent-500 border-accent-500 text-white'
                                            : 'bg-white dark:bg-slate-800 border-gray-200 dark:border-slate-700 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700'}`}>
                                        {typeMeta(t).label}
                                    </button>
                                ))}
                            </>
                        )}
                        {jobOptions.length > 0 && (
                            <select value={job} onChange={e => setJob(e.target.value)}
                                className="px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-gray-700 dark:text-slate-200">
                                <option value="all">All jobs</option>
                                {jobOptions.map(j => <option key={j} value={j}>{j}</option>)}
                            </select>
                        )}
                    </div>
                )}
            </div>

            {/* List */}
            {todos.length === 0 ? (
                <div className="rounded-xl border border-dashed border-gray-300 dark:border-slate-700 p-12 text-center text-sm text-gray-400 dark:text-slate-500">
                    {status === 'done' ? 'No completed to-dos.' : 'No to-dos here. Accepted meeting action items show up as to-dos.'}
                </div>
            ) : filtered.length === 0 ? (
                <div className="rounded-xl border border-dashed border-gray-300 dark:border-slate-700 p-10 text-center text-sm text-gray-400 dark:text-slate-500">
                    No to-dos match these filters.
                    {hasActiveFilters && (
                        <button onClick={() => { setDueFilter('all'); setItemType('all'); setJob('all'); setQ(''); }}
                            className="ml-2 text-accent-600 dark:text-accent-300 hover:underline">Clear filters</button>
                    )}
                </div>
            ) : (
                <div className="space-y-5">
                    {groups.map(g => {
                        const isCollapsed = collapsed.has(g.key);
                        const danger = g.key === 'overdue';
                        return (
                            <section key={g.key}>
                                <button onClick={() => toggleCollapse(g.key)}
                                    className="flex items-center gap-2 w-full text-left mb-2 group">
                                    <span className={`text-gray-400 dark:text-slate-500 text-xs transition-transform ${isCollapsed ? '-rotate-90' : ''}`}>▾</span>
                                    <h2 className={`text-sm font-semibold ${danger ? 'text-red-600 dark:text-red-400' : 'text-gray-700 dark:text-slate-200'}`}>
                                        {g.label}
                                    </h2>
                                    <span className="text-xs text-gray-400 dark:text-slate-500">{g.items.length}</span>
                                    <span className="flex-1 border-t border-gray-100 dark:border-slate-800 ml-1" />
                                </button>
                                {!isCollapsed && (
                                    <ul className="space-y-2">
                                        {g.items.map(it => {
                                            const done = it.status === 'done';
                                            const overdue = isOverdue(it);
                                            const dueToday = it.due_date === today && !done;
                                            const meta = typeMeta(it.item_type);
                                            const jl = jobLabel(it);
                                            const metaParts = [
                                                isAdmin && it.owner_name ? it.owner_name : null,
                                                it.meeting_title || null,
                                                jl,
                                            ].filter(Boolean);
                                            return (
                                                <li key={it.id}
                                                    className="flex items-start gap-3 rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-3 hover:border-gray-300 dark:hover:border-slate-600 transition-colors">
                                                    <input
                                                        type="checkbox" checked={done} disabled={busy === it.id}
                                                        onChange={() => toggleDone(it)}
                                                        className="mt-0.5 h-4 w-4 shrink-0 accent-accent-500 cursor-pointer disabled:opacity-50"
                                                        title={done ? 'Reopen' : 'Mark done'}
                                                    />
                                                    <div className="flex-1 min-w-0">
                                                        <div className={`text-sm leading-snug ${done ? 'line-through text-gray-400 dark:text-slate-500' : 'text-gray-900 dark:text-slate-100'}`}>
                                                            {it.title}
                                                        </div>
                                                        {metaParts.length > 0 && (
                                                            <div className="mt-1 text-xs text-gray-500 dark:text-slate-400 truncate">
                                                                {metaParts.join(' · ')}
                                                            </div>
                                                        )}
                                                    </div>
                                                    <div className="flex shrink-0 items-center gap-2">
                                                        {it.item_type && (
                                                            <Badge tint={meta.tint} className="!px-2 !py-0.5 !text-xs hidden sm:inline-flex">
                                                                {meta.label}
                                                            </Badge>
                                                        )}
                                                        {it.due_date && (
                                                            <span className={`whitespace-nowrap text-xs font-medium px-2 py-0.5 rounded-full ring-1 ring-inset ${
                                                                done
                                                                    ? 'bg-slate-100 text-slate-500 ring-slate-200/80 dark:bg-slate-500/10 dark:text-slate-400 dark:ring-slate-500/30'
                                                                    : overdue
                                                                        ? 'bg-red-50 text-red-700 ring-red-200/70 dark:bg-red-500/10 dark:text-red-300 dark:ring-red-500/30'
                                                                        : dueToday
                                                                            ? 'bg-amber-50 text-amber-700 ring-amber-200/70 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/30'
                                                                            : 'bg-slate-100 text-slate-600 ring-slate-200/80 dark:bg-slate-500/10 dark:text-slate-300 dark:ring-slate-500/30'
                                                            }`}>
                                                                {overdue ? 'overdue · ' : 'due '}{fmtDue(it.due_date)}
                                                            </span>
                                                        )}
                                                    </div>
                                                </li>
                                            );
                                        })}
                                    </ul>
                                )}
                            </section>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
