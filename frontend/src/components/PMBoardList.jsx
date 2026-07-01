/**
 * @milehigh-header
 * schema_version: 3
 * purpose: Renders the PM Kanban as the 6 Trello-list columns (mirroring the physical board) of release cards, plus read-only per-installer-crew columns.
 * exports:
 *   PMBoardList: Trello-mirroring board — the 6 Trello-list columns followed by one read-only column per configured installer crew; releases group by their backend-computed trello_list, and a release with a hard date + assigned installer ALSO renders as a copy in its installer column.
 * imports_from: [react, ../services/jobsApi, ./PMBoardCardModal, ../constants/installerPalette, ../utils/formatters]
 * imported_by: [frontend/src/pages/PMBoardContent.jsx]
 * invariants:
 *   - PM Board is a READ-ONLY viewer over the shared releases dataset. The drag-to-stage write path is kept intact but gated off by READ_ONLY (flip to false to restore drag-to-change-stage). Installer columns were always read-only.
 *   - Stage columns and floor stages mirror app/trello/list_mapper.py (TRELLO_LIST_TO_DB_STAGE) — the backend is the source of truth; this is a copy for grouping.
 *   - Releases group by job.trello_list (backend-computed via TrelloListMapper); Hold/unmapped (null) are hidden.
 *   - Installer columns come from /brain/installer-teams and use the Gantt lane palette so List and Timeline colors match.
 *   - A release appears in an installer column iff it has a hard date (start_install_formulaTF === false with a Start install value) AND a matching installer. install_hrs is intentionally NOT required (unlike the Gantt timeline).
 * updated_by_agent: 2026-06-10 (ported pared-down board to shared-releases-layer, read-only)
 */
import React, { useState, useMemo, useRef, useEffect } from 'react';
import { jobsApi } from '../services/jobsApi';
import { PMBoardCardModal } from './PMBoardCardModal';
import { INSTALLER_PALETTE } from '../constants/installerPalette';
import { localTodayStr } from '../utils/formatters';

// PM Board (and the Timeline) are read-only views over the shared releases
// dataset — only Job Log writes. The drag-to-stage path below is kept intact
// rather than torn down; this flag gates the only mutation so the board cannot
// write back. Flip to false to restore drag-to-change-stage editing.
const READ_ONLY = true;

// The 6 physical Trello lists, in board order. `floorStage` is the canonical DB
// stage a card takes when dropped here — it mirrors TRELLO_LIST_TO_DB_STAGE in
// app/trello/list_mapper.py (the backend remains the source of truth).
const TRELLO_COLUMNS = [
    {
        list: 'Released', label: 'Released', floorStage: 'Released',
        colors: { base: 'rgb(59 130 246)', text: 'rgb(30 64 175)' },
    },
    {
        list: 'Fit Up Complete.', label: 'Fit Up Complete', floorStage: 'Fitup Complete',
        colors: { base: 'rgb(99 102 241)', text: 'rgb(55 48 163)' },
    },
    {
        list: 'Paint complete', label: 'Paint Complete', floorStage: 'Paint Complete',
        colors: { base: 'rgb(16 185 129)', text: 'rgb(6 95 70)' },
    },
    {
        list: 'Store at MHMW for shipping', label: 'Store at MHMW', floorStage: 'Store at MHMW',
        colors: { base: 'rgb(20 184 166)', text: 'rgb(17 94 89)' },
    },
    {
        list: 'Shipping planning', label: 'Shipping Planning', floorStage: 'Ship Planning',
        colors: { base: 'rgb(245 158 11)', text: 'rgb(146 64 14)' },
    },
    {
        list: 'Shipping completed', label: 'Shipping Completed', floorStage: 'Ship Complete',
        colors: { base: 'rgb(139 92 246)', text: 'rgb(91 33 182)' },
    },
];

// A release is eligible for an installer column when it has a hard date and an
// assigned installer. Trimmed, matching the Gantt's toBar — a padded installer
// value must group/match the same way in both views.
const hasHardDateAndInstaller = (job) =>
    job['start_install_formulaTF'] === false &&
    !!job['Start install'] &&
    !!(job.installer || '').trim();

