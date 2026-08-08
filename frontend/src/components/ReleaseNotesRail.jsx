/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Right rail on the release hub — a single newest-first timeline of notes
 *   intermingled with stage and date changes (who + when), all from ReleaseEvents.
 * exports:
 *   ReleaseNotesRail: Right-hand activity column. Props: job, release, currentNotes.
 * imports_from: [react, ../services/jobsApi, ./ReleaseActivityFeed]
 * imported_by: [frontend/src/components/ReleaseHubModal.jsx]
 * invariants:
 *   - Read-only. Notes are still edited in the Job Log cell; stage/date writes stay
 *     on their own controls. This is a filtered render of /brain/events only.
 *   - Notes keep the full-body treatment; system updates render as compact chips so
 *     the feed stays scannable when both kinds mix.
 *   - No-op edits (from === to) are dropped.
 * updated_by_agent: 2026-08-08T00:00:00Z
 */
import React, { useCallback, useEffect, useState } from 'react';

import { jobsApi } from '../services/jobsApi';
import { ACTIVITY_ACTIONS, summarizeActivity } from './ReleaseActivityFeed';

const initialsOf = (name) => {
    const s = (name || '').toString().trim();
    if (!s) return '?';
    const parts = s.split(/\s+/);
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
};

const formatStamp = (iso) => {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d)) return '';
    const sameDay = d.toDateString() === new Date().toDateString();
    const time = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    if (sameDay) return `Today · ${time}`;
    return `${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })} · ${time}`;
};

const noteValues = (evt) => {
    const p = evt.payload || evt;
    const to = p.to ?? p.new ?? p.new_value ?? p.notes ?? null;
    const from = p.from ?? p.old ?? p.old_value ?? null;
    return { to, from };
};

const fromTo = (payload = {}) => {
    const from = payload.from ?? payload.old ?? payload.old_value ?? null;
    const to = payload.to ?? payload.new ?? payload.new_value ?? null;
    return { from, to };
};

/** Short kind label for the chip on non-note rows. */
const kindLabel = (action) => {
    if (action === 'update_stage') return 'Stage';
    if (action === 'update_ship_date') return 'Ship';
    if (action === 'update_start_install' || action === 'clear_hard_date') return 'Install';
    return 'Update';
};

const sortMs = (iso) => {
    if (!iso) return 0;
    const t = new Date(iso).getTime();
    return Number.isFinite(t) ? t : 0;
};

function NoteEntry({ author, at, body, current, cleared }) {
    return (
        <div style={{ marginBottom: 14 }}>
            <div className="flex items-start" style={{ gap: 9 }}>
                <div
                    className="shrink-0 grid place-items-center font-bold"
                    style={{
                        width: 26, height: 26, borderRadius: '50%', fontSize: 10.5,
                        background: current ? 'var(--accent)' : 'var(--accent-soft)',
                        color: current ? 'var(--accent-ink)' : 'var(--accent)',
                    }}
                >
                    {initialsOf(author)}
                </div>
                <div className="min-w-0 flex-1">
                    <div className="flex items-baseline flex-wrap" style={{ gap: 7 }}>
                        <span className="font-bold text-ink" style={{ fontSize: 12.5 }}>
                            {author || 'Unknown'}
                        </span>
                        <span className="font-mono text-ink-3" style={{ fontSize: 11 }}>
                            {formatStamp(at)}
                        </span>
                        {current && (
                            <span
                                className="font-bold uppercase"
                                style={{
                                    fontSize: 9.5, letterSpacing: '.05em', padding: '1px 5px',
                                    borderRadius: 4, background: 'var(--accent-soft)', color: 'var(--accent)',
                                }}
                            >
                                Current
                            </span>
                        )}
                        <span
                            className="font-bold uppercase text-ink-3"
                            style={{
                                fontSize: 9.5, letterSpacing: '.05em', padding: '1px 5px',
                                borderRadius: 4, background: 'var(--surface)', border: '1px solid var(--hairline)',
                            }}
                        >
                            Note
                        </span>
                    </div>
                    <div
                        className={`whitespace-pre-wrap break-words ${cleared ? 'text-ink-3 italic' : 'text-ink'}`}
                        style={{ marginTop: 3, fontSize: 12.5, lineHeight: 1.45 }}
                    >
                        {cleared ? 'Note cleared' : body}
                    </div>
                </div>
            </div>
        </div>
    );
}

/** Compact system update — sits in the same timeline as notes without competing for weight. */
function UpdateEntry({ author, at, text, kind }) {
    return (
        <div style={{ marginBottom: 12 }}>
            <div className="flex items-start" style={{ gap: 9 }}>
                <div
                    className="shrink-0 grid place-items-center font-bold text-ink-3"
                    style={{
                        width: 26, height: 26, borderRadius: '50%', fontSize: 10.5,
                        background: 'var(--surface)',
                        border: '1px solid var(--hairline-strong)',
                    }}
                >
                    {kind === 'Stage' ? 'S' : kind === 'Ship' ? 'Sh' : kind === 'Install' ? 'In' : '·'}
                </div>
                <div className="min-w-0 flex-1">
                    <div className="flex items-baseline flex-wrap" style={{ gap: 7 }}>
                        <span className="font-bold text-ink" style={{ fontSize: 12.5 }}>
                            {author || 'System'}
                        </span>
                        <span className="font-mono text-ink-3" style={{ fontSize: 11 }}>
                            {formatStamp(at)}
                        </span>
                        <span
                            className="font-bold uppercase"
                            style={{
                                fontSize: 9.5, letterSpacing: '.05em', padding: '1px 5px',
                                borderRadius: 4,
                                background: 'var(--surface)',
                                border: '1px solid var(--hairline)',
                                color: 'var(--text-2)',
                            }}
                        >
                            {kind}
                        </span>
                    </div>
                    <div
                        className="text-ink-2"
                        style={{ marginTop: 3, fontSize: 12.5, lineHeight: 1.45 }}
                    >
                        {text}
                    </div>
                </div>
            </div>
        </div>
    );
}

