import { Fragment, useState, useEffect, useCallback } from 'react';
import { checkAuth } from '../utils/auth';
import {
    fetchFcCollectionRuns,
    fetchFcCollectionRunDetail,
    triggerFcCollectionRun,
} from '../services/fcCollectionApi';

const BUCKET_TONES = {
    succeeded:     { label: 'Pulled this run', heading: 'text-emerald-700 dark:text-emerald-300', chip: 'bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200', empty: 'Nothing was pulled in this run.', tooltipField: null },
    still_missing: { label: 'Still missing',   heading: 'text-amber-700 dark:text-amber-300',     chip: 'bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200', empty: 'No releases left waiting.',         tooltipField: 'reason' },
    errored:       { label: 'Errored',         heading: 'text-red-700 dark:text-red-300',         chip: 'bg-red-100 dark:bg-red-900/40 text-red-800 dark:text-red-200',           empty: null,                                tooltipField: 'error' },
};

const STAT_TONES = {
    slate:   'text-slate-700 dark:text-slate-200',
    emerald: 'text-emerald-700 dark:text-emerald-400',
    amber:   'text-amber-700 dark:text-amber-400',
    red:     'text-red-600 dark:text-red-400',
};

function formatTimestamp(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleString();
}

function formatDuration(ms) {
    if (ms == null) return '—';
    if (ms < 1000) return `${ms} ms`;
    return `${(ms / 1000).toFixed(1)} s`;
}

function BucketSection({ bucket, items }) {
    const { label, heading, chip, empty, tooltipField } = BUCKET_TONES[bucket];
    if (items.length === 0 && empty === null) return null;
    return (
        <div>
            <div className={`text-sm font-semibold mb-2 ${heading}`}>
                {label} ({items.length})
            </div>
            {items.length === 0 ? (
                <div className="text-xs text-slate-500 dark:text-slate-400 italic">{empty}</div>
            ) : (
                <div className="flex flex-wrap">
                    {items.map(e => (
                        <span
                            key={`${bucket}-${e.job}-${e.release}`}
                            title={tooltipField ? (e[tooltipField] || '') : ''}
                            className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-md mr-1.5 mb-1.5 ${chip}`}
                        >
                            <span className="font-mono">{e.job}-{e.release}</span>
                        </span>
                    ))}
                </div>
            )}
        </div>
    );
}

function RunDetailRows({ detail }) {
    if (!detail) return null;
    const buckets = detail.details || {};
    return (
        <div className="bg-slate-50 dark:bg-slate-900 px-6 py-5 border-t border-slate-200 dark:border-slate-700 space-y-4">
            <BucketSection bucket="succeeded"     items={buckets.succeeded     || []} />
            <BucketSection bucket="still_missing" items={buckets.still_missing || []} />
            <BucketSection bucket="errored"       items={buckets.errored       || []} />
        </div>
    );
}

function Stat({ label, value, tone = 'slate' }) {
    return (
        <div>
            <div className="text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wide">{label}</div>
            <div className={`text-2xl font-bold tabular-nums ${STAT_TONES[tone] || STAT_TONES.slate}`}>{value}</div>
        </div>
    );
}

export default function FcCollection() {
    // null = pending, true/false = resolved. Avoids a separate authChecked flag.
    const [isAdmin, setIsAdmin] = useState(null);
    // null = not yet loaded; array = loaded. Avoids a separate loading flag.
    const [runs, setRuns] = useState(null);
    const [running, setRunning] = useState(false);
    const [expandedId, setExpandedId] = useState(null);
    const [detailById, setDetailById] = useState({});
    const [error, setError] = useState(null);

    useEffect(() => {
        (async () => {
            const user = await checkAuth();
            setIsAdmin(!!user?.is_admin);
        })();
    }, []);

    const loadRuns = useCallback(async () => {
        setError(null);
        try {
            const list = await fetchFcCollectionRuns();
            setRuns(list);
        } catch (e) {
            setError('Failed to load runs.');
            setRuns([]);
        }
    }, []);

    useEffect(() => {
        if (isAdmin) loadRuns();
    }, [isAdmin, loadRuns]);

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

    if (isAdmin === null) {
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

    const latest = runs && runs[0];

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
                        {runs === null
                            ? 'Loading…'
                            : <>No runs recorded yet. Click <strong>Run now</strong> to fire the worker.</>}
                    </div>
                )}
            </div>

            <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 overflow-hidden">
                <div className="px-5 py-3 border-b border-slate-200 dark:border-slate-700">
                    <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-200">Recent runs</h2>
                </div>
                {runs === null ? (
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
