/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Flag-gated read-only chat assistant ("Carmen"). Chrome owns a circular CM
 *          launcher next to the notification bell; this module renders that circle
 *          and a top-down expandable modal. Answers DB questions, shows cost/time/token
 *          metrics, and surfaces look-ahead PDFs. Admins get an access-management panel.
 *          Two voice modes: push-to-talk (record a clip -> xAI speech-to-text -> the same
 *          read-only agent -> xAI text-to-speech) and Live, an open realtime conversation
 *          where the browser holds a WebSocket to xAI and Carmen's tools answer her lookups.
 * exports:
 *   CarmenButton: circular CM launcher for AppShell (header + upper-right pod).
 *   BBChatWidget: default. Props: { enabled, isAdmin, open, onClose, anchorRef }. Null when !enabled || !open.
 * imports_from: [react, ../services/bbChatApi, ../services/carmenVoiceApi,
 *                ../hooks/useVoiceRecorder, ../hooks/useCarmenLive, ./carmen/LookaheadPdfCard]
 * imported_by: [components/AppShell.jsx]
 * invariants:
 *   - Renders nothing unless `enabled` (the caller passes user.is_carmen_chat).
 *   - Read-only: the UI never asks the server to mutate data — spoken turns included.
 *   - The mic only renders when the server reports voice configured (xAI key present).
 *   - One clip plays at a time; the previous object URL is revoked before the next starts.
 *   - Live mode and push-to-talk are mutually exclusive; starting one stops the other.
 *   - Every message carries a stable `id` and is keyed by it. Keying by array index
 *     remounts a card when anything is inserted above it, which silently resets the
 *     proposal card's applied state — the write lands but the UI says "not saved yet".
 *   - A proposal's outcome lives on the MESSAGE, not in the card, for the same reason.
 *   - No floating bottom bubble — the launcher sits next to the notification bell.
 *   - Panel drops from the CM bubble (upper right) and grows down/left; it does not cover the last Job Log row.
 */
import { useState, useRef, useEffect, useCallback, forwardRef } from 'react';
import { createPortal } from 'react-dom';
import { sendMessage, listAccessUsers, setUserAccess } from '../services/bbChatApi';
import { getVoiceConfig, sendVoiceTurn, speakText, audioUrlFromEnvelope } from '../services/carmenVoiceApi';
import useVoiceRecorder from '../hooks/useVoiceRecorder';
import useCarmenLive from '../hooks/useCarmenLive';
import LookaheadPdfCard, { extractLookaheadArtifacts } from './carmen/LookaheadPdfCard';
import ChangeProposalCard from './carmen/ChangeProposalCard';

const DEFAULT_W = 420;
const MIN_W = 320;
const MIN_H = 280;
const VIEW_MARGIN = 12;

function defaultHeight() {
    if (typeof window === 'undefined') return 420;
    return Math.round(Math.min(520, Math.max(MIN_H, window.innerHeight * 0.52)));
}

