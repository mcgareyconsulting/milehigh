/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Visualizes installer release windows as a Gantt-style timeline with day-snap drag, resize, and horizontal scroll for prototype scheduling.
 * exports:
 *   GanttChart: Day-snap timeline with move/resize drag interactions; week-snap navigation; horizontal scroll for multi-week visibility
 * imports_from: [react, ../services/jobsApi]
 * imported_by: [frontend/src/pages/PMBoard.jsx]
 * invariants:
 *   - Drag overrides live in component state only; never persisted to backend
 *   - When filterComplete is true, releases whose stage === 'Complete' are excluded; "Shipping Complete" rows stay visible
 *   - Projects with zero visible releases after filtering are omitted entirely
 *   - Week-snap nav buttons always anchor viewStart to a Monday; horizontal scroll is free-form within the rendered range
 * updated_by_agent: 2026-05-04T00:00:00Z (timeline drag prototype)
 */
import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { jobsApi } from '../services/jobsApi';

const addDays = (isoDate, days) => {
    const d = new Date(isoDate + 'T00:00:00');
    d.setDate(d.getDate() + days);
    return d.toISOString().split('T')[0];
};

const daysBetween = (startIso, endIso) => {
    const s = new Date(startIso + 'T00:00:00');
    const e = new Date(endIso + 'T00:00:00');
    return Math.round((e - s) / (1000 * 60 * 60 * 24));
};

const todayIso = () => {
    const d = new Date();
    return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, '0'), String(d.getDate()).padStart(2, '0')].join('-');
};

// Snap an ISO date to the Monday of that week (Mon = day 1, Sun = day 0 → -6).
const mondayOf = (isoDate) => {
    const d = new Date(isoDate + 'T00:00:00');
    const dow = d.getDay();
    const offset = dow === 0 ? -6 : 1 - dow;
    d.setDate(d.getDate() + offset);
    return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, '0'), String(d.getDate()).padStart(2, '0')].join('-');
};

const minIso = (a, b) => (a < b ? a : b);
const maxIso = (a, b) => (a > b ? a : b);

const VIEW_DAYS = 7;
const DAY_PX = 80;
const PAD_DAYS = 14;
const SIDEBAR_PX = 192;

const DAY_GRID_STYLE = {
    backgroundImage: 'linear-gradient(to right, rgba(0,0,0,0.06) 1px, transparent 1px)',
    backgroundSize: `${DAY_PX}px 100%`,
    backgroundRepeat: 'repeat'
};

