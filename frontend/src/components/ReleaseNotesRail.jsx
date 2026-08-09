/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Right Activity rail on the release hub — day-grouped timeline of notes,
 *   stage, fab order, and date changes; + Note overwrites Job Log notes.
 * exports:
 *   ReleaseNotesRail: Right-hand activity column
 *   buildTimeline: pure transform of /brain/events → rail items (tests)
 *   groupByDay: pure day grouping helper (tests)
 * imports_from: [react, ../services/jobsApi, ../utils/stageTint, ./ReleaseActivityFeed]
 * imported_by: [frontend/src/components/ReleaseHubModal.jsx]
 * invariants:
 *   - Activity includes notes, stage, fab order, ship date, start install / hard clear
 *   - Notes are full history: every update_notes `to`, plus any `from` not already
 *     covered by an older event's `to` (so a first overwrite still shows prior text)
 *   - Same-user same-minute fab_order folds into a stage entry as "also Fab Order…"
 *   - Notes write via existing updateNotes (full field overwrite) + event history
 *   - No CURRENT badge; no-op edits (from === to) dropped
 * updated_by_agent: 2026-08-08T00:00:00Z
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';

import { jobsApi } from '../services/jobsApi';
import { stageTint } from '../utils/stageTint';
import {
    ACTIVITY_ACTIONS,
    formatDateValue,
    fromTo,
    summarizeActivity,
} from './ReleaseActivityFeed';

export const initialsOf = (name) => {
    const s = (name || '').toString().trim();
    if (!s) return '?';
    const parts = s.split(/\s+/);
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
};

/** Time only — day lives on the group divider. */
const formatTime = (iso) => {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d)) return '';
    return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
};

/** Day bucket key + display label: "TUE · APR 7". */
export const dayBucket = (iso) => {
    if (!iso) return { key: 'unknown', label: 'UNKNOWN DATE' };
    const d = new Date(iso);
    if (isNaN(d)) return { key: 'unknown', label: 'UNKNOWN DATE' };
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    const dow = d.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase();
    const mon = d.toLocaleDateString('en-US', { month: 'short' }).toUpperCase();
    const day = d.getDate();
    return { key, label: `${dow} · ${mon} ${day}` };
};

const noteValues = (evt) => {
    const p = evt.payload || evt;
    const to = p.to ?? p.new ?? p.new_value ?? p.notes ?? null;
    const from = p.from ?? p.old ?? p.old_value ?? null;
    return { to, from };
};

const sortMs = (iso) => {
    if (!iso) return 0;
    const t = new Date(iso).getTime();
    return Number.isFinite(t) ? t : 0;
};

/** Floor timestamp to minute for merge matching. */
const minuteKey = (iso) => {
    const t = sortMs(iso);
    if (!t) return 0;
    return Math.floor(t / 60000);
};

const authorKey = (name) => (name || '').toString().trim().toLowerCase();

function DayDivider({ label }) {
    return (
        <div className="flex items-center" style={{ gap: 8, margin: '14px 0 10px' }}>
            <span
                className="font-bold uppercase shrink-0"
                style={{ fontSize: 10, letterSpacing: '.04em', color: 'var(--text-3)' }}
            >
                {label}
            </span>
            <div className="flex-1 min-w-0" style={{ height: 1, background: 'var(--border)' }} />
        </div>
    );
}

function Avatar({ name }) {
    return (
        <div
            className="shrink-0 grid place-items-center font-bold"
            style={{
                width: 26,
                height: 26,
                borderRadius: '50%',
                fontSize: 10.5,
                background: 'var(--accent-soft)',
                color: 'var(--accent)',
            }}
        >
            {initialsOf(name)}
        </div>
    );
}

function EntryHeader({ author, at }) {
    return (
        <div className="flex items-baseline flex-wrap" style={{ gap: 7 }}>
            <span className="font-bold text-ink" style={{ fontSize: 12.5 }}>
                {author || 'Unknown'}
            </span>
            <span className="font-mono text-ink-3" style={{ fontSize: 10.5 }}>
                {formatTime(at)}
            </span>
        </div>
    );
}

