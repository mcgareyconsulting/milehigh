import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useLocation } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useBananaBoyChat } from '../../hooks/useBananaBoyChat';
import { useVoiceRecorder } from '../../hooks/useVoiceRecorder';
import BananaBoyAnimation from './BananaBoyAnimation';
import { buildGoogleLinkUrl, messageForGoogleError } from '../../services/googleAuthApi';
import { setBananaBoyPreferences } from '../../services/bananaBoyApi';

export default function ChatModal({ user, onClose, onUserChange }) {
    const { messages, loading, sending, error, send, sendVoice, clear } = useBananaBoyChat(true);
    const { isRecording, error: recorderError, start: startRecording, stop: stopRecording } = useVoiceRecorder();
    const audioRef = useRef(null);
    const [draft, setDraft] = useState('');
    const [briefSaving, setBriefSaving] = useState(false);
    const listRef = useRef(null);
    const textareaRef = useRef(null);
    const location = useLocation();
    const gmailLinked = !!user?.gmail_linked;
    const briefOn = !!user?.wants_daily_brief;
    const params = new URLSearchParams(location.search);
    const googleErrorCode = params.get('google_error');
    const googleErrorMsg = googleErrorCode ? messageForGoogleError(googleErrorCode) : null;
    const justConnected = params.get('gmail_connected') === '1';

    const handleConnectGmail = () => {
        const next = window.location.pathname + window.location.search;
        window.location.href = buildGoogleLinkUrl(next);
    };

    const handleToggleBrief = async () => {
        if (briefSaving) return;
        setBriefSaving(true);
        try {
            await setBananaBoyPreferences({ wants_daily_brief: !briefOn });
            if (onUserChange) await onUserChange();
        } catch (e) {
            // Silent — toggle just won't flip if the API rejects.
        } finally {
            setBriefSaving(false);
        }
    };

    useEffect(() => {
        if (justConnected && onUserChange) onUserChange();
    }, [justConnected, onUserChange]);

    useEffect(() => {
        if (listRef.current) {
            listRef.current.scrollTop = listRef.current.scrollHeight;
        }
    }, [messages, sending]);

    useEffect(() => {
        textareaRef.current?.focus();
    }, []);

    const handleSubmit = async (e) => {
        e?.preventDefault();
        const text = draft.trim();
        if (!text || sending) return;
        setDraft('');
        await send(text);
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit();
        }
    };

    const handleClear = async () => {
        if (messages.length === 0) return;
        await clear();
    };

    const playReply = (audioB64, audioMime) => {
        if (!audioB64) return;
        try {
            if (audioRef.current) {
                audioRef.current.pause();
                audioRef.current = null;
            }
            const a = new Audio(`data:${audioMime || 'audio/mpeg'};base64,${audioB64}`);
            audioRef.current = a;
            a.play().catch(() => { /* user gesture issue — silently skip */ });
        } catch {
            /* ignore playback errors */
        }
    };

    const handleVoiceStart = async (e) => {
        e?.preventDefault();
        if (sending || isRecording) return;
        await startRecording();
    };

    const handleVoiceStop = async (e) => {
        e?.preventDefault();
        if (!isRecording) return;
        const blob = await stopRecording();
        if (!blob || blob.size === 0) return;
        const ext = (blob.type && blob.type.includes('mp4')) ? 'mp4' : 'webm';
        const data = await sendVoice(blob, `voice.${ext}`);
        if (data?.audio_b64) playReply(data.audio_b64, data.audio_mime);
    };

    useEffect(() => () => {
        if (audioRef.current) {
            audioRef.current.pause();
            audioRef.current = null;
        }
    }, []);

    return createPortal(
        <div
            className="fixed bottom-20 right-6 z-50 w-[35rem] max-w-[calc(100vw-2rem)] h-[42rem] max-h-[calc(100vh-6rem)] bg-white dark:bg-slate-800 rounded-xl shadow-2xl border border-gray-200 dark:border-slate-700 flex flex-col"
            role="dialog"
            aria-label="Banana Boy chat"
        >
            <header className="relative border-b border-gray-200 dark:border-slate-700 bg-[#f5f1e8] dark:bg-slate-900 overflow-hidden">
                <BananaBoyAnimation enabled={true} className="h-24 w-full" />
                <div className="absolute top-2 left-3 right-2 z-10 flex items-center justify-between text-sm">
                    <span className="font-semibold text-gray-900 dark:text-slate-100 drop-shadow-sm">Banana Boy</span>
                    <div className="flex items-center gap-2">
                        <button
                            type="button"
                            onClick={handleToggleBrief}
                            disabled={briefSaving}
                            title={
                                briefOn
                                    ? 'Daily 6:30am brief is on — click to turn off'
                                    : 'Get a daily 6:30am brief in this chat'
                            }
                            className={
                                briefOn
                                    ? 'px-2 py-0.5 rounded bg-amber-100/90 dark:bg-amber-900/60 text-amber-900 dark:text-amber-200 hover:bg-amber-200/90 dark:hover:bg-amber-900/80 text-xs disabled:opacity-50'
                                    : 'px-2 py-0.5 rounded bg-white/70 dark:bg-slate-800/70 text-gray-700 dark:text-slate-200 hover:text-gray-900 dark:hover:text-slate-100 text-xs disabled:opacity-50'
                            }
                        >
                            {briefOn ? '☼ Daily brief' : 'Daily brief'}
                        </button>
                        <button
                            type="button"
                            onClick={handleConnectGmail}
                            title={
                                gmailLinked
                                    ? `Connected as ${user?.gmail_email || 'Gmail'} — click to reconnect or update permissions`
                                    : 'Connect Gmail'
                            }
                            className={
                                gmailLinked
                                    ? 'px-2 py-0.5 rounded bg-green-100/90 dark:bg-green-900/60 text-green-800 dark:text-green-200 hover:bg-green-200/90 dark:hover:bg-green-900/80 text-xs'
                                    : 'px-2 py-0.5 rounded bg-white/70 dark:bg-slate-800/70 text-gray-700 dark:text-slate-200 hover:text-gray-900 dark:hover:text-slate-100 text-xs'
                            }
                        >
                            {gmailLinked ? '✓ Gmail' : 'Connect Gmail'}
                        </button>
                        <button
                            type="button"
                            onClick={handleClear}
                            disabled={messages.length === 0}
                            className="px-2 py-0.5 rounded bg-white/70 dark:bg-slate-800/70 text-gray-600 dark:text-slate-300 hover:text-gray-900 dark:hover:text-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                            Clear
                        </button>
                    </div>
                </div>
            </header>

            <div ref={listRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
                {googleErrorMsg && (
                    <div className="text-xs rounded-md bg-amber-50 dark:bg-amber-900/30 px-3 py-2 text-amber-900 dark:text-amber-200 border border-amber-200 dark:border-amber-800">
                        {googleErrorMsg}
                    </div>
                )}
                {loading && (
                    <div className="text-sm text-gray-500 dark:text-slate-400">Loading…</div>
                )}
                {!loading && messages.length === 0 && (
                    <div className="text-sm text-gray-500 dark:text-slate-400">
                        Hi — I'm Banana Boy. Ask me anything.
                    </div>
                )}
                {messages.map((m) => (
                    <MessageBubble key={m.id} message={m} />
                ))}
                {sending && (
                    <div className="text-sm text-gray-500 dark:text-slate-400 italic">
                        {looksLikeComplianceQuery(messages)
                            ? 'Pulling the fab drawing and scanning for compliance issues — give it a sec…'
                            : 'Banana Boy is thinking…'}
                    </div>
                )}
                {isRecording && (
                    <div className="text-sm text-red-600 dark:text-red-400 italic flex items-center gap-2">
                        <span className="inline-block w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                        Listening… release to send
                    </div>
                )}
                {error && (
                    <div className="text-sm text-red-600 dark:text-red-400">{error}</div>
                )}
                {recorderError && !error && (
                    <div className="text-sm text-amber-700 dark:text-amber-400">{recorderError}</div>
                )}
            </div>

            <form onSubmit={handleSubmit} className="border-t border-gray-200 dark:border-slate-700 p-3 flex items-end gap-2">
                <textarea
                    ref={textareaRef}
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Message Banana Boy…"
                    rows={2}
                    className="flex-1 resize-none rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-gray-900 dark:text-slate-100 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent-500"
                    disabled={sending}
                />
                <button
                    type="button"
                    onMouseDown={handleVoiceStart}
                    onMouseUp={handleVoiceStop}
                    onMouseLeave={isRecording ? handleVoiceStop : undefined}
                    onTouchStart={handleVoiceStart}
                    onTouchEnd={handleVoiceStop}
                    disabled={sending}
                    title={isRecording ? 'Release to send' : 'Hold to talk'}
                    aria-pressed={isRecording}
                    className={
                        isRecording
                            ? 'px-3 py-2 rounded-lg text-white bg-red-500 hover:bg-red-600 select-none'
                            : 'px-3 py-2 rounded-lg text-white bg-gray-500 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed select-none'
                    }
                >
                    🎤
                </button>
                <button
                    type="submit"
                    disabled={sending || !draft.trim()}
                    className="px-4 py-2 rounded-lg font-medium text-sm bg-accent-500 hover:bg-accent-600 text-white disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    Send
                </button>
            </form>
        </div>,
        document.body
    );
}

