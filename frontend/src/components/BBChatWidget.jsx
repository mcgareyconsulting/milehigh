/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Floating, flag-gated read-only chat assistant ("Carmen"). Renders a bubble on every
 *          page for users with Carmen-chat access; answers DB questions and shows per-answer
 *          cost/time/token metrics. Admins get an access-management panel. Look-ahead PDF
 *          tool results surface as LookaheadPdfCard (open/download with session auth).
 * exports:
 *   BBChatWidget: default. Props: { enabled: bool, isAdmin: bool }. Renders null when !enabled.
 * imports_from: [react, ../services/bbChatApi, ./carmen/LookaheadPdfCard]
 * imported_by: [components/AppShell.jsx]
 * invariants:
 *   - Renders nothing unless `enabled` (the caller passes user.is_carmen_chat).
 *   - Read-only: the UI never asks the server to mutate data.
 */
import { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { sendMessage, listAccessUsers, setUserAccess } from '../services/bbChatApi';
import LookaheadPdfCard, { extractLookaheadArtifacts } from './carmen/LookaheadPdfCard';

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

function AccessPanel({ onClose }) {
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
        <div className="absolute inset-0 z-10 flex flex-col bg-white dark:bg-slate-800 rounded-2xl">
            <div className="shrink-0 flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-slate-600">
                <span className="text-sm font-semibold text-gray-800 dark:text-slate-100">Carmen Chat access</span>
                <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-slate-200 text-lg leading-none">←</button>
            </div>
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
        </div>
    );
}

export default function BBChatWidget({ enabled, isAdmin }) {
    const [open, setOpen] = useState(false);
    const [showAccess, setShowAccess] = useState(false);
    const [messages, setMessages] = useState([]); // {role, content, metrics?}
    const [conversationId, setConversationId] = useState(null);
    const [input, setInput] = useState('');
    const [busy, setBusy] = useState(false);
    const scrollRef = useRef(null);

    useEffect(() => {
        if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }, [messages, busy]);

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

    const onKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    };

    if (!enabled) return null;

    // Portal to <body> so the widget isn't caught by the app's global
    // `#root > div > div { width:100% !important }` layout rule (and escapes any
    // ancestor overflow/stacking context).
    return createPortal(
        <>
            {/* Bubble */}
            <button
                type="button"
                onClick={() => setOpen((o) => !o)}
                className="fixed bottom-4 right-4 z-50 w-11 h-11 rounded-full bg-accent-500 hover:bg-accent-600 text-white flex items-center justify-center shadow-sm hover:shadow-md ring-1 ring-black/5 opacity-70 hover:opacity-100 focus:opacity-100 transition-all duration-200 motion-safe:hover:scale-105 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-400 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-slate-900"
                style={{ marginBottom: 'env(safe-area-inset-bottom)' }}
                aria-label={open ? 'Close Carmen chat' : 'Open Carmen chat'}
                title="Ask Carmen — read-only data assistant"
            >
                <span className={open ? 'text-base leading-none' : 'text-xs font-bold tracking-wider leading-none'}>
                    {open ? '✕' : 'CM'}
                </span>
            </button>

            {/* Panel — bounded to the viewport so it never runs off the top; height fits
                between the bubble (44px tall at bottom-4) and a top gap via max-h calc. */}
            {open && (
                <div
                    className="fixed z-50 bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-gray-200 dark:border-slate-600 flex flex-col overflow-hidden"
                    style={{
                        right: '1rem',
                        bottom: 'calc(4.75rem + env(safe-area-inset-bottom))',
                        // Geometry is inline so it can't be defeated by utility cascade/containing-block quirks:
                        // a 26rem card that shrinks to fit narrow (mobile) viewports with a margin each side.
                        width: 'min(26rem, calc(100vw - 2rem))',
                        height: '32rem',
                        maxHeight: 'calc(100dvh - 5.75rem)',
                    }}
                >
                    {showAccess ? (
                        <AccessPanel onClose={() => setShowAccess(false)} />
                    ) : (
                        <>
                            {/* Header */}
                            <div className="shrink-0 flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-slate-600 bg-gradient-to-r from-accent-500 to-accent-600 text-white">
                                <div className="flex items-center gap-2">
                                    <span className="font-bold">Carmen</span>
                                    <span className="text-xs opacity-80">read-only data assistant</span>
                                </div>
                                <div className="flex items-center gap-1">
                                    <button onClick={newChat} title="New chat" className="p-1.5 rounded hover:bg-white/20 text-sm">✎</button>
                                    {isAdmin && (
                                        <button onClick={() => setShowAccess(true)} title="Manage access" className="p-1.5 rounded hover:bg-white/20 text-sm">⚙</button>
                                    )}
                                </div>
                            </div>

                            {/* Messages */}
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

                            {/* Input */}
                            <div className="shrink-0 border-t border-gray-200 dark:border-slate-600 p-2 flex items-end gap-2">
                                <textarea
                                    value={input}
                                    onChange={(e) => setInput(e.target.value)}
                                    onKeyDown={onKeyDown}
                                    rows={1}
                                    placeholder="Ask about your data…"
                                    className="flex-1 resize-none max-h-24 rounded-xl border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-gray-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-accent-400"
                                />
                                <button
                                    onClick={send}
                                    disabled={busy || !input.trim()}
                                    className="shrink-0 h-9 px-4 rounded-xl bg-accent-500 hover:bg-accent-600 disabled:opacity-40 text-white text-sm font-medium"
                                >
                                    Send
                                </button>
                            </div>
                        </>
                    )}
                </div>
            )}
        </>,
        document.body,
    );
}
