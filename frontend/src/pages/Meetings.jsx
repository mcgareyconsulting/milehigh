/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Admin page for the meeting → checklist → to-do/notify flow — paste a transcript, then curate
 *          the agent-proposed checklist (yes / no / edit owner + due date). Accepted items notify their owner.
 * exports:
 *   Meetings: Page component (admin-only).
 * imports_from: [react, ../utils/auth, ../services/meetingsApi]
 * imported_by: [App.jsx]
 * invariants:
 *   - Admin-only; non-admins see an access-denied message (matches Board).
 *   - Owner + due date are agent-proposed but the reviewer has final say before accepting.
 */
import { useState, useEffect, useCallback } from 'react';
import { checkAuth } from '../utils/auth';
import {
    createMeeting, fetchMeetings, fetchMeeting,
    reviewChecklistItem, fetchAssignableUsers, scanDue,
} from '../services/meetingsApi';

const MEETING_TYPES = [
    { value: 'internal_draft', label: 'Internal — Draft' },
    { value: 'internal_shop', label: 'Internal — Shop' },
    { value: 'gc_pm', label: 'GC / PM' },
    { value: 'other', label: 'Other' },
];
const MEETING_TYPE_LABEL = Object.fromEntries(MEETING_TYPES.map(t => [t.value, t.label]));

