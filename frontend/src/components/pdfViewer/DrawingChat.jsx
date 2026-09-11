/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Carmen chat scoped to the open drawing version — the fast path beside the
 *   heavy review. Sits under the pinned findings in the viewer dock's Review tab.
 * exports:
 *   DrawingChat: props { releaseId, versionId, enabled, onCite }
 * imports_from: [react, ../../services/jobsApi]
 * imported_by: [frontend/src/components/pdfViewer/ReviewTab.jsx]
 * invariants:
 *   - Session-only: turns live in component state and are dropped when the version
 *     changes or the modal closes — the server persists nothing
 *   - The client sends prior turns back as `history`; the server re-reads the cached PDF
 *   - Answers render light markdown (**bold**, - bullets, `code`); a "p<N>" citation
 *     inside any of them becomes a jump chip
 *   - Idle it is bottom-docked (mt-auto) and only as tall as its composer; with a thread
 *     running it claims flex-1 so the transcript, not empty findings, owns the dock
 * updated_by_agent: 2026-09-07T00:00:00Z
 */
import React, { useEffect, useRef, useState } from 'react';

import { jobsApi } from '../../services/jobsApi';

const SUGGESTIONS = [
    'Summarize this drawing set.',
    'What changed in the markups on this version?',
    'Does every hole have hardware that fits, and do the counts match?',
];

//: "…see p4." / "(p12)" — the model cites sheets by label but often anchors a page too.
//  Built per call: a global regex carries lastIndex between uses.
const pageCiteRe = () => /\bp(?:age\s*)?(\d{1,3})\b/gi;