function Chip({ children, bg, fg, mono = false }) {
    return (
        <span
            className={`inline-block font-semibold ${mono ? 'font-mono' : ''}`}
            style={{
                fontSize: 11,
                padding: '2px 7px',
                borderRadius: 5,
                background: bg,
                color: fg,
                maxWidth: 160,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                verticalAlign: 'middle',
            }}
            title={typeof children === 'string' ? children : undefined}
        >
            {children}
        </span>
    );
}

function NoteEntry({ author, at, body, cleared }) {
    return (
        <div style={{ marginBottom: 12 }}>
            <div className="flex items-start" style={{ gap: 9 }}>
                <Avatar name={author} />
                <div className="min-w-0 flex-1">
                    <EntryHeader author={author} at={at} />
                    <div
                        className="bg-surface border border-hairline"
                        style={{ marginTop: 6, borderRadius: 8, padding: '8px 10px' }}
                    >
                        <span
                            className="font-bold uppercase inline-block"
                            style={{
                                fontSize: 9.5,
                                letterSpacing: '.05em',
                                padding: '1px 5px',
                                borderRadius: 4,
                                background: 'var(--st-amber-bg)',
                                color: 'var(--st-amber-fg)',
                                marginBottom: 6,
                            }}
                        >
                            Note
                        </span>
                        <div
                            className={`whitespace-pre-wrap break-words ${cleared ? 'text-ink-3 italic' : 'text-ink'}`}
                            style={{ fontSize: 12.5, lineHeight: 1.45 }}
                        >
                            {cleared ? 'Note cleared' : body}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

function StageEntry({ author, at, from, to, alsoFab }) {
    const toTint = stageTint(to);
    return (
        <div style={{ marginBottom: 12 }}>
            <div className="flex items-start" style={{ gap: 9 }}>
                <Avatar name={author} />
                <div className="min-w-0 flex-1">
                    <EntryHeader author={author} at={at} />
                    <div className="flex items-center flex-wrap" style={{ gap: 6, marginTop: 5 }}>
                        {from != null && from !== '' && (
                            <Chip bg="var(--head-bg)" fg="var(--text-2)">{String(from)}</Chip>
                        )}
                        <span className="text-ink-3" style={{ fontSize: 12 }}>→</span>
                        <Chip bg={toTint.bg} fg={toTint.fg}>{String(to || '—')}</Chip>
                    </div>
                    {alsoFab && (
                        <div className="text-ink-3" style={{ marginTop: 4, fontSize: 11.5 }}>
                            also Fab Order {alsoFab.from ?? '—'} → {alsoFab.to ?? '—'}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

function FabEntry({ author, at, from, to }) {
    return (
        <div style={{ marginBottom: 12 }}>
            <div className="flex items-start" style={{ gap: 9 }}>
                <Avatar name={author} />
                <div className="min-w-0 flex-1">
                    <EntryHeader author={author} at={at} />
                    <div className="flex items-center flex-wrap text-ink-2" style={{ gap: 6, marginTop: 5, fontSize: 12.5 }}>
                        <span>Fab Order</span>
                        <Chip bg="var(--head-bg)" fg="var(--text-2)" mono>{String(from ?? '—')}</Chip>
                        <span className="text-ink-3">→</span>
                        <Chip bg="var(--st-green-bg)" fg="var(--st-green-fg)" mono>{String(to ?? '—')}</Chip>
                    </div>
                </div>
            </div>
        </div>
    );
}

function DateEntry({ author, at, label, valueLabel, hard, cleared }) {
    return (
        <div style={{ marginBottom: 12 }}>
            <div className="flex items-start" style={{ gap: 9 }}>
                <Avatar name={author} />
                <div className="min-w-0 flex-1">
                    <EntryHeader author={author} at={at} />
                    <div className="flex items-center flex-wrap" style={{ gap: 6, marginTop: 5, fontSize: 12.5 }}>
                        <span className="text-ink-2">{cleared ? `${label} cleared` : `${label} set to`}</span>
                        {!cleared && valueLabel != null && (
                            <Chip bg="var(--st-green-bg)" fg="var(--st-green-fg)" mono>{valueLabel}</Chip>
                        )}
                        {hard && (
                            <span
                                className="jl-flag-green font-bold uppercase"
                                style={{ fontSize: 10, letterSpacing: '.05em', padding: '2px 6px', borderRadius: 4 }}
                            >
                                HARD
                            </span>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

/**
 * Turn raw /brain/events into mixed timeline items (notes + stage/date/fab).
 * Newest first. Merges same-user same-minute fab into stage.
 * Notes history includes every `to` and backfills missing `from` text so an
 * overwrite always leaves a traceback (not only the latest body).
 * Exported for tests.
 */
export function buildTimeline(rawEvents, { currentNotes = '' } = {}) {
    const notes = [];
    const noteEvents = []; // raw note changes for history backfill
    const stages = [];
    const fabs = [];
    const others = [];

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
            const sk = sortMs(at);
            noteEvents.push({
                id: e.id,
                author,
                at,
                from: prev,
                to: body,
                sortKey: sk,
            });
            notes.push({
                id: e.id,
                kind: 'note',
                author,
                at,
                body,
                sortKey: sk,
            });
            continue;
        }

        if (!ACTIVITY_ACTIONS.has(e.action)) continue;

        if (e.action === 'update_stage') {
            stages.push({
                id: e.id,
                kind: 'stage',
                author,
                at,
                from,
                to,
                sortKey: sortMs(at),
            });
            continue;
        }

        if (e.action === 'update_fab_order') {
            fabs.push({
                id: e.id,
                kind: 'fab',
                author,
                at,
                from,
                to,
                sortKey: sortMs(at),
            });
            continue;
        }

        // Dates / hard clear — structured for chips.
        if (e.action === 'update_ship_date') {
            const toLabel = formatDateValue(to);
            others.push({
                id: e.id,
                kind: 'date',
                author,
                at,
                label: 'Ship date',
                valueLabel: toLabel,
                cleared: toLabel == null,
                hard: false,
                sortKey: sortMs(at),
            });
            continue;
        }

        if (e.action === 'update_start_install') {
            const asap = payload.asap === true || payload.to_asap === true
                || /^asap$/i.test(String(to || ''));
            const hard = payload.hard === true || payload.is_hard === true
                || payload.start_install_formulaTF === false;
            const toLabel = asap ? 'ASAP' : formatDateValue(to);
            others.push({
                id: e.id,
                kind: 'date',
                author,
                at,
                label: 'Start install',
                valueLabel: toLabel,
                cleared: !asap && toLabel == null,
                hard: hard && !asap && toLabel != null,
                sortKey: sortMs(at),
            });
            continue;
        }

        if (e.action === 'clear_hard_date') {
            others.push({
                id: e.id,
                kind: 'date',
                author,
                at,
                label: 'Hard start-install date',
                valueLabel: null,
                cleared: true,
                hard: false,
                sortKey: sortMs(at),
            });
            continue;
        }

        // Fallback sentence for anything else in ACTIVITY_ACTIONS.
        const summary = summarizeActivity(e);
        if (!summary) continue;
        others.push({
            id: e.id,
            kind: 'date',
            author: summary.author,
            at,
            label: summary.text,
            valueLabel: null,
            cleared: true,
            hard: false,
            sortKey: sortMs(at),
        });
    }

    // Backfill note history: if an overwrite's `from` is not already some event's
    // `to`, the prior text never had its own event (seed / first modal save).
    // Inject it so Activity is a full notes traceback, not only the latest body.
    const knownTos = new Set(noteEvents.map((e) => e.to));
    const injectedFrom = new Set();
    const oldestFirst = [...noteEvents].sort(
        (a, b) => a.sortKey - b.sortKey || (a.id || 0) - (b.id || 0)
    );
    for (const e of oldestFirst) {
        const prev = (e.from ?? '').toString();
        if (!prev || knownTos.has(prev) || injectedFrom.has(prev)) continue;
        if (prev === e.to) continue;
        injectedFrom.add(prev);
        notes.push({
            id: `from-${e.id}`,
            kind: 'note',
            author: 'Job Log',
            at: e.at,
            body: prev,
            // Sit just under the overwrite that replaced it (same day bucket).
            sortKey: e.sortKey > 0 ? e.sortKey - 1 : 0,
            prior: true,
        });
    }

    // Merge fab into stage when same author + same minute.
    const consumedFab = new Set();
    for (const stage of stages) {
        const match = fabs.find((f) =>
            !consumedFab.has(f.id)
            && authorKey(f.author) === authorKey(stage.author)
            && minuteKey(f.at) === minuteKey(stage.at)
            && minuteKey(f.at) !== 0
        );
        if (match) {
            stage.alsoFab = { from: match.from, to: match.to };
            consumedFab.add(match.id);
        }
    }
    const standaloneFab = fabs.filter((f) => !consumedFab.has(f.id));

    const items = [...notes, ...stages, ...standaloneFab, ...others];
    items.sort((a, b) => b.sortKey - a.sortKey || String(b.id).localeCompare(String(a.id)));

    // Surface Job Log field notes not yet present in the event window (no CURRENT badge).
    const current = (currentNotes ?? '').toString().trim();
    const firstNote = items.find((i) => i.kind === 'note');
    const newestNoteMatches = firstNote && firstNote.body.trim() === current;
    if (current !== '' && !newestNoteMatches) {
        items.unshift({
            id: 'field-current',
            kind: 'note',
            author: 'Job Log',
            at: null,
            body: current,
            sortKey: Number.MAX_SAFE_INTEGER,
        });
    }

    return items;
}

/** Group timeline items by calendar day (newest day first). Exported for tests. */
export function groupByDay(items) {
    const groups = [];
    const indexByKey = new Map();
    for (const item of items || []) {
        const { key, label } = dayBucket(item.at);
        let g = indexByKey.get(key);
        if (!g) {
            g = { key, label, items: [] };
            indexByKey.set(key, g);
            groups.push(g);
        }
        g.items.push(item);
    }
    return groups;
}

export function ReleaseNotesRail({
    job,
    release,
    currentNotes,
    onNotesChanged = null,
}) {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [composing, setComposing] = useState(false);
    const [draft, setDraft] = useState('');
    const [saving, setSaving] = useState(false);
    const [saveError, setSaveError] = useState(null);
    const [localNotes, setLocalNotes] = useState(currentNotes ?? '');
    const textareaRef = useRef(null);

    useEffect(() => {
        setLocalNotes(currentNotes ?? '');
    }, [currentNotes]);

    const load = useCallback(() => {
        if (job == null || !release) { setLoading(false); return; }
        setLoading(true);
        jobsApi.getNotesHistory(job, release, 200)
            .then((data) => {
                const raw = Array.isArray(data) ? data : (data?.events || []);
                setItems(buildTimeline(raw, { currentNotes: localNotes }));
                setError(null);
            })
            .catch(() => setError('Could not load activity.'))
            .finally(() => setLoading(false));
    }, [job, release, localNotes]);

    useEffect(() => { load(); }, [load]);

    const openComposer = () => {
        setComposing(true);
        setDraft('');
        setSaveError(null);
        // Focus after paint.
        requestAnimationFrame(() => textareaRef.current?.focus());
    };

    const cancelComposer = () => {
        setComposing(false);
        setDraft('');
        setSaveError(null);
    };

    const saveNote = async () => {
        if (job == null || !release) return;
        setSaving(true);
        setSaveError(null);
        const next = draft; // full overwrite of Job Log Notes field
        try {
            await jobsApi.updateNotes(job, release, next);
            setLocalNotes(next);
            onNotesChanged?.(next);
            setComposing(false);
            setDraft('');
            // Reload history so the new update_notes event appears.
            const data = await jobsApi.getNotesHistory(job, release, 200);
            const raw = Array.isArray(data) ? data : (data?.events || []);
            setItems(buildTimeline(raw, { currentNotes: next }));
        } catch (err) {
            setSaveError(err?.message || 'Could not save note.');
        } finally {
            setSaving(false);
        }
    };

    const groups = groupByDay(items);

    return (
        <div className="flex flex-col min-h-0 border-l border-hairline bg-surface-2">
            <div className="shrink-0 flex items-center border-b border-hairline" style={{ gap: 8, padding: '12px 16px 10px' }}>
                <span className="text-jl-label font-bold uppercase text-ink-3">Activity</span>
                <span
                    className="font-mono font-semibold"
                    style={{
                        fontSize: 10.5,
                        padding: '1px 6px',
                        borderRadius: 999,
                        background: 'var(--head-bg)',
                        color: 'var(--text-3)',
                    }}
                >
                    {items.length}
                </span>
                <div className="flex-1" />
                <span className="text-ink-3" style={{ fontSize: 10.5 }}>Newest first</span>
                <button
                    type="button"
                    onClick={openComposer}
                    className="font-semibold border-0 cursor-pointer"
                    style={{
                        fontSize: 11.5,
                        padding: '4px 9px',
                        borderRadius: 999,
                        background: 'var(--accent-soft)',
                        color: 'var(--accent)',
                    }}
                >
                    + Note
                </button>
            </div>

            {composing && (
                <div className="shrink-0 border-b border-hairline bg-surface" style={{ padding: '10px 14px' }}>
                    <textarea
                        ref={textareaRef}
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        rows={3}
                        placeholder="Overwrite Job Log notes…"
                        disabled={saving}
                        className="w-full text-ink bg-surface-2 border border-hairline rounded-md resize-y"
                        style={{ fontSize: 12.5, padding: '8px 10px', lineHeight: 1.4 }}
                    />
                    {saveError && (
                        <p className="text-jl-2" style={{ color: 'var(--fl-red-fg)', marginTop: 6 }}>{saveError}</p>
                    )}
                    <div className="flex items-center justify-end" style={{ gap: 8, marginTop: 8 }}>
                        <button
                            type="button"
                            onClick={cancelComposer}
                            disabled={saving}
                            className="text-ink-2 bg-transparent border-0 cursor-pointer font-medium"
                            style={{ fontSize: 12, padding: '4px 8px' }}
                        >
                            Cancel
                        </button>
                        <button
                            type="button"
                            onClick={saveNote}
                            disabled={saving}
                            className="font-semibold border-0 cursor-pointer text-white disabled:opacity-50"
                            style={{
                                fontSize: 12,
                                padding: '5px 12px',
                                borderRadius: 7,
                                background: 'var(--accent)',
                            }}
                        >
                            {saving ? 'Saving…' : 'Save note'}
                        </button>
                    </div>
                    <p className="text-ink-3" style={{ fontSize: 10.5, marginTop: 6, lineHeight: 1.35 }}>
                        Saves replace the Job Log Notes field (same as editing the cell).
                    </p>
                </div>
            )}

            <div className="flex-1 min-h-0 overflow-auto" style={{ padding: '4px 16px 12px' }}>
                {loading && <p className="text-jl-2 text-ink-3 italic" style={{ marginTop: 8 }}>Loading activity…</p>}
                {error && <p className="text-jl-2" style={{ color: 'var(--fl-red-fg)', marginTop: 8 }}>{error}</p>}

                {!loading && !error && groups.map((group) => (
                    <div key={group.key}>
                        <DayDivider label={group.label} />
                        {group.items.map((item, i) => {
                            const key = item.id ?? `${group.key}-${i}`;
                            if (item.kind === 'note') {
                                return (
                                    <NoteEntry
                                        key={key}
                                        author={item.author}
                                        at={item.at}
                                        body={item.body}
                                        cleared={item.body.trim() === ''}
                                    />
                                );
                            }
                            if (item.kind === 'stage') {
                                return (
                                    <StageEntry
                                        key={key}
                                        author={item.author}
                                        at={item.at}
                                        from={item.from}
                                        to={item.to}
                                        alsoFab={item.alsoFab}
                                    />
                                );
                            }
                            if (item.kind === 'fab') {
                                return (
                                    <FabEntry
                                        key={key}
                                        author={item.author}
                                        at={item.at}
                                        from={item.from}
                                        to={item.to}
                                    />
                                );
                            }
                            return (
                                <DateEntry
                                    key={key}
                                    author={item.author}
                                    at={item.at}
                                    label={item.label}
                                    valueLabel={item.valueLabel}
                                    hard={item.hard}
                                    cleared={item.cleared}
                                />
                            );
                        })}
                    </div>
                ))}

                {!loading && !error && items.length === 0 && (
                    <p className="text-jl-2 text-ink-3 italic" style={{ marginTop: 8 }}>
                        No notes, stage, fab, or date changes on this release yet.
                    </p>
                )}
            </div>

            <div className="shrink-0 border-t border-hairline bg-surface" style={{ padding: '10px 14px 12px' }}>
                <p className="text-ink-3" style={{ fontSize: 11, lineHeight: 1.4 }}>
                    Notes are edited here or in the Job Log. Stage and date changes land
                    here automatically — full undo history is on the Change Log tab.
                </p>
            </div>
        </div>
    );
}

export default ReleaseNotesRail;
