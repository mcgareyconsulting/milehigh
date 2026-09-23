/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The subcontractor's To-Dos tab — a phone-portrait page with two segments: the to-dos
 *          assigned to this account (grouped by due urgency, tap the check to mark done, "Done"
 *          toggle to see finished ones) and the @mentions / to-do pings addressed to it (unread
 *          first; tapping marks read and opens the release it points at when there is one).
 * exports:
 *   SubcontractorTodos: Page component, rendered inside SubcontractorShell's Outlet.
 * imports_from: [react, react-router-dom, ../services/subPortalApi, ../components/sub/SubReleaseSheet]
 * imported_by: [App.jsx]
 * invariants:
 *   - Everything shown is server-scoped to this account (owner_subcontractor_id / subcontractor_id);
 *     the page never passes an owner and never sees another sub's rows.
 *   - Marking read refreshes the shell badge through the outlet context so the tab count is honest.
 *   - Due buckets mirror the staff To-Dos page (Overdue / Today / This week / Later / No date) so a
 *     PM and a sub talking about "this week" mean the same thing.
 *   - The segment is in the URL (?seg=mentions) so the account sheet's Notifications row and a
 *     tapped push can land directly on Mentions.
 *   - RED badges mean unread: the To-Dos segment badge is the count of to-dos whose assignment /
 *     deadline ping is unread, the Mentions badge the unread mentions. Showing the To-Dos segment
 *     clears the to-do pings (the list itself is the read receipt); a mention clears when tapped
 *     or via Mark all read. With nothing unread the To-Dos badge falls back to the open count in
 *     the neutral colour.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useOutletContext, useSearchParams } from 'react-router-dom';
import SubReleaseSheet from '../components/sub/SubReleaseSheet';
import SubEmpty from '../components/sub/SubEmpty';
import {
    listSubTodos, setSubTodoStatus, listSubNotifications, markSubNotificationRead, markAllSubRead,
    TODO_NOTIFICATION_TYPES, MENTION_NOTIFICATION_TYPES,
} from '../services/subPortalApi';

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
    return isNaN(d) ? iso : d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
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

const BUCKETS = [
    { key: 'overdue', label: 'Overdue', tone: 'text-red-700 dark:text-red-300' },
    { key: 'today', label: 'Due today', tone: 'text-brand' },
    { key: 'week', label: 'This week', tone: 'text-ink-2' },
    { key: 'later', label: 'Later', tone: 'text-ink-3' },
    { key: 'nodate', label: 'No date', tone: 'text-ink-3' },
    { key: 'done', label: 'Done', tone: 'text-ink-3' },
];
function bucketOf(t, today) {
    if (t.status === 'done') return 'done';
    if (!t.due_date) return 'nodate';
    if (t.due_date < today) return 'overdue';
    if (t.due_date === today) return 'today';
    if (t.due_date <= addDays(today, 7)) return 'week';
    return 'later';
}

const ITEM_TYPE_LABEL = { action: 'Action', needs_gc_update: 'GC update', decision: 'Decision', risk: 'Risk', fyi: 'FYI' };

function TodoCard({ t, busy, onToggle, onOpenRelease }) {
    const done = t.status === 'done';
    return (
        <div className={`sub-card flex items-start gap-3 p-4 ${done ? 'opacity-70' : ''}`}>
            <button
                type="button"
                aria-label={done ? 'Reopen' : 'Mark done'}
                disabled={busy}
                onClick={() => onToggle(t)}
                className={`mt-0.5 w-6 h-6 shrink-0 rounded-full border-2 flex items-center justify-center ${
                    done ? 'bg-brand border-brand text-white' : 'border-hairline-strong text-transparent'
                } disabled:opacity-50`}
            >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20 6L9 17l-5-5" /></svg>
            </button>
            <div className="min-w-0 flex-1">
                <div className={`text-[15px] font-bold break-words ${done ? 'line-through text-ink-3' : 'text-ink'}`}>{t.title}</div>
                {t.detail && <div className="mt-0.5 text-xs text-ink-2 break-words">{t.detail}</div>}
                <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-ink-3">
                    {t.due_date && <span>due {fmtDue(t.due_date)}</span>}
                    {t.item_type && t.item_type !== 'action' && <span className="sub-pill">{ITEM_TYPE_LABEL[t.item_type] || t.item_type}</span>}
                    {t.release_id && (
                        <button type="button" onClick={() => onOpenRelease(t.release_id)}
                            className="font-mono font-bold text-brand">
                            {t.release_code}
                        </button>
                    )}
                    {t.release_job_name && <span className="truncate max-w-[12rem]">{t.release_job_name}</span>}
                </div>
            </div>
        </div>
    );
}

