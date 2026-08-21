/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Flag-gated read-only chat assistant ("Carmen"). Chrome owns a circular CM
 *          launcher next to the notification bell; this module renders that circle
 *          and a top-down expandable modal. Answers DB questions, shows cost/time/token
 *          metrics, and surfaces look-ahead PDFs. Admins get an access-management panel.
 * exports:
 *   CarmenButton: circular CM launcher for AppShell (header + upper-right pod).
 *   BBChatWidget: default. Props: { enabled, isAdmin, open, onClose, anchorRef }. Null when !enabled || !open.
 * imports_from: [react, ../services/bbChatApi, ./carmen/LookaheadPdfCard]
 * imported_by: [components/AppShell.jsx]
 * invariants:
 *   - Renders nothing unless `enabled` (the caller passes user.is_carmen_chat).
 *   - Read-only: the UI never asks the server to mutate data.
 *   - No floating bottom bubble — the launcher sits next to the notification bell.
 *   - Panel drops from the CM bubble (upper right) and grows down/left; it does not cover the last Job Log row.
 */
import { useState, useRef, useEffect, useCallback, forwardRef } from 'react';
import { createPortal } from 'react-dom';
import { sendMessage, listAccessUsers, setUserAccess } from '../services/bbChatApi';
import LookaheadPdfCard, { extractLookaheadArtifacts } from './carmen/LookaheadPdfCard';

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
        setMessages((prev) => [...prev, { role: 'user', content: text }]);
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

    const newChat = () => { setMessages([]); setConversationId(null); };

    const closePanel = () => {
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
                        {!showAccess && <span className="text-[11px] opacity-80 hidden sm:inline">read-only</span>}
                    </div>
                    <div className="flex items-center gap-0.5">
                        {showAccess ? (
                            <button type="button" onClick={() => setShowAccess(false)} title="Back to chat" aria-label="Back to chat" className="grid place-items-center w-7 h-7 rounded-md hover:bg-white/15">
                                <HeaderIcon d="M15 19l-7-7 7-7" />
                            </button>
                        ) : (
                            <>
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
                                    </div>
                                )}
                                {messages.map((m, i) => (
                                    <div key={i} className={m.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
                                        <div className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm break-words ${m.role === 'user'
                                            ? 'bg-accent-500 text-white rounded-br-sm whitespace-pre-wrap'
                                            : 'bg-gray-100 dark:bg-slate-700 text-gray-800 dark:text-slate-100 rounded-bl-sm'}`}>
                                            {m.role === 'assistant' ? <Markdown text={m.content} /> : m.content}
                                            {m.role === 'assistant' && (m.artifacts || []).map((art, j) => (
                                                <LookaheadPdfCard key={art.artifact_id || art.download_path || j} artifact={art} />
                                            ))}
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

                            <div className="shrink-0 border-t border-hairline p-2 pb-3 flex items-end gap-2">
                                <textarea
                                    ref={inputRef}
                                    value={input}
                                    onChange={(e) => setInput(e.target.value)}
                                    onKeyDown={onKeyDown}
                                    rows={1}
                                    placeholder="Ask about your data…"
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
