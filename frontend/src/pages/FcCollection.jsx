import { Fragment, useState, useEffect, useCallback } from 'react';
import { checkAuth } from '../utils/auth';
import {
    fetchFcCollectionRuns,
    fetchFcCollectionRunDetail,
    triggerFcCollectionRun,
} from '../services/fcCollectionApi';

function formatTimestamp(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleString();
}

function formatDuration(ms) {
    if (ms == null) return '—';
    if (ms < 1000) return `${ms} ms`;
    return `${(ms / 1000).toFixed(1)} s`;
}

function ReleaseChip({ entry }) {
    return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-md bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 mr-1.5 mb-1.5">
            <span className="font-mono">{entry.job}-{entry.release}</span>
        </span>
    );
}

function RunDetailRows({ detail }) {
    if (!detail) return null;
    const buckets = detail.details || {};
    const succeeded = buckets.succeeded || [];
    const stillMissing = buckets.still_missing || [];
    const errored = buckets.errored || [];

    return (
        <div className="bg-slate-50 dark:bg-slate-900 px-6 py-5 border-t border-slate-200 dark:border-slate-700 space-y-4">
            <div>
                <div className="text-sm font-semibold text-emerald-700 dark:text-emerald-300 mb-2">
                    Pulled this run ({succeeded.length})
                </div>
                {succeeded.length === 0 ? (
                    <div className="text-xs text-slate-500 dark:text-slate-400 italic">Nothing was pulled in this run.</div>
                ) : (
                    <div className="flex flex-wrap">
                        {succeeded.map(e => <ReleaseChip key={`s-${e.job}-${e.release}`} entry={e} />)}
                    </div>
                )}
            </div>

            <div>
                <div className="text-sm font-semibold text-amber-700 dark:text-amber-300 mb-2">
                    Still missing ({stillMissing.length})
                </div>
                {stillMissing.length === 0 ? (
                    <div className="text-xs text-slate-500 dark:text-slate-400 italic">No releases left waiting.</div>
                ) : (
                    <div className="flex flex-wrap">
                        {stillMissing.map(e => (
                            <span
                                key={`m-${e.job}-${e.release}`}
                                title={e.reason || ''}
                                className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-md bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200 mr-1.5 mb-1.5"
                            >
                                <span className="font-mono">{e.job}-{e.release}</span>
                            </span>
                        ))}
                    </div>
                )}
            </div>

            {errored.length > 0 && (
                <div>
                    <div className="text-sm font-semibold text-red-700 dark:text-red-300 mb-2">
                        Errored ({errored.length})
                    </div>
                    <div className="flex flex-wrap">
                        {errored.map(e => (
                            <span
                                key={`e-${e.job}-${e.release}`}
                                title={e.error || ''}
                                className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-md bg-red-100 dark:bg-red-900/40 text-red-800 dark:text-red-200 mr-1.5 mb-1.5"
                            >
                                <span className="font-mono">{e.job}-{e.release}</span>
                            </span>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

export default function FcCollection() {
    const [authChecked, setAuthChecked] = useState(false);
    const [isAdmin, setIsAdmin] = useState(false);
    const [runs, setRuns] = useState([]);
    const [loading, setLoading] = useState(true);
    const [running, setRunning] = useState(false);
    const [expandedId, setExpandedId] = useState(null);
    const [detailById, setDetailById] = useState({});
    const [error, setError] = useState(null);

    useEffect(() => {
        (async () => {
            const user = await checkAuth();
            setIsAdmin(!!user?.is_admin);
            setAuthChecked(true);
        })();
    }, []);

    const loadRuns = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const list = await fetchFcCollectionRuns();
            setRuns(list);
        } catch (e) {
            setError('Failed to load runs.');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (authChecked && isAdmin) loadRuns();
    }, [authChecked, isAdmin, loadRuns]);

    const handleRunNow = async () => {
        if (running) return;
        setRunning(true);
        setError(null);
        try {
            await triggerFcCollectionRun();
            await loadRuns();
        } catch (e) {
            setError('Manual run failed. Check server logs.');
        } finally {
            setRunning(false);
        }
    };

    const toggleExpand = async (run) => {
        if (expandedId === run.id) {
            setExpandedId(null);
            return;
        }
        setExpandedId(run.id);
        if (!detailById[run.id]) {
            try {
                const detail = await fetchFcCollectionRunDetail(run.id);
                setDetailById(prev => ({ ...prev, [run.id]: detail }));
            } catch (e) {
                setError(`Failed to load detail for run ${run.id}.`);
            }
        }
    };

    if (!authChecked) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-[#f8fafc] dark:bg-slate-900">
                <div className="text-gray-600 dark:text-slate-400">Loading...</div>
            </div>
        );
    }

    if (!isAdmin) {
        return (
            <div className="max-w-3xl mx-auto px-6 py-12">
                <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 mb-2">FC Drawing Collection</h1>
                <div className="rounded-lg bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-200 px-4 py-3">
                    Admin access required.
                </div>
            </div>
        );
    }

    const latest = runs[0];

    return (
        <div className="max-w-6xl mx-auto px-6 py-8">
            <div className="flex items-start justify-between mb-6 gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
                        FC Drawing Collection — Nightly Runs
                    </h1>
                    <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
                        Releases sometimes hit the job log before Procore's Final PDF Pack exists.
                        The worker retries each night at 02:00 for releases <code className="text-xs">released</code> within the last 7 days.
                    </p>
                </div>
                <button
                    type="button"
                    onClick={handleRunNow}
                    disabled={running}
                    className="shrink-0 px-4 py-2 rounded-lg font-medium bg-accent-500 text-white hover:bg-accent-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                    {running ? 'Running…' : 'Run now'}
                </button>
            </div>

            {error && (
                <div className="mb-4 rounded-lg bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-200 px-4 py-2 text-sm">
                    {error}
                </div>
            )}

            {/* Latest summary card */}
            <div className="mb-6 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-5">
                {latest ? (
                    <>
                        <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-3">
                            Last run · {formatTimestamp(latest.run_at)} · {latest.trigger}
                        </div>
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                            <Stat label="Candidates" value={latest.candidates} tone="slate" />
                            <Stat label="Pulled" value={latest.succeeded} tone="emerald" />
                            <Stat label="Still missing" value={latest.still_missing} tone="amber" />
                            <Stat label="Errors" value={latest.errored} tone={latest.errored > 0 ? 'red' : 'slate'} />
                        </div>
                    </>
                ) : (
                    <div className="text-sm text-slate-500 dark:text-slate-400">
                        No runs recorded yet. Click <strong>Run now</strong> to fire the worker.
                    </div>
                )}
            </div>

            {/* History table */}
            <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 overflow-hidden">
                <div className="px-5 py-3 border-b border-slate-200 dark:border-slate-700">
                    <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-200">Recent runs</h2>
                </div>
                {loading ? (
                    <div className="px-5 py-8 text-center text-slate-500 dark:text-slate-400 text-sm">Loading…</div>
                ) : runs.length === 0 ? (
                    <div className="px-5 py-8 text-center text-slate-500 dark:text-slate-400 text-sm">No runs yet.</div>
                ) : (
                    <table className="w-full text-sm">
                        <thead className="bg-slate-50 dark:bg-slate-900/40 text-slate-600 dark:text-slate-400 text-xs uppercase tracking-wide">
                            <tr>
                                <th className="text-left px-5 py-2 font-medium">When</th>
                                <th className="text-left px-3 py-2 font-medium">Trigger</th>
                                <th className="text-right px-3 py-2 font-medium">Candidates</th>
                                <th className="text-right px-3 py-2 font-medium">Pulled</th>
                                <th className="text-right px-3 py-2 font-medium">Still missing</th>
                                <th className="text-right px-3 py-2 font-medium">Errored</th>
                                <th className="text-right px-3 py-2 font-medium">Duration</th>
                                <th className="px-3 py-2"></th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                            {runs.map(run => (
                                <Fragment key={run.id}>
                                    <tr
                                        onClick={() => toggleExpand(run)}
                                        className="cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-900/40"
                                    >
                                        <td className="px-5 py-2 text-slate-700 dark:text-slate-200">{formatTimestamp(run.run_at)}</td>
                                        <td className="px-3 py-2 text-slate-600 dark:text-slate-300 capitalize">{run.trigger}</td>
                                        <td className="px-3 py-2 text-right tabular-nums text-slate-700 dark:text-slate-200">{run.candidates}</td>
                                        <td className="px-3 py-2 text-right tabular-nums font-medium text-emerald-700 dark:text-emerald-400">{run.succeeded}</td>
                                        <td className="px-3 py-2 text-right tabular-nums text-amber-700 dark:text-amber-400">{run.still_missing}</td>
                                        <td className={`px-3 py-2 text-right tabular-nums ${run.errored > 0 ? 'text-red-600 dark:text-red-400 font-medium' : 'text-slate-500 dark:text-slate-400'}`}>{run.errored}</td>
                                        <td className="px-3 py-2 text-right tabular-nums text-slate-500 dark:text-slate-400">{formatDuration(run.duration_ms)}</td>
                                        <td className="px-3 py-2 text-right text-slate-400">
                                            {expandedId === run.id ? '▾' : '▸'}
                                        </td>
                                    </tr>
                                    {expandedId === run.id && (
                                        <tr>
                                            <td colSpan={8} className="p-0">
                                                <RunDetailRows detail={detailById[run.id]} />
                                            </td>
                                        </tr>
                                    )}
                                </Fragment>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}

const TONES = {
    slate:   'text-slate-700 dark:text-slate-200',
    emerald: 'text-emerald-700 dark:text-emerald-400',
    amber:   'text-amber-700 dark:text-amber-400',
    red:     'text-red-600 dark:text-red-400',
};

function Stat({ label, value, tone = 'slate' }) {
    return (
        <div>
            <div className="text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wide">{label}</div>
            <div className={`text-2xl font-bold tabular-nums ${TONES[tone] || TONES.slate}`}>{value}</div>
        </div>
    );
}
