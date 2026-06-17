/**
 * @milehigh-header
 * schema_version: 2
 * purpose: Read-only installer-team scheduling timeline. Y-axis is one lane per installer team;
 *   each eligible release renders as a bar spanning Start install → comp_eta_effective. Pure
 *   client selector over the shared releases dataset (useReleases) — no fetch, no writes.
 * exports:
 *   GanttChart: Team-laned read-only timeline with week-snap nav and a jump-to-date picker.
 * imports_from: [react, ../services/jobsApi, ../context/ReleasesContext, ../constants/installerPalette, ../utils/formatters, ./ReleaseDetailModal]
 * imported_by: [frontend/src/pages/PMBoardContent.jsx]
 * invariants:
 *   - READ-ONLY: bars cannot be dragged, resized, or reassigned. The Timeline never writes; only Job Log does.
 *     Bars are clickable to open a read-only detail modal (ReleaseDetailModal); clicking never edits.
 *   - Lanes come from /brain/installer-teams (the roster); any installer present in the data but off-roster is appended as an extra lane so no bar is silently dropped. Lane colors come from the shared constants/installerPalette so List and Timeline match.
 *   - Eligibility mirrors the List installer columns plus an install_hrs gate (matching the backend /gantt-data filter): hard date (start_install_formulaTF === false) + Start install + installer + Install HRS > 0 + Stage Group in FABRICATION/READY_TO_SHIP/COMPLETE.
 *   - Overlapping bars within a lane stack into packed sub-rows so they never visually collide.
 *   - When filterComplete is true, releases whose Stage === 'Complete' are excluded.
 *   - Week-snap nav buttons always anchor viewStart to a Monday; horizontal scroll is free-form then day-snaps.
 * updated_by_agent: 2026-06-17 (clickable bars open a read-only release detail modal; enriched tooltip title)
 */
import React, { useState, useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import { jobsApi } from '../services/jobsApi';
import { useReleases } from '../context/ReleasesContext';
import { INSTALLER_PALETTE } from '../constants/installerPalette';
import { localTodayStr as todayIso } from '../utils/formatters';
import ReleaseDetailModal from './ReleaseDetailModal';

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

// Snap an ISO date to the Monday of that week (Mon = day 1, Sun = day 0 → -6).
const mondayOf = (isoDate) => {
    const d = new Date(isoDate + 'T00:00:00');
    const dow = d.getDay();
    const offset = dow === 0 ? -6 : 1 - dow;
    d.setDate(d.getDate() + offset);
    return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, '0'), String(d.getDate()).padStart(2, '0')].join('-');
};

// ISO (or ISO-with-time) → YYYY-MM-DD; '' for null/empty.
const dayPart = (v) => (v ? String(v).slice(0, 10) : '');

const minIso = (a, b) => (a < b ? a : b);
const maxIso = (a, b) => (a > b ? a : b);

const VIEW_DAYS = 7;
const DAY_PX = 80;
const PAD_DAYS = 14;
const SIDEBAR_PX = 192;
const ROW_H = 30;   // height of one packed sub-row within a lane
const BAR_H = 24;
const BAR_PAD = (ROW_H - BAR_H) / 2;

const ELIGIBLE_STAGE_GROUPS = new Set(['FABRICATION', 'READY_TO_SHIP', 'COMPLETE']);

const DAY_GRID_STYLE = {
    backgroundImage: 'linear-gradient(to right, rgba(0,0,0,0.06) 1px, transparent 1px)',
    backgroundSize: `${DAY_PX}px 100%`,
    backgroundRepeat: 'repeat'
};

// A shared release row qualifies for the installer timeline when it has a hard
// Start install date, an assigned installer, positive install hours, and sits in
// a fabrication/ship/complete stage group. Mirrors the backend /gantt-data filter.
function toBar(job, filterComplete) {
    if (filterComplete && job['Stage'] === 'Complete') return null;
    if (job['start_install_formulaTF'] !== false) return null;
    const startDate = dayPart(job['Start install']);
    if (!startDate) return null;
    const team = (job.installer || '').trim();
    if (!team) return null;
    const installHrs = Number(job['Install HRS']);
    if (!(installHrs > 0)) return null;
    if (!ELIGIBLE_STAGE_GROUPS.has(job['Stage Group'])) return null;
    // comp_eta_effective is the serializer's canonical end (prefers comp_eta, else
    // derives a window, floored at start_install) — never before startDate.
    const endDate = dayPart(job['comp_eta_effective']) || dayPart(job['Comp. ETA']) || startDate;
    return {
        id: job['id'],
        job: job['Job #'],
        release: job['Release #'],
        jobName: job['Job'] || '',
        description: job['Description'] || '',
        team,
        startDate,
        endDate,
        pm: job['PM'] || '',
        by: job['BY'] || '',
        // Full source row, handed to the read-only detail modal on click (carries every
        // core field + Trello/Procore/viewer links the modal renders without a fetch).
        raw: job,
    };
}

