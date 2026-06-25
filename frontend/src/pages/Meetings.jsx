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
import { useState, useEffect, useCallback, useRef } from 'react';
import { checkAuth } from '../utils/auth';
import {
    fetchMeetings, fetchMeeting, generateChecklist,
    reviewChecklistItem, fetchAssignableUsers, scanDue, sendBot, createManualMeeting,
    updateMeeting, generateLearnings,
} from '../services/meetingsApi';
import { searchByJob } from '../services/jobSearchApi';

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
    release_id: it.release_id != null ? String(it.release_id) : '',
    submittal_id: it.submittal_id != null ? String(it.submittal_id) : '',
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
    const [botAgenda, setBotAgenda] = useState('');
    const [botBusy, setBotBusy] = useState(false);
    const [learnBusy, setLearnBusy] = useState(false);
    const [learnAnchor, setLearnAnchor] = useState(null);  // learned_at at click time
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
        try { setMeetings(await fetchMeetings() || []); }
        catch { setMeetings([]); setError('Failed to load meetings'); }
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
            const meeting = await sendBot({
                meeting_url: url, title, agenda_text: botAgenda.trim() || undefined,
            });
            setMeetings(prev => [meeting, ...prev.filter(m => m.id !== meeting.id)]);
            setSelected(meeting); seedDrafts(meeting);
            setBotUrl(''); setBotName(''); setBotAgenda(''); setShowSendBot(false);
        } catch (err) {
            setError(err?.response?.data?.error || 'Failed to send bot');
        } finally {
            setBotBusy(false);
        }
    };

    // Save edited pre-meeting agenda/notes onto the open meeting.
    const handleSaveAgenda = async (text) => {
        if (!selected) return;
        try {
            const m = await updateMeeting(selected.id, { agenda_text: text });
            setSelected(s => ({ ...s, agenda_text: m.agenda_text }));
        } catch { setError('Failed to save agenda'); }
    };

    // Kick off (re)synthesis of learnings, then poll until learned_at advances.
    const handleGenerateLearnings = async () => {
        if (!selected) return;
        setLearnBusy(true); setLearnAnchor(selected.learned_at || null); setError(null);
        try {
            await generateLearnings(selected.id);
        } catch (err) {
            setError(err?.response?.data?.error || 'Failed to generate learnings');
            setLearnBusy(false);
        }
    };

    const handleGenerate = async () => {
        if (!selected) return;
        // Regenerate (clear + rebuild) when the meeting already has items.
        const regenerate = (selected.items || []).length > 0;
        setGenerating(true); setError(null);
        try {
            // Returns 202 with extract_status='extracting'; the poller below takes over
            // until extraction finishes — the LLM calls run in the background.
            const updated = await generateChecklist(selected.id, { regenerate });
            setSelected(updated);
        } catch (err) {
            setError(err?.response?.data?.error || 'Failed to generate to-do list');
            setGenerating(false);
        }
    };

    // Checklist extraction runs in the background; poll the open meeting until it leaves
    // 'extracting', then show the items (or surface the failure).
    useEffect(() => {
        if (selected?.extract_status !== 'extracting') return;
        const id = selected.id;
        let cancelled = false;
        const tick = async () => {
            try {
                const m = await fetchMeeting(id);
                if (cancelled || m.id !== id || m.extract_status === 'extracting') return;
                setSelected(m); seedDrafts(m); setGenerating(false);
                setMeetings(prev => prev.map(x => (x.id === m.id ? { ...x, item_count: m.item_count } : x)));
                if (m.extract_status === 'failed') {
                    setError(m.extract_error || 'Failed to generate to-do list');
                }
            } catch { /* transient — keep polling */ }
        };
        const h = setInterval(tick, 2500);
        return () => { cancelled = true; clearInterval(h); };
    }, [selected?.extract_status, selected?.id]);

    // Learnings synthesis runs in the background; poll the open meeting until learned_at
    // advances past where it was when we kicked off, then show the fresh learning.
    useEffect(() => {
        if (!learnBusy || !selected) return;
        const id = selected.id;
        let cancelled = false;
        const tick = async () => {
            try {
                const m = await fetchMeeting(id);
                if (cancelled || m.id !== id || !m.learned_at || m.learned_at === learnAnchor) return;
                setSelected(m); seedDrafts(m); setLearnBusy(false);
            } catch { /* transient — keep polling */ }
        };
        const h = setInterval(tick, 3000);
        return () => { cancelled = true; clearInterval(h); };
    }, [learnBusy, learnAnchor, selected?.id]);

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
            release_id: d.release_id ? Number(d.release_id) : null,
            submittal_id: d.submittal_id || null,
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
    // True while a (possibly background) extraction is running — covers both the click
    // we just made and a meeting opened while its run is already in flight.
    const isGenerating = generating || selected?.extract_status === 'extracting';

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
                                    <button onClick={handleGenerate} disabled={isGenerating || !canGenerate}
                                        className="text-[11px] px-2 py-1 rounded-md border border-gray-300 dark:border-slate-600 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700 disabled:opacity-50">
                                        {isGenerating ? 'Regenerating…' : 'Regenerate'}
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
                                            <p className="text-sm text-gray-500 dark:text-slate-400 mb-3">
                                                {isGenerating
                                                    ? 'Generating to-dos from the transcript — this can take a minute…'
                                                    : 'No to-dos yet — generate them from the transcript.'}
                                            </p>
                                            <button onClick={handleGenerate} disabled={isGenerating}
                                                className="px-4 py-2 text-sm font-medium rounded-lg bg-accent-500 hover:bg-accent-600 text-white disabled:opacity-50">
                                                {isGenerating ? 'Generating…' : 'Generate to-do list'}
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
                    <ContextLearningPanel
                        meeting={selected}
                        onSaveAgenda={handleSaveAgenda}
                        onGenerateLearnings={handleGenerateLearnings}
                        learnBusy={learnBusy}
                    />
                </div>
            )}

            {showSendBot && (
                <SendBotModal
                    url={botUrl} name={botName} agenda={botAgenda} busy={botBusy} error={error}
                    onUrl={setBotUrl} onName={setBotName} onAgenda={setBotAgenda}
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
    if (!meetings?.length) {
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

function SendBotModal({ url, name, agenda, busy, error, onUrl, onName, onAgenda, onSubmit, onClose }) {
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
                <div>
                    <textarea
                        rows={4} placeholder="Agenda / pre-meeting notes (optional) — paste the agenda or upload a .md below; fed into to-do extraction as context."
                        value={agenda} onChange={e => onAgenda(e.target.value)}
                        className="w-full px-3 py-2 text-xs rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-gray-900 dark:text-slate-100"
                    />
                    <div className="mt-1 flex items-center justify-between gap-2">
                        <p className="text-[10px] text-gray-400 dark:text-slate-500">
                            Grounds to-do extraction with what the meeting is about — job state is added automatically.
                        </p>
                        <label className="shrink-0 text-[10px] px-2 py-1 rounded-md border border-gray-300 dark:border-slate-600 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700 cursor-pointer">
                            Upload .md
                            <input
                                type="file" accept=".md,.markdown,.txt,text/markdown,text/plain" className="hidden"
                                onChange={e => {
                                    const file = e.target.files?.[0];
                                    if (!file) return;
                                    const reader = new FileReader();
                                    reader.onload = () => onAgenda(String(reader.result || ''));
                                    reader.readAsText(file);
                                    e.target.value = '';  // allow re-selecting the same file
                                }}
                            />
                        </label>
                    </div>
                </div>
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

function ContextLearningPanel({ meeting, onSaveAgenda, onGenerateLearnings, learnBusy }) {
    const [agenda, setAgenda] = useState(meeting.agenda_text || '');
    const [savedAt, setSavedAt] = useState(null);
    // Re-seed the editor when switching meetings.
    useEffect(() => { setAgenda(meeting.agenda_text || ''); setSavedAt(null); }, [meeting.id]);

    const learning = meeting.learning;
    const payload = learning?.payload || {};
    const dirty = (agenda || '') !== (meeting.agenda_text || '');
    const save = async () => { await onSaveAgenda(agenda.trim()); setSavedAt(Date.now()); };

    const renderMap = (obj) =>
        obj && typeof obj === 'object'
            ? Object.entries(obj).filter(([, v]) => v).map(([k, v]) => (
                <li key={k}><span className="font-medium capitalize">{k.replace(/_/g, ' ')}:</span> {String(v)}</li>
            ))
            : null;

    return (
        <div className="rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4 space-y-4">
            {/* Meeting summary (the second output — grounded by during-meeting events) */}
            {meeting.summary && (
                <div>
                    <h3 className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-slate-500 mb-1">Meeting summary</h3>
                    <p className="whitespace-pre-wrap text-xs text-gray-700 dark:text-slate-300">{meeting.summary}</p>
                </div>
            )}

            {/* Brain drifts (v3) — where what was said diverged from the job log / DWL.
                Read-only: surfaced for the reviewer to act on; the system never writes back. */}
            {meeting.drifts?.length > 0 && (
                <div className={meeting.summary ? 'border-t border-gray-100 dark:border-slate-700 pt-3' : ''}>
                    <h3 className="text-[11px] font-semibold uppercase tracking-wide text-rose-500 dark:text-rose-400 mb-1">
                        ⚠ Brain drifts ({meeting.drifts.length})
                    </h3>
                    <p className="text-[10px] text-gray-400 dark:text-slate-500 mb-2">
                        Where what was said disagrees with the Brain. Read-only — update the job log / DWL yourself.
                    </p>
                    <ul className="space-y-1.5">
                        {meeting.drifts.map(d => (
                            <li key={d.id} className="rounded-lg border border-rose-200 dark:border-rose-900/50 bg-rose-50/50 dark:bg-rose-900/10 p-2">
                                <div className="flex items-center gap-2 flex-wrap">
                                    <span className={`px-1.5 py-0.5 text-[10px] font-semibold rounded ${d.kind === 'agreed_change'
                                        ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'
                                        : 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300'}`}>
                                        {d.kind === 'agreed_change' ? 'agreed change' : 'contradiction'}
                                    </span>
                                    <span className="text-[11px] font-medium text-gray-800 dark:text-slate-200">{d.ref}</span>
                                    {d.entity_name && <span className="text-[10px] text-gray-400 dark:text-slate-500 truncate max-w-[160px]">{d.entity_name}</span>}
                                    {d.confidence != null && <span className="ml-auto text-[10px] text-gray-400">{Math.round(d.confidence * 100)}%</span>}
                                </div>
                                <p className="mt-1 text-[11px] text-gray-700 dark:text-slate-300">
                                    <span className="font-medium">{d.field}</span>: said{' '}
                                    <span className="font-semibold text-rose-700 dark:text-rose-300">{String(d.stated_value)}</span>
                                    {' · Brain shows '}
                                    <span className="font-semibold">{d.brain_value == null ? '—' : String(d.brain_value)}</span>
                                </p>
                                {d.quote && <p className="mt-0.5 text-[10px] italic text-gray-500 dark:text-slate-400">“{d.quote}”</p>}
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            {/* Pre-meeting context */}
            <div className={meeting.summary ? 'border-t border-gray-100 dark:border-slate-700 pt-3' : ''}>
                <h3 className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-slate-500 mb-1">Pre-meeting context</h3>
                <textarea
                    rows={3} value={agenda} onChange={e => setAgenda(e.target.value)}
                    placeholder="Agenda / notes for this meeting — grounds to-do extraction."
                    className="w-full px-3 py-2 text-xs rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-gray-900 dark:text-slate-100"
                />
                <div className="mt-1 flex items-center gap-2">
                    <button onClick={save} disabled={!dirty}
                        className="text-[11px] px-2 py-1 rounded-md border border-gray-300 dark:border-slate-600 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700 disabled:opacity-50">
                        Save notes
                    </button>
                    {savedAt && !dirty && <span className="text-[10px] text-emerald-600 dark:text-emerald-400">Saved</span>}
                </div>
                {meeting.context_snapshot && (
                    <details className="mt-2">
                        <summary className="text-[11px] text-gray-500 dark:text-slate-400 cursor-pointer hover:underline">
                            Job updates during the meeting (used for the summary)
                        </summary>
                        <pre className="mt-1 whitespace-pre-wrap text-[11px] text-gray-600 dark:text-slate-300 max-h-56 overflow-auto rounded-lg bg-gray-50 dark:bg-slate-900/50 p-2 border border-gray-100 dark:border-slate-700">{meeting.context_snapshot}</pre>
                    </details>
                )}
            </div>

            {/* Learnings */}
            <div className="border-t border-gray-100 dark:border-slate-700 pt-3">
                <div className="flex items-center justify-between gap-2 mb-1">
                    <h3 className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-slate-500">Learnings</h3>
                    <button onClick={onGenerateLearnings} disabled={learnBusy}
                        className="text-[11px] px-2 py-1 rounded-md border border-gray-300 dark:border-slate-600 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700 disabled:opacity-50">
                        {learnBusy ? 'Synthesizing…' : learning ? 'Regenerate learnings' : 'Generate learnings'}
                    </button>
                </div>
                {learning ? (
                    <div className="space-y-2 text-xs text-gray-700 dark:text-slate-300">
                        {learning.summary && <p>{learning.summary}</p>}
                        {payload.by_outcome && (
                            <div>
                                <p className="text-[11px] font-semibold text-gray-500 dark:text-slate-400">By review outcome</p>
                                <ul className="list-disc ml-4 text-[11px]">{renderMap(payload.by_outcome)}</ul>
                            </div>
                        )}
                        {payload.by_item_type && (
                            <div>
                                <p className="text-[11px] font-semibold text-gray-500 dark:text-slate-400">By item type</p>
                                <ul className="list-disc ml-4 text-[11px]">{renderMap(payload.by_item_type)}</ul>
                            </div>
                        )}
                        {payload.by_event && (
                            <div>
                                <p className="text-[11px] font-semibold text-gray-500 dark:text-slate-400">Vs. recent activity</p>
                                <p className="text-[11px]">{String(payload.by_event)}</p>
                            </div>
                        )}
                        <p className="text-[10px] text-gray-400 dark:text-slate-500">
                            {learning.model === 'stub' ? 'deterministic only (no API)' : `${learning.model} · ${formatCost(learning.cost_usd)}`}
                            {meeting.learned_at ? ` · ${formatWhen(meeting.learned_at)}` : ''}
                        </p>
                    </div>
                ) : (
                    <p className="text-[11px] text-gray-400 dark:text-slate-500">
                        {learnBusy
                            ? 'Synthesizing learnings from the reviewed checklist…'
                            : 'Generated automatically once every to-do has been reviewed — or generate now.'}
                    </p>
                )}
            </div>
        </div>
    );
}

// Anchor a to-do to a release OR a submittal by hand. Pick the kind with the toggle,
// then search by project NAME (how people think) or a 1–3 digit job number (the
// system's key). Sets release_id XOR submittal_id on the draft (committed on Yes).
// Reuses /brain/job-search, which returns both kinds for any query.
function RecordPicker({ releaseId, submittalId, matchSource, matchedLabel, matchedJobNumber, linkedReleaseLabel, onPick }) {
    const [open, setOpen] = useState(false);
    const [kind, setKind] = useState(matchSource === 'submittal' ? 'submittal' : 'release');
    const [q, setQ] = useState('');
    const [data, setData] = useState({ releases: [], submittals: [] });
    const [searching, setSearching] = useState(false);
    const ref = useRef(null);

    // Close when clicking anywhere outside the picker (the dropdown lives inside `ref`).
    useEffect(() => {
        if (!open) return;
        const onDown = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
        document.addEventListener('mousedown', onDown);
        return () => document.removeEventListener('mousedown', onDown);
    }, [open]);

    const run = async (term) => {
        setQ(term);
        if (!term.trim()) { setData({ releases: [], submittals: [] }); return; }
        setSearching(true);
        try {
            const r = await searchByJob(term.trim());
            setData({ releases: r.releases, submittals: r.submittals });
        } catch { setData({ releases: [], submittals: [] }); }
        finally { setSearching(false); }
    };

    const linked = releaseId || submittalId;
    const linkedRel = data.releases.find(r => String(r.id) === String(releaseId));
    const linkedSub = data.submittals.find(s => String(s.submittal_id) === String(submittalId));
    // Both kinds read as "number · name" so it's clear which record is linked.
    const label = releaseId
        ? (linkedRel ? `${linkedRel.job_release} · ${linkedRel.job_name}` : linkedReleaseLabel || matchedLabel || `release #${releaseId}`)
        : submittalId
            ? (linkedSub ? `${linkedSub.project_number} · ${linkedSub.project_name || linkedSub.title}` : matchedLabel || (matchedJobNumber ? `${matchedJobNumber} · submittal` : `submittal ${submittalId}`))
            : (matchedLabel || 'link record');

    const results = kind === 'release' ? data.releases : data.submittals;
    const tab = (k, text) => (
        <button type="button" onClick={() => setKind(k)}
            className={`px-2 py-0.5 text-[11px] rounded-md border ${kind === k
                ? 'border-indigo-400 text-indigo-700 dark:border-indigo-600 dark:text-indigo-300 font-medium'
                : 'border-gray-300 dark:border-slate-600 text-gray-500 dark:text-slate-400'}`}>
            {text}
        </button>
    );

    // Opening on a matched-but-unlinked item pre-loads that job's records so the reviewer
    // can pick the right release (with descriptions) in one click.
    const toggleOpen = () => {
        const next = !open;
        setOpen(next);
        if (next && !q && matchedJobNumber) run(String(matchedJobNumber));
    };

    return (
        <div className="relative" ref={ref}>
            <button type="button" onClick={toggleOpen}
                className={`px-2 py-1 text-xs rounded-md border ${linked
                    ? 'border-indigo-300 text-indigo-700 dark:border-indigo-700 dark:text-indigo-300'
                    : 'border-gray-300 dark:border-slate-600 text-gray-600 dark:text-slate-300'} bg-white dark:bg-slate-900`}>
                🔗 {label}
            </button>
            {open && (
                <div className="absolute z-10 mt-1 w-72 p-2 rounded-md border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 shadow-lg">
                    <div className="flex gap-1 mb-1.5">
                        {tab('release', 'Release')}
                        {tab('submittal', 'Submittal')}
                    </div>
                    <input autoFocus type="text" value={q} placeholder="project name or job # (e.g. sand creek, 480)"
                        onChange={e => run(e.target.value)}
                        className="w-full px-2 py-1 text-xs rounded border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-gray-900 dark:text-slate-100 mb-1" />
                    <div className="max-h-44 overflow-y-auto">
                        {searching && <p className="text-[11px] text-gray-400 px-1 py-0.5">Searching…</p>}
                        {!searching && kind === 'release' && results.map(r => (
                            <button key={r.id} type="button"
                                onClick={() => { onPick({ release_id: String(r.id), submittal_id: '' }); setOpen(false); }}
                                className="block w-full text-left px-1.5 py-1 text-[11px] rounded hover:bg-gray-100 dark:hover:bg-slate-700 text-gray-700 dark:text-slate-200">
                                <div className="font-medium">{r.job_release} · {r.job_name || `job ${r.job}`}</div>
                                {r.description && <div className="text-gray-400">{r.description}</div>}
                            </button>
                        ))}
                        {!searching && kind === 'submittal' && results.map(s => (
                            <button key={s.submittal_id} type="button"
                                onClick={() => { onPick({ release_id: '', submittal_id: String(s.submittal_id) }); setOpen(false); }}
                                className="block w-full text-left px-1.5 py-1 text-[11px] rounded hover:bg-gray-100 dark:hover:bg-slate-700 text-gray-700 dark:text-slate-200">
                                <div className="font-medium">{s.project_number ? `${s.project_number} · ` : ''}{s.project_name || s.title || `submittal ${s.submittal_id}`}</div>
                                {s.title && s.title !== s.project_name && <div className="text-gray-400">{s.title}</div>}
                            </button>
                        ))}
                        {!searching && q && results.length === 0 && (
                            <p className="text-[11px] text-gray-400 px-1 py-0.5">No matching {kind}s</p>
                        )}
                    </div>
                    {linked && (
                        <button type="button" onClick={() => { onPick({ release_id: '', submittal_id: '' }); setOpen(false); }}
                            className="mt-1 text-[11px] text-rose-600 dark:text-rose-400 hover:underline">
                            Clear link
                        </button>
                    )}
                </div>
            )}
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
                        {item.match_source === 'submittal' ? 'Submittal' : 'Release'}
                        {item.release_job_release ? ` · ${item.release_job_release}` : ''} · {item.matched_job_name || `job ${item.matched_job_number}`}{item.confidence != null ? ` · ${Math.round(item.confidence * 100)}%` : ''}
                    </span>
                )}
                {item.owner_inferred && <span className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">owner inferred</span>}
                {item.name_corrected && <span className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-cyan-100 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300">name cleaned</span>}
                {item.brain_update_pending && (
                    <span title="The room agreed to this change but the Brain still shows the old value — update it."
                        className="px-1.5 py-0.5 text-[10px] font-semibold rounded bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300">
                        ⚠ Brain not updated
                    </span>
                )}
                <span className={`ml-auto px-1.5 py-0.5 text-[10px] font-medium rounded capitalize ${STATUS_PILL[item.status]}`}>{item.status}</span>
            </div>
            {item.release_description && (
                <p className="mb-1.5 text-[11px] text-gray-500 dark:text-slate-400">
                    <span className="text-gray-400">Release scope:</span> {item.release_description}
                </p>
            )}
            {item.expected_update && (
                <p className="mb-1.5 text-[11px] text-gray-500 dark:text-slate-400">
                    Agreed update: <span className="font-medium">{item.expected_update.field}</span>
                    {' → '}<span className="font-medium">{String(item.expected_update.new_value)}</span>
                    {' '}({item.expected_update.target})
                </p>
            )}

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
                        <RecordPicker
                            releaseId={draft.release_id}
                            submittalId={draft.submittal_id}
                            matchSource={item.match_source}
                            matchedLabel={item.matched_job_name || (item.matched_job_number ? `job ${item.matched_job_number}` : '')}
                            matchedJobNumber={item.matched_job_number}
                            linkedReleaseLabel={item.release_job_release ? `${item.release_job_release} · ${item.matched_job_name || ''}`.trim() : ''}
                            onPick={patch => onDraft(patch)}
                        />
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
