import { useState, useEffect, useCallback } from 'react';
import { checkAuth } from '../utils/auth';
import {
    fetchMatchingProjects,
    fetchMatchingDrrs,
    linkSubmittalRelease,
    unlinkSubmittalRelease,
    markSubmittalNoMatch,
} from '../services/submittalMatchingApi';

// Outcome badge tones for the matcher's confidence classes.
const OUTCOME_BADGES = {
    confident: { label: 'Confident', cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' },
    ambiguous: { label: 'Pick one', cls: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300' },
    weak: { label: 'Weak', cls: 'bg-surface-2 text-ink-2' },
    no_overlap: { label: 'No suggestion', cls: 'bg-surface-2 text-ink-3' },
    no_pool: { label: 'No releases in job', cls: 'bg-red-50 text-red-600 dark:bg-red-900/30 dark:text-red-300' },
};

function StatTile({ label, value, tone = 'slate' }) {
    const tones = {
        slate: 'text-ink',
        green: 'text-emerald-600 dark:text-emerald-400',
        amber: 'text-amber-600 dark:text-amber-400',
        red: 'text-red-600 dark:text-red-400',
    };
    return (
        <div className="rounded-xl border border-hairline bg-surface px-4 py-3">
            <div className="text-xs text-ink-3 uppercase tracking-wide">{label}</div>
            <div className={`text-2xl font-bold tabular-nums ${tones[tone] || tones.slate}`}>{value}</div>
        </div>
    );
}

function CandidateRow({ candidate, onLink, disabled }) {
    return (
        <div className="flex items-center gap-3 py-1.5">
            <button
                type="button"
                onClick={() => onLink(candidate.release_pk)}
                disabled={disabled}
                className="shrink-0 px-2.5 py-1 rounded-md text-xs font-medium bg-accent-500 text-white hover:bg-accent-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
                Link
            </button>
            <div className="min-w-0">
                <div className="text-sm text-ink truncate">
                    <span className="font-mono font-medium">{candidate.job}-{candidate.release}</span>
                    <span className="mx-1.5 text-ink-3">·</span>
                    {candidate.description || <em className="text-ink-3">no description</em>}
                    {candidate.is_archived && (
                        <span className="ml-2 text-[10px] uppercase tracking-wide text-ink-3">archived</span>
                    )}
                </div>
                <div className="text-xs text-ink-3">
                    {candidate.released ? `released ${candidate.released}` : 'no release date'}
                    <span className="mx-1.5">·</span>
                    shared: {candidate.shared_tokens.join(', ')}
                </div>
            </div>
        </div>
    );
}

function DrrCard({ drr, onLink, onUnlink, onNoMatch, busy }) {
    const badge = OUTCOME_BADGES[drr.suggestion.outcome] || OUTCOME_BADGES.weak;
    const isLinked = drr.link_status === 'linked';
    const isNoMatch = drr.link_status === 'no_match';

    return (
        <div className="rounded-xl border border-hairline bg-surface p-4">
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                    <div className="font-medium text-ink">{drr.title}</div>
                    <div className="text-xs text-ink-3 mt-0.5">
                        {drr.status || '—'}
                        {drr.closed_at && <><span className="mx-1.5">·</span>closed {drr.closed_at.slice(0, 10)}</>}
                        {drr.rel != null && <><span className="mx-1.5">·</span>Rel {drr.rel}</>}
                    </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                    {!isLinked && !isNoMatch && (
                        <span className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${badge.cls}`}>{badge.label}</span>
                    )}
                    {(isLinked || isNoMatch) && (
                        <button
                            type="button"
                            onClick={() => onUnlink(drr.id)}
                            disabled={busy}
                            className="px-2.5 py-1 rounded-md text-xs font-medium border border-hairline-strong text-ink-2 hover:bg-surface-2 disabled:opacity-50 transition-colors"
                        >
                            Undo
                        </button>
                    )}
                    {!isLinked && !isNoMatch && (
                        <button
                            type="button"
                            onClick={() => onNoMatch(drr.id)}
                            disabled={busy}
                            className="px-2.5 py-1 rounded-md text-xs font-medium border border-hairline-strong text-ink-2 hover:bg-surface-2 disabled:opacity-50 transition-colors"
                        >
                            No match
                        </button>
                    )}
                </div>
            </div>

            {isLinked && drr.linked_release && (
                <div className="mt-3 rounded-lg bg-emerald-50 dark:bg-emerald-900/20 px-3 py-2 text-sm text-emerald-800 dark:text-emerald-200">
                    Linked to <span className="font-mono font-medium">{drr.linked_release.job}-{drr.linked_release.release}</span>
                    <span className="mx-1.5 text-emerald-500">·</span>{drr.linked_release.description}
                    {drr.fc_inferred_days != null && (
                        <span className="ml-2 text-xs text-emerald-600 dark:text-emerald-300">
                            (inferred FC span: {drr.fc_inferred_days}d from DRR close to release)
                        </span>
                    )}
                </div>
            )}

            {isNoMatch && (
                <div className="mt-3 rounded-lg bg-surface-2 px-3 py-2 text-sm text-ink-2">
                    Reviewed — no job-log release for this scope.
                </div>
            )}

            {!isLinked && !isNoMatch && drr.suggestion.candidates.length > 0 && (
                <div className="mt-3 border-t border-hairline pt-2 divide-y divide-[var(--border)]">
                    {drr.suggestion.candidates.map(c => (
                        <CandidateRow key={c.release_pk} candidate={c} disabled={busy} onLink={rid => onLink(drr.id, rid)} />
                    ))}
                </div>
            )}
        </div>
    );
}

export default function SubmittalMatching() {
    // null = pending, true/false = resolved.
    const [isAdmin, setIsAdmin] = useState(null);
    // null = not yet loaded; array = loaded.
    const [projects, setProjects] = useState(null);
    const [selected, setSelected] = useState('');
    const [detail, setDetail] = useState(null);
    const [showReviewed, setShowReviewed] = useState(false);
    const [busyId, setBusyId] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        (async () => {
            const user = await checkAuth();
            setIsAdmin(!!user?.is_admin);
        })();
    }, []);

    const loadProjects = useCallback(async () => {
        setError(null);
        try {
            const list = await fetchMatchingProjects();
            setProjects(list);
            return list;
        } catch {
            setError('Failed to load projects.');
            setProjects([]);
            return [];
        }
    }, []);

    const loadDetail = useCallback(async (project) => {
        if (!project) { setDetail(null); return; }
        setError(null);
        try {
            const data = await fetchMatchingDrrs(project);
            setDetail(data);
        } catch {
            setError(`Failed to load DRRs for project ${project}.`);
        }
    }, []);

    useEffect(() => {
        if (!isAdmin) return;
        (async () => {
            const list = await loadProjects();
            // Preselect the project with the most unreviewed DRRs.
            if (list.length > 0) setSelected(prev => prev || list[0].project_number);
        })();
    }, [isAdmin, loadProjects]);

    useEffect(() => {
        if (isAdmin && selected) loadDetail(selected);
    }, [isAdmin, selected, loadDetail]);

    const refresh = useCallback(async () => {
        await Promise.all([loadProjects(), loadDetail(selected)]);
    }, [loadProjects, loadDetail, selected]);

    const runAction = async (drrId, action) => {
        setBusyId(drrId);
        setError(null);
        try {
            await action();
            await refresh();
        } catch (e) {
            const msg = e?.response?.data?.message || e?.response?.data?.error || 'Action failed.';
            setError(msg);
        } finally {
            setBusyId(null);
        }
    };

    const handleLink = (drrId, releaseId) => runAction(drrId, () => linkSubmittalRelease(drrId, releaseId));
    const handleUnlink = (drrId) => runAction(drrId, () => unlinkSubmittalRelease(drrId));
    const handleNoMatch = (drrId) => runAction(drrId, () => markSubmittalNoMatch(drrId));

    if (isAdmin === null) {
        return (
            <div className="min-h-[calc(100vh_-_var(--app-chrome-h))] flex items-center justify-center bg-canvas">
                <div className="text-ink-3">Loading...</div>
            </div>
        );
    }

    if (!isAdmin) {
        return (
            <div className="max-w-3xl mx-auto px-6 py-12">
                <h1 className="text-2xl font-bold text-ink mb-2">Submittal Matching</h1>
                <div className="rounded-lg bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-200 px-4 py-3">
                    Admin access required.
                </div>
            </div>
        );
    }

    const summary = projects?.find(p => p.project_number === selected);
    const visibleDrrs = detail?.drrs?.filter(d => showReviewed || d.link_status === '') || [];

    return (
        <div className="w-full min-h-[calc(100vh_-_var(--app-chrome-h))] bg-canvas">
        <div className="max-w-6xl mx-auto px-6 py-8">
            <div className="mb-6">
                <h1 className="text-2xl font-bold text-ink">
                    Submittal Matching — DRR → Release
                </h1>
                <p className="text-sm text-ink-3 mt-1 max-w-3xl">
                    Confirm which job-log release each DRR became. Suggestions are description matches
                    scoped to the project (archived releases included). Every confirmed link improves the
                    scheduling pipeline's timing data — the inferred FC span (DRR close → release) appears
                    as you link.
                </p>
            </div>

            {error && (
                <div className="mb-4 rounded-lg bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-200 px-4 py-2 text-sm">
                    {error}
                </div>
            )}

            <div className="flex flex-wrap items-end gap-4 mb-5">
                <label className="block">
                    <span className="block text-xs uppercase tracking-wide text-ink-3 mb-1">Project</span>
                    <select
                        value={selected}
                        onChange={e => setSelected(e.target.value)}
                        className="rounded-lg border border-hairline-strong bg-input-bg text-ink px-3 py-2 text-sm"
                    >
                        {(projects || []).map(p => (
                            <option key={p.project_number} value={p.project_number}>
                                {p.project_number} — {p.project_name || 'Unknown'} ({p.unreviewed} to review)
                            </option>
                        ))}
                    </select>
                </label>
                <label className="flex items-center gap-2 pb-2 text-sm text-ink-2 cursor-pointer">
                    <input
                        type="checkbox"
                        checked={showReviewed}
                        onChange={e => setShowReviewed(e.target.checked)}
                        className="rounded border-hairline-strong"
                    />
                    Show reviewed
                </label>
            </div>

            {summary && (
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6">
                    <StatTile label="DRRs" value={summary.drr_total} />
                    <StatTile label="Linked" value={summary.linked} tone="green" />
                    <StatTile label="No match" value={summary.no_match} />
                    <StatTile label="To review" value={summary.unreviewed} tone={summary.unreviewed > 0 ? 'amber' : 'green'} />
                    <StatTile label="Releases in job" value={summary.release_pool} tone={summary.release_pool === 0 ? 'red' : 'slate'} />
                </div>
            )}

            <div className="space-y-3">
                {detail === null && selected && (
                    <div className="text-ink-3 text-sm">Loading DRRs…</div>
                )}
                {detail !== null && visibleDrrs.length === 0 && (
                    <div className="rounded-xl border border-dashed border-hairline-strong px-4 py-8 text-center text-sm text-ink-3">
                        {showReviewed ? 'No DRRs in this project.' : 'All DRRs in this project are reviewed. 🎉'}
                    </div>
                )}
                {visibleDrrs.map(drr => (
                    <DrrCard
                        key={drr.id}
                        drr={drr}
                        busy={busyId === drr.id}
                        onLink={handleLink}
                        onUnlink={handleUnlink}
                        onNoMatch={handleNoMatch}
                    />
                ))}
            </div>
        </div>
        </div>
    );
}