function GanttChart({ filterComplete = false }) {
    const [projects, setProjects] = useState([]);
    const [loading, setLoading] = useState(true);
    const [initialLoad, setInitialLoad] = useState(true);
    const [error, setError] = useState(null);
    const [hoveredItem, setHoveredItem] = useState(null);
    const [hoverPosition, setHoverPosition] = useState({ x: 0, y: 0 });
    const [overrides, setOverrides] = useState({});
    const [dragging, setDragging] = useState(false);
    const [viewStart, setViewStart] = useState(() => mondayOf(todayIso()));
    const [datePickerOpen, setDatePickerOpen] = useState(false);
    const [datePickerValue, setDatePickerValue] = useState('');
    const scrollContainerRef = useRef(null);
    // Set by nav handlers (and once after data loads) to request a scroll on the next render.
    // Drag-driven re-renders don't set this, so the chart never auto-scrolls mid-drag.
    const scrollIntentRef = useRef(null);

    useEffect(() => {
        const fetchData = async () => {
            try {
                setLoading(true);
                setError(null);

                const [ganttData, jobs] = await Promise.all([
                    jobsApi.fetchGanttData(),
                    filterComplete ? jobsApi.fetchAllJobs() : Promise.resolve([])
                ]);

                let filteredProjects = ganttData.projects || [];

                if (filterComplete && jobs.length > 0) {
                    const nonCompleteJobs = new Set();
                    jobs.forEach(job => {
                        if (job['Stage'] !== 'Complete') {
                            const jobNum = String(job['Job #'] || '').trim();
                            const releaseNum = String(job['Release #'] || '').trim();
                            if (jobNum && releaseNum) {
                                nonCompleteJobs.add(`${jobNum}-${releaseNum}`);
                            }
                        }
                    });

                    filteredProjects = filteredProjects
                        .map(project => {
                            const filteredReleases = project.releases.filter(release => {
                                const jobNum = String(release.job || '').trim();
                                const releaseNum = String(release.release || '').trim();
                                const jobKey = `${jobNum}-${releaseNum}`;
                                return nonCompleteJobs.has(jobKey);
                            });

                            if (filteredReleases.length === 0) {
                                return null;
                            }

                            return {
                                ...project,
                                releases: filteredReleases
                            };
                        })
                        .filter(project => project !== null);
                }

                setProjects(filteredProjects);
                setOverrides({});
            } catch (err) {
                setError(err.message || 'Failed to load Gantt chart data');
            } finally {
                setLoading(false);
                setInitialLoad(false);
            }
        };

        fetchData();
    }, [filterComplete]);

    const releaseKey = (release) => `${release.job}-${release.release}`;

    const getReleaseDates = useCallback((release) => {
        const key = releaseKey(release);
        return overrides[key] ?? { startDate: release.startDate, endDate: release.endDate };
    }, [overrides]);

    // chartRange spans every release (with overrides applied) plus padding,
    // anchored to a Monday. Always wide enough to also include the snapped
    // viewStart week so navigation never lands outside the rendered chart.
    const chartRange = useMemo(() => {
        const viewEnd = addDays(viewStart, VIEW_DAYS - 1);
        let minDate = viewStart;
        let maxDate = viewEnd;
        projects.forEach(project => {
            project.releases.forEach(release => {
                const dates = overrides[releaseKey(release)] ?? { startDate: release.startDate, endDate: release.endDate };
                if (dates.startDate) minDate = minIso(minDate, dates.startDate);
                if (dates.endDate) maxDate = maxIso(maxDate, dates.endDate);
            });
        });
        const firstDay = mondayOf(addDays(minDate, -PAD_DAYS));
        const lastDay = addDays(maxDate, PAD_DAYS);
        const totalDays = daysBetween(firstDay, lastDay) + 1;
        return { firstDay, totalDays, totalPx: totalDays * DAY_PX };
    }, [projects, overrides, viewStart]);

    const dayHeaders = useMemo(() => {
        const todayStr = todayIso();
        const headers = [];
        for (let i = 0; i < chartRange.totalDays; i++) {
            const iso = addDays(chartRange.firstDay, i);
            const d = new Date(iso + 'T00:00:00');
            const isWeekend = d.getDay() === 0 || d.getDay() === 6;
            headers.push({
                iso,
                weekday: d.toLocaleDateString('en-US', { weekday: 'short' }),
                dayNum: d.getDate(),
                month: d.toLocaleDateString('en-US', { month: 'short' }),
                isToday: iso === todayStr,
                isWeekend,
                leftPx: i * DAY_PX
            });
        }
        return headers;
    }, [chartRange.firstDay, chartRange.totalDays]);

    const calculateBarPosition = (startDateStr, endDateStr) => {
        if (!startDateStr || !endDateStr) {
            return { left: 0, width: 0, visible: false };
        }
        const startIdx = daysBetween(chartRange.firstDay, startDateStr);
        const endIdx = daysBetween(chartRange.firstDay, endDateStr);
        if (endIdx < 0 || startIdx >= chartRange.totalDays) {
            return { left: 0, width: 0, visible: false };
        }
        const left = startIdx * DAY_PX;
        const width = (endIdx - startIdx + 1) * DAY_PX;
        return { left, width, visible: true };
    };

    const formatDate = (dateStr) => {
        if (!dateStr) return '';
        const date = new Date(dateStr + 'T00:00:00');
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    };

    const handleMouseMove = (e, item) => {
        if (dragging) return;
        setHoveredItem(item);
        setHoverPosition({ x: e.clientX, y: e.clientY });
    };

    const handleMouseLeave = () => {
        setHoveredItem(null);
    };

    const startDrag = (e, release, mode) => {
        e.preventDefault();
        e.stopPropagation();

        const dragStartX = e.clientX;
        const key = releaseKey(release);
        const initial = overrides[key] ?? { startDate: release.startDate, endDate: release.endDate };
        const initialDuration = daysBetween(initial.startDate, initial.endDate);
        let lastDaysDelta = null;

        setDragging(true);
        setHoveredItem(null);

        const onMove = (moveEvent) => {
            const daysDelta = Math.round((moveEvent.clientX - dragStartX) / DAY_PX);
            if (daysDelta === lastDaysDelta) return;
            lastDaysDelta = daysDelta;
            let newStart = initial.startDate;
            let newEnd = initial.endDate;

            if (mode === 'move') {
                newStart = addDays(initial.startDate, daysDelta);
                newEnd = addDays(initial.endDate, daysDelta);
            } else if (mode === 'resize-start') {
                const clamped = Math.min(daysDelta, initialDuration);
                newStart = addDays(initial.startDate, clamped);
            } else if (mode === 'resize-end') {
                const clamped = Math.max(daysDelta, -initialDuration);
                newEnd = addDays(initial.endDate, clamped);
            }

            setOverrides(prev => ({ ...prev, [key]: { startDate: newStart, endDate: newEnd } }));
        };

        const onUp = () => {
            window.removeEventListener('mousemove', onMove);
            window.removeEventListener('mouseup', onUp);
            setDragging(false);
        };

        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
    };

    const weekLabel = useMemo(() => {
        const start = new Date(viewStart + 'T00:00:00');
        const end = new Date(addDays(viewStart, VIEW_DAYS - 1) + 'T00:00:00');
        const sameMonth = start.getMonth() === end.getMonth() && start.getFullYear() === end.getFullYear();
        const startMonth = start.toLocaleDateString('en-US', { month: 'short' });
        const endMonth = end.toLocaleDateString('en-US', { month: 'short' });
        const year = end.getFullYear();
        return sameMonth
            ? `${startMonth} ${start.getDate()}–${end.getDate()}, ${year}`
            : `${startMonth} ${start.getDate()} – ${endMonth} ${end.getDate()}, ${year}`;
    }, [viewStart]);

    const navigateTo = (next, behavior = 'smooth') => {
        scrollIntentRef.current = { targetWeek: next, behavior };
        setViewStart(next);
    };
    const goPrevWeek = () => navigateTo(addDays(viewStart, -7));
    const goNextWeek = () => navigateTo(addDays(viewStart, 7));
    const goToday = () => navigateTo(mondayOf(todayIso()));

    const openDatePicker = () => {
        setDatePickerValue(viewStart);
        setDatePickerOpen(true);
    };
    const jumpToPickedDate = () => {
        if (datePickerValue) {
            navigateTo(mondayOf(datePickerValue));
        }
        setDatePickerOpen(false);
    };

    // Set initial-scroll intent once the chart first renders with real data.
    useEffect(() => {
        if (!initialLoad && !scrollIntentRef.current) {
            scrollIntentRef.current = { targetWeek: viewStart, behavior: 'auto' };
        }
    }, [initialLoad, viewStart]);

    // Consume the scroll intent — runs after every render that might have made the
    // intent's target date land at a stable position. Drag re-renders never set
    // an intent, so the chart stays put while the user drags.
    useEffect(() => {
        const intent = scrollIntentRef.current;
        if (!intent || !scrollContainerRef.current) return;
        if (intent.targetWeek !== viewStart) return;
        const targetX = daysBetween(chartRange.firstDay, intent.targetWeek) * DAY_PX;
        scrollContainerRef.current.scrollTo({ left: targetX, behavior: intent.behavior });
        scrollIntentRef.current = null;
    }, [viewStart, chartRange.firstDay]);

    const viewStartLeftPx = daysBetween(chartRange.firstDay, viewStart) * DAY_PX;
    const viewWindowWidthPx = VIEW_DAYS * DAY_PX;

    return (
        <>
            <div ref={scrollContainerRef} className="flex-1 overflow-auto h-full">
                {loading && initialLoad && (
                    <div className="text-center py-12">
                        <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-accent-500 mb-4"></div>
                        <p className="text-gray-600 font-medium">Loading Gantt chart data...</p>
                    </div>
                )}

                {error && (
                    <div className="bg-red-50 border-l-4 border-red-500 text-red-700 px-6 py-4 rounded-lg shadow-sm m-4">
                        <div className="flex items-start">
                            <span className="text-xl mr-3">⚠️</span>
                            <div>
                                <p className="font-semibold">Unable to load Gantt chart data</p>
                                <p className="text-sm mt-1">{error}</p>
                            </div>
                        </div>
                    </div>
                )}

                {!initialLoad && !error && projects.length > 0 && (
                    <div style={{ width: SIDEBAR_PX + chartRange.totalPx }}>
                        {/* Sticky header */}
                        <div className="sticky top-0 z-30 bg-gray-100 border-b-2 border-gray-300 flex" style={{ minHeight: '60px' }}>
                            <div
                                className="sticky left-0 z-40 flex-shrink-0 border-r-2 border-gray-300 bg-gray-100 px-2 py-2 flex flex-col justify-center gap-1"
                                style={{ width: SIDEBAR_PX }}
                            >
                                <div className="flex items-center gap-1">
                                    <button
                                        onClick={goPrevWeek}
                                        className="px-2 py-0.5 text-xs rounded bg-white border border-gray-300 hover:bg-gray-50"
                                        title="Previous week"
                                    >◀</button>
                                    <button
                                        onClick={goToday}
                                        className="px-2 py-0.5 text-xs rounded bg-white border border-gray-300 hover:bg-gray-50 font-medium"
                                    >Today</button>
                                    <button
                                        onClick={goNextWeek}
                                        className="px-2 py-0.5 text-xs rounded bg-white border border-gray-300 hover:bg-gray-50"
                                        title="Next week"
                                    >▶</button>
                                    <button
                                        onClick={openDatePicker}
                                        className="px-2 py-0.5 text-xs rounded bg-white border border-gray-300 hover:bg-gray-50"
                                        title="Jump to date"
                                    >📅</button>
                                </div>
                                <span className="text-[10px] text-gray-600 font-medium">{weekLabel}</span>
                            </div>
                            <div className="relative flex-shrink-0" style={{ width: chartRange.totalPx, minHeight: '60px' }}>
                                {/* Snapped-week highlight */}
                                <div
                                    className="absolute top-0 bottom-0 bg-accent-100/60 border-x border-accent-400 pointer-events-none"
                                    style={{ left: viewStartLeftPx, width: viewWindowWidthPx }}
                                />
                                {dayHeaders.map((day) => (
                                    <div
                                        key={day.iso}
                                        className={`absolute border-r border-gray-300 text-center py-1 flex flex-col items-center justify-center ${day.isWeekend ? 'bg-gray-200/40' : ''} ${day.isToday ? 'bg-accent-200' : ''}`}
                                        style={{
                                            left: day.leftPx,
                                            width: DAY_PX,
                                            height: '100%'
                                        }}
                                    >
                                        <span className="text-[10px] font-semibold text-gray-600 uppercase">{day.weekday}</span>
                                        <span className="text-sm font-bold text-gray-800">{day.dayNum}</span>
                                        <span className="text-[9px] text-gray-500">{day.month}</span>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Body rows */}
                        <div>
                            {projects.map((project) => (
                                <div key={project.project}>
                                    {/* Project header label */}
                                    <div className="flex" style={{ minHeight: '28px' }}>
                                        <div
                                            className="sticky left-0 z-20 flex-shrink-0 border-r-2 border-gray-300 bg-gray-50 px-2 py-1 flex items-center"
                                            style={{ width: SIDEBAR_PX }}
                                        >
                                            <span className="text-sm font-bold text-gray-800 truncate">
                                                Project {project.project} — {project.projectName}
                                            </span>
                                        </div>
                                        <div className="bg-gray-50 flex-shrink-0" style={{ width: chartRange.totalPx, height: 28 }} />
                                    </div>

                                    {/* Release rows */}
                                    {project.releases.map((release) => {
                                        const dates = getReleaseDates(release);
                                        const releaseBar = calculateBarPosition(dates.startDate, dates.endDate);

                                        return (
                                            <div key={`${release.job}-${release.release}`} className="flex" style={{ minHeight: '28px' }}>
                                                <div
                                                    className="sticky left-0 z-20 flex-shrink-0 border-r-2 border-gray-300 bg-white px-2 py-1 pl-6 flex items-center"
                                                    style={{ width: SIDEBAR_PX }}
                                                >
                                                    <span className="text-xs text-gray-600">
                                                        {release.job}-{release.release}
                                                    </span>
                                                </div>
                                                <div
                                                    className="relative bg-white flex-shrink-0"
                                                    style={{ width: chartRange.totalPx, height: 24, ...DAY_GRID_STYLE }}
                                                >
                                                    {/* Snapped-week tint */}
                                                    <div
                                                        className="absolute top-0 bottom-0 bg-accent-50/40 pointer-events-none"
                                                        style={{ left: viewStartLeftPx, width: viewWindowWidthPx }}
                                                    />
                                                    {releaseBar.visible && (
                                                        <div
                                                            className={`absolute h-6 rounded shadow-sm flex items-center px-1 select-none ${dragging ? 'cursor-grabbing' : 'cursor-grab'}`}
                                                            style={{
                                                                left: releaseBar.left,
                                                                width: releaseBar.width,
                                                                backgroundColor: project.color,
                                                                opacity: 0.85
                                                            }}
                                                            onMouseDown={(e) => startDrag(e, release, 'move')}
                                                            onMouseMove={(e) => handleMouseMove(e, {
                                                                type: 'release',
                                                                job: release.job,
                                                                release: release.release,
                                                                jobName: release.jobName,
                                                                description: release.description,
                                                                startDate: dates.startDate,
                                                                endDate: dates.endDate,
                                                                pm: release.pm,
                                                                by: release.by
                                                            })}
                                                            onMouseLeave={handleMouseLeave}
                                                        >
                                                            {[
                                                                { side: 'left-0', mode: 'resize-start' },
                                                                { side: 'right-0', mode: 'resize-end' }
                                                            ].map(({ side, mode }) => (
                                                                <div
                                                                    key={mode}
                                                                    className={`absolute ${side} top-0 h-full cursor-ew-resize`}
                                                                    style={{ width: '8px' }}
                                                                    onMouseDown={(e) => startDrag(e, release, mode)}
                                                                />
                                                            ))}
                                                            <span className="text-white text-[10px] font-medium truncate pointer-events-none px-1">
                                                                {release.job}-{release.release}
                                                            </span>
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {!initialLoad && !error && projects.length === 0 && (
                    <div className="text-center py-12">
                        <p className="text-gray-600 font-medium">No releases with hard start-install dates and install hours found.</p>
                    </div>
                )}
            </div>
            {datePickerOpen && (
                <div
                    className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center"
                    onClick={() => setDatePickerOpen(false)}
                >
                    <div
                        className="bg-white rounded-lg shadow-2xl p-5 w-80"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <h3 className="text-sm font-bold text-gray-800 mb-3">Jump to date</h3>
                        <p className="text-xs text-gray-600 mb-3">Pick any date — the timeline will snap to that week's Monday.</p>
                        <input
                            type="date"
                            value={datePickerValue}
                            onChange={(e) => setDatePickerValue(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter') jumpToPickedDate(); }}
                            className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent-400"
                            autoFocus
                        />
                        <div className="flex justify-end gap-2 mt-4">
                            <button
                                onClick={() => setDatePickerOpen(false)}
                                className="px-3 py-1.5 text-sm rounded border border-gray-300 bg-white hover:bg-gray-50 text-gray-700"
                            >Cancel</button>
                            <button
                                onClick={jumpToPickedDate}
                                disabled={!datePickerValue}
                                className="px-3 py-1.5 text-sm rounded bg-accent-500 text-white hover:bg-accent-600 disabled:opacity-50 disabled:cursor-not-allowed"
                            >Jump</button>
                        </div>
                    </div>
                </div>
            )}
            {hoveredItem && !dragging && (
                <div
                    className="fixed bg-gray-900 text-white text-xs rounded-lg shadow-xl p-3 z-50 pointer-events-none"
                    style={{
                        left: `${hoverPosition.x + 10}px`,
                        top: `${hoverPosition.y + 10}px`,
                        maxWidth: '300px'
                    }}
                >
                    <div className="font-bold mb-1">Job {hoveredItem.job}-{hoveredItem.release}</div>
                    <div className="text-gray-300">{hoveredItem.jobName}</div>
                    {hoveredItem.description && (
                        <div className="text-gray-400 text-[10px] mt-1">{hoveredItem.description}</div>
                    )}
                    <div className="mt-2 pt-2 border-t border-gray-700">
                        <div>Start Install: {formatDate(hoveredItem.startDate)}</div>
                        <div>Comp ETA: {formatDate(hoveredItem.endDate)}</div>
                        {hoveredItem.pm && <div>PM: {hoveredItem.pm}</div>}
                        {hoveredItem.by && <div>BY: {hoveredItem.by}</div>}
                    </div>
                </div>
            )}
        </>
    );
}

export default GanttChart;
