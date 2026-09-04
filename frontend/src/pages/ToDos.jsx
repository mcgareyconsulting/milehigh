/**
 * @milehigh-header
 * schema_version: 1
 * purpose: To-Dos page — two equal columns in Job Log redesign styling. The left column is the
 *          viewed user's assigned to-dos (grouped into collapsible due-urgency sections, narrowed
 *          by status / due / type / job / text filters); the right is the @mentions of that same
 *          user (board comments, drawing comments, DWL notes) with unread emphasis and
 *          click-through. One page-level owner control drives both columns.
 * exports:
 *   ToDos: Page component (any authenticated user).
 * imports_from: [react, react-router-dom, ../utils/auth, ../services/todosApi, ../services/meetingsApi,
 *                ../services/notificationApi, ../utils/desktopNotifications, ../components/Dropdown]
 * imported_by: [App.jsx]
 * invariants:
 *   - Scope is server-enforced on both columns: an admin may view any user or everyone, a
 *     non-admin only ever sees and modifies their own rows. The owner control is admin-only UI
 *     over that gate, never the gate itself.
 *   - Everyone lands on their own queue; an admin widens explicitly.
 *   - Owner + status filter server-side; due window / item type / job / text / mentioner filter
 *     client-side. Status is a multi-select over {open, done}: both selected collapses to the
 *     server's 'all'; none selected is an honest empty view, not a silent "everything".
 *   - The due window is a multi-select set; empty means "no due filter", not "no results".
 *   - Mentions belonging to someone else are read-only here — no mark-read on click, no "Mark all
 *     read" — because read state is that person's, not the viewer's.
 *   - The mentions column asks the API for MENTION_TYPES only, so a burst of to-do notifications
 *     cannot push mentions past the row cap. The mentioner filter narrows that loaded page
 *     client-side — its options are the authors actually present, like the job filter.
 *   - Colors come from the Job Log design tokens (surface / hairline / ink / flag vars) — never a
 *     `dark:` twin on a token class, which would pin one theme's value into the other.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { checkAuth } from '../utils/auth';
import { fetchTodos, setTodoStatus } from '../services/todosApi';
import { fetchAssignableUsers } from '../services/meetingsApi';
import {
    fetchNotifications,
    markNotificationRead,
    markAllRead,
    MENTION_TYPES,
} from '../services/notificationApi';
import { navigateForNotification } from '../utils/desktopNotifications';
import Dropdown, { DropdownItem } from '../components/Dropdown';

/** Page-level owner scope meaning "every user", for both columns. */
const SCOPE_ALL = 'all';

// Status is multi-select over these two; picking both is the server's 'all'.
const STATUS_OPTIONS = [
    { value: 'open', label: 'Open' },
    { value: 'done', label: 'Done' },
];
/** Collapse the selected status set into the server's ?status value. */
const statusParamFor = (set) => {
    if (set.size === 2) return 'all';
    if (set.has('open')) return 'open';
    if (set.has('done')) return 'done';
    return null; // nothing selected — don't ask the server for anything
};

// Item type → friendly label + chip colors drawn from the token palette.
const ITEM_TYPE_META = {
    action: { label: 'Action', fg: 'var(--st-blue-fg)', bg: 'var(--st-blue-bg)' },
    needs_gc_update: { label: 'GC update', fg: 'var(--st-amber-fg)', bg: 'var(--st-amber-bg)' },
    decision: { label: 'Decision', fg: 'var(--st-purple-fg)', bg: 'var(--st-purple-bg)' },
    risk: { label: 'Risk', fg: 'var(--fl-red-fg)', bg: 'var(--fl-red-bg)' },
    fyi: { label: 'FYI', fg: 'var(--text-2)', bg: 'var(--surface-2)' },
};
const ITEM_TYPE_ORDER = ['action', 'needs_gc_update', 'decision', 'risk', 'fyi'];
const typeMeta = (t) => ITEM_TYPE_META[t] || { label: t, fg: 'var(--text-2)', bg: 'var(--surface-2)' };

// Due-urgency buckets. 'done' is terminal so completed items never read as "overdue".
const BUCKETS = [
    { key: 'overdue', label: 'Overdue' },
    { key: 'today', label: 'Due today' },
    { key: 'week', label: 'This week' },
    { key: 'later', label: 'Later' },
    { key: 'nodate', label: 'No date' },
    { key: 'done', label: 'Done' },
];
// Every window (Overdue included) lives in one multi-select dropdown; an empty
// selection means "no due filter" rather than "no results". 'done' is excluded —
// the status control already decides whether completed work is visible.
const DUE_MENU = BUCKETS.filter(b => b.key !== 'done');
const DUE_LABEL = Object.fromEntries(BUCKETS.map(b => [b.key, b.label]));