const MD_COMPONENTS = {
    p: ({ node, ...props }) => <p className="mb-2 last:mb-0" {...props} />,
    ul: ({ node, ...props }) => <ul className="list-disc pl-5 mb-2 last:mb-0 space-y-0.5" {...props} />,
    ol: ({ node, ...props }) => <ol className="list-decimal pl-5 mb-2 last:mb-0 space-y-0.5" {...props} />,
    li: ({ node, ...props }) => <li className="leading-snug" {...props} />,
    h1: ({ node, ...props }) => <h1 className="text-base font-semibold mt-2 mb-1" {...props} />,
    h2: ({ node, ...props }) => <h2 className="text-sm font-semibold mt-2 mb-1" {...props} />,
    h3: ({ node, ...props }) => <h3 className="text-sm font-semibold mt-1 mb-1" {...props} />,
    code: ({ node, inline, className, children, ...props }) =>
        inline ? (
            <code className="px-1 py-0.5 rounded bg-black/10 dark:bg-white/10 text-[0.85em] font-mono" {...props}>
                {children}
            </code>
        ) : (
            <pre className="my-2 p-2 rounded bg-black/10 dark:bg-white/10 overflow-x-auto text-xs">
                <code className={className} {...props}>{children}</code>
            </pre>
        ),
    a: ({ node, ...props }) => (
        <a className="underline" target="_blank" rel="noreferrer" {...props} />
    ),
    table: ({ node, ...props }) => (
        <div className="overflow-x-auto my-2">
            <table className="text-xs border-collapse" {...props} />
        </div>
    ),
    th: ({ node, ...props }) => <th className="border border-gray-300 dark:border-slate-600 px-2 py-1 text-left font-medium" {...props} />,
    td: ({ node, ...props }) => <td className="border border-gray-300 dark:border-slate-600 px-2 py-1" {...props} />,
};