const fmtCost = (c) => (c == null ? '—' : c < 0.01 ? `$${c.toFixed(4)}` : `$${c.toFixed(3)}`);
const fmtMs = (ms) => (ms == null ? '—' : ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`);
const fmtNum = (n) => (n == null ? '0' : n.toLocaleString());
const fmtClock = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
const MAX_CLIP_SECONDS = 120;

let _msgSeq = 0;
const nextMsgId = () => { _msgSeq += 1; return `m${_msgSeq}`; };

// Spoken confirmation of a pending change. The words are the USER'S, transcribed — the
// model can never confirm its own proposal, it can only put the card up.
const SAID_YES = /^\s*(yes|yeah|yep|yup|sure|ok|okay|confirm(ed)?|do it|go ahead|send it|apply( it)?|that'?s right|correct|looks good)\b/i;
const SAID_NO = /^\s*(no|nope|cancel|stop|don'?t|never ?mind|scratch that|hold off|wait)\b/i;

// Render inline **bold** / `code`; everything else is plain text (no HTML injection).
function inline(text) {
    return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean).map((p, i) => {
        if (p.startsWith('**') && p.endsWith('**')) return <strong key={i}>{p.slice(2, -2)}</strong>;
        if (p.startsWith('`') && p.endsWith('`')) return <code key={i} className="text-[0.85em] bg-black/5 dark:bg-white/10 rounded px-1">{p.slice(1, -1)}</code>;
        return <span key={i}>{p}</span>;
    });
}

// Minimal, dependency-free markdown for the chat bubble: headings, bullets, and paragraphs.
// Keeps Carmen's answers clean without pulling in a markdown library.
function Markdown({ text }) {
    const lines = (text || '').split('\n');
    const blocks = [];
    let bullets = null;
    const flush = () => {
        if (bullets) {
            blocks.push(<ul key={`u${blocks.length}`} className="list-disc pl-4 space-y-0.5">{bullets}</ul>);
            bullets = null;
        }
    };
    lines.forEach((line, i) => {
        const bullet = line.match(/^\s*[-*]\s+(.*)/);
        const heading = line.match(/^#{1,6}\s+(.*)/);
        if (bullet) {
            (bullets ||= []).push(<li key={i}>{inline(bullet[1])}</li>);
        } else if (heading) {
            flush();
            blocks.push(<p key={i} className="font-semibold">{inline(heading[1])}</p>);
        } else {
            flush();
            if (line.trim()) blocks.push(<p key={i}>{inline(line)}</p>);
        }
    });
    flush();
    return <div className="space-y-1.5">{blocks}</div>;
}

function Metrics({ m }) {
    if (!m) return null;
    return (
        <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-gray-400 dark:text-slate-500">
            <span title="Estimated Anthropic cost for this answer">💵 {fmtCost(m.cost_usd)}</span>
            <span title="Wall-clock time">⏱ {fmtMs(m.duration_ms)}</span>
            <span title="Input / output tokens">🔤 {fmtNum(m.input_tokens)} in / {fmtNum(m.output_tokens)} out</span>
            {m.tool_calls > 0 && <span title="Read-only SQL queries run">🔎 {m.tool_calls} {m.tool_calls === 1 ? 'query' : 'queries'}</span>}
            {m.request_id && <span className="opacity-60" title="Anthropic request id (for spend reconciliation)">#{m.request_id}</span>}
        </div>
    );
}

const MIC_D = 'M12 3a3 3 0 00-3 3v5a3 3 0 006 0V6a3 3 0 00-3-3zM5 11a7 7 0 0014 0M12 18v3M8 21h8';
const STOP_D = 'M7 7h10v10H7z';
const SPEAKER_ON_D = 'M11 5L6 9H3v6h3l5 4V5zM15.8 8.6a4.5 4.5 0 010 6.8M18.6 6a8.5 8.5 0 010 12';
const SPEAKER_OFF_D = 'M11 5L6 9H3v6h3l5 4V5zM17 10l4 4M21 10l-4 4';
const LIVE_D = 'M12 4v16M8 8v8M16 8v8M4 11v2M20 11v2';

function Icon({ d, size = 15 }) {
    return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d={d} />
        </svg>
    );
}

/** Replay one written answer aloud. Only rendered when the server has voice configured. */
function SpeakButton({ text, onSpeak }) {
    const [busy, setBusy] = useState(false);
    const click = async () => {
        if (busy) return;
        setBusy(true);
        try {
            await onSpeak(text);
        } finally {
            setBusy(false);
        }
    };
    return (
        <button
            type="button"
            onClick={click}
            disabled={busy}
            title="Read this answer aloud"
            aria-label="Read this answer aloud"
            className={`mt-1.5 inline-flex items-center gap-1 text-[10px] text-gray-400 dark:text-slate-500 hover:text-accent-500 disabled:opacity-50 ${busy ? 'animate-pulse' : ''}`}
        >
            <Icon d={SPEAKER_ON_D} size={12} />
            {busy ? 'Speaking\u2026' : 'Listen'}
        </button>
    );
}

function AccessPanel() {
    const [users, setUsers] = useState(null);
    const [error, setError] = useState('');
    useEffect(() => {
        listAccessUsers().then(setUsers).catch(() => setError('Failed to load users'));
    }, []);
    const toggle = async (u) => {
        const next = !u.is_carmen_chat;
        setUsers((prev) => prev.map((x) => (x.id === u.id ? { ...x, is_carmen_chat: next } : x)));
        try {
            await setUserAccess(u.id, next);
        } catch {
            setUsers((prev) => prev.map((x) => (x.id === u.id ? { ...x, is_carmen_chat: !next } : x)));
        }
    };
    return (
        <div className="flex-1 min-h-0 overflow-y-auto p-2">
            {error && <p className="p-3 text-sm text-red-500">{error}</p>}
            {!users && !error && <p className="p-3 text-sm text-gray-400">Loading…</p>}
            {users && users.map((u) => (
                <div key={u.id} className="flex items-center justify-between px-2 py-2 rounded-lg hover:bg-gray-50 dark:hover:bg-slate-700">
                    <div className="min-w-0">
                        <div className="text-sm text-gray-800 dark:text-slate-100 truncate">{u.name}</div>
                        <div className="text-[11px] text-gray-400 dark:text-slate-500 truncate">{u.username}{u.is_admin ? ' · admin' : ''}</div>
                    </div>
                    <button
                        onClick={() => toggle(u)}
                        disabled={u.is_admin}
                        title={u.is_admin ? 'Admins always have access' : ''}
                        className={`relative flex-shrink-0 w-11 h-6 rounded-full transition-colors ${(u.is_carmen_chat || u.is_admin) ? 'bg-accent-500' : 'bg-gray-200 dark:bg-slate-600'} ${u.is_admin ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                        <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${(u.is_carmen_chat || u.is_admin) ? 'translate-x-5' : 'translate-x-0'}`} />
                    </button>
                </div>
            ))}
        </div>
    );
}

function clamp(n, lo, hi) {
    return Math.max(lo, Math.min(hi, n));
}

function fallbackAnchor() {
    return { top: 56, right: 12 };
}

function measureAnchor(anchorRef) {
    const el = anchorRef?.current;
    const r = el?.getBoundingClientRect();
    if (r && r.width > 0) {
        return {
            top: Math.round(r.bottom + 8),
            right: Math.round(Math.max(VIEW_MARGIN, window.innerWidth - r.right)),
        };
    }
    return fallbackAnchor();
}

function clampSize({ w, h }, anchor = fallbackAnchor()) {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const maxW = Math.max(MIN_W, vw - anchor.right - VIEW_MARGIN);
    const maxH = Math.max(MIN_H, vh - anchor.top - VIEW_MARGIN);
    return {
        w: clamp(Number.isFinite(w) ? w : MIN_W, MIN_W, maxW),
        h: clamp(Number.isFinite(h) ? h : MIN_H, MIN_H, maxH),
    };
}

function HeaderIcon({ d }) {
    return (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d={d} />
        </svg>
    );
}

function ResizeHandles({ active, onBegin, onSnapHeight, onSnapMax }) {
    const wash = active ? 'bg-accent-500/15' : 'hover:bg-accent-500/10';
    const edge = `absolute z-10 touch-none transition-colors ${wash}`;
    // Inset bars so the hover is an L along the frame, not a filled square over the input.
    const cornerL = active
        ? 'shadow-[inset_8px_0_0_0_rgba(47,95,208,0.15),inset_0_-8px_0_0_rgba(47,95,208,0.15)]'
        : 'hover:shadow-[inset_8px_0_0_0_rgba(47,95,208,0.10),inset_0_-8px_0_0_rgba(47,95,208,0.10)]';
    return (
        <>
            <div
                role="separator"
                aria-label="Resize Carmen chat"
                aria-orientation="horizontal"
                data-carmen="resize-s"
                title="Drag to change height · double-click to fill"
                onPointerDown={onBegin('resize-s')}
                onMouseDown={onBegin('resize-s')}
                onDoubleClick={(e) => { e.preventDefault(); onSnapHeight(); }}
                className={`${edge} left-8 right-0 bottom-0 h-2 cursor-ns-resize rounded-br-2xl`}
            />
            <div
                aria-hidden="true"
                title="Drag to change width"
                onPointerDown={onBegin('resize-w')}
                onMouseDown={onBegin('resize-w')}
                className={`${edge} top-0 bottom-8 left-0 w-2 cursor-ew-resize rounded-tl-2xl`}
            />
            <div
                data-carmen="resize-sw"
                title="Drag to resize · double-click to fill"
                onPointerDown={onBegin('resize-sw')}
                onMouseDown={onBegin('resize-sw')}
                onDoubleClick={(e) => { e.preventDefault(); onSnapMax(); }}
                className={`absolute bottom-0 left-0 z-20 h-8 w-8 cursor-nesw-resize touch-none rounded-bl-2xl transition-shadow ${cornerL}`}
            />
        </>
    );
}

/** Circular CM launcher — lives to the right of the notification bell. */
export const CarmenButton = forwardRef(function CarmenButton({ onClick, open = false, size = 36, className = '' }, ref) {
    return (
        <button
            ref={ref}
            type="button"
            data-carmen="launcher"
            onClick={onClick}
            aria-label={open ? 'Close Carmen chat' : 'Open Carmen chat'}
            aria-expanded={open}
            title="Ask Carmen — read-only data assistant"
            className={`shrink-0 rounded-full bg-accent-500 hover:bg-accent-600 text-white grid place-items-center font-bold tracking-wider shadow-sm ring-1 ring-black/5 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-400 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900 ${open ? 'ring-2 ring-offset-2 ring-accent-300' : ''} ${className}`}
            style={{ width: size, height: size, fontSize: size < 32 ? 9 : 11 }}
        >
            CM
        </button>
    );
});

export default function BBChatWidget({ enabled, isAdmin, open = false, onClose, anchorRef }) {
    const [showAccess, setShowAccess] = useState(false);
    const [messages, setMessages] = useState([]); // {role, content, metrics?}
    const [conversationId, setConversationId] = useState(null);
    const [input, setInput] = useState('');
    const [busy, setBusy] = useState(false);
    const [voiceCfg, setVoiceCfg] = useState(null);   // null until /voice/config answers
    const [autoSpeak, setAutoSpeak] = useState(true); // speak answers to spoken questions
    const [voiceNotice, setVoiceNotice] = useState('');
    const [size, setSize] = useState(() => ({ w: DEFAULT_W, h: defaultHeight() }));
    const [anchor, setAnchor] = useState(fallbackAnchor);
    const [resizing, setResizing] = useState(false);
    const scrollRef = useRef(null);
    const panelRef = useRef(null);
    const inputRef = useRef(null);
    const dragRef = useRef(null);
    const sizeRef = useRef(size);
    const anchorBoxRef = useRef(anchor);
    const restoringRef = useRef(null);
    const audioRef = useRef(null);
    const audioUrlRef = useRef(null);
    const liveArtifactsRef = useRef([]);
    const pendingProposalRef = useRef(null);   // the card awaiting a yes/no
    const confirmRef = useRef(null);           // ChangeProposalCard's confirm handler
    anchorBoxRef.current = anchor;

    const commitSize = useCallback((next) => {
        sizeRef.current = next;
        setSize(next);
        const el = panelRef.current;
        if (el) {
            el.style.width = `${next.w}px`;
            el.style.height = `${next.h}px`;
        }
    }, []);

    // One clip at a time: stop whatever is playing and release its object URL first.
    const stopAudio = useCallback(() => {
        if (audioRef.current) {
            audioRef.current.pause();
            audioRef.current = null;
        }
        if (audioUrlRef.current) {
            URL.revokeObjectURL(audioUrlRef.current);
            audioUrlRef.current = null;
        }
    }, []);

    const playEnvelope = useCallback((envelope) => {
        const url = audioUrlFromEnvelope(envelope);
        if (!url) return;
        stopAudio();
        audioUrlRef.current = url;
        const el = new Audio(url);
        audioRef.current = el;
        el.play().catch(() => {
            // Autoplay can be refused until the tab has been interacted with; the
            // per-message Listen button is the manual fallback.
            setVoiceNotice('Playback was blocked — tap Listen to hear the answer.');
        });
    }, [stopAudio]);

    const speak = useCallback(async (text) => {
        try {
            setVoiceNotice('');
            playEnvelope(await speakText(text));
        } catch {
            setVoiceNotice('Carmen could not speak that.');
        }
    }, [playEnvelope]);

    useEffect(() => stopAudio, [stopAudio]);

    useEffect(() => {
        if (!open || voiceCfg) return;
        getVoiceConfig()
            .then(setVoiceCfg)
            .catch(() => setVoiceCfg({ enabled: false, configured: false }));
    }, [open, voiceCfg]);

    useEffect(() => {
        if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }, [messages, busy]);

    useEffect(() => {
        if (open) inputRef.current?.focus();
    }, [open]);

    useEffect(() => {
        if (!open) return undefined;
        const apply = () => {
            const next = measureAnchor(anchorRef);
            setAnchor(next);
            commitSize(clampSize(sizeRef.current, next));
        };
        apply();
        window.addEventListener('resize', apply);
        return () => window.removeEventListener('resize', apply);
    }, [open, anchorRef, commitSize]);

    useEffect(() => {
        const onMove = (e) => {
            const d = dragRef.current;
            if (!d) return;
            if (e.cancelable) e.preventDefault();
            const box = anchorBoxRef.current;
            const dx = e.clientX - d.startX;
            const dy = e.clientY - d.startY;
            if (!Number.isFinite(dx) || !Number.isFinite(dy)) return;
            let next = d.orig;
            if (d.mode === 'resize-s') {
                next = clampSize({ w: d.orig.w, h: d.orig.h + dy }, box);
            } else if (d.mode === 'resize-w') {
                next = clampSize({ w: d.orig.w - dx, h: d.orig.h }, box);
            } else if (d.mode === 'resize-sw') {
                next = clampSize({ w: d.orig.w - dx, h: d.orig.h + dy }, box);
            }
            sizeRef.current = next;
            const el = panelRef.current;
            if (el) {
                el.style.width = `${next.w}px`;
                el.style.height = `${next.h}px`;
            }
        };
        const onUp = () => {
            if (!dragRef.current) return;
            dragRef.current = null;
            setSize(sizeRef.current);
            setResizing(false);
            document.body.classList.remove('carmen-resizing');
        };
        const opts = { capture: true, passive: false };
        window.addEventListener('pointermove', onMove, opts);
        window.addEventListener('mousemove', onMove, opts);
        window.addEventListener('pointerup', onUp, opts);
        window.addEventListener('mouseup', onUp, opts);
        window.addEventListener('pointercancel', onUp, opts);
        return () => {
            window.removeEventListener('pointermove', onMove, opts);
            window.removeEventListener('mousemove', onMove, opts);
            window.removeEventListener('pointerup', onUp, opts);
            window.removeEventListener('mouseup', onUp, opts);
            window.removeEventListener('pointercancel', onUp, opts);
            document.body.classList.remove('carmen-resizing');
        };
    }, []);

    useEffect(() => {
        if (!open) return undefined;
        const onKey = (e) => {
            if (e.key === 'Escape') {
                setShowAccess(false);
                onClose?.();
            }
        };
        const onDown = (e) => {
            if (panelRef.current?.contains(e.target)) return;
            if (anchorRef?.current?.contains(e.target)) return;
            setShowAccess(false);
            onClose?.();
        };
        window.addEventListener('keydown', onKey);
        document.addEventListener('mousedown', onDown);
        return () => {
            window.removeEventListener('keydown', onKey);
            document.removeEventListener('mousedown', onDown);
        };
    }, [open, onClose, anchorRef]);

    const beginResize = (mode) => (e) => {
        if (e.button === 2) return;
        if (e.cancelable) e.preventDefault();
        e.stopPropagation();
        const rect = panelRef.current?.getBoundingClientRect();
        const orig = (rect && rect.width > 0 && rect.height > 0)
            ? { w: rect.width, h: rect.height }
            : sizeRef.current;
        dragRef.current = {
            mode,
            startX: e.clientX,
            startY: e.clientY,
            orig,
        };
        try {
            e.currentTarget.setPointerCapture?.(e.pointerId);
        } catch {
            /* jsdom throws on setPointerCapture without a real pointer id */
        }
        setResizing(true);
        document.body.classList.add('carmen-resizing');
    };

    const snapHeight = () => {
        const box = measureAnchor(anchorRef);
        const cur = sizeRef.current;
        const max = clampSize({ w: cur.w, h: 1e5 }, box);
        const atMax = cur.h >= max.h - 16;
        if (!atMax) restoringRef.current = { ...cur };
        commitSize(atMax
            ? clampSize({ w: cur.w, h: restoringRef.current?.h || defaultHeight() }, box)
            : max);
    };

    const snapMax = () => {
        const box = measureAnchor(anchorRef);
        const cur = sizeRef.current;
        const max = clampSize({ w: 1e5, h: 1e5 }, box);
        const atMax = cur.h >= max.h - 16 && cur.w >= max.w - 16;
        if (!atMax) restoringRef.current = { ...cur };
        commitSize(atMax
            ? clampSize(restoringRef.current || { w: DEFAULT_W, h: defaultHeight() }, box)
            : max);
    };

    const send = useCallback(async () => {
        const text = input.trim();
        if (!text || busy) return;
        setInput('');
        setMessages((prev) => [...prev, { id: nextMsgId(), role: 'user', content: text }]);
        setBusy(true);
        try {
            const res = await sendMessage(text, conversationId);
            setConversationId(res.conversation_id);
            const a = res.assistant_message;
            const artifacts = extractLookaheadArtifacts(a.content, a.artifacts);
            setMessages((prev) => [...prev, {
                role: 'assistant',
                content: a.content,
                metrics: a.metrics,
                artifacts,
            }]);
        } catch {
            setMessages((prev) => [...prev, { role: 'assistant', content: '⚠️ Something went wrong. Please try again.', metrics: null }]);
        } finally {
            setBusy(false);
        }
    }, [input, busy, conversationId]);

    /** One spoken turn: the clip goes up, the transcript and the answer come back. */
    const sendClip = useCallback(async (blob, filename) => {
        if (busy) return;
        setVoiceNotice('');
        setBusy(true);
        setMessages((prev) => [...prev, { id: nextMsgId(), role: 'user', content: '\u{1F3A4} \u2026', pending: true }]);
        try {
            const res = await sendVoiceTurn(blob, conversationId, filename);
            setConversationId(res.conversation_id);
            const a = res.assistant_message;
            const artifacts = extractLookaheadArtifacts(a.content, a.artifacts);
            setMessages((prev) => [
                ...prev.slice(0, -1),
                { id: nextMsgId(), role: 'user', content: res.transcript, spoken: true },
                { id: nextMsgId(), role: 'assistant', content: a.content, metrics: a.metrics, artifacts },
            ]);
            if (res.voice_error) setVoiceNotice(res.voice_error);
            else if (autoSpeak && res.audio) playEnvelope(res.audio);
        } catch (err) {
            const status = err?.response?.status;
            const detail = err?.response?.data?.error;
            setMessages((prev) => prev.slice(0, -1));
            setVoiceNotice(detail || (status === 503
                ? 'Carmen\u2019s voice isn\u2019t configured on this server yet.'
                : 'Something went wrong with that recording.'));
        } finally {
            setBusy(false);
        }
    }, [busy, conversationId, autoSpeak, playEnvelope]);

    const recorder = useVoiceRecorder({ maxSeconds: MAX_CLIP_SECONDS, onClip: sendClip });
    const voiceReady = !!voiceCfg?.configured && recorder.supported;

    // Live mode posts as it happens rather than at end of turn: the question when the
    // transcript finalises, then her written answer — which lands before she starts
    // speaking, so there's something on screen to read while she talks.
    const onLiveUserText = useCallback((text, turnId) => {
        setMessages((prev) => {
            // Same turn = same bubble. A sentence split by VAD arrives as several
            // transcription items; they update this message rather than stacking.
            const existing = prev.findIndex((m) => m.role === 'user' && m.turnId === turnId);
            if (existing !== -1) {
                const next = [...prev];
                next[existing] = { ...next[existing], content: text };
                return next;
            }
            // Transcription can finalise after the card is already up; slot the question
            // above any trailing proposal so the pane still reads question-then-answer.
            let at = prev.length;
            while (at > 0 && prev[at - 1].kind === 'proposal') at -= 1;
            const next = [...prev];
            next.splice(at, 0, { id: nextMsgId(), role: 'user', content: text, spoken: true, turnId });
            return next;
        });
        // "go ahead" while a card is up confirms it. The intent comes from the person's
        // own transcribed words, and the exact change is already on screen to read.
        const pending = pendingProposalRef.current;
        if (!pending) return;
        if (SAID_YES.test(text)) {
            pendingProposalRef.current = null;
            confirmRef.current?.();
        } else if (SAID_NO.test(text)) {
            pendingProposalRef.current = null;
            setMessages((prev) => prev.map((m) => (m.proposal === pending
                ? { ...m, proposalCancelled: true } : m)));
        }
    }, []);

    const onLiveProposal = useCallback((proposal) => {
        const superseded = pendingProposalRef.current;
        pendingProposalRef.current = proposal;
        confirmRef.current = null;   // the old card's confirm handler is dead
        setMessages((prev) => [
            // Drop the card this one corrects. Two live cards for the same release is a
            // trap — you'd confirm whichever you clicked, including the wrong one.
            ...prev.filter((m) => !(m.kind === 'proposal' && m.proposal === superseded)),
            { id: nextMsgId(), role: 'assistant', kind: 'proposal', proposal, live: true },
        ]);
    }, []);

    /** Summarise an apply for the live session so she can say it landed. */
    const describeOutcome = useCallback((proposal, result) => {
        const who = `${proposal.plan?.job}-${proposal.plan?.release}`;
        if (result?.cancelled) return `The person cancelled the change to ${who}. Nothing was saved.`;
        const labels = (result?.results || [])
            .filter((r) => r.status === 'applied')
            .map((r) => r.label.toLowerCase());
        const failed = (result?.results || []).filter((r) => r.status === 'failed');
        if (!labels.length) return `The change to ${who} failed and nothing was saved.`;
        const base = `Applied to ${who}: ${labels.join(' and ')} updated and saved.`;
        return failed.length
            ? `${base} But ${failed.map((f) => f.label.toLowerCase()).join(' and ')} failed.`
            : `${base} Acknowledge in a few words.`;
    }, []);

    const onLiveAssistantText = useCallback((text) => {
        const artifacts = liveArtifactsRef.current;
        liveArtifactsRef.current = [];
        setMessages((prev) => [...prev, { id: nextMsgId(), role: 'assistant', content: text, artifacts, live: true }]);
    }, []);

    const live = useCarmenLive({
        conversationId,
        onConversationId: setConversationId,
        onUserText: onLiveUserText,
        onAssistantText: onLiveAssistantText,
        onArtifact: (a) => liveArtifactsRef.current.push(a),
        onProposal: onLiveProposal,
    });
    const notifyAppliedRef = useRef(null);
    notifyAppliedRef.current = live.notifyApplied;
    const liveReady = !!voiceCfg?.live?.configured && live.supported;
    const liveOn = live.status === 'connecting' || live.status === 'live';

    const toggleLive = useCallback(() => {
        if (liveOn) { live.stop(); return; }
        recorder.cancel();   // the two mic modes can't share the microphone
        stopAudio();
        live.start();
    }, [liveOn, live, recorder, stopAudio]);

    const newChat = () => {
        live.stop();
        stopAudio();
        setMessages([]);
        setConversationId(null);
        setVoiceNotice('');
    };

    const closePanel = () => {
        recorder.cancel();
        live.stop();
        stopAudio();
        setShowAccess(false);
        onClose?.();
    };

    const onKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    };

    if (!enabled || !open) return null;

    // Portal to <body> so the widget isn't caught by the app's global
    // `#root > div > div { width:100% !important }` layout rule (and escapes any
    // ancestor overflow/stacking context).
    return createPortal(
        <>
            <div
                ref={panelRef}
                role="dialog"
                aria-label="Carmen chat"
                data-carmen="panel"
                className="carmen-drop fixed z-[61] bg-surface border border-hairline flex flex-col overflow-hidden rounded-2xl"
                style={{
                    top: anchor.top,
                    right: anchor.right,
                    width: size.w,
                    height: size.h,
                    maxWidth: `calc(100vw - ${anchor.right + VIEW_MARGIN}px)`,
                    maxHeight: `calc(100dvh - ${anchor.top + VIEW_MARGIN}px)`,
                    boxShadow: resizing
                        ? '0 0 0 2px rgba(47, 95, 208, 0.35), var(--shadow)'
                        : 'var(--shadow)',
                }}
            >
                <div className="shrink-0 flex items-center justify-between pl-3.5 pr-2 py-2 bg-gradient-to-r from-accent-500 to-accent-600 text-white">
                    <div className="flex items-center gap-2 min-w-0">
                        <span className="font-semibold text-sm">{showAccess ? 'Carmen Chat access' : 'Carmen'}</span>
                        {!showAccess && (
                            <span className="text-[11px] opacity-80 hidden sm:inline">
                                {voiceCfg?.live?.can_edit ? 'can edit' : 'read-only'}
                            </span>
                        )}
                    </div>
                    <div className="flex items-center gap-0.5">
                        {showAccess ? (
                            <button type="button" onClick={() => setShowAccess(false)} title="Back to chat" aria-label="Back to chat" className="grid place-items-center w-7 h-7 rounded-md hover:bg-white/15">
                                <HeaderIcon d="M15 19l-7-7 7-7" />
                            </button>
                        ) : (
                            <>
                                {voiceReady && (
                                    <button
                                        type="button"
                                        onClick={() => { if (autoSpeak) stopAudio(); setAutoSpeak((v) => !v); }}
                                        title={autoSpeak ? 'Carmen speaks her answers' : 'Carmen stays silent'}
                                        aria-label={autoSpeak ? 'Mute Carmen' : 'Let Carmen speak'}
                                        aria-pressed={autoSpeak}
                                        className={`grid place-items-center w-7 h-7 rounded-md hover:bg-white/15 ${autoSpeak ? '' : 'opacity-50'}`}
                                    >
                                        <HeaderIcon d={autoSpeak ? SPEAKER_ON_D : SPEAKER_OFF_D} />
                                    </button>
                                )}
                                <button type="button" onClick={newChat} title="New chat" aria-label="New chat" className="grid place-items-center w-7 h-7 rounded-md hover:bg-white/15">
                                    <HeaderIcon d="M12 5v14M5 12h14" />
                                </button>
                                {isAdmin && (
                                    <button type="button" onClick={() => setShowAccess(true)} title="Manage access" aria-label="Manage access" className="grid place-items-center w-7 h-7 rounded-md hover:bg-white/15">
                                        <HeaderIcon d="M12 15a3 3 0 100-6 3 3 0 000 6zM4 12h2M18 12h2M6.3 6.3l1.4 1.4M16.3 16.3l1.4 1.4M6.3 17.7l1.4-1.4M16.3 7.7l1.4-1.4" />
                                    </button>
                                )}
                            </>
                        )}
                        <button type="button" onClick={closePanel} title="Close" aria-label="Close Carmen chat" className="grid place-items-center w-7 h-7 rounded-md hover:bg-white/15">
                            <HeaderIcon d="M6 6l12 12M18 6L6 18" />
                        </button>
                    </div>
                </div>

                    {showAccess ? (
                        <AccessPanel />
                    ) : (
                        <>
                            <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto p-3 space-y-3">
                                {messages.length === 0 && (
                                    <div className="text-center text-sm text-gray-400 dark:text-slate-500 mt-8 px-4">
                                        <p className="mb-2 text-2xl">📋</p>
                                        <p>Name a release, submittal, or project — lifecycle summaries, look-aheads, and print-ready PDFs.</p>
                                        <p className="mt-2 text-xs">e.g. &quot;summarize 290-153&quot; or &quot;3-week look-ahead PDF for Novel Flatiron&quot;</p>
                                        {voiceReady && (
                                            <p className="mt-2 text-xs">
                                                Or press the mic and just ask
                                                {liveReady && <> \u2014 the bars start a live conversation</>}.
                                            </p>
                                        )}
                                    </div>
                                )}
                                {messages.map((m, i) => (
                                    <div key={m.id || i} className={m.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
                                        <div className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm break-words ${m.role === 'user'
                                            ? 'bg-accent-500 text-white rounded-br-sm whitespace-pre-wrap'
                                            : 'bg-gray-100 dark:bg-slate-700 text-gray-800 dark:text-slate-100 rounded-bl-sm'}`}>
                                            {m.kind === 'proposal' ? (
                                                <ChangeProposalCard
                                                    proposal={m.proposal}
                                                    disabled={m.proposalCancelled}
                                                    outcome={m.proposalOutcome}
                                                    onApplied={(result) => {
                                                        if (pendingProposalRef.current === m.proposal) {
                                                            pendingProposalRef.current = null;
                                                        }
                                                        setMessages((prev) => prev.map((x) => (
                                                            x.id === m.id ? { ...x, proposalOutcome: result } : x
                                                        )));
                                                        notifyAppliedRef.current?.(describeOutcome(m.proposal, result));
                                                    }}
                                                    registerConfirm={(fn) => {
                                                        if (m.proposal === pendingProposalRef.current) confirmRef.current = fn;
                                                    }}
                                                />
                                            ) : m.role === 'assistant' ? <Markdown text={m.content} /> : m.content}
                                            {m.role === 'assistant' && (m.artifacts || []).map((art, j) => (
                                                <LookaheadPdfCard key={art.artifact_id || art.download_path || j} artifact={art} />
                                            ))}
                                            {m.role === 'assistant' && m.kind !== 'proposal' && voiceReady && <SpeakButton text={m.content} onSpeak={speak} />}
                                            {m.role === 'assistant' && <Metrics m={m.metrics} />}
                                        </div>
                                    </div>
                                ))}
                                {busy && (
                                    <div className="flex justify-start">
                                        <div className="bg-gray-100 dark:bg-slate-700 rounded-2xl rounded-bl-sm px-3 py-2 text-sm text-gray-400">
                                            <span className="inline-block animate-pulse">Carmen is thinking…</span>
                                        </div>
                                    </div>
                                )}
                            </div>

                            <div className="shrink-0 border-t border-hairline p-2 pb-3">
                                {(voiceNotice || recorder.error || live.error) && (
                                    <p className="px-1 pb-1.5 text-[11px] text-amber-600 dark:text-amber-400">
                                        {live.error || recorder.error || voiceNotice}
                                    </p>
                                )}
                                {liveOn ? (
                                    <div className="space-y-1.5">
                                        <div className="flex items-center gap-2">
                                            <div className="flex-1 flex items-center gap-2 h-9 px-3 rounded-xl bg-accent-50 dark:bg-accent-900/20 border border-accent-200 dark:border-accent-800/60">
                                                <span className={`w-2 h-2 rounded-full ${live.status === 'connecting' ? 'bg-amber-500' : live.speaking ? 'bg-accent-500' : 'bg-emerald-500'} animate-pulse`} />
                                                <span className="text-sm text-gray-700 dark:text-slate-200">
                                                    {live.status === 'connecting'
                                                        ? 'Connecting\u2026'
                                                        : live.speaking
                                                            ? 'Carmen is speaking'
                                                            : live.userSpeaking ? 'Listening\u2026' : 'Live \u2014 just talk'}
                                                </span>
                                                <span className="ml-auto tabular-nums text-xs text-gray-400 dark:text-slate-500">
                                                    {fmtClock(live.elapsed)}
                                                </span>
                                            </div>
                                            <button
                                                type="button"
                                                onClick={toggleLive}
                                                title="End the live call"
                                                className="shrink-0 h-9 px-4 rounded-xl bg-red-500 hover:bg-red-600 text-white text-sm font-medium"
                                            >
                                                End
                                            </button>
                                        </div>
                                        {(live.partial.user || live.partial.assistant) && (
                                            <p className="px-1 text-[11px] text-gray-400 dark:text-slate-500 line-clamp-2">
                                                {live.partial.assistant || live.partial.user}
                                            </p>
                                        )}
                                    </div>
                                ) : recorder.recording ? (
                                    <div className="flex items-center gap-2">
                                        <div className="flex-1 flex items-center gap-2 h-9 px-3 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/60">
                                            <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                                            <span className="text-sm text-red-700 dark:text-red-300">Listening…</span>
                                            <span className="ml-auto tabular-nums text-xs text-red-500/80">
                                                {fmtClock(recorder.seconds)} / {fmtClock(MAX_CLIP_SECONDS)}
                                            </span>
                                        </div>
                                        <button
                                            type="button"
                                            onClick={recorder.cancel}
                                            title="Discard this recording"
                                            className="shrink-0 h-9 px-3 rounded-xl border border-gray-200 dark:border-slate-600 text-sm text-gray-500 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700"
                                        >
                                            Cancel
                                        </button>
                                        <button
                                            type="button"
                                            onClick={recorder.stop}
                                            title="Send this recording to Carmen"
                                            className="shrink-0 h-9 px-4 rounded-xl bg-red-500 hover:bg-red-600 text-white text-sm font-medium inline-flex items-center gap-1.5"
                                        >
                                            <Icon d={STOP_D} size={13} />
                                            Send
                                        </button>
                                    </div>
                                ) : (
                                    <div className="flex items-end gap-2">
                                        {voiceReady && (
                                            <button
                                                type="button"
                                                onClick={recorder.start}
                                                disabled={busy}
                                                title="Ask Carmen out loud"
                                                aria-label="Ask Carmen out loud"
                                                className="shrink-0 h-9 w-9 grid place-items-center rounded-xl border border-gray-200 dark:border-slate-600 text-gray-500 dark:text-slate-300 hover:text-accent-500 hover:border-accent-400 disabled:opacity-40"
                                            >
                                                <Icon d={MIC_D} size={16} />
                                            </button>
                                        )}
                                        {liveReady && (
                                            <button
                                                type="button"
                                                onClick={toggleLive}
                                                disabled={busy}
                                                title="Start a live conversation \u2014 talk and interrupt freely"
                                                aria-label="Start a live conversation"
                                                className="shrink-0 h-9 w-9 grid place-items-center rounded-xl border border-gray-200 dark:border-slate-600 text-gray-500 dark:text-slate-300 hover:text-accent-500 hover:border-accent-400 disabled:opacity-40"
                                            >
                                                <Icon d={LIVE_D} size={16} />
                                            </button>
                                        )}
                                        <textarea
                                            ref={inputRef}
                                            value={input}
                                            onChange={(e) => setInput(e.target.value)}
                                            onKeyDown={onKeyDown}
                                            rows={1}
                                            placeholder={voiceReady ? 'Ask about your data — or press the mic…' : 'Ask about your data…'}
                                            className="flex-1 resize-none max-h-24 rounded-xl border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-gray-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-accent-400"
                                        />
                                        <button
                                            type="button"
                                            onClick={send}
                                            disabled={busy || !input.trim()}
                                            className="shrink-0 h-9 px-4 rounded-xl bg-accent-500 hover:bg-accent-600 disabled:opacity-40 text-white text-sm font-medium"
                                        >
                                            Send
                                        </button>
                                    </div>
                                )}
                            </div>
                        </>
                    )}

                    <ResizeHandles
                        active={resizing}
                        onBegin={beginResize}
                        onSnapHeight={snapHeight}
                        onSnapMax={snapMax}
                    />
                </div>
        </>,
        document.body,
    );
}