function GanttChart({ filterComplete = false }) {
    const { jobs, loading } = useReleases();
    const [installerTeams, setInstallerTeams] = useState([]);
    const [teamsLoaded, setTeamsLoaded] = useState(false);
    const [hoveredItem, setHoveredItem] = useState(null);
    const [hoverPosition, setHoverPosition] = useState({ x: 0, y: 0 });
    const [selectedRelease, setSelectedRelease] = useState(null);   // full job row for the detail modal
    const [viewStart, setViewStart] = useState(() => mondayOf(todayIso()));
    const [navNonce, setNavNonce] = useState(0);   // bumps each nav so the scroll fires even when viewStart is unchanged
    const [datePickerOpen, setDatePickerOpen] = useState(false);
    const [datePickerValue, setDatePickerValue] = useState('');
    const scrollContainerRef = useRef(null);
    const bodyRef = useRef(null);
    const prevFirstDayRef = useRef(null);   // last chart origin, for scroll-anchoring on reflow
    const snapTimerRef = useRef(null);      // debounce for week-snapping free horizontal scroll
    const didInitialScrollRef = useRef(false); // initial scroll-to-this-Monday done once per mount
    // Set by nav handlers (and once after data loads) to request a scroll on the next render.
    const scrollIntentRef = useRef(null);

    // Installer team roster → lane order. Read-only config; one fetch.
    useEffect(() => {
        let cancelled = false;
        jobsApi.getInstallerTeams()
            .then((teams) => { if (!cancelled) setInstallerTeams(teams); })
            .catch((err) => console.error('Failed to load installer teams:', err))
            .finally(() => { if (!cancelled) setTeamsLoaded(true); });
        return () => { cancelled = true; };
    }, []);

    // Eligible release bars, selected client-side from the shared dataset.
    const releases = useMemo(
        () => jobs.map((j) => toBar(j, filterComplete)).filter(Boolean),
        [jobs, filterComplete]
    );

    // Lane order: configured roster first, then any off-roster installer present in
    // the data (so no eligible bar is silently dropped). Color by final position.
    const teamsMeta = useMemo(() => {
        const ordered = [...installerTeams];
        const seen = new Set(ordered);
        releases.forEach((r) => {
            if (r.team && !seen.has(r.team)) { seen.add(r.team); ordered.push(r.team); }
        });
        return ordered.map((team, i) => ({ team, color: INSTALLER_PALETTE[i % INSTALLER_PALETTE.length] }));
    }, [installerTeams, releases]);

    const initialLoad = (loading && jobs.length === 0) || !teamsLoaded;

    // chartRange spans every release plus padding, anchored to a Monday, and always
    // wide enough to include the snapped viewStart week.
    const chartRange = useMemo(() => {
        const viewEnd = addDays(viewStart, VIEW_DAYS - 1);
        let minDate = viewStart;
        let maxDate = viewEnd;
        releases.forEach((release) => {
            if (release.startDate) minDate = minIso(minDate, release.startDate);
            if (release.endDate) maxDate = maxIso(maxDate, release.endDate);
        });
        const firstDay = mondayOf(addDays(minDate, -PAD_DAYS));
        const lastDay = addDays(maxDate, PAD_DAYS);
        const totalDays = daysBetween(firstDay, lastDay) + 1;
        return { firstDay, totalDays, totalPx: totalDays * DAY_PX };
    }, [releases, viewStart]);

    // When the chart origin (firstDay) shifts — e.g. a polled update introduces an
    // earlier release and grows the chart on the left — every bar's pixel position
    // moves with it. Restore the same content under the viewport so it stays visually
    // anchored instead of leaping sideways. Skipped when a nav scroll intent is pending.
    useLayoutEffect(() => {
        const curr = chartRange.firstDay;
        const prev = prevFirstDayRef.current;
        prevFirstDayRef.current = curr;
        if (prev === null || prev === curr || scrollIntentRef.current) return;
        const el = scrollContainerRef.current;
        if (!el) return;
        el.scrollLeft += daysBetween(curr, prev) * DAY_PX;
    }, [chartRange.firstDay]);

    // Build lanes: one per team, with overlapping releases packed into sub-rows.
    const bands = useMemo(() => {
        let top = 0;
        return teamsMeta.map(({ team, color }) => {
            const laneReleases = releases
                .filter((r) => r.team === team)
                .sort((a, b) => (a.startDate || '').localeCompare(b.startDate || ''));

            const rowEnds = []; // last endDate ISO per sub-row
            const items = laneReleases.map((release) => {
                let rowIndex = rowEnds.findIndex((end) => release.startDate && release.startDate > end);
                if (rowIndex === -1) {
                    rowIndex = rowEnds.length;
                    rowEnds.push(release.endDate || release.startDate);
                } else {
                    rowEnds[rowIndex] = release.endDate || release.startDate;
                }
                return { release, rowIndex };
            });

            const rows = Math.max(1, rowEnds.length);
            const height = rows * ROW_H;
            const band = { team, color, items, rows, height, top };
            top += height;
            return band;
        });
    }, [teamsMeta, releases]);

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
        setHoveredItem(item);
        setHoverPosition({ x: e.clientX, y: e.clientY });
    };

    const handleMouseLeave = () => {
        setHoveredItem(null);
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
        setNavNonce((n) => n + 1);   // ensures the consume effect re-runs even if next === viewStart (e.g. Today)
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

    // On first render with real data, snap the view so the current week's Monday sits
    // at the left edge. Done directly (not via the nav scroll-intent) because that path
    // only fires when firstDay changes — which it doesn't when every release is in the
    // future, leaving the view stuck ~2 weeks before today. Once per mount.
    useLayoutEffect(() => {
        if (initialLoad || didInitialScrollRef.current) return;
        if (teamsMeta.length === 0 || !scrollContainerRef.current) return;
        didInitialScrollRef.current = true;
        const targetX = daysBetween(chartRange.firstDay, mondayOf(todayIso())) * DAY_PX;
        scrollContainerRef.current.scrollLeft = Math.max(0, targetX);
    }, [initialLoad, teamsMeta.length, chartRange.firstDay]);

    // Consume the scroll intent — runs after every render that might have made the intent's
    // target date land at a stable position.
    useEffect(() => {
        const intent = scrollIntentRef.current;
        if (!intent || !scrollContainerRef.current) return;
        if (intent.targetWeek !== viewStart) return;
        const targetX = daysBetween(chartRange.firstDay, intent.targetWeek) * DAY_PX;
        scrollContainerRef.current.scrollTo({ left: Math.max(0, targetX), behavior: intent.behavior });
        scrollIntentRef.current = null;
    }, [viewStart, chartRange.firstDay, navNonce]);

    // Day-snap free horizontal scrolling: when the user stops scrolling, glide to the
    // nearest day boundary so the left edge never sits mid-day. Skipped while a nav
    // scroll intent settles.
    const handleScrollSnap = () => {
        if (snapTimerRef.current) clearTimeout(snapTimerRef.current);
        snapTimerRef.current = setTimeout(() => {
            const el = scrollContainerRef.current;
            if (!el || scrollIntentRef.current) return;
            const snapped = Math.round(el.scrollLeft / DAY_PX) * DAY_PX;
            if (Math.abs(snapped - el.scrollLeft) > 1) {
                el.scrollTo({ left: snapped, behavior: 'smooth' });
            }
        }, 140);
    };

    useEffect(() => () => clearTimeout(snapTimerRef.current), []);

    const viewStartLeftPx = daysBetween(chartRange.firstDay, viewStart) * DAY_PX;
    const viewWindowWidthPx = VIEW_DAYS * DAY_PX;

    return (
        <>
            <div ref={scrollContainerRef} className="flex-1 overflow-auto h-full" onScroll={handleScrollSnap}>
                {initialLoad && (
                    <div className="text-center py-12">
                        <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-accent-500 mb-4"></div>
                        <p className="text-gray-600 font-medium">Loading timeline data...</p>
                    </div>
                )}

                {!initialLoad && teamsMeta.length > 0 && (
                    <div className="flex flex-col" style={{ width: SIDEBAR_PX + chartRange.totalPx, minHeight: '100%' }}>
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

                        {/* Lanes (one per installer team). Lanes flex-grow to fill the
                            viewport so the grid never leaves dead white space below; they
                            never shrink below their packed-row height (minHeight). */}
                        <div ref={bodyRef} className="flex-1 flex flex-col">
                            {bands.map((band) => (
                                <div
                                    key={band.team}
                                    data-lane-team={band.team}
                                    className="flex border-b border-gray-200"
                                    style={{ minHeight: band.height, flex: `1 1 ${band.height}px` }}
                                >
                                    <div
                                        className="sticky left-0 z-20 flex-shrink-0 border-r-2 border-gray-300 px-2 py-1 flex items-center gap-2 bg-gray-50"
                                        style={{ width: SIDEBAR_PX, height: '100%' }}
                                    >
                                        <span className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: band.color }} />
                                        <span className="text-sm font-bold text-gray-800 truncate">{band.team}</span>
                                        {band.items.length > 0 && (
                                            <span className="text-[10px] text-gray-500 ml-auto">{band.items.length}</span>
                                        )}
                                    </div>
                                    <div
                                        className="relative flex-shrink-0 bg-white"
                                        style={{ width: chartRange.totalPx, height: '100%', ...DAY_GRID_STYLE }}
                                    >
                                        {/* Snapped-week tint */}
                                        <div
                                            className="absolute top-0 bottom-0 bg-accent-50/40 pointer-events-none"
                                            style={{ left: viewStartLeftPx, width: viewWindowWidthPx }}
                                        />
                                        {band.items.map(({ release, rowIndex }) => {
                                            const bar = calculateBarPosition(release.startDate, release.endDate);
                                            if (!bar.visible) return null;
                                            return (
                                                <div
                                                    key={`${release.job}-${release.release}`}
                                                    className="absolute rounded shadow-sm flex items-center px-1 select-none cursor-pointer hover:opacity-100"
                                                    style={{
                                                        left: bar.left,
                                                        width: bar.width,
                                                        top: rowIndex * ROW_H + BAR_PAD,
                                                        height: BAR_H,
                                                        backgroundColor: band.color,
                                                        opacity: 0.85
                                                    }}
                                                    onClick={() => setSelectedRelease(release.raw)}
                                                    onMouseMove={(e) => handleMouseMove(e, {
                                                        type: 'release',
                                                        job: release.job,
                                                        release: release.release,
                                                        jobName: release.jobName,
                                                        description: release.description,
                                                        team: release.team,
                                                        startDate: release.startDate,
                                                        endDate: release.endDate,
                                                        pm: release.pm,
                                                        by: release.by
                                                    })}
                                                    onMouseLeave={handleMouseLeave}
                                                >
                                                    <span className="text-white text-[10px] font-medium truncate pointer-events-none px-1">
                                                        <span className="font-bold">{release.job}-{release.release}</span>
                                                        {release.jobName ? ` · ${release.jobName}` : ''}
                                                        {release.description ? ` — ${release.description}` : ''}
                                                    </span>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {!initialLoad && teamsMeta.length === 0 && (
                    <div className="text-center py-12">
                        <p className="text-gray-600 font-medium">No installer teams configured.</p>
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
            {hoveredItem && (
                <div
                    className="fixed bg-gray-900 text-white text-xs rounded-lg shadow-xl p-3 z-50 pointer-events-none"
                    style={{
                        left: `${hoverPosition.x + 10}px`,
                        top: `${hoverPosition.y + 10}px`,
                        maxWidth: '300px'
                    }}
                >
                    <div className="font-bold mb-1">
                        Job {hoveredItem.job}-{hoveredItem.release}{hoveredItem.jobName ? ` · ${hoveredItem.jobName}` : ''}
                    </div>
                    {hoveredItem.description && (
                        <div className="text-gray-300 text-[10px]">{hoveredItem.description}</div>
                    )}
                    <div className="mt-2 pt-2 border-t border-gray-700">
                        {hoveredItem.team && <div>Team: {hoveredItem.team}</div>}
                        <div>Start Install: {formatDate(hoveredItem.startDate)}</div>
                        <div>Comp ETA: {formatDate(hoveredItem.endDate)}</div>
                        {hoveredItem.pm && <div>PM: {hoveredItem.pm}</div>}
                        {hoveredItem.by && <div>BY: {hoveredItem.by}</div>}
                    </div>
                </div>
            )}
            <ReleaseDetailModal
                isOpen={!!selectedRelease}
                release={selectedRelease}
                onClose={() => setSelectedRelease(null)}
            />
        </>
    );
}

export default GanttChart;