// Best-effort heuristic: if the user's latest message names a job-release
// (e.g. "480-299") AND uses a compliance/code/drawing keyword, surface a
// scan-specific "this takes a sec" hint while we wait. Pure UX — backend
// makes its own dispatch decision via the LLM.
const COMPLIANCE_KEYWORDS = /\b(compliance|code|codes|scan|drawing|drawings|fab|fc|ibc|ada|aisc|aws|osha|guard|guardrail|handrail|riser|tread)\b/i;
const JOB_RELEASE = /\b\d{2,4}\s*[-_ ]\s*\d{2,4}\b/;

function looksLikeComplianceQuery(messages) {
    if (!messages || messages.length === 0) return false;
    // Walk back to the most recent user message.
    for (let i = messages.length - 1; i >= 0; i -= 1) {
        const m = messages[i];
        if (m.role !== 'user') continue;
        const text = m.content || '';
        return JOB_RELEASE.test(text) && COMPLIANCE_KEYWORDS.test(text);
    }
    return false;
}

function formatUsage(usage) {
    if (!usage || !usage.calls || usage.calls.length === 0) return null;
    const cost = usage.total_cost_usd || 0;
    const seconds = (usage.total_duration_ms || 0) / 1000;
    const totalIn = usage.calls.reduce((a, c) => a + (c.input_tokens || 0), 0);
    const totalOut = usage.calls.reduce((a, c) => a + (c.output_tokens || 0), 0);
    const ops = usage.calls.map((c) => c.operation).filter(Boolean);
    const opStr = ops.length > 1 ? ` · ${ops.join(' + ')}` : '';
    return `${seconds.toFixed(1)}s · ${totalIn.toLocaleString()} in / ${totalOut.toLocaleString()} out · $${cost.toFixed(4)}${opStr}`;
}

function MessageBubble({ message }) {
    const isUser = message.role === 'user';
    const base = 'rounded-lg px-3 py-2 text-sm break-words max-w-[85%]';
    const userCls = `${base} whitespace-pre-wrap bg-accent-500 text-white ml-auto ${message.failed ? 'opacity-60 ring-2 ring-red-400' : ''}`;
    const assistantCls = `${base} bg-gray-100 dark:bg-slate-700 text-gray-900 dark:text-slate-100`;
    const usageLine = !isUser ? formatUsage(message.usage) : null;
    return (
        <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
            <div className={isUser ? userCls : assistantCls}>
                {isUser ? (
                    message.content
                ) : (
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>
                        {message.content}
                    </ReactMarkdown>
                )}
                {message.failed && (
                    <div className="text-xs text-red-200 mt-1">failed to send</div>
                )}
            </div>
            {usageLine && (
                <div className="text-[10px] text-gray-400 dark:text-slate-500 mt-0.5 ml-1 font-mono">
                    {usageLine}
                </div>
            )}
        </div>
    );
}
