/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Notes history rail on the release hub — every value the release's Notes field has held, newest first, read from the existing update_notes event stream.
 * exports:
 *   ReleaseNotesRail: Right-hand notes column. Props: job, release, currentNotes.
 * imports_from: [react, ../services/jobsApi]
 * imported_by: [frontend/src/components/ReleaseHubModal.jsx]
 * invariants:
 *   - Read-only. The Notes field is edited in the Job Log cell; this renders what that
 *     editing has already recorded. There is no second notes store — an earlier pass added
 *     one and it was removed as a duplicate of this event stream.
 *   - Source is /brain/events filtered to action === 'update_notes', the same feed
 *     NotesHistoryModal used before it was folded in here.
 *   - No-op edits (from === to) are dropped: saving a cell without changing it still emits
 *     an event, and showing those would pad the history with duplicates.
 * updated_by_agent: 2026-08-06T00:00:00Z
 */
import React, { useCallback, useEffect, useState } from 'react';

import { jobsApi } from '../services/jobsApi';

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

/** Pull the note text out of an event payload, tolerating the shapes /brain/events returns. */
const noteValues = (evt) => {
    const p = evt.payload || evt;
    const to = p.to ?? p.new ?? p.new_value ?? p.notes ?? null;
    const from = p.from ?? p.old ?? p.old_value ?? null;
    return { to, from };
};

function Entry({ author, at, body, current, cleared }) {
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

export function ReleaseNotesRail({ job, release, currentNotes }) {
    const [entries, setEntries] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const load = useCallback(() => {
        if (job == null || !release) { setLoading(false); return; }
        setLoading(true);
        jobsApi.getNotesHistory(job, release, 200)
            .then((data) => {
                const raw = Array.isArray(data) ? data : (data?.events || []);
                const notes = raw
                    .filter((e) => e.action === 'update_notes')
                    .map((e) => {
                        const { to, from } = noteValues(e);
                        return {
                            id: e.id,
                            // /brain/events names the author `user_name`; `source`
                            // is the SYSTEM that made the change (Brain / Trello),
                            // so it's only the fallback when no person is attached.
                            author: e.user_name || e.source || 'Brain',
                            at: e.created_at || e.timestamp,
                            body: (to ?? '').toString(),
                            from: (from ?? '').toString(),
                        };
                    })
                    // A save that didn't change anything still emits an event.
                    .filter((n) => n.body !== n.from);
                setEntries(notes);
                setError(null);
            })
            .catch(() => setError('Could not load notes history.'))
            .finally(() => setLoading(false));
    }, [job, release]);

    useEffect(() => { load(); }, [load]);

    const current = (currentNotes ?? '').toString().trim();
    // The newest event usually IS the current note. When it is, don't print the
    // same text twice — badge that entry as Current instead.
    const newestMatchesField = entries.length > 0 && entries[0].body.trim() === current;
    const showFieldOnTop = current !== '' && !newestMatchesField;

    return (
        <div className="flex flex-col min-h-0 border-l border-hairline bg-surface-2">
            <div className="shrink-0 flex items-center border-b border-hairline" style={{ gap: 8, padding: '12px 16px 10px' }}>
                <span className="text-jl-label font-bold uppercase text-ink-3">Notes</span>
                <span className="font-mono text-ink-3" style={{ fontSize: 11 }}>
                    {entries.length + (showFieldOnTop ? 1 : 0)}
                </span>
                <div className="flex-1" />
                <span className="text-ink-3" style={{ fontSize: 10.5 }}>Newest first</span>
            </div>

            <div className="flex-1 min-h-0 overflow-auto" style={{ padding: '12px 16px' }}>
                {loading && <p className="text-jl-2 text-ink-3 italic">Loading notes…</p>}
                {error && <p className="text-jl-2" style={{ color: 'var(--fl-red-fg)' }}>{error}</p>}

                {/* The field can hold a note older than the event stream's window, or one
                    written before events were recorded — show it rather than imply
                    the release has no note. */}
                {!loading && showFieldOnTop && (
                    <Entry author="Job Log" at={null} body={current} current />
                )}

                {!loading && !error && entries.map((n, i) => (
                    <Entry
                        key={n.id ?? i}
                        author={n.author}
                        at={n.at}
                        body={n.body}
                        cleared={n.body.trim() === ''}
                        current={i === 0 && newestMatchesField}
                    />
                ))}

                {!loading && !error && entries.length === 0 && !showFieldOnTop && (
                    <p className="text-jl-2 text-ink-3 italic">No notes on this release yet.</p>
                )}
            </div>

            <div className="shrink-0 border-t border-hairline bg-surface" style={{ padding: '10px 14px 12px' }}>
                <p className="text-ink-3" style={{ fontSize: 11, lineHeight: 1.4 }}>
                    Notes are edited in the Job Log's Notes column. Every change lands here.
                </p>
            </div>
        </div>
    );
}

export default ReleaseNotesRail;