const ITEM_TYPES = [
    { value: 'action', label: 'Action', badge: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300' },
    { value: 'needs_gc_update', label: 'GC update', badge: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300' },
    { value: 'decision', label: 'Decision', badge: 'bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300' },
    { value: 'risk', label: 'Risk', badge: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300' },
    { value: 'fyi', label: 'FYI', badge: 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300' },
];
const ITEM_TYPE_BADGE = Object.fromEntries(ITEM_TYPES.map(t => [t.value, t]));

const draftFromItem = (it) => ({
    title: it.title || '',
    detail: it.detail || '',
    item_type: it.item_type || 'action',
    gc_facing: !!it.gc_facing,
    owner_user_id: String(it.owner_user_id ?? it.proposed_owner_user_id ?? ''),
    due_date: it.due_date ?? it.proposed_due_date ?? '',
});

// --- Self-contained demo (no backend / LLM / DB needed) --------------------
// A realistic post-meeting checklist so the HITL review can be shown live to a
// client. Review actions on a demo meeting mutate local state only.
const DEMO_USERS = [
    { id: 1, first_name: 'Bill', last_name: "O'Neill" },
    { id: 2, first_name: 'David', last_name: 'Servold' },
    { id: 3, first_name: 'Katie', last_name: 'Hearn' },
    { id: 4, first_name: 'Luis', last_name: 'Solano' },
    { id: 5, first_name: 'Gary', last_name: 'Almeida' },
    { id: 6, first_name: 'Dalton', last_name: 'Rauer' },
];

const DEMO_TRANSCRIPT = `Shop touch-base — Tuesday AM

Bill: Let's run the list. Stair 6 first — what happened with the treads?
Luis: They didn't fit on the install attempt, the landing connection was off. We need to refab the treads and get them back to site, I'm thinking Thursday.
Bill: Alright. Garrett's going to ask about Stair 5 again on our call.
Gary: Five's still in drafting — realistically four weeks out before it's released for fab. I'll get him the updated timeline today so we're straight with him.
David: On the loose lintels — those are galvanized, I need to confirm the lead time with Dencol before we promise a date.
Gary: Pergola precast is still on hold, we're waiting on Wildcat to stamp the anchor detail. That's blocking, somebody needs to chase it.
Luis: Area 2 relief angle is welded and through QC, it's basically ready to ship — just need to lock the delivery and install window.
David: Trash room decking is still in drafting, so there's no on-site date to give yet.
Bill: Good. Let's get the redo moving this morning.`;

const _addDays = (n) => {
    const d = new Date();
    d.setDate(d.getDate() + n);
    return d.toISOString().slice(0, 10);
};

function buildDemoMeeting() {
    const mk = (id, item_type, title, owner, days, conf, gc, detail = null) => ({
        id, status: 'proposed', item_type, title, detail, gc_facing: gc, confidence: conf,
        proposed_owner_user_id: owner, owner_user_id: null,
        proposed_due_date: days == null ? null : _addDays(days), due_date: null,
        release_id: null, submittal_id: null,
    });
    return {
        id: 'demo', demo: true, title: 'Shop touch-base (demo)',
        meeting_type: 'internal_shop', project_number: '480', item_count: 6,
        items: [
            mk('d1', 'action', "Stair #6 — treads didn't fit; refab and get back to site", 4, 2, 0.93, false,
                'Landing connection was off on the install attempt; redo treads.'),
            mk('d2', 'needs_gc_update', 'Send Garrett the revised Stair #5 timeline — still in drafting (~4 weeks out)', 5, 1, 0.88, true),
            mk('d3', 'action', 'Confirm galvanizing lead time on the loose lintels with Dencol', 2, 3, 0.76, false),
            mk('d4', 'risk', 'Precast pergola on hold pending Wildcat stamp / anchor approval — escalate', 5, 1, 0.81, true),
            mk('d5', 'action', 'Area 2 relief angle welded & through QC — coordinate ship + install window', 4, 4, 0.70, false),
            mk('d6', 'decision', 'Trash room decking stays in drafting — no on-site date until released', 2, null, 0.64, false),
        ],
    };
}

export default function Meetings() {
    const [isAdmin, setIsAdmin] = useState(false);
    const [loading, setLoading] = useState(true);
    const [meetings, setMeetings] = useState([]);
    const [selected, setSelected] = useState(null);   // meeting + items
    const [users, setUsers] = useState([]);
    const [drafts, setDrafts] = useState({});          // itemId -> draft
    const [form, setForm] = useState({ title: '', meeting_type: 'internal_shop', transcript: '' });
    const [submitting, setSubmitting] = useState(false);
    const [busyItem, setBusyItem] = useState(null);
    const [error, setError] = useState(null);
    const [scanMsg, setScanMsg] = useState(null);

    useEffect(() => {
        checkAuth().then(u => { setIsAdmin(u?.is_admin || false); setLoading(false); });
    }, []);

    const loadMeetings = useCallback(async () => {
        try { setMeetings(await fetchMeetings()); } catch { setError('Failed to load meetings'); }
    }, []);

    useEffect(() => {
        if (!isAdmin) return;
        loadMeetings();
        fetchAssignableUsers().then(setUsers).catch(() => {});
    }, [isAdmin, loadMeetings]);

    const seedDrafts = (meeting) => {
        const d = {};
        (meeting.items || []).forEach(it => { d[it.id] = draftFromItem(it); });
        setDrafts(d);
    };

    const openMeeting = async (id) => {
        setError(null);
        try {
            const m = await fetchMeeting(id);
            setSelected(m);
            seedDrafts(m);
        } catch { setError('Failed to load meeting'); }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!form.transcript.trim()) return;
        setSubmitting(true); setError(null);
        try {
            const m = await createMeeting(form);
            setSelected(m);
            seedDrafts(m);
            setMeetings(prev => [{ ...m }, ...prev]);
            setForm({ title: '', meeting_type: form.meeting_type, transcript: '' });
        } catch {
            setError('Failed to ingest meeting');
        } finally {
            setSubmitting(false);
        }
    };

    const loadDemo = () => {
        const m = buildDemoMeeting();
        setForm(f => ({ ...f, title: m.title, meeting_type: 'internal_shop', transcript: DEMO_TRANSCRIPT }));
        setSelected(m);
        seedDrafts(m);
        setError(null);
    };

    const setDraft = (itemId, patch) =>
        setDrafts(prev => ({ ...prev, [itemId]: { ...prev[itemId], ...patch } }));

    const replaceItem = (updated) =>
        setSelected(prev => prev && ({
            ...prev,
            items: prev.items.map(it => (it.id === updated.id ? updated : it)),
        }));

    const review = async (itemId, action) => {
        const d = drafts[itemId] || {};
        const fields = action === 'reject' ? undefined : {
            title: d.title,
            detail: d.detail || null,
            item_type: d.item_type,
            gc_facing: d.gc_facing,
            owner_user_id: d.owner_user_id ? Number(d.owner_user_id) : null,
            due_date: d.due_date || null,
        };
        // Demo meeting: mutate local state only — no backend round-trip.
        if (selected?.demo) {
            const cur = selected.items.find(i => i.id === itemId);
            const updated = action === 'reject' ? { ...cur, status: 'rejected' }
                : action === 'done' ? { ...cur, status: 'done' }
                    : { ...cur, status: 'accepted', ...fields };
            replaceItem(updated);
            return;
        }
        setBusyItem(itemId); setError(null);
        try {
            replaceItem(await reviewChecklistItem(itemId, { action, fields }));
        } catch {
            setError('Failed to update item');
        } finally {
            setBusyItem(null);
        }
    };

    const runScan = async () => {
        setScanMsg(null);
        try { setScanMsg(`Notified ${await scanDue()} owner(s).`); }
        catch { setScanMsg('Scan failed'); }
    };

    if (loading) return <div className="flex-1 flex items-center justify-center"><span className="text-gray-500 dark:text-slate-400">Loading…</span></div>;
    if (!isAdmin) return <div className="flex-1 flex items-center justify-center"><span className="text-gray-500 dark:text-slate-400">Admin access required.</span></div>;

    const items = selected?.items || [];
    const proposedCount = items.filter(i => i.status === 'proposed').length;
    const ownerOptions = selected?.demo ? DEMO_USERS : users;

    return (
        <div className="flex-1 p-4 md:p-6 max-w-[1400px] mx-auto w-full">
            <h1 className="text-xl font-bold text-gray-900 dark:text-slate-100 mb-4">Meetings &amp; Action Items</h1>
            {error && <div className="mb-3 px-3 py-2 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300 text-sm">{error}</div>}

            <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-5">
                {/* Left: ingest + recent */}
                <div className="space-y-5">
                    <form onSubmit={handleSubmit} className="rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4 space-y-3">
                        <div className="flex items-center justify-between">
                            <h2 className="text-sm font-semibold text-gray-800 dark:text-slate-200">Log a meeting</h2>
                            <button type="button" onClick={loadDemo}
                                className="text-[11px] px-2 py-1 rounded-md border border-accent-300 dark:border-accent-600 text-accent-600 dark:text-accent-300 hover:bg-accent-50 dark:hover:bg-accent-900/20">
                                Load demo
                            </button>
                        </div>
                        <input
                            type="text" placeholder="Title (e.g. Shop touch-base)"
                            value={form.title} onChange={e => setForm({ ...form, title: e.target.value })}
                            className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-gray-900 dark:text-slate-100"
                        />
                        <select
                            value={form.meeting_type} onChange={e => setForm({ ...form, meeting_type: e.target.value })}
                            className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-gray-900 dark:text-slate-100"
                        >
                            {MEETING_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                        </select>
                        <textarea
                            placeholder="Paste the meeting transcript…" rows={8}
                            value={form.transcript} onChange={e => setForm({ ...form, transcript: e.target.value })}
                            className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-gray-900 dark:text-slate-100 font-mono"
                        />
                        <button
                            type="submit" disabled={submitting || !form.transcript.trim()}
                            className="w-full px-3 py-2 text-sm font-medium rounded-lg bg-accent-500 hover:bg-accent-600 text-white disabled:opacity-50"
                        >
                            {submitting ? 'Extracting…' : 'Ingest & build checklist'}
                        </button>
                    </form>

                    <div className="rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4">
                        <div className="flex items-center justify-between mb-2">
                            <h2 className="text-sm font-semibold text-gray-800 dark:text-slate-200">Recent meetings</h2>
                            <button onClick={runScan} title="Send due-date notifications now"
                                className="text-[11px] px-2 py-1 rounded-md border border-gray-300 dark:border-slate-600 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700">
                                Scan due
                            </button>
                        </div>
                        {scanMsg && <p className="text-[11px] text-gray-500 dark:text-slate-400 mb-2">{scanMsg}</p>}
                        <ul className="space-y-1.5">
                            {meetings.length === 0 && <li className="text-xs text-gray-400 dark:text-slate-500">No meetings yet.</li>}
                            {meetings.map(m => (
                                <li key={m.id}>
                                    <button onClick={() => openMeeting(m.id)}
                                        className={`w-full text-left rounded-lg border p-2 transition-colors ${selected?.id === m.id
                                            ? 'border-accent-300 dark:border-accent-600 bg-accent-50 dark:bg-accent-900/20'
                                            : 'border-gray-200 dark:border-slate-700 hover:border-gray-300 dark:hover:border-slate-600'}`}>
                                        <div className="text-xs font-medium text-gray-900 dark:text-slate-100 truncate">{m.title}</div>
                                        <div className="text-[11px] text-gray-400 dark:text-slate-500">
                                            {MEETING_TYPE_LABEL[m.meeting_type] || m.meeting_type} · {m.item_count} item(s)
                                            {m.project_number ? ` · #${m.project_number}` : ''}
                                        </div>
                                    </button>
                                </li>
                            ))}
                        </ul>
                    </div>
                </div>

                {/* Right: checklist review */}
                <div className="rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4">
                    {!selected ? (
                        <div className="h-full flex items-center justify-center py-16 text-sm text-gray-400 dark:text-slate-500">
                            Ingest a meeting or pick one to review its checklist.
                        </div>
                    ) : (
                        <>
                            <div className="flex items-center justify-between mb-3">
                                <h2 className="text-sm font-semibold text-gray-800 dark:text-slate-200">
                                    {selected.title}
                                    {selected.demo && <span className="ml-2 px-1.5 py-0.5 text-[10px] font-semibold rounded bg-accent-100 text-accent-700 dark:bg-accent-900/40 dark:text-accent-300">DEMO</span>}
                                    <span className="ml-2 text-xs font-normal text-gray-400 dark:text-slate-500">
                                        {proposedCount} to review · {items.length} total
                                    </span>
                                </h2>
                            </div>
                            {items.length === 0 && <p className="text-sm text-gray-400 dark:text-slate-500">No action items were surfaced.</p>}
                            <ul className="space-y-2.5">
                                {items.map(it => (
                                    <ChecklistRow
                                        key={it.id} item={it} users={ownerOptions}
                                        draft={drafts[it.id] || draftFromItem(it)}
                                        busy={busyItem === it.id}
                                        onDraft={(patch) => setDraft(it.id, patch)}
                                        onAccept={() => review(it.id, 'accept')}
                                        onReject={() => review(it.id, 'reject')}
                                        onDone={() => review(it.id, 'done')}
                                    />
                                ))}
                            </ul>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}

function ChecklistRow({ item, users, draft, busy, onDraft, onAccept, onReject, onDone }) {
    const isProposed = item.status === 'proposed';
    const badge = ITEM_TYPE_BADGE[item.item_type] || ITEM_TYPE_BADGE.action;
    const ownerName = users.find(u => String(u.id) === String(item.owner_user_id));
    const STATUS_PILL = {
        accepted: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
        rejected: 'bg-gray-200 text-gray-500 dark:bg-slate-700 dark:text-slate-400',
        done: 'bg-slate-200 text-slate-600 dark:bg-slate-600 dark:text-slate-200',
        proposed: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300',
    };

    return (
        <li className={`rounded-lg border p-3 ${item.status === 'rejected' ? 'opacity-60' : ''}
            border-gray-200 dark:border-slate-700 bg-gray-50/40 dark:bg-slate-900/40`}>
            <div className="flex items-center gap-2 mb-1.5">
                <span className={`px-1.5 py-0.5 text-[10px] font-medium rounded ${badge.badge}`}>{badge.label}</span>
                {item.gc_facing && <span className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">GC-facing</span>}
                {item.confidence != null && <span className="text-[10px] text-gray-400 dark:text-slate-500">conf {Math.round(item.confidence * 100)}%</span>}
                <span className={`ml-auto px-1.5 py-0.5 text-[10px] font-medium rounded capitalize ${STATUS_PILL[item.status]}`}>{item.status}</span>
            </div>

            {isProposed ? (
                <>
                    <input
                        type="text" value={draft.title} onChange={e => onDraft({ title: e.target.value })}
                        className="w-full px-2 py-1.5 text-sm rounded-md border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-gray-900 dark:text-slate-100 mb-2"
                    />
                    <div className="flex flex-wrap items-center gap-2">
                        <select value={draft.item_type} onChange={e => onDraft({ item_type: e.target.value })}
                            className="px-2 py-1 text-xs rounded-md border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-gray-700 dark:text-slate-200">
                            {ITEM_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                        </select>
                        <select value={draft.owner_user_id} onChange={e => onDraft({ owner_user_id: e.target.value })}
                            className="px-2 py-1 text-xs rounded-md border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-gray-700 dark:text-slate-200">
                            <option value="">— owner —</option>
                            {users.map(u => <option key={u.id} value={u.id}>{u.first_name} {u.last_name}</option>)}
                        </select>
                        <input type="date" value={draft.due_date || ''} onChange={e => onDraft({ due_date: e.target.value })}
                            className="px-2 py-1 text-xs rounded-md border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-gray-700 dark:text-slate-200" />
                        <label className="flex items-center gap-1 text-xs text-gray-600 dark:text-slate-300">
                            <input type="checkbox" checked={draft.gc_facing} onChange={e => onDraft({ gc_facing: e.target.checked })} /> GC
                        </label>
                        <div className="ml-auto flex gap-1.5">
                            <button onClick={onReject} disabled={busy}
                                className="px-2.5 py-1 text-xs rounded-md border border-gray-300 dark:border-slate-600 text-gray-600 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-700 disabled:opacity-50">No</button>
                            <button onClick={onAccept} disabled={busy}
                                className="px-2.5 py-1 text-xs font-medium rounded-md bg-emerald-500 hover:bg-emerald-600 text-white disabled:opacity-50">Yes</button>
                        </div>
                    </div>
                </>
            ) : (
                <div className="flex items-center gap-2">
                    <span className={`text-sm text-gray-800 dark:text-slate-200 ${item.status === 'done' ? 'line-through' : ''}`}>{item.title}</span>
                    <span className="ml-auto text-[11px] text-gray-500 dark:text-slate-400">
                        {ownerName ? `${ownerName.first_name} ${ownerName.last_name}` : 'unassigned'}{item.due_date ? ` · due ${item.due_date}` : ''}
                    </span>
                    {item.status === 'accepted' && ownerName && item.due_date && (
                        <span className="text-[11px] text-emerald-600 dark:text-emerald-400 whitespace-nowrap">🔔 reminder set</span>
                    )}
                    {item.status === 'accepted' && (
                        <button onClick={onDone} disabled={busy}
                            className="px-2 py-0.5 text-[11px] rounded-md border border-gray-300 dark:border-slate-600 text-gray-600 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-700 disabled:opacity-50">Done</button>
                    )}
                </div>
            )}
        </li>
    );
}