/** Mentioner filter sentinel: no narrowing. */
const ANY_MENTIONER = 'all';

const MENTIONS_LIMIT = 50;
const MENTIONS_POLL_MS = 60000;

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

const timeAgo = (dateStr) => {
    const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
    if (!Number.isFinite(seconds)) return '';
    if (seconds < 60) return 'just now';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d ago`;
    return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

const jobLabel = (it) =>
    it.matched_job_name || (it.matched_job_number ? `job ${it.matched_job_number}` : null);

const userName = (u) => `${u.first_name || ''} ${u.last_name || ''}`.trim() || u.username || 'Unknown';
const initials = (u) =>
    (`${(u.first_name || '')[0] || ''}${(u.last_name || '')[0] || ''}`.toUpperCase()
        || (u.username || '?')[0].toUpperCase());
const initialsFromName = (name) => {
    const parts = (name || '').trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return '@';
    return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
};

const bucketOf = (it, today, weekOut) => {
    if (it.status === 'done') return 'done';
    if (!it.due_date) return 'nodate';
    if (it.due_date < today) return 'overdue';
    if (it.due_date === today) return 'today';
    if (it.due_date <= weekOut) return 'week';
    return 'later';
};

/** Where a mention came from, for the source chip + fallback context line. */
const mentionSource = (n) => {
    if (n.board_item_id) return { label: 'Board', context: n.board_item_title };
    if (n.drawing_version_comment_id) {
        return {
            label: 'Drawing',
            context: [
                n.release_job_number != null ? `${n.release_job_number}-${n.release_number}` : null,
                n.drawing_version_number ? `v${n.drawing_version_number}` : null,
            ].filter(Boolean).join(' · ') || null,
        };
    }
    if (n.submittal_id) {
        return {
            label: 'DWL',
            context: [n.submittal_project_number, n.submittal_project_name, n.submittal_title]
                .filter(Boolean).join(' · ') || `Submittal ${n.submittal_id}`,
        };
    }
    return { label: 'Mention', context: null };
};

/** Strip the trailing `in "<title>"` the old board message format embedded. */
const mentionHeadline = (n) => (n.board_item_title
    ? (n.message || '').replace(/ in ".*"$/, '')
    : (n.message || 'You were mentioned'));

const PANEL_CLS = 'bg-surface border border-hairline-strong rounded-[14px] flex flex-col min-h-0 overflow-hidden';
const PANEL_HEAD_CLS = 'shrink-0 bg-surface-2 border-b border-hairline';

function Avatar({ user, size = 20 }) {
    return (
        <span
            className="inline-flex items-center justify-center shrink-0 rounded-full font-semibold"
            style={{
                width: size,
                height: size,
                fontSize: Math.round(size * 0.45),
                background: 'var(--accent-soft)',
                color: 'var(--accent)',
            }}
        >
            {initials(user)}
        </span>
    );
}

function NameAvatar({ name, size = 26 }) {
    return (
        <span
            className="inline-flex items-center justify-center shrink-0 rounded-full font-semibold"
            style={{
                width: size,
                height: size,
                fontSize: Math.round(size * 0.42),
                background: 'var(--accent-soft)',
                color: 'var(--accent)',
            }}
            aria-hidden
        >
            {initialsFromName(name)}
        </span>
    );
}

function AllUsersGlyph({ size = 20 }) {
    return (
        <span
            className="inline-flex items-center justify-center shrink-0 rounded-full font-semibold bg-surface-2 text-ink-3"
            style={{ width: size, height: size, fontSize: Math.round(size * 0.5) }}
        >
            ∗
        </span>
    );
}

/** Small pill used for counts in panel headers and section rules. */
function CountPill({ children, tone = 'neutral', title }) {
    const style = tone === 'accent'
        ? { background: 'var(--accent)', color: 'var(--accent-ink)' }
        : { background: 'var(--surface)', color: 'var(--text-2)', border: '1px solid var(--border)' };
    return (
        <span
            className="inline-grid place-items-center font-semibold tabular-nums shrink-0"
            style={{ ...style, minWidth: 20, height: 18, padding: '0 6px', borderRadius: 999, fontSize: 11.5 }}
            title={title}
        >
            {children}
        </span>
    );
}

export default function ToDos() {
    const navigate = useNavigate();
    const [loading, setLoading] = useState(true);
    const [authed, setAuthed] = useState(false);
    const [me, setMe] = useState(null);
    const [isAdmin, setIsAdmin] = useState(false);
    const [todos, setTodos] = useState([]);
    // Server-side scope. `scope` stays null until auth resolves so the first fetch
    // already carries the default (me) rather than loading everyone and refetching.
    const [scope, setScope] = useState(null);
    const [statuses, setStatuses] = useState(() => new Set(['open']));
    const [users, setUsers] = useState([]);
    // Client-side filters
    const [dueFilters, setDueFilters] = useState(() => new Set());
    const [itemType, setItemType] = useState('all');
    const [job, setJob] = useState('all');
    const [q, setQ] = useState('');
    const [mentioner, setMentioner] = useState(ANY_MENTIONER);
    const [collapsed, setCollapsed] = useState(() => new Set());
    const [busy, setBusy] = useState(null);
    const [error, setError] = useState(null);
    // Mentions column
    const [mentions, setMentions] = useState([]);
    const [mentionsUnread, setMentionsUnread] = useState(0);
    const [mentionsLoading, setMentionsLoading] = useState(true);

    const statusParam = statusParamFor(statuses);

    useEffect(() => {
        checkAuth().then(u => {
            setAuthed(!!u);
            setMe(u || null);
            setIsAdmin(u?.is_admin || false);
            // Everyone lands on their own queue; admins widen from the dropdown.
            setScope(u ? String(u.id) : null);
            setLoading(false);
        });
    }, []);

    const viewingAll = scope === SCOPE_ALL;
    const viewingSelf = !!me && scope === String(me.id);

    const load = useCallback(async () => {
        if (scope === null) return;
        setError(null);
        // No status selected — there is nothing to ask for; show the empty view.
        if (!statusParam) { setTodos([]); return; }
        try {
            const d = await fetchTodos({ status: statusParam, owner: viewingAll ? undefined : scope });
            setTodos(d.todos);
            setIsAdmin(d.is_admin);
        } catch { setError('Failed to load to-dos'); }
    }, [statusParam, scope, viewingAll]);

    useEffect(() => { if (authed) load(); }, [authed, load]);
    useEffect(() => { if (isAdmin) fetchAssignableUsers().then(setUsers).catch(() => {}); }, [isAdmin]);

    const loadMentions = useCallback(async () => {
        if (scope === null) return;
        try {
            const d = await fetchNotifications({ types: MENTION_TYPES, limit: MENTIONS_LIMIT, owner: scope });
            setMentions(d.notifications || []);
            setMentionsUnread(d.unread_count || 0);
        } catch { /* the to-dos column still works without mentions */ }
        finally { setMentionsLoading(false); }
    }, [scope]);

    useEffect(() => {
        if (!authed || scope === null) return undefined;
        loadMentions();
        const id = setInterval(loadMentions, MENTIONS_POLL_MS);
        return () => clearInterval(id);
    }, [authed, scope, loadMentions]);

    const toggleDone = async (it) => {
        const next = it.status === 'done' ? 'accepted' : 'done';
        setBusy(it.id); setError(null);
        try {
            const updated = await setTodoStatus(it.id, next);
            // Drop the row if its new status is no longer one the view asks for.
            setTodos(prev => prev
                .map(t => (t.id === it.id ? { ...t, status: updated.status } : t))
                .filter(t => statuses.has(t.status === 'done' ? 'done' : 'open')));
        } catch { setError('Failed to update to-do'); }
        finally { setBusy(null); }
    };

    const openMention = async (n) => {
        // Read state belongs to the recipient — never flip it on someone else's behalf.
        if (!n.is_read && viewingSelf) {
            try {
                await markNotificationRead(n.id);
                setMentions(prev => prev.map(m => (m.id === n.id ? { ...m, is_read: true } : m)));
                setMentionsUnread(c => Math.max(0, c - 1));
            } catch { /* navigate anyway — the read flag is not load-bearing */ }
        }
        navigateForNotification(n, navigate);
    };

    const markMentionsRead = async () => {
        try {
            await markAllRead({ types: MENTION_TYPES });
            setMentions(prev => prev.map(m => ({ ...m, is_read: true })));
            setMentionsUnread(0);
        } catch { /* leave the badge alone on failure */ }
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
            if (dueFilters.size && !dueFilters.has(bucketOf(it, today, weekOut))) return false;
            if (needle) {
                const hay = `${it.title || ''} ${it.detail || ''}`.toLowerCase();
                if (!hay.includes(needle)) return false;
            }
            return true;
        });
    }, [todos, itemType, job, dueFilters, q, today, weekOut]);

    // Mentioners present in the loaded page, for the mentions filter.
    const mentionerOptions = useMemo(() => {
        const present = new Set(mentions.map(m => m.author_name).filter(Boolean));
        return [...present].sort((a, b) => a.localeCompare(b));
    }, [mentions]);

    useEffect(() => {
        if (mentioner !== ANY_MENTIONER && !mentionerOptions.includes(mentioner)) {
            setMentioner(ANY_MENTIONER);
        }
    }, [mentionerOptions, mentioner]);

    const visibleMentions = useMemo(() => (
        mentioner === ANY_MENTIONER
            ? mentions
            : mentions.filter(m => m.author_name === mentioner)
    ), [mentions, mentioner]);

    // Group the filtered set into ordered, non-empty buckets.
    const groups = useMemo(() => {
        const by = {};
        for (const it of filtered) {
            const b = bucketOf(it, today, weekOut);
            (by[b] ||= []).push(it);
        }
        return BUCKETS.filter(b => by[b.key]?.length).map(b => ({ ...b, items: by[b.key] }));
    }, [filtered, today, weekOut]);

    const overdueCount = useMemo(
        () => filtered.filter(it => bucketOf(it, today, weekOut) === 'overdue').length,
        [filtered, today, weekOut],
    );

    const toggleCollapse = (key) => setCollapsed(prev => {
        const next = new Set(prev);
        next.has(key) ? next.delete(key) : next.add(key);
        return next;
    });

    if (loading) {
        return (
            <div className="flex-1 flex items-center justify-center bg-canvas">
                <span className="text-ink-3 text-xs">Loading…</span>
            </div>
        );
    }
    if (!authed) {
        return (
            <div className="flex-1 flex items-center justify-center bg-canvas">
                <span className="text-ink-3 text-xs">Please log in to see your to-dos.</span>
            </div>
        );
    }

    const isOverdue = (it) => it.due_date && it.status !== 'done' && it.due_date < today;
    const hasActiveFilters = dueFilters.size > 0 || itemType !== 'all' || job !== 'all' || !!q.trim();
    const clearFilters = () => { setDueFilters(new Set()); setItemType('all'); setJob('all'); setQ(''); };

    /** Toggle one member of a Set-valued filter. */
    const toggleIn = (setter) => (key) => setter(prev => {
        const next = new Set(prev);
        next.has(key) ? next.delete(key) : next.add(key);
        return next;
    });
    const toggleStatus = toggleIn(setStatuses);
    const toggleDue = toggleIn(setDueFilters);

    // Shared trigger styling for the filter row, so the controls read as one set.
    const triggerCls = (active, danger = false) =>
        `px-2.5 py-1 rounded-[7px] text-xs font-semibold whitespace-nowrap border inline-flex items-center gap-1 transition-colors ${active
            ? (danger
                ? 'bg-red-50 border-red-300 text-red-700'
                : 'bg-brand-soft border-hairline-strong text-brand')
            : 'bg-surface border-hairline-strong text-ink-2 hover:bg-surface-2'}`;

    const statusLabel = statuses.size === 2
        ? 'All'
        : (STATUS_OPTIONS.find(o => statuses.has(o.value))?.label || 'No status');
    // Overdue in the selection tints the whole control red — that's the one window
    // worth spotting from across the toolbar.
    const dueDanger = dueFilters.has('overdue');
    const dueLabel = dueFilters.size === 0
        ? 'Any due date'
        : (dueFilters.size === 1
            ? DUE_LABEL[[...dueFilters][0]]
            : `${dueFilters.size} due windows`);

    const scopedUser = users.find(u => String(u.id) === String(scope));
    const scopeName = viewingAll
        ? 'All users'
        : (viewingSelf ? 'You' : (scopedUser ? userName(scopedUser) : 'You'));
    const scopeSuffix = viewingAll
        ? 'across everyone'
        : (viewingSelf ? 'assigned to you' : `for ${scopeName}`);

    return (
        <div className="w-full bg-canvas flex flex-col lg:h-[calc(100vh_-_var(--app-chrome-h))] lg:overflow-hidden">
            <div className="mx-auto w-full max-w-[1500px] px-3 md:px-5 py-3 md:py-4 flex-1 min-h-0 flex flex-col gap-3">

                {/* Page header — the owner scope drives BOTH columns. */}
                <header className="shrink-0 flex items-end justify-between gap-3 flex-wrap notif-pod-reserve">
                    <div className="min-w-0">
                        <h1 className="text-ink truncate" style={{ fontWeight: 700, fontSize: 20, letterSpacing: '-.3px' }}>
                            To-Dos &amp; Mentions
                        </h1>
                        <p className="text-ink-3 text-xs mt-0.5">
                            {viewingAll
                                ? 'Every assigned to-do and @mention across the team.'
                                : `The queue on the left, every @mention on the right — ${scopeSuffix}.`}
                        </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                        {error && (
                            <div
                                className="text-xs font-semibold px-2.5 py-1 rounded-[7px]"
                                style={{ background: 'var(--fl-red-bg)', color: 'var(--fl-red-fg)' }}
                                role="alert"
                            >
                                {error}
                            </div>
                        )}
                        {/* Admin-only UI over a server-enforced gate: a non-admin's rows stay
                            pinned to themselves no matter what the client sends. */}
                        {isAdmin && (
                            <Dropdown
                                align="right"
                                menuWidth={230}
                                icon={viewingAll
                                    ? <AllUsersGlyph size={20} />
                                    : <Avatar user={scopedUser || { username: me?.username }} size={20} />}
                                label={<span className="ml-1.5">{scopeName}</span>}
                                active={!viewingSelf}
                                buttonClassName={`px-2.5 py-1.5 text-xs font-semibold rounded-[7px] border inline-flex items-center gap-1 whitespace-nowrap transition-colors ${!viewingSelf
                                    ? 'bg-brand-soft border-hairline-strong text-brand'
                                    : 'bg-surface border-hairline-strong text-ink-2 hover:bg-surface-2'}`}
                            >
                                <DropdownItem
                                    onClick={() => setScope(SCOPE_ALL)}
                                    active={viewingAll}
                                    icon={<AllUsersGlyph />}
                                >
                                    All users
                                </DropdownItem>
                                {users.map(u => (
                                    <DropdownItem
                                        key={u.id}
                                        onClick={() => setScope(String(u.id))}
                                        active={String(u.id) === String(scope)}
                                        icon={<Avatar user={u} size={20} />}
                                    >
                                        {userName(u)}{me && String(u.id) === String(me.id) ? ' (me)' : ''}
                                    </DropdownItem>
                                ))}
                            </Dropdown>
                        )}
                    </div>
                </header>

                <div className="grid gap-3 flex-1 min-h-0 lg:grid-cols-2">

                    {/* ── Left: to-dos ───────────────────────────────────────────── */}
                    <section className={PANEL_CLS} aria-label="To-dos">
                        <div className={PANEL_HEAD_CLS} style={{ padding: '10px 12px' }}>
                            <div className="flex items-center gap-2 flex-wrap">
                                <h2 className="text-ink" style={{ fontWeight: 700, fontSize: 15 }}>To-Dos</h2>
                                <span className="text-ink-3 text-xs truncate">{scopeSuffix}</span>
                                <div className="flex-1" />
                                {overdueCount > 0 && (
                                    <span
                                        className="text-xs font-semibold px-2 py-0.5 rounded-full"
                                        style={{ background: 'var(--fl-red-bg)', color: 'var(--fl-red-fg)' }}
                                    >
                                        {overdueCount} overdue
                                    </span>
                                )}
                                <span className="text-ink-3 text-xs tabular-nums">{filtered.length} shown</span>
                            </div>

                            {/* One filter line: status · due · type · job · search. Each control
                                is a dropdown so the row never needs a second line. */}
                            <div className="flex items-center gap-1.5 flex-wrap mt-2.5">
                                <Dropdown
                                    menuWidth={150}
                                    closeOnSelect={false}
                                    label={statusLabel}
                                    active={statuses.size !== 1 || !statuses.has('open')}
                                    buttonClassName={triggerCls(statuses.size !== 1 || !statuses.has('open'))}
                                >
                                    <DropdownItem onClick={() => setStatuses(new Set(['open', 'done']))} active={statuses.size === 2}>
                                        All
                                    </DropdownItem>
                                    {STATUS_OPTIONS.map(o => (
                                        <DropdownItem key={o.value} onClick={() => toggleStatus(o.value)} active={statuses.has(o.value)}>
                                            {o.label}
                                        </DropdownItem>
                                    ))}
                                </Dropdown>

                                <Dropdown
                                    menuWidth={175}
                                    closeOnSelect={false}
                                    label={dueLabel}
                                    active={dueFilters.size > 0}
                                    buttonClassName={triggerCls(dueFilters.size > 0, dueDanger)}
                                >
                                    <DropdownItem onClick={() => setDueFilters(new Set())} active={dueFilters.size === 0}>
                                        Any due date
                                    </DropdownItem>
                                    {DUE_MENU.map(b => (
                                        <DropdownItem key={b.key} onClick={() => toggleDue(b.key)} active={dueFilters.has(b.key)}>
                                            {b.key === 'overdue'
                                                ? <span className="text-red-600 font-semibold">{b.label}</span>
                                                : b.label}
                                        </DropdownItem>
                                    ))}
                                </Dropdown>

                                {typeOptions.length > 1 && (
                                    <Dropdown
                                        menuWidth={160}
                                        label={itemType === 'all' ? 'All types' : typeMeta(itemType).label}
                                        active={itemType !== 'all'}
                                        buttonClassName={triggerCls(itemType !== 'all')}
                                    >
                                        <DropdownItem onClick={() => setItemType('all')} active={itemType === 'all'}>
                                            All types
                                        </DropdownItem>
                                        {typeOptions.map(t => (
                                            <DropdownItem key={t} onClick={() => setItemType(t)} active={itemType === t}>
                                                {typeMeta(t).label}
                                            </DropdownItem>
                                        ))}
                                    </Dropdown>
                                )}

                                {/* Job stays a native select — the list runs long and the OS picker
                                    handles that better than a menu. */}
                                {jobOptions.length > 0 && (
                                    <select
                                        value={job}
                                        onChange={e => setJob(e.target.value)}
                                        className={`${triggerCls(job !== 'all')} max-w-[170px]`}
                                    >
                                        <option value="all">All jobs</option>
                                        {jobOptions.map(j => <option key={j} value={j}>{j}</option>)}
                                    </select>
                                )}

                                <div className="relative flex-1 min-w-[130px] max-w-[220px]">
                                    <input
                                        type="text" value={q} onChange={e => setQ(e.target.value)} placeholder="Search to-dos…"
                                        className="w-full px-2.5 py-1 text-xs rounded-[7px] border border-hairline-strong bg-input-bg text-ink-2 placeholder:text-ink-3 focus:outline-none focus:ring-2 focus:ring-accent-400/40 focus:border-accent-400"
                                    />
                                    {q && (
                                        <button onClick={() => setQ('')} title="Clear search"
                                            className="absolute right-1.5 top-1/2 -translate-y-1/2 text-ink-3 hover:text-ink-2 text-sm leading-none">×</button>
                                    )}
                                </div>

                                {hasActiveFilters && (
                                    <button
                                        onClick={clearFilters}
                                        className="text-xs font-semibold text-brand hover:opacity-80 whitespace-nowrap"
                                    >
                                        Clear
                                    </button>
                                )}
                            </div>
                        </div>

                        {/* Body */}
                        <div className="flex-1 min-h-0 overflow-y-auto">
                            {!statusParam ? (
                                <div className="p-10 text-center text-xs text-ink-3">
                                    No status selected.
                                    <button
                                        onClick={() => setStatuses(new Set(['open', 'done']))}
                                        className="ml-2 text-brand hover:underline font-semibold"
                                    >
                                        Show all
                                    </button>
                                </div>
                            ) : todos.length === 0 ? (
                                <div className="p-10 text-center text-xs text-ink-3">
                                    {statusParam === 'done'
                                        ? 'No completed to-dos.'
                                        : 'Nothing here. Accepted meeting action items show up as to-dos.'}
                                </div>
                            ) : filtered.length === 0 ? (
                                <div className="p-10 text-center text-xs text-ink-3">
                                    No to-dos match these filters.
                                    {hasActiveFilters && (
                                        <button onClick={clearFilters} className="ml-2 text-brand hover:underline font-semibold">
                                            Clear filters
                                        </button>
                                    )}
                                </div>
                            ) : (
                                groups.map(g => {
                                    const isCollapsed = collapsed.has(g.key);
                                    const danger = g.key === 'overdue';
                                    return (
                                        <section key={g.key}>
                                            <button
                                                onClick={() => toggleCollapse(g.key)}
                                                className="sticky top-0 z-10 w-full flex items-center gap-2 px-3 py-1.5 border-b border-hairline bg-head-bg text-left"
                                                aria-expanded={!isCollapsed}
                                            >
                                                <span className={`text-ink-3 text-[10px] transition-transform ${isCollapsed ? '-rotate-90' : ''}`}>▼</span>
                                                <span
                                                    className={`font-bold uppercase ${danger ? 'text-red-600' : 'text-ink-2'}`}
                                                    style={{ fontSize: 12, letterSpacing: '.06em' }}
                                                >
                                                    {g.label}
                                                </span>
                                                <CountPill tone={danger ? 'accent' : 'neutral'}>{g.items.length}</CountPill>
                                            </button>

                                            {!isCollapsed && (
                                                <ul className="divide-y divide-hairline">
                                                    {g.items.map(it => {
                                                        const done = it.status === 'done';
                                                        const overdue = isOverdue(it);
                                                        const dueToday = it.due_date === today && !done;
                                                        const meta = typeMeta(it.item_type);
                                                        const jl = jobLabel(it);
                                                        const metaParts = [
                                                            !viewingSelf && it.owner_name ? it.owner_name : null,
                                                            it.meeting_title || null,
                                                            jl,
                                                        ].filter(Boolean);
                                                        const duePill = done
                                                            ? { background: 'var(--surface-2)', color: 'var(--text-3)', border: '1px solid var(--border)' }
                                                            : overdue
                                                                ? { background: 'var(--fl-red-bg)', color: 'var(--fl-red-fg)' }
                                                                : dueToday
                                                                    ? { background: 'var(--fl-amber-bg)', color: 'var(--fl-amber-fg)' }
                                                                    : { background: 'var(--surface-2)', color: 'var(--text-2)', border: '1px solid var(--border)' };
                                                        return (
                                                            <li
                                                                key={it.id}
                                                                className="flex items-start gap-2.5 px-3 py-2.5 transition-colors hover:bg-[var(--row-hover)]"
                                                            >
                                                                <input
                                                                    type="checkbox" checked={done} disabled={busy === it.id}
                                                                    onChange={() => toggleDone(it)}
                                                                    className="mt-[3px] h-4 w-4 shrink-0 accent-accent-500 cursor-pointer disabled:opacity-50"
                                                                    title={done ? 'Reopen' : 'Mark done'}
                                                                />
                                                                <div className="flex-1 min-w-0">
                                                                    <div
                                                                        className={done ? 'line-through text-ink-3' : 'text-ink'}
                                                                        style={{ fontSize: 13.5, lineHeight: 1.35, fontWeight: done ? 400 : 500 }}
                                                                    >
                                                                        {it.title}
                                                                    </div>
                                                                    {metaParts.length > 0 && (
                                                                        <div className="mt-0.5 text-ink-3 truncate" style={{ fontSize: 12 }}>
                                                                            {metaParts.join(' · ')}
                                                                        </div>
                                                                    )}
                                                                </div>
                                                                <div className="flex shrink-0 items-center gap-1.5 pt-[1px]">
                                                                    {it.item_type && (
                                                                        <span
                                                                            className="hidden sm:inline-block font-semibold whitespace-nowrap"
                                                                            style={{
                                                                                background: meta.bg, color: meta.fg,
                                                                                padding: '2px 8px', borderRadius: 6, fontSize: 11.5,
                                                                            }}
                                                                        >
                                                                            {meta.label}
                                                                        </span>
                                                                    )}
                                                                    {it.due_date && (
                                                                        <span
                                                                            className="whitespace-nowrap font-semibold tabular-nums"
                                                                            style={{ ...duePill, padding: '2px 8px', borderRadius: 999, fontSize: 11.5 }}
                                                                        >
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
                                })
                            )}
                        </div>
                    </section>

                    {/* ── Right: mentions ────────────────────────────────────────── */}
                    <aside className={`${PANEL_CLS} max-h-[70vh] lg:max-h-none`} aria-label="Mentions">
                        <div className={`${PANEL_HEAD_CLS} flex items-center gap-2`} style={{ padding: '10px 12px' }}>
                            <h2 className="text-ink" style={{ fontWeight: 700, fontSize: 15 }}>Mentions</h2>
                            {mentionsUnread > 0 && (
                                <CountPill
                                    tone="accent"
                                    title={viewingSelf ? 'Unread' : `Unread ${scopeSuffix}`}
                                >
                                    {mentionsUnread}
                                </CountPill>
                            )}
                            {/* Who did the mentioning. Options are the authors present in the
                                loaded page, so this narrows what you can see, never hides a
                                mentioner who has rows further down the feed. */}
                            {mentionerOptions.length > 1 && (
                                <Dropdown
                                    menuWidth={190}
                                    label={mentioner === ANY_MENTIONER ? 'Anyone' : mentioner}
                                    active={mentioner !== ANY_MENTIONER}
                                    buttonClassName={triggerCls(mentioner !== ANY_MENTIONER)}
                                >
                                    <DropdownItem onClick={() => setMentioner(ANY_MENTIONER)} active={mentioner === ANY_MENTIONER}>
                                        Anyone
                                    </DropdownItem>
                                    {mentionerOptions.map(name => (
                                        <DropdownItem
                                            key={name}
                                            onClick={() => setMentioner(name)}
                                            active={mentioner === name}
                                            icon={<NameAvatar name={name} size={20} />}
                                        >
                                            {name}
                                        </DropdownItem>
                                    ))}
                                </Dropdown>
                            )}
                            <div className="flex-1" />
                            {/* Read state belongs to the recipient — only offer the sweep on your own. */}
                            {viewingSelf && mentionsUnread > 0 && (
                                <button
                                    onClick={markMentionsRead}
                                    className="text-xs font-semibold text-brand hover:opacity-80 whitespace-nowrap"
                                >
                                    Mark all read
                                </button>
                            )}
                        </div>

                        <div className="flex-1 min-h-0 overflow-y-auto divide-y divide-hairline">
                            {mentionsLoading ? (
                                <div className="p-10 text-center text-xs text-ink-3">Loading…</div>
                            ) : visibleMentions.length === 0 ? (
                                <div className="p-10 text-center text-xs text-ink-3">
                                    {mentioner !== ANY_MENTIONER ? (
                                        <>
                                            No mentions from {mentioner} here.
                                            <button
                                                onClick={() => setMentioner(ANY_MENTIONER)}
                                                className="ml-2 text-brand hover:underline font-semibold"
                                            >
                                                Show anyone
                                            </button>
                                        </>
                                    ) : (viewingSelf ? 'No one has @mentioned you yet.' : `No @mentions ${scopeSuffix}.`)}
                                </div>
                            ) : (
                                visibleMentions.map(n => {
                                    const src = mentionSource(n);
                                    return (
                                        <button
                                            key={n.id}
                                            type="button"
                                            onClick={() => openMention(n)}
                                            className={`w-full text-left px-3 py-2.5 flex items-start gap-2.5 transition-colors ${
                                                n.is_read ? 'hover:bg-[var(--row-hover)]' : 'bg-brand-soft'
                                            }`}
                                        >
                                            <NameAvatar name={n.author_name} />
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-1.5">
                                                    <span
                                                        className="text-ink truncate"
                                                        style={{ fontSize: 13, fontWeight: n.is_read ? 500 : 700 }}
                                                    >
                                                        {mentionHeadline(n)}
                                                    </span>
                                                    {!n.is_read && (
                                                        <span
                                                            className="shrink-0 rounded-full"
                                                            style={{ width: 7, height: 7, background: 'var(--accent)' }}
                                                            aria-label="Unread"
                                                        />
                                                    )}
                                                </div>
                                                {n.excerpt && (
                                                    <p
                                                        className="text-ink-2 mt-1"
                                                        style={{
                                                            fontSize: 12.5, lineHeight: 1.4,
                                                            borderLeft: '2px solid var(--border-strong)',
                                                            paddingLeft: 7,
                                                            display: '-webkit-box',
                                                            WebkitLineClamp: 3,
                                                            WebkitBoxOrient: 'vertical',
                                                            overflow: 'hidden',
                                                        }}
                                                    >
                                                        {n.excerpt}
                                                    </p>
                                                )}
                                                <div className="flex items-center gap-1.5 mt-1 min-w-0">
                                                    <span
                                                        className="shrink-0 font-semibold uppercase"
                                                        style={{
                                                            background: 'var(--surface-2)', color: 'var(--text-3)',
                                                            border: '1px solid var(--border)',
                                                            padding: '1px 6px', borderRadius: 999,
                                                            fontSize: 10, letterSpacing: '.05em',
                                                        }}
                                                    >
                                                        {src.label}
                                                    </span>
                                                    {/* Who was mentioned. Server sends this only off your own queue. */}
                                                    {n.owner_name && (
                                                        <span
                                                            className="shrink-0 font-semibold"
                                                            style={{
                                                                background: 'var(--accent-soft)', color: 'var(--accent)',
                                                                padding: '1px 6px', borderRadius: 999, fontSize: 10,
                                                            }}
                                                        >
                                                            → {n.owner_name}
                                                        </span>
                                                    )}
                                                    {src.context && (
                                                        <span className="text-ink-3 truncate" style={{ fontSize: 11.5 }} title={src.context}>
                                                            {src.context}
                                                        </span>
                                                    )}
                                                    <span className="text-ink-3 shrink-0 ml-auto" style={{ fontSize: 11 }}>
                                                        {timeAgo(n.created_at)}
                                                    </span>
                                                </div>
                                            </div>
                                        </button>
                                    );
                                })
                            )}
                        </div>
                    </aside>
                </div>
            </div>
        </div>
    );
}