//: `**bold**` and `` `code` ``, in one pass so neither eats the other's delimiters.
const INLINE_RE = /\*\*(.+?)\*\*|`([^`]+)`/g;

const BULLET_RE = /^\s*[-*•]\s+(.*)$/;

const fmtCost = (usd) => {
    if (!usd && usd !== 0) return null;
    return usd < 0.01 ? `${(usd * 100).toFixed(2)}¢` : `$${usd.toFixed(2)}`;
};

/** Page citations in a run of plain text, as clickable jump chips. */
function withCites(text, onCite, keyBase) {
    if (typeof onCite !== 'function') return [text];
    const re = pageCiteRe();
    const parts = [];
    let last = 0;
    let m;
    while ((m = re.exec(text)) !== null) {
        const page = parseInt(m[1], 10);
        if (!page) continue;
        if (m.index > last) parts.push(text.slice(last, m.index));
        parts.push(
            <button
                key={`${keyBase}-cite-${m.index}`}
                type="button"
                onClick={() => onCite(page, null)}
                className="border-0 cursor-pointer font-bold align-baseline"
                style={{
                    fontSize: 11.5, padding: '0 6px', borderRadius: 999,
                    background: '#fef3c7', color: '#b45309',
                }}
                title={`Jump to page ${page}`}
            >
                {m[0]} ↵
            </button>
        );
        last = m.index + m[0].length;
    }
    if (!parts.length) return [text];
    parts.push(text.slice(last));
    return parts;
}

/**
 * Inline markdown for one line. Carmen writes **bold** labels and `code` naturally;
 * rendering them as literal asterisks is what the raw text looked like before.
 */
function renderInline(text, onCite, keyBase) {
    const out = [];
    const re = INLINE_RE;
    re.lastIndex = 0;
    let last = 0;
    let m;
    while ((m = re.exec(text)) !== null) {
        if (m.index > last) out.push(...withCites(text.slice(last, m.index), onCite, `${keyBase}-${last}`));
        if (m[1] !== undefined) {
            out.push(
                <strong key={`${keyBase}-b-${m.index}`} className="font-semibold">
                    {withCites(m[1], onCite, `${keyBase}-b${m.index}`)}
                </strong>
            );
        } else {
            out.push(
                <code
                    key={`${keyBase}-c-${m.index}`}
                    className="font-mono bg-surface-2 rounded"
                    style={{ padding: '0 4px', fontSize: '.92em' }}
                >
                    {m[2]}
                </code>
            );
        }
        last = m.index + m[0].length;
    }
    if (last < text.length) out.push(...withCites(text.slice(last), onCite, `${keyBase}-${last}`));
    return out;
}

/**
 * Block-level render of an answer: bullet runs become a real list, everything else a
 * paragraph. Deliberately small — bold, bullets, inline code and blank-line breaks are
 * what Carmen actually emits in a short answer; headings and tables are not, and the
 * system prompt steers her away from them.
 */
function AnswerBody({ text, onCite }) {
    const lines = (text || '').split('\n');
    const blocks = [];
    let bullets = null;
    let para = [];

    const flushPara = () => {
        if (!para.length) return;
        const body = para.join(' ');
        blocks.push(
            <p key={`p${blocks.length}`} style={{ margin: blocks.length ? '6px 0 0' : 0 }}>
                {renderInline(body, onCite, `p${blocks.length}`)}
            </p>
        );
        para = [];
    };
    const flushBullets = () => {
        if (!bullets) return;
        const items = bullets;
        blocks.push(
            <ul key={`u${blocks.length}`} style={{ margin: '4px 0 0', paddingLeft: 16, listStyle: 'disc' }}>
                {items.map((item, i) => (
                    <li key={i} style={{ marginTop: i ? 2 : 0 }}>
                        {renderInline(item, onCite, `u${blocks.length}-${i}`)}
                    </li>
                ))}
            </ul>
        );
        bullets = null;
    };

    lines.forEach((line) => {
        const bullet = line.match(BULLET_RE);
        if (bullet) {
            flushPara();
            bullets = bullets || [];
            bullets.push(bullet[1]);
            return;
        }
        flushBullets();
        if (!line.trim()) flushPara();
        else para.push(line.trim());
    });
    flushPara();
    flushBullets();

    return <>{blocks}</>;
}

export function DrawingChat({ releaseId, versionId, enabled = false, onCite = null }) {
    const [turns, setTurns] = useState([]);      // [{role, content, metrics?}]
    const [draft, setDraft] = useState('');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);
    const scrollRef = useRef(null);

    // A chat is about ONE drawing. Switching versions starts a new thread rather than
    // carrying answers about the old PDF into questions about the new one.
    useEffect(() => {
        setTurns([]);
        setDraft('');
        setError(null);
    }, [versionId]);

    useEffect(() => {
        const el = scrollRef.current;
        if (el) el.scrollTop = el.scrollHeight;
    }, [turns, busy]);

    const send = async (text) => {
        const message = (text ?? draft).trim();
        if (!message || busy || !versionId) return;
        const history = turns.map((t) => ({ role: t.role, content: t.content }));
        setTurns((prev) => [...prev, { role: 'user', content: message }]);
        setDraft('');
        setError(null);
        setBusy(true);
        try {
            const res = await jobsApi.carmenDrawingChat(releaseId, versionId, message, history);
            setTurns((prev) => [...prev, {
                role: 'assistant',
                content: res?.answer || '(no answer)',
                metrics: res?.metrics || null,
            }]);
        } catch (err) {
            setError(err?.message || 'Carmen could not answer that');
            // Drop the unanswered question so a retry doesn't double it into history.
            setTurns((prev) => prev.slice(0, -1));
            setDraft(message);
        } finally {
            setBusy(false);
        }
    };

    const onKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            send();
        }
    };

    if (!enabled) return null;

    const hasTurns = turns.length > 0;

    return (
        <div
            className={
                'flex flex-col min-h-0 border-t border-hairline '
                // Idle, mt-auto pins the composer to the bottom of the dock instead of
                // leaving it stranded mid-panel under an empty findings block. With a
                // thread running, the transcript takes every row the findings don't.
                + (hasTurns ? 'flex-1' : 'shrink-0 mt-auto')
            }
            style={{ background: 'var(--surface)' }}
        >
            <div
                className="shrink-0 flex items-center border-b border-hairline"
                style={{ gap: 8, padding: '8px 12px', background: 'var(--surface-2)' }}
            >
                <span
                    className="font-bold uppercase"
                    style={{ fontSize: 12, letterSpacing: '.06em', color: 'var(--text-2)' }}
                >
                    Ask Carmen
                </span>
                <span className="text-ink-3" style={{ fontSize: 11 }}>this drawing</span>
                {hasTurns && (
                    <button
                        type="button"
                        onClick={() => { setTurns([]); setError(null); }}
                        className="ml-auto bg-transparent border-0 cursor-pointer text-ink-3 hover:text-ink"
                        style={{ fontSize: 11.5 }}
                        title="Clear this thread (nothing is saved either way)"
                    >
                        Clear
                    </button>
                )}
            </div>

            {hasTurns && (
                <div
                    ref={scrollRef}
                    className="flex-1 min-h-0 overflow-y-auto"
                    style={{ padding: '10px 12px', minHeight: 200 }}
                >
                    <div className="space-y-2">
                        {turns.map((t, i) => (
                            t.role === 'user' ? (
                                <div key={i} className="flex justify-end">
                                    <p
                                        className="rounded-lg bg-surface-2 text-ink"
                                        style={{ padding: '6px 9px', fontSize: 13, maxWidth: '88%' }}
                                    >
                                        {t.content}
                                    </p>
                                </div>
                            ) : (
                                <div key={i}>
                                    <div
                                        className="text-ink break-words"
                                        style={{ fontSize: 13.5, lineHeight: 1.5 }}
                                    >
                                        <AnswerBody text={t.content} onCite={onCite} />
                                    </div>
                                    {t.metrics && (
                                        <p className="text-ink-3" style={{ fontSize: 10.5, marginTop: 3 }}>
                                            {[
                                                t.metrics.model,
                                                t.metrics.duration_ms ? `${(t.metrics.duration_ms / 1000).toFixed(1)}s` : null,
                                                fmtCost(t.metrics.cost_usd),
                                                t.metrics.cache_read_tokens ? 'cached' : null,
                                            ].filter(Boolean).join(' · ')}
                                        </p>
                                    )}
                                </div>
                            )
                        ))}
                        {busy && (
                            <p className="text-ink-3 italic" style={{ fontSize: 12.5 }}>Carmen is reading…</p>
                        )}
                    </div>
                </div>
            )}

            {!hasTurns && (
                <div className="shrink-0" style={{ padding: '8px 12px 0' }}>
                    <p className="text-ink-3" style={{ fontSize: 12, marginBottom: 6 }}>
                        Quick questions about the open version — seconds, not the full review.
                    </p>
                    <div className="flex flex-wrap" style={{ gap: 5 }}>
                        {SUGGESTIONS.map((s) => (
                            <button
                                key={s}
                                type="button"
                                onClick={() => send(s)}
                                disabled={busy}
                                className="border border-hairline bg-surface-2 cursor-pointer text-ink-2 hover:text-ink disabled:opacity-50"
                                style={{ fontSize: 11.5, padding: '3px 8px', borderRadius: 999 }}
                            >
                                {s}
                            </button>
                        ))}
                    </div>
                    {busy && (
                        <p className="text-ink-3 italic" style={{ fontSize: 12.5, marginTop: 6 }}>
                            Carmen is reading…
                        </p>
                    )}
                </div>
            )}

            {error && (
                <p style={{ fontSize: 11.5, color: 'var(--fl-red-bg)', padding: '6px 12px 0' }}>{error}</p>
            )}

            <div className="shrink-0 flex items-end" style={{ gap: 6, padding: '8px 12px' }}>
                <textarea
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={onKeyDown}
                    rows={2}
                    placeholder="Ask about this drawing…"
                    disabled={busy}
                    className="flex-1 rounded-md border border-hairline bg-surface text-ink resize-none disabled:opacity-60"
                    style={{ padding: '6px 8px', fontSize: 13 }}
                />
                <button
                    type="button"
                    onClick={() => send()}
                    disabled={busy || !draft.trim()}
                    className="shrink-0 border-0 cursor-pointer font-semibold text-white disabled:opacity-40"
                    style={{ fontSize: 12.5, padding: '7px 12px', borderRadius: 6, background: '#264093' }}
                >
                    {busy ? '…' : 'Ask'}
                </button>
            </div>
        </div>
    );
}

export default DrawingChat;
