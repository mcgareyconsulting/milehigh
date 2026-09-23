/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The Activity tab of the sub release page (release-mobile-recommendations.md §5): the
 *          desktop rail's rows (day dividers, initials avatar, before → after chips for stage /
 *          date changes, sentences for photo / drawing events, note bodies) newest first, with the
 *          note composer pinned to the bottom above the safe area.
 * exports:
 *   SubReleaseActivity: ({ releaseId, onCount })
 * imports_from: [react, ../../services/subPortalApi, ../ReleaseNotesRail (buildTimeline, groupByDay,
 *                initialsOf), ../ReleaseActivityFeed (formatDateValue)]
 * imported_by: [pages/SubcontractorRelease.jsx]
 * invariants:
 *   - Rows come from the sub-scoped activity route (SUB_ACTIVITY_ACTIONS only) and are shaped by the
 *     SAME buildTimeline() the staff rail uses, so a sub and a PM read one event identically.
 *   - Notes post through the sub notes route; the server attributes them "sub:<id>" and the row
 *     comes back with the sub's own name and a green avatar.
 *   - Newest first, no ordering toggle on mobile.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { addSubNote, getSubActivity } from '../../services/subPortalApi';
import { buildTimeline, groupByDay, initialsOf } from '../ReleaseNotesRail';
import { formatDateValue } from '../ReleaseActivityFeed';

const timeOf = (iso) => {
    if (!iso) return '';
    const d = new Date(iso);
    return isNaN(d) ? '' : d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
};

function Delta({ from, to, isDate }) {
    const f = isDate ? formatDateValue(from) : from;
    const t = isDate ? formatDateValue(to) : to;
    return (
        <span className="delta">
            {f != null && f !== '' && <span className="from">{String(f)}</span>}
            {f != null && f !== '' && <span aria-hidden="true">→</span>}
            <span className="to">{t == null || t === '' ? 'cleared' : String(t)}</span>
        </span>
    );
}

function EventRow({ item, subKinds }) {
    const author = item.author || 'Brain';
    const isSub = subKinds.has(item.id);
    return (
        <div className="sub-event">
            <div className={`avatar${isSub ? ' sub' : ''}`} aria-hidden="true">{initialsOf(author)}</div>
            <div className="body">
                <div className="who"><b>{author}</b><span>{timeOf(item.at)}</span></div>
                {item.kind === 'note' && <div className="text">{item.body}</div>}
                {item.kind === 'stage' && (
                    <div className="text">Stage <Delta from={item.from} to={item.to} /></div>
                )}
                {item.kind === 'date' && (
                    <div className="text">{item.label || 'Date'} <Delta from={item.from} to={item.to} isDate /></div>
                )}
                {item.kind === 'sentence' && <div className="text">{item.text}</div>}
                {item.kind === 'fab' && <div className="text">Fab order <Delta from={item.from} to={item.to} /></div>}
            </div>
        </div>
    );
}

const SEND = <svg viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M22 2L11 13" /><path d="M22 2L15 22l-4-9-9-4z" /></svg>;

export default function SubReleaseActivity({ releaseId, onCount }) {
    const [raw, setRaw] = useState(null);
    const [error, setError] = useState(null);
    const [draft, setDraft] = useState('');
    const [posting, setPosting] = useState(false);
    const listRef = useRef(null);

    const load = useCallback(async () => {
        try {
            const rows = await getSubActivity(releaseId);
            setRaw(rows);
            setError(null);
        } catch (e) {
            setError(e?.response?.data?.error || 'Could not load activity');
        }
    }, [releaseId]);
    useEffect(() => { load(); }, [load]);

    const items = useMemo(() => buildTimeline(raw || []), [raw]);
    const groups = useMemo(() => groupByDay(items), [items]);
    // Which rows were authored by a subcontractor account (green avatar).
    const subKinds = useMemo(() => new Set((raw || []).filter((e) => e.actor_kind === 'sub').map((e) => e.id)), [raw]);

    useEffect(() => { if (raw) onCount?.(items.length); }, [raw, items.length, onCount]);

    const send = async () => {
        const body = draft.trim();
        if (!body || posting) return;
        setPosting(true);
        try {
            await addSubNote(releaseId, body);
            setDraft('');
            await load();
            listRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
        } catch (e) {
            setError(e?.response?.data?.error || 'Could not post the note');
        } finally {
            setPosting(false);
        }
    };

    return (
        <div className="flex-1 min-h-0 flex flex-col">
            <div ref={listRef} className="flex-1 min-h-0 overflow-y-auto px-4 pb-4">
                {error && <p className="py-3 text-sm text-red-600">{error}</p>}
                {!raw && !error && <p className="py-3 text-sm text-ink-3">Loading…</p>}
                {raw && items.length === 0 && (
                    <p className="py-8 text-center text-sm text-ink-3">No activity on this release yet. Your note will be the first.</p>
                )}
                {groups.map((g) => (
                    <section key={g.key}>
                        <div className="sub-day-divider">{g.label}</div>
                        {g.items.map((it) => <EventRow key={it.id} item={it} subKinds={subKinds} />)}
                    </section>
                ))}
            </div>
            <div className="sub-composer">
                <textarea
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    placeholder="Add a note…"
                    rows={1}
                    aria-label="Add a note"
                    onInput={(e) => { e.target.style.height = 'auto'; e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`; }}
                />
                <button type="button" className="send" aria-label="Post note" disabled={!draft.trim() || posting} onClick={send}>{SEND}</button>
            </div>
        </div>
    );
}