function MentionCard({ n, onTap }) {
    return (
        <button type="button" onClick={() => onTap(n)}
            className={`sub-card w-full text-left p-4 ${n.is_read ? '' : 'border-l-4 border-brand'}`}>
            <div className="flex items-start justify-between gap-2">
                <span className={`text-[15px] break-words ${n.is_read ? 'text-ink-2' : 'text-ink font-bold'}`}>{n.message}</span>
                {!n.is_read && <span className="mt-1.5 w-2.5 h-2.5 rounded-full bg-brand shrink-0" aria-label="Unread" />}
            </div>
            {n.excerpt && <p className="mt-1 text-xs text-ink-2 line-clamp-3 break-words">“{n.excerpt}”</p>}
            <div className="mt-1.5 flex flex-wrap items-center gap-x-2 text-[11px] text-ink-3">
                <span>{timeAgo(n.created_at)}</span>
                {n.release_code && <span className="font-mono font-bold text-brand">{n.release_code}</span>}
                {n.release_issue_display_id && <span>issue {n.release_issue_display_id}</span>}
                {n.drawing_version_number && <span>drawing v{n.drawing_version_number}</span>}
            </div>
        </button>
    );
}

export default function SubcontractorTodos() {
    const { refreshUnread, unread } = useOutletContext();
    const [params, setParams] = useSearchParams();
    const segment = params.get('seg') === 'mentions' ? 'mentions' : 'todos';
    const setSegment = (k) => setParams(k === 'mentions' ? { seg: 'mentions' } : {}, { replace: true });
    const [todos, setTodos] = useState([]);
    const [showDone, setShowDone] = useState(false);
    const [notifs, setNotifs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [busyId, setBusyId] = useState(null);
    const [openId, setOpenId] = useState(null);

    const load = useCallback(async (silent = false) => {
        if (!silent) setLoading(true);
        setError(null);
        try {
            const [t, n] = await Promise.all([listSubTodos('all'), listSubNotifications(50)]);
            setTodos(t);
            setNotifs(n.notifications);
        } catch (e) {
            setError(e?.response?.data?.error || e.message || 'Failed to load');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { load(); }, [load]);
    useEffect(() => {
        const onVis = () => { if (document.visibilityState === 'visible') load(true); };
        document.addEventListener('visibilitychange', onVis);
        return () => document.removeEventListener('visibilitychange', onVis);
    }, [load]);

    const today = todayDenver();
    const grouped = useMemo(() => {
        const g = Object.fromEntries(BUCKETS.map((b) => [b.key, []]));
        todos.forEach((t) => g[bucketOf(t, today)].push(t));
        return g;
    }, [todos, today]);
    const openCount = todos.filter((t) => t.status !== 'done').length;
    const unreadMentions = notifs.filter((n) => !n.is_read && MENTION_NOTIFICATION_TYPES.includes(n.type)).length;
    const unreadTodos = unread?.unread_todos || 0;
    const mentionRows = notifs.filter((n) => MENTION_NOTIFICATION_TYPES.includes(n.type));

    // Viewing the To-Dos list is the read receipt for to-do pings: clear them once shown.
    useEffect(() => {
        if (loading || segment !== 'todos' || unreadTodos === 0) return;
        markAllSubRead({ types: TODO_NOTIFICATION_TYPES }).then(refreshUnread).catch(() => {});
    }, [loading, segment, unreadTodos, refreshUnread]);

    const toggle = async (t) => {
        const next = t.status === 'done' ? 'accepted' : 'done';
        setBusyId(t.id);
        setTodos((prev) => prev.map((x) => (x.id === t.id ? { ...x, status: next } : x)));
        try {
            const saved = await setSubTodoStatus(t.id, next);
            setTodos((prev) => prev.map((x) => (x.id === t.id ? saved : x)));
        } catch {
            setTodos((prev) => prev.map((x) => (x.id === t.id ? t : x)));
            setError('Could not update that to-do');
        } finally {
            setBusyId(null);
        }
    };

    const tapMention = async (n) => {
        if (!n.is_read) {
            setNotifs((prev) => prev.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)));
            markSubNotificationRead(n.id).then(refreshUnread).catch(() => {});
        }
        if (n.release_id) setOpenId(n.release_id);
    };

    const readAll = async () => {
        setNotifs((prev) => prev.map((x) => (MENTION_NOTIFICATION_TYPES.includes(x.type) ? { ...x, is_read: true } : x)));
        try { await markAllSubRead({ types: MENTION_NOTIFICATION_TYPES }); } finally { refreshUnread(); }
    };

    return (
        <div className="flex-1 min-h-0 flex flex-col">
            <div className="sub-seg" role="tablist" aria-label="To-Dos or Mentions">
                <button type="button" role="tab" aria-selected={segment === 'todos'} className={segment === 'todos' ? 'active' : ''} onClick={() => setSegment('todos')}>
                    To-Dos
                    {unreadTodos > 0
                        ? <span className="sub-badge alert" aria-label={`${unreadTodos} new`}>{unreadTodos}</span>
                        : openCount > 0 && <span className="sub-badge">{openCount}</span>}
                </button>
                <button type="button" role="tab" aria-selected={segment === 'mentions'} className={segment === 'mentions' ? 'active' : ''} onClick={() => setSegment('mentions')}>
                    Mentions{unreadMentions > 0 && <span className="sub-badge alert" aria-label={`${unreadMentions} unread`}>{unreadMentions}</span>}
                </button>
            </div>

            {loading && <div className="text-ink-3 text-sm px-4 py-3">Loading…</div>}
            {error && <div className="text-red-600 text-sm px-4 py-3">{error}</div>}

            {!loading && segment === 'todos' && (
                <div className="flex-1 min-h-0 flex flex-col gap-1 px-4 pb-4">
                    {openCount === 0 && grouped.done.length === 0 && (
                        <SubEmpty icon="check" title="No to-dos yet" body="When MHMW assigns you something, it shows up here." />
                    )}
                    {openCount === 0 && grouped.done.length > 0 && (
                        <SubEmpty icon="check" title="All caught up" body="Nothing open. Finished items are below." />
                    )}
                    {BUCKETS.filter((b) => b.key !== 'done').map((b) => grouped[b.key].length > 0 && (
                        <section key={b.key}>
                            <h2 className={`sticky top-0 z-10 bg-canvas/95 backdrop-blur px-1 py-1.5 text-xs font-extrabold uppercase tracking-wide ${b.tone}`}>
                                {b.label} · {grouped[b.key].length}
                            </h2>
                            <div className="flex flex-col gap-2.5 pt-2 pb-3">
                                {grouped[b.key].map((t) => (
                                    <TodoCard key={t.id} t={t} busy={busyId === t.id} onToggle={toggle} onOpenRelease={setOpenId} />
                                ))}
                            </div>
                        </section>
                    ))}
                    {grouped.done.length > 0 && (
                        <section>
                            <button type="button" onClick={() => setShowDone((v) => !v)}
                                className="w-full flex items-center justify-between px-1 py-1.5 text-xs font-extrabold uppercase tracking-wide text-ink-3">
                                <span>Done · {grouped.done.length}</span>
                                <span aria-hidden="true">{showDone ? '▾' : '▸'}</span>
                            </button>
                            {showDone && (
                                <div className="flex flex-col gap-2 pt-1 pb-3">
                                    {grouped.done.map((t) => (
                                        <TodoCard key={t.id} t={t} busy={busyId === t.id} onToggle={toggle} onOpenRelease={setOpenId} />
                                    ))}
                                </div>
                            )}
                        </section>
                    )}
                </div>
            )}

            {!loading && segment === 'mentions' && (
                <div className="flex-1 min-h-0 flex flex-col gap-2.5 px-4 pb-4 pt-2">
                    {unreadMentions > 0 && (
                        <button type="button" onClick={readAll} className="self-end px-2 py-1 text-[13px] font-bold text-brand">
                            Mark all read
                        </button>
                    )}
                    {mentionRows.length === 0 && (
                        <SubEmpty icon="bell" title="No mentions yet" body="When someone at MHMW @mentions you, it lands here." />
                    )}
                    {mentionRows.map((n) => <MentionCard key={n.id} n={n} onTap={tapMention} />)}
                </div>
            )}

            <SubReleaseSheet releaseId={openId} onClose={() => setOpenId(null)} todos={todos} />
        </div>
    );
}
