/**
 * @milehigh-header
 * schema_version: 2
 * purpose: Renders the PM Kanban as the 6 Trello-list columns (mirroring the physical board) of release cards, plus vendor pick-up cards in the Shipping planning column.
 * exports:
 *   PMBoardList: Trello-mirroring board — columns are the 6 Trello lists; releases group by their backend-computed trello_list; pick-ups render as PU cards with assignee chips.
 * imports_from: [react, ../services/jobsApi, ./PMBoardCardModal]
 * imported_by: [frontend/src/pages/PMBoard.jsx]
 * invariants:
 *   - Columns and floor stages mirror app/trello/list_mapper.py (TRELLO_LIST_TO_DB_STAGE) — the backend is the source of truth; this is a copy for drag targets.
 *   - Releases group by job.trello_list (backend-computed via TrelloListMapper); Hold/unmapped (null) are hidden.
 *   - Dropping a release on a column sets its stage to that column's floor stage; pick-up cards are display-only.
 * updated_by_agent: 2026-05-26 (Trello-list collapse + pick-up cards)
 */
import React, { useState, useMemo, useRef, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { jobsApi } from '../services/jobsApi';
import { PMBoardCardModal } from './PMBoardCardModal';
import { PickupCardModal } from './PickupCardModal';

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

// Stable-ish color per assignee initials so the same person keeps a color across cards.
const CHIP_PALETTE = [
    'rgb(59 130 246)', 'rgb(16 185 129)', 'rgb(245 158 11)',
    'rgb(139 92 246)', 'rgb(236 72 153)', 'rgb(20 184 166)',
];
const chipColor = (key) => {
    let h = 0;
    for (let i = 0; i < (key || '').length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
    return CHIP_PALETTE[h % CHIP_PALETTE.length];
};

function AssigneeChips({ assignees }) {
    if (!assignees || assignees.length === 0) return null;
    return (
        <div className="flex items-center -space-x-1.5 mt-1.5">
            {assignees.map((a) => (
                <span
                    key={a.username}
                    title={a.name}
                    className="inline-flex items-center justify-center w-5 h-5 rounded-full text-[9px] font-bold text-white ring-1 ring-white dark:ring-slate-800"
                    style={{ backgroundColor: chipColor(a.initials) }}
                >
                    {a.initials}
                </span>
            ))}
        </div>
    );
}

function PMBoardList({ jobs, onUpdate }) {
    const [draggedJob, setDraggedJob] = useState(null);
    const [dragOverColumn, setDragOverColumn] = useState(null);
    const [updatingJobs, setUpdatingJobs] = useState(new Set());
    const [selectedJob, setSelectedJob] = useState(null);
    const [selectedPickup, setSelectedPickup] = useState(null);
    const [pickups, setPickups] = useState([]);
    const [searchParams, setSearchParams] = useSearchParams();
    const didDragRef = useRef(false);

    // Pick-up cards for the board (PU Dencol: …), reloaded whenever jobs refresh
    // so a freshly-ingested pick-up appears on the next poll/refetch.
    useEffect(() => {
        let cancelled = false;
        jobsApi.fetchPickupBoard()
            .then((data) => { if (!cancelled) setPickups(data); })
            .catch((err) => console.error('Failed to load pickup board:', err));
        return () => { cancelled = true; };
    }, [jobs]);

    // Deep link: the Job Log "PU Card" button jumps here with ?pu=<job>-<release>.
    // Open that pick-up's modal once pickups are loaded, then consume the param so
    // it doesn't reopen on every poll/refresh.
    useEffect(() => {
        const target = searchParams.get('pu');
        if (!target || pickups.length === 0) return;
        const match = pickups.find((p) => `${p.job}-${p.release}` === target);
        if (match) {
            setSelectedPickup(match);
            searchParams.delete('pu');
            setSearchParams(searchParams, { replace: true });
        }
    }, [pickups, searchParams, setSearchParams]);

    // Group releases into the 6 Trello-list columns by their backend-computed
    // trello_list. Cards with no list (Hold / unmapped) are intentionally hidden.
    const jobsByList = useMemo(() => {
        const grouped = {};
        TRELLO_COLUMNS.forEach((c) => { grouped[c.list] = []; });

        jobs.forEach((job) => {
            const list = job.trello_list;
            if (list && grouped[list]) grouped[list].push(job);
        });

        Object.keys(grouped).forEach((list) => {
            grouped[list].sort((a, b) => {
                const orderA = a['Fab Order'] ?? 999999;
                const orderB = b['Fab Order'] ?? 999999;
                return orderA - orderB;
            });
        });
        return grouped;
    }, [jobs]);

    // Pick-up cards grouped by their target list (Shipping planning).
    const pickupsByList = useMemo(() => {
        const grouped = {};
        TRELLO_COLUMNS.forEach((c) => { grouped[c.list] = []; });
        pickups.forEach((p) => {
            const list = p.trello_list;
            if (list && grouped[list]) grouped[list].push(p);
        });
        return grouped;
    }, [pickups]);

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
                {TRELLO_COLUMNS.map((column) => {
                    const { list, label, colors } = column;
                    const listJobs = jobsByList[list] || [];
                    const listPickups = pickupsByList[list] || [];
                    const isDragOver = dragOverColumn === list;
                    const count = listJobs.length + listPickups.length;

                    return (
                        <div
                            key={list}
                            className={`flex-1 min-w-[230px] min-h-0 bg-gray-50 dark:bg-slate-700/40 border border-gray-200 dark:border-slate-600 rounded-lg flex flex-col transition-shadow ${isDragOver ? 'ring-2 ring-blue-500/60 shadow-md' : ''}`}
                            onDragOver={(e) => handleDragOver(e, list)}
                            onDragLeave={handleDragLeave}
                            onDrop={(e) => handleDrop(e, column)}
                        >
                            {/* Column header */}
                            <div
                                className="px-2.5 py-1.5 border-t-[3px] rounded-t-lg bg-white dark:bg-slate-800 flex items-center justify-between"
                                style={{ borderTopColor: colors.base }}
                            >
                                <span className="text-[11px] font-bold uppercase tracking-wide text-gray-700 dark:text-slate-200 truncate">
                                    {label}
                                </span>
                                <span className="bg-gray-100 dark:bg-slate-600 text-gray-600 dark:text-slate-300 px-1.5 py-0.5 rounded text-[10px] font-semibold flex-shrink-0">
                                    {count}
                                </span>
                            </div>

                            {/* Column content */}
                            <div className="flex-1 overflow-y-auto p-1.5 space-y-1.5">
                                {/* Pick-up cards first — they're the action items in this list */}
                                {listPickups.map((p) => (
                                    <div
                                        key={`pu-${p.id}`}
                                        onClick={() => setSelectedPickup(p)}
                                        className="relative bg-amber-50 dark:bg-amber-900/20 border border-amber-300 dark:border-amber-700/60 rounded-md overflow-hidden cursor-pointer transition-all hover:shadow-md hover:border-amber-400 dark:hover:border-amber-600"
                                        title={p.email_subject || p.name}
                                    >
                                        <div className="absolute left-0 top-0 bottom-0 w-1 bg-amber-500" />
                                        <div className="pl-2.5 pr-2 py-1.5">
                                            <div className="flex items-center gap-1.5">
                                                <span className="bg-amber-500 text-white text-[8px] font-bold px-1 py-0.5 rounded uppercase tracking-wide">
                                                    PU
                                                </span>
                                                <span className="font-semibold text-xs text-gray-900 dark:text-slate-100">
                                                    {p.vendor}: {p.job}-{p.release}
                                                </span>
                                            </div>
                                            {p.job_name && (
                                                <div className="text-[11px] text-gray-600 dark:text-slate-300 truncate mt-0.5" title={p.job_name}>
                                                    {p.job_name}
                                                </div>
                                            )}
                                            <AssigneeChips assignees={p.assignees} />
                                        </div>
                                    </div>
                                ))}

                                {/* Release cards */}
                                {listJobs.length === 0 && listPickups.length === 0 ? (
                                    <div className="text-center text-gray-400 dark:text-slate-500 text-xs py-6">—</div>
                                ) : (
                                    listJobs.map((job) => {
                                        const jobId = `${job['Job #']}-${job['Release #']}`;
                                        const isUpdating = updatingJobs.has(jobId);
                                        const isDragging = draggedJob &&
                                            draggedJob['Job #'] === job['Job #'] &&
                                            draggedJob['Release #'] === job['Release #'];

                                        return (
                                            <div
                                                key={jobId}
                                                draggable={!isUpdating}
                                                onDragStart={(e) => handleDragStart(e, job)}
                                                onDragEnd={handleDragEnd}
                                                onClick={() => handleCardClick(job, column)}
                                                className={`relative bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 rounded-md cursor-pointer transition-all overflow-hidden ${isDragging ? 'opacity-50' : ''} ${isUpdating ? 'opacity-50 cursor-wait' : 'hover:shadow-md hover:border-gray-300 dark:hover:border-slate-500'}`}
                                            >
                                                <div className="absolute left-0 top-0 bottom-0 w-1" style={{ backgroundColor: colors.base }} />
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
                                                </div>
                                            </div>
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

            <PickupCardModal
                isOpen={!!selectedPickup}
                onClose={() => setSelectedPickup(null)}
                pickup={selectedPickup}
            />
        </div>
    );
}

export default PMBoardList;
