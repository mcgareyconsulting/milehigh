/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Admin page for the meeting → to-do flow. Center lists recent meetings; opening one shows its
 *          transcript with a "Generate to-do list" button that builds a reviewable checklist (yes/no/edit
 *          owner + due). "Send Bot" (a button + modal) dispatches a Recall notetaker to a meeting link;
 *          "Paste transcript" creates a meeting from raw text (the bot-couldn't-join fallback).
 * exports:
 *   Meetings: Page component (admin-only).
 * imports_from: [react, ../utils/auth, ../services/meetingsApi]
 * imported_by: [App.jsx]
 * invariants:
 *   - Admin-only; non-admins see an access-denied message (matches Board).
 *   - Owner + due date are agent-proposed but the reviewer has final say before accepting.
 *   - Recall meetings carry a live bot_status; the list polls while any bot is mid-flight.
 */
import { useState, useEffect, useCallback } from 'react';
import { checkAuth } from '../utils/auth';
import {
    fetchMeetings, fetchMeeting, generateChecklist,
    reviewChecklistItem, fetchAssignableUsers, scanDue, sendBot, createManualMeeting,
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

// Recall bot lifecycle → display. Terminal states stop the status polling.
const BOT_TERMINAL = ['done', 'call_ended', 'fatal', 'failed', 'media_expired', 'recording_denied'];
const isLiveBot = (s) => !!s && !BOT_TERMINAL.includes(s);
const BOT_STATUS_PILL = {
    scheduled: 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300',
    joining: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
    in_waiting_room: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
    in_call_not_recording: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
    in_call_recording: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
    recording_denied: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
    transcribing: 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300',
    call_ended: 'bg-slate-200 text-slate-600 dark:bg-slate-600 dark:text-slate-200',
    done: 'bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300',
    fatal: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
    failed: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
};
const botStatusLabel = (s) => (s || 'unknown').replace(/_/g, ' ');
// Mile High is a Denver shop; show all times in Denver regardless of the viewer.
const COMPANY_TZ = 'America/Denver';
const formatWhen = (iso) => {
    if (!iso) return '';
    // Backend timestamps are naive UTC (no offset) — append 'Z' so they parse as UTC
    // rather than the browser's local zone, then render in the company's timezone.
    const s = /([zZ]|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`;
    const d = new Date(s);
    return isNaN(d) ? '' : d.toLocaleString('en-US', {
        timeZone: COMPANY_TZ,
        month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
    });
};
const formatCost = (c) => (c == null ? '' : c < 0.01 ? `$${c.toFixed(4)}` : `$${c.toFixed(2)}`);

const draftFromItem = (it) => ({
    title: it.title || '',
    detail: it.detail || '',
    item_type: it.item_type || 'action',
    gc_facing: !!it.gc_facing,
    owner_user_id: String(it.owner_user_id ?? it.proposed_owner_user_id ?? ''),
    due_date: it.due_date ?? it.proposed_due_date ?? '',
});

export default function Meetings() {
    const [isAdmin, setIsAdmin] = useState(false);
    const [loading, setLoading] = useState(true);
    const [meetings, setMeetings] = useState([]);
    const [selected, setSelected] = useState(null);   // open meeting (+ items + transcript)
    const [users, setUsers] = useState([]);
    const [drafts, setDrafts] = useState({});          // itemId -> draft
    const [busyItem, setBusyItem] = useState(null);
    const [error, setError] = useState(null);
    const [scanMsg, setScanMsg] = useState(null);
    const [showSendBot, setShowSendBot] = useState(false);
    const [botUrl, setBotUrl] = useState('');
    const [botName, setBotName] = useState('');
    const [botBusy, setBotBusy] = useState(false);
    const [generating, setGenerating] = useState(false);
    const [showPaste, setShowPaste] = useState(false);
    const [pasteTitle, setPasteTitle] = useState('');
    const [pasteType, setPasteType] = useState('internal_shop');
    const [pasteText, setPasteText] = useState('');
    const [pasteBusy, setPasteBusy] = useState(false);

    const seedDrafts = (meeting) => {
        const d = {};
        (meeting?.items || []).forEach(it => { d[it.id] = draftFromItem(it); });
        setDrafts(d);
    };

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

    const openMeeting = async (id) => {
        setError(null);
        try {
            const m = await fetchMeeting(id);
            setSelected(m); seedDrafts(m);
        } catch { setError('Failed to load meeting'); }
    };

    const handleSendBot = async (e) => {
        e.preventDefault();
        // Pull the real link out of the field — tolerant of a pasted "label: <url>"
        // prefix or stray whitespace that would otherwise reach Recall verbatim.
        const raw = botUrl.trim();
        const url = (raw.match(/https?:\/\/\S+/) || [raw])[0];
        if (!url) return;
        // Name: explicit field wins; else best-effort from the pasted blob's leading text.
        const pasted = raw.replace(/https?:\/\/\S+/g, '').replace(/[\s:–-]+$/g, '').trim();
        const title = botName.trim() || pasted.split('\n')[0].slice(0, 120) || undefined;
        setBotBusy(true); setError(null);
        try {
            const meeting = await sendBot({ meeting_url: url, title });
            setMeetings(prev => [meeting, ...prev.filter(m => m.id !== meeting.id)]);
            setSelected(meeting); seedDrafts(meeting);
            setBotUrl(''); setBotName(''); setShowSendBot(false);
        } catch (err) {
            setError(err?.response?.data?.error || 'Failed to send bot');
        } finally {
            setBotBusy(false);
        }
    };

    const handleGenerate = async () => {
        if (!selected) return;
        setGenerating(true); setError(null);
        try {
            const updated = await generateChecklist(selected.id);
            setSelected(updated); seedDrafts(updated);
            setMeetings(prev => prev.map(m => (m.id === updated.id ? { ...m, item_count: updated.item_count } : m)));
        } catch (err) {
            setError(err?.response?.data?.error || 'Failed to generate to-do list');
        } finally {
            setGenerating(false);
        }
    };

    const handleCreateManual = async (e) => {
        e.preventDefault();
        const transcript = pasteText.trim();
        if (!transcript) return;
        setPasteBusy(true); setError(null);
        try {
            const meeting = await createManualMeeting({
                title: pasteTitle.trim() || undefined, meeting_type: pasteType, transcript,
            });
            setMeetings(prev => [meeting, ...prev.filter(m => m.id !== meeting.id)]);
            setSelected(meeting); seedDrafts(meeting);
            setPasteTitle(''); setPasteText(''); setShowPaste(false);
        } catch (err) {
            setError(err?.response?.data?.error || 'Failed to create meeting');
        } finally {
            setPasteBusy(false);
        }
    };

    // While any recall bot is mid-flight, poll the list so statuses update live.
    useEffect(() => {
        if (!isAdmin) return;
        if (!meetings.some(m => m.source === 'recall' && isLiveBot(m.bot_status))) return;
        const t = setInterval(loadMeetings, 8000);
        return () => clearInterval(t);
    }, [isAdmin, meetings, loadMeetings]);

    // Mirror the polled bot_status onto the open meeting; when the bot finishes,
    // re-fetch the detail so its freshly-pulled transcript shows.
    useEffect(() => {
        if (!selected || selected.source !== 'recall') return;
        const fresh = meetings.find(m => m.id === selected.id);
        if (!fresh || fresh.bot_status === selected.bot_status) return;
        setSelected(s => ({ ...s, bot_status: fresh.bot_status }));
        if (fresh.bot_status === 'done' && !selected.transcript) {
            fetchMeeting(selected.id).then(setSelected).catch(() => {});
        }
    }, [meetings, selected]);

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
    const ownerOptions = users;
    const transcriptText = selected?.transcript ?? '';
    const hasTranscript = !!transcriptText.trim();
    const canGenerate = !!transcriptText.trim();

    return (
        <div className="flex-1 p-4 md:p-6 max-w-[1400px] mx-auto w-full">
            {/* Header */}
            <div className="flex items-center justify-between gap-3 mb-4">
                <h1 className="text-xl font-bold text-gray-900 dark:text-slate-100">Meetings &amp; Action Items</h1>
                <div className="flex items-center gap-2">
                    <button onClick={runScan} title="Send due-date notifications now"
                        className="text-[11px] px-2 py-1.5 rounded-md border border-gray-300 dark:border-slate-600 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700">
                        Scan due
                    </button>
                    <button onClick={() => { setError(null); setShowPaste(true); }}
                        className="px-3 py-1.5 text-sm font-medium rounded-lg border border-accent-300 dark:border-accent-600 text-accent-600 dark:text-accent-300 hover:bg-accent-50 dark:hover:bg-accent-900/20">
                        Paste transcript
                    </button>
                    <button onClick={() => { setError(null); setShowSendBot(true); }}
                        className="px-3 py-1.5 text-sm font-medium rounded-lg bg-accent-500 hover:bg-accent-600 text-white">
                        + Send Bot
                    </button>
                </div>
            </div>
            {scanMsg && <p className="text-[11px] text-gray-500 dark:text-slate-400 mb-2">{scanMsg}</p>}
            {error && !showSendBot && !showPaste && <div className="mb-3 px-3 py-2 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300 text-sm">{error}</div>}

            {/* Body: recent-meetings list (nothing open) or the opened meeting detail */}
            {!selected ? (
                <MeetingsList meetings={meetings} onOpen={openMeeting} />
            ) : (
                <div className="space-y-3">
                    <button onClick={() => setSelected(null)}
                        className="text-xs text-accent-600 dark:text-accent-300 hover:underline">← All meetings</button>
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                        {/* Transcript pane */}
                        <div className="rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4">
                            <div className="flex items-start justify-between gap-2 mb-2">
                                <h2 className="text-sm font-semibold text-gray-800 dark:text-slate-200">{selected.title}</h2>
                                {selected.source === 'recall' && selected.bot_status && (
                                    <span className={`shrink-0 px-1.5 py-0.5 text-[10px] font-semibold rounded capitalize ${BOT_STATUS_PILL[selected.bot_status] || 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300'} ${isLiveBot(selected.bot_status) ? 'animate-pulse' : ''}`}>
                                        {botStatusLabel(selected.bot_status)}
                                    </span>
                                )}
                            </div>
                            <div className="text-[11px] text-gray-400 dark:text-slate-500 mb-3 space-y-0.5">
                                {selected.occurred_at && <div>{selected.source === 'recall' ? '🤖 ' : ''}{formatWhen(selected.occurred_at)}</div>}
                                {selected.meeting_url && (
                                    <div className="truncate">
                                        <a href={selected.meeting_url} target="_blank" rel="noreferrer" className="text-accent-600 dark:text-accent-300 hover:underline">{selected.meeting_url}</a>
                                    </div>
                                )}
                            </div>
                            <h3 className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-slate-500 mb-1">Transcript</h3>
                            {hasTranscript ? (
                                <div className="whitespace-pre-wrap text-xs text-gray-700 dark:text-slate-300 max-h-[55vh] overflow-auto rounded-lg bg-gray-50 dark:bg-slate-900/50 p-3 border border-gray-100 dark:border-slate-700">
                                    {transcriptText}
                                </div>
                            ) : (
                                <p className="text-sm text-gray-400 dark:text-slate-500 py-6 text-center">
                                    {isLiveBot(selected.bot_status)
                                        ? 'Bot is in the meeting — the transcript will appear here once it finishes.'
                                        : 'No transcript yet.'}
                                </p>
                            )}
                        </div>

                        {/* To-do pane */}
                        <div className="rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4">
                            <div className="flex items-center justify-between gap-2 mb-3">
                                <h2 className="text-sm font-semibold text-gray-800 dark:text-slate-200">
                                    To-do list
                                    {items.length > 0 && (
                                        <span className="ml-2 text-xs font-normal text-gray-400 dark:text-slate-500">{proposedCount} to review · {items.length} total</span>
                                    )}
                                </h2>
                                {items.length > 0 && (
                                    <button onClick={handleGenerate} disabled={generating || !canGenerate}
                                        className="text-[11px] px-2 py-1 rounded-md border border-gray-300 dark:border-slate-600 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700 disabled:opacity-50">
                                        {generating ? 'Regenerating…' : 'Regenerate'}
                                    </button>
                                )}
                            </div>
                            {selected.extract_model && (
                                <p className="text-[11px] text-gray-400 dark:text-slate-500 mb-2">
                                    {selected.extract_model === 'stub'
                                        ? '⚠ keyword stub (no API key/credits) · $0'
                                        : `${selected.extract_model} · ${(selected.extract_input_tokens || 0).toLocaleString()} in + ${(selected.extract_output_tokens || 0).toLocaleString()} out tok · ${formatCost(selected.extract_cost_usd)}`}
                                </p>
                            )}
                            {items.length > 0 ? (
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
                            ) : (
                                <div className="py-10 text-center">
                                    {canGenerate ? (
                                        <>
                                            <p className="text-sm text-gray-500 dark:text-slate-400 mb-3">No to-dos yet — generate them from the transcript.</p>
                                            <button onClick={handleGenerate} disabled={generating}
                                                className="px-4 py-2 text-sm font-medium rounded-lg bg-accent-500 hover:bg-accent-600 text-white disabled:opacity-50">
                                                {generating ? 'Generating…' : 'Generate to-do list'}
                                            </button>
                                        </>
                                    ) : (
                                        <p className="text-sm text-gray-400 dark:text-slate-500">
                                            {isLiveBot(selected.bot_status)
                                                ? 'Waiting for the transcript — the to-do list can be generated once the meeting ends.'
                                                : 'No transcript available to generate a to-do list.'}
                                        </p>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {showSendBot && (
                <SendBotModal
                    url={botUrl} name={botName} busy={botBusy} error={error}
                    onUrl={setBotUrl} onName={setBotName}
                    onSubmit={handleSendBot} onClose={() => setShowSendBot(false)}
                />
            )}
            {showPaste && (
                <PasteTranscriptModal
                    title={pasteTitle} type={pasteType} text={pasteText} busy={pasteBusy} error={error}
                    onTitle={setPasteTitle} onType={setPasteType} onText={setPasteText}
                    onSubmit={handleCreateManual} onClose={() => setShowPaste(false)}
                />
            )}
        </div>
    );
}

function MeetingsList({ meetings, onOpen }) {
    if (!meetings.length) {
        return (
            <div className="rounded-xl border border-dashed border-gray-300 dark:border-slate-700 p-12 text-center text-sm text-gray-400 dark:text-slate-500">
                No meetings yet. Use “Send Bot” to dispatch a notetaker to a call.
            </div>
        );
    }
    return (
        <ul className="space-y-2">
            {meetings.map(m => (
                <li key={m.id}>
                    <button onClick={() => onOpen(m.id)}
                        className="w-full text-left rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-3 hover:border-gray-300 dark:hover:border-slate-600 transition-colors">
                        <div className="flex items-center gap-2">
                            <div className="flex-1 text-sm font-medium text-gray-900 dark:text-slate-100 truncate">{m.title}</div>
                            {m.source === 'recall' && m.bot_status && (
                                <span className={`shrink-0 px-1.5 py-0.5 text-[10px] font-semibold rounded capitalize ${BOT_STATUS_PILL[m.bot_status] || 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300'} ${isLiveBot(m.bot_status) ? 'animate-pulse' : ''}`}>
                                    {botStatusLabel(m.bot_status)}
                                </span>
                            )}
                        </div>
                        <div className="mt-0.5 text-[11px] text-gray-400 dark:text-slate-500">
                            {m.source === 'recall'
                                ? `🤖 bot${m.occurred_at ? ` · ${formatWhen(m.occurred_at)}` : ''} · ${m.item_count} to-do(s)`
                                : `${MEETING_TYPE_LABEL[m.meeting_type] || m.meeting_type} · ${m.item_count} item(s)${m.project_number ? ` · #${m.project_number}` : ''}`}
                        </div>
                    </button>
                </li>
            ))}
        </ul>
    );
}

function SendBotModal({ url, name, busy, error, onUrl, onName, onSubmit, onClose }) {
    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
            <form onSubmit={onSubmit} onClick={e => e.stopPropagation()}
                className="w-full max-w-md rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-5 space-y-3 shadow-xl">
                <div className="flex items-center justify-between">
                    <h2 className="text-base font-semibold text-gray-900 dark:text-slate-100">Send a notetaker bot</h2>
                    <button type="button" onClick={onClose} aria-label="Close"
                        className="text-gray-400 hover:text-gray-600 dark:hover:text-slate-200 text-lg leading-none">✕</button>
                </div>
                <p className="text-xs text-gray-500 dark:text-slate-400">
                    Paste a Teams or Google Meet link. BB joins the call, records, and transcribes — no Azure admin or calendar access needed.
                </p>
                <input
                    type="text" inputMode="url" autoComplete="off" spellCheck={false} autoFocus
                    placeholder="https://teams.microsoft.com/l/meetup-join/…"
                    value={url} onChange={e => onUrl(e.target.value)}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-gray-900 dark:text-slate-100"
                />
                <input
                    type="text" placeholder="Meeting name (optional)"
                    value={name} onChange={e => onName(e.target.value)}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-gray-900 dark:text-slate-100"
                />
                {error && <p className="text-[11px] text-red-600 dark:text-red-400">{error}</p>}
                <div className="flex justify-end gap-2 pt-1">
                    <button type="button" onClick={onClose}
                        className="px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-slate-600 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700">Cancel</button>
                    <button type="submit" disabled={busy || !url.trim()}
                        className="px-3 py-2 text-sm font-medium rounded-lg bg-accent-500 hover:bg-accent-600 text-white disabled:opacity-50">
                        {busy ? 'Sending…' : 'Send Bot'}
                    </button>
                </div>
            </form>
        </div>
    );
}

function PasteTranscriptModal({ title, type, text, busy, error, onTitle, onType, onText, onSubmit, onClose }) {
    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
            <form onSubmit={onSubmit} onClick={e => e.stopPropagation()}
                className="w-full max-w-2xl rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-5 space-y-3 shadow-xl">
                <div className="flex items-center justify-between">
                    <h2 className="text-base font-semibold text-gray-900 dark:text-slate-100">Paste a transcript</h2>
                    <button type="button" onClick={onClose} aria-label="Close"
                        className="text-gray-400 hover:text-gray-600 dark:hover:text-slate-200 text-lg leading-none">✕</button>
                </div>
                <p className="text-xs text-gray-500 dark:text-slate-400">
                    Creates a meeting from raw transcript text — open it and hit “Generate to-do list” to run the extractor.
                    Also the fallback when a bot couldn’t join (Teams lobby / tenant policy).
                </p>
                <div className="flex gap-2">
                    <input type="text" placeholder="Title (optional)" value={title} onChange={e => onTitle(e.target.value)}
                        className="flex-1 px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-gray-900 dark:text-slate-100" />
                    <select value={type} onChange={e => onType(e.target.value)}
                        className="px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-gray-700 dark:text-slate-200">
                        {MEETING_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                    </select>
                </div>
                <textarea placeholder="Paste the meeting transcript…" rows={12} value={text} onChange={e => onText(e.target.value)}
                    className="w-full px-3 py-2 text-xs font-mono rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-gray-900 dark:text-slate-100" />
                {error && <p className="text-[11px] text-red-600 dark:text-red-400">{error}</p>}
                <div className="flex items-center justify-between gap-2 pt-1">
                    {text ? <span className="text-[10px] text-gray-400 dark:text-slate-500">{text.length.toLocaleString()} chars</span> : <span />}
                    <div className="flex gap-2">
                        <button type="button" onClick={onClose}
                            className="px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-slate-600 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700">Cancel</button>
                        <button type="submit" disabled={busy || !text.trim()}
                            className="px-3 py-2 text-sm font-medium rounded-lg bg-accent-500 hover:bg-accent-600 text-white disabled:opacity-50">
                            {busy ? 'Creating…' : 'Create meeting'}
                        </button>
                    </div>
                </div>
            </form>
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
                {(item.matched_job_name || item.matched_job_number) && (
                    <span className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300">
                        {item.match_source === 'submittal' ? 'Submittal' : 'Release'} · {item.matched_job_name || `job ${item.matched_job_number}`}{item.confidence != null ? ` · ${Math.round(item.confidence * 100)}%` : ''}
                    </span>
                )}
                {item.owner_inferred && <span className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">owner inferred</span>}
                {item.name_corrected && <span className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-cyan-100 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300">name cleaned</span>}
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