/**
 * Turn the raw /brain/events list into a mixed timeline: notes + stage/date updates.
 * Newest first. Exported for unit tests.
 */
export function buildTimeline(rawEvents, { currentNotes = '' } = {}) {
    const items = [];

    for (const e of rawEvents || []) {
        const at = e.created_at || e.timestamp;
        const author = e.user_name || e.source || 'Brain';
        const payload = e.payload || {};
        const { from, to } = fromTo(payload);
        if (from != null && to != null && String(from) === String(to)) continue;

        if (e.action === 'update_notes') {
            const { to: noteTo, from: noteFrom } = noteValues(e);
            const body = (noteTo ?? '').toString();
            const prev = (noteFrom ?? '').toString();
            if (body === prev) continue;
            items.push({
                id: e.id,
                kind: 'note',
                author,
                at,
                body,
                sortKey: sortMs(at),
            });
            continue;
        }

        if (ACTIVITY_ACTIONS.has(e.action)) {
            const summary = summarizeActivity(e);
            if (!summary) continue;
            items.push({
                id: e.id,
                kind: 'update',
                updateKind: kindLabel(e.action),
                author: summary.author,
                at,
                text: summary.text,
                sortKey: sortMs(at),
            });
        }
    }

    items.sort((a, b) => b.sortKey - a.sortKey || (b.id || 0) - (a.id || 0));

    const current = (currentNotes ?? '').toString().trim();
    const firstNote = items.find((i) => i.kind === 'note');
    const newestNoteMatches = firstNote && firstNote.body.trim() === current;
    const orphanNote = current !== '' && !newestNoteMatches
        ? { id: 'field-current', kind: 'note', author: 'Job Log', at: null, body: current, current: true, sortKey: Number.MAX_SAFE_INTEGER }
        : null;

    if (orphanNote) items.unshift(orphanNote);

    // Badge the newest matching note as Current (same behavior as the old rail).
    if (newestNoteMatches && firstNote) {
        firstNote.current = true;
    }

    return items;
}

export function ReleaseNotesRail({ job, release, currentNotes }) {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const load = useCallback(() => {
        if (job == null || !release) { setLoading(false); return; }
        setLoading(true);
        jobsApi.getNotesHistory(job, release, 200)
            .then((data) => {
                const raw = Array.isArray(data) ? data : (data?.events || []);
                setItems(buildTimeline(raw, { currentNotes }));
                setError(null);
            })
            .catch(() => setError('Could not load activity.'))
            .finally(() => setLoading(false));
    }, [job, release, currentNotes]);

    useEffect(() => { load(); }, [load]);

    const noteCount = items.filter((i) => i.kind === 'note').length;
    const updateCount = items.filter((i) => i.kind === 'update').length;

    return (
        <div className="flex flex-col min-h-0 border-l border-hairline bg-surface-2">
            <div className="shrink-0 flex items-center border-b border-hairline" style={{ gap: 8, padding: '12px 16px 10px' }}>
                <span className="text-jl-label font-bold uppercase text-ink-3">Activity</span>
                <span className="font-mono text-ink-3" style={{ fontSize: 11 }} title={`${noteCount} notes · ${updateCount} updates`}>
                    {items.length}
                </span>
                <div className="flex-1" />
                <span className="text-ink-3" style={{ fontSize: 10.5 }}>Newest first</span>
            </div>

            <div className="flex-1 min-h-0 overflow-auto" style={{ padding: '12px 16px' }}>
                {loading && <p className="text-jl-2 text-ink-3 italic">Loading activity…</p>}
                {error && <p className="text-jl-2" style={{ color: 'var(--fl-red-fg)' }}>{error}</p>}

                {!loading && !error && items.map((item, i) => (
                    item.kind === 'note' ? (
                        <NoteEntry
                            key={item.id ?? `n-${i}`}
                            author={item.author}
                            at={item.at}
                            body={item.body}
                            cleared={item.body.trim() === ''}
                            current={!!item.current}
                        />
                    ) : (
                        <UpdateEntry
                            key={item.id ?? `u-${i}`}
                            author={item.author}
                            at={item.at}
                            text={item.text}
                            kind={item.updateKind}
                        />
                    )
                ))}

                {!loading && !error && items.length === 0 && (
                    <p className="text-jl-2 text-ink-3 italic">
                        No notes or date/stage changes on this release yet.
                    </p>
                )}
            </div>

            <div className="shrink-0 border-t border-hairline bg-surface" style={{ padding: '10px 14px 12px' }}>
                <p className="text-ink-3" style={{ fontSize: 11, lineHeight: 1.4 }}>
                    Notes are edited in the Job Log. Stage and date changes show up here
                    automatically — full undo history is on the Change Log tab.
                </p>
            </div>
        </div>
    );
}

export default ReleaseNotesRail;