// "May 28" from an ISO date string; empty for null/unparseable.
const fmtShortDate = (iso) => {
    if (!iso) return '';
    const d = new Date(String(iso).slice(0, 10) + 'T00:00:00');
    if (isNaN(d)) return '';
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

// Pill color for the installer-card date range, mirroring the Job Log Start install
// cell: red = ASAP, yellow = overdue (start install in the past), green = good.
const dateRangePillClass = (job) => {
    if (job['start_install_asap'] === true) return 'bg-red-500 text-white';
    const installDay = String(job['Start install'] ?? '').split('T')[0];
    if (installDay && installDay < localTodayStr()) return 'bg-yellow-400 text-gray-900';
    return 'bg-green-400 text-gray-900';
};

// Shared release card used by both the stage columns and the installer columns so
// they look identical. Installer columns pass draggable={false} (read-only).
function ReleaseCard({ job, colorBase, draggable, isUpdating, isDragging, showDateRange, onDragStart, onDragEnd, onClick }) {
    return (
        <div
            draggable={draggable}
            onDragStart={draggable ? onDragStart : undefined}
            onDragEnd={draggable ? onDragEnd : undefined}
            onClick={onClick}
            className={`relative bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 rounded-md cursor-pointer transition-all overflow-hidden ${isDragging ? 'opacity-50' : ''} ${isUpdating ? 'opacity-50 cursor-wait' : 'hover:shadow-md hover:border-gray-300 dark:hover:border-slate-500'}`}
        >
            <div className="absolute left-0 top-0 bottom-0 w-1" style={{ backgroundColor: colorBase }} />
            <div className="pl-2.5 pr-2 py-1.5">
                <div className="flex items-start justify-between gap-2">
                    <span className="font-semibold text-xs text-gray-900 dark:text-slate-100 shrink-0">
                        {job['Job #']}-{job['Release #']}
                    </span>
                    {job['Fab Order'] !== null && job['Fab Order'] !== undefined && (
                        <span className="text-[10px] font-medium text-gray-500 dark:text-slate-400 shrink-0">
                            #{job['Fab Order']}
                        </span>
                    )}
                </div>
                {job['Job'] && (
                    <div className="text-[11px] text-gray-700 dark:text-slate-300 truncate mt-0.5" title={job['Job']}>
                        {job['Job']}
                    </div>
                )}
                {job['Description'] && (
                    <div className="text-[11px] text-gray-500 dark:text-slate-400 line-clamp-2 mt-0.5" title={job['Description']}>
                        {job['Description']}
                    </div>
                )}
                {showDateRange && job['Start install'] && (
                    <div className="mt-1.5">
                        <span
                            className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-semibold ${dateRangePillClass(job)}`}
                            title={job['start_install_asap'] === true ? 'ASAP' : 'Start install → Comp. ETA'}
                        >
                            🗓 {fmtShortDate(job['Start install'])}
                            {job['Comp. ETA'] ? ` → ${fmtShortDate(job['Comp. ETA'])}` : ''}
                        </span>
                    </div>
                )}
            </div>
        </div>
    );
}

function PMBoardList({ jobs, onUpdate }) {
    const [draggedJob, setDraggedJob] = useState(null);
    const [dragOverColumn, setDragOverColumn] = useState(null);
    const [updatingJobs, setUpdatingJobs] = useState(new Set());
    const [selectedJob, setSelectedJob] = useState(null);
    const [installerTeams, setInstallerTeams] = useState([]);
    const didDragRef = useRef(false);

    // Configured installer teams → read-only columns appended after the 6 stage lists.
    useEffect(() => {
        let cancelled = false;
        jobsApi.getInstallerTeams()
            .then((teams) => { if (!cancelled) setInstallerTeams(teams); })
            .catch((err) => console.error('Failed to load installer teams:', err));
        return () => { cancelled = true; };
    }, []);

    // One read-only column per configured installer team, colored to match the
    // Gantt lane for that team.
    const installerColumns = useMemo(() => (
        installerTeams.map((team, i) => {
            const base = INSTALLER_PALETTE[i % INSTALLER_PALETTE.length];
            return {
                kind: 'installer',
                list: team,          // grouping key === Releases.installer
                label: team,
                colors: { base, text: base },
            };
        })
    ), [installerTeams]);

    const allColumns = useMemo(() => ([
        ...TRELLO_COLUMNS.map((c) => ({ ...c, kind: 'stage' })),
        ...installerColumns,
    ]), [installerColumns]);

    // Group releases into the 6 Trello-list columns by their backend-computed
    // trello_list. Cards with no list (Hold / unmapped) are intentionally hidden.
    const jobsByList = useMemo(() => {
        const grouped = {};
        TRELLO_COLUMNS.forEach((c) => { grouped[c.list] = []; });

        // Trip-wire for list_mapper.py drift: a non-null trello_list that doesn't
        // match any TRELLO_COLUMNS entry means the backend renamed/added a list and
        // this hardcoded mirror is stale — warn instead of silently hiding cards.
        const unknownLists = new Set();
        jobs.forEach((job) => {
            const list = job.trello_list;
            if (!list) return; // Hold / unmapped — hidden by design
            if (grouped[list]) grouped[list].push(job);
            else unknownLists.add(list);
        });
        if (unknownLists.size > 0) {
            console.warn(
                '[PMBoard] Releases hidden — trello_list value(s) not in TRELLO_COLUMNS (update PMBoardList to match app/trello/list_mapper.py):',
                [...unknownLists]
            );
        }

        Object.keys(grouped).forEach((list) => {
            grouped[list].sort((a, b) => {
                const orderA = a['Fab Order'] ?? 999999;
                const orderB = b['Fab Order'] ?? 999999;
                return orderA - orderB;
            });
        });
        return grouped;
    }, [jobs]);

    // Group hard-date + assigned releases into their installer column. A release
    // here is a copy — it also still shows in its stage column. Sorted by start
    // install (the installer's scheduling order).
    const jobsByInstaller = useMemo(() => {
        const grouped = {};
        installerTeams.forEach((team) => { grouped[team] = []; });

        jobs.forEach((job) => {
            if (!hasHardDateAndInstaller(job)) return;
            const team = (job.installer || '').trim();
            if (grouped[team]) grouped[team].push(job);
        });

        Object.keys(grouped).forEach((team) => {
            grouped[team].sort((a, b) => (
                String(a['Start install'] || '').localeCompare(String(b['Start install'] || ''))
            ));
        });
        return grouped;
    }, [jobs, installerTeams]);

    const handleDragStart = (e, job) => {
        didDragRef.current = false;
        setDraggedJob(job);
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/html', '');
    };

    const handleDragEnd = () => {
        didDragRef.current = true;
        setDraggedJob(null);
    };

    const handleCardClick = (job, column) => {
        if (didDragRef.current) {
            didDragRef.current = false;
            return;
        }
        setSelectedJob({ job, column });
    };

    const handleDragOver = (e, list) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        setDragOverColumn(list);
    };

    const handleDragLeave = () => setDragOverColumn(null);

    const handleDrop = async (e, column) => {
        e.preventDefault();
        setDragOverColumn(null);

        // Read-only board: never write stage back. (Stage-column cards aren't
        // draggable while READ_ONLY, so this is belt-and-suspenders.)
        if (READ_ONLY) return;

        if (!draggedJob) return;

        // Dropping on a Trello-list column advances the release to that list's floor stage.
        const targetStage = column.floorStage;
        if ((draggedJob['Stage'] || 'Released') === targetStage) {
            setDraggedJob(null);
            return;
        }

        const jobId = `${draggedJob['Job #']}-${draggedJob['Release #']}`;
        setUpdatingJobs((prev) => new Set(prev).add(jobId));
        try {
            await jobsApi.updateStage(draggedJob['Job #'], draggedJob['Release #'], targetStage);
            if (onUpdate) onUpdate();
        } catch (error) {
            console.error('Failed to update stage:', error);
            alert(`Failed to update stage: ${error.message}`);
        } finally {
            setUpdatingJobs((prev) => {
                const next = new Set(prev);
                next.delete(jobId);
                return next;
            });
            setDraggedJob(null);
        }
    };

    return (
        <div className="flex-1 min-h-0 overflow-x-auto overflow-y-hidden p-2 flex flex-col">
            <div className="flex gap-2 flex-1 min-h-0">
                {allColumns.map((column) => {
                    const { list, label, colors, kind } = column;
                    const isInstaller = kind === 'installer';
                    // Stage columns are drop targets only when editing is enabled.
                    const isDropTarget = !isInstaller && !READ_ONLY;
                    const listJobs = isInstaller
                        ? (jobsByInstaller[list] || [])
                        : (jobsByList[list] || []);
                    const isDragOver = isDropTarget && dragOverColumn === list;
                    const count = listJobs.length;

                    return (
                        <div
                            key={`${kind}-${list}`}
                            className={`flex-1 min-w-[230px] min-h-0 bg-gray-50 dark:bg-slate-700/40 border border-gray-200 dark:border-slate-600 rounded-lg flex flex-col transition-shadow ${isDragOver ? 'ring-2 ring-blue-500/60 shadow-md' : ''}`}
                            onDragOver={isDropTarget ? (e) => handleDragOver(e, list) : undefined}
                            onDragLeave={isDropTarget ? handleDragLeave : undefined}
                            onDrop={isDropTarget ? (e) => handleDrop(e, column) : undefined}
                        >
                            {/* Column header */}
                            <div
                                className="px-2.5 py-1.5 border-t-[3px] rounded-t-lg bg-white dark:bg-slate-800 flex items-center justify-between"
                                style={{ borderTopColor: colors.base }}
                            >
                                <span className="text-[11px] font-bold uppercase tracking-wide text-gray-700 dark:text-slate-200 truncate flex items-center gap-1">
                                    {isInstaller && <span className="not-italic">👷</span>}
                                    {label}
                                </span>
                                <span className="bg-gray-100 dark:bg-slate-600 text-gray-600 dark:text-slate-300 px-1.5 py-0.5 rounded text-[10px] font-semibold flex-shrink-0">
                                    {count}
                                </span>
                            </div>

                            {/* Column content */}
                            <div className="flex-1 overflow-y-auto p-1.5 space-y-1.5">
                                {/* Release cards */}
                                {count === 0 ? (
                                    <div className="text-center text-gray-400 dark:text-slate-500 text-xs py-6">—</div>
                                ) : (
                                    listJobs.map((job) => {
                                        const jobId = `${job['Job #']}-${job['Release #']}`;
                                        const isUpdating = updatingJobs.has(jobId);
                                        const isDragging = isDropTarget && draggedJob &&
                                            draggedJob['Job #'] === job['Job #'] &&
                                            draggedJob['Release #'] === job['Release #'];

                                        return (
                                            <ReleaseCard
                                                key={jobId}
                                                job={job}
                                                colorBase={colors.base}
                                                draggable={isDropTarget && !isUpdating}
                                                isUpdating={isUpdating}
                                                isDragging={isDragging}
                                                showDateRange={isInstaller}
                                                onDragStart={(e) => handleDragStart(e, job)}
                                                onDragEnd={handleDragEnd}
                                                onClick={() => handleCardClick(job, column)}
                                            />
                                        );
                                    })
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>

            <PMBoardCardModal
                isOpen={!!selectedJob}
                onClose={() => setSelectedJob(null)}
                job={selectedJob?.job}
                stageColor={selectedJob ? {
                    base: selectedJob.column.colors.base,
                    text: selectedJob.column.colors.text,
                    light: 'rgb(243 244 246)',
                    border: selectedJob.column.colors.base,
                } : null}
            />
        </div>
    );
}

export default PMBoardList;
