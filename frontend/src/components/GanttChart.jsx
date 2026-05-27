/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Installer-team scheduling timeline. Y-axis is one lane per installer team; each
 *   release renders as a bar spanning start_install → comp_eta. Day-snap drag/resize persists
 *   the dates, and dragging a bar into another team's lane reassigns the installer.
 * exports:
 *   GanttChart: Team-laned timeline with move/resize drag persisted to the backend; week-snap nav.
 * imports_from: [react, ../services/jobsApi]
 * imported_by: [frontend/src/pages/PMBoard.jsx]
 * invariants:
 *   - Each configured installer team gets a lane even when empty (drop target).
 *   - Overlapping bars within a lane stack into packed sub-rows so they never visually collide.
 *   - Drag overrides are applied optimistically, persisted on mouse-up, and reverted on failure.
 *   - resize-start writes start_install; resize-end writes comp_eta; move shifts both; a vertical
 *     drop into another lane writes installer. Only changed fields are sent.
 *   - When filterComplete is true, releases whose stage === 'Complete' are excluded.
 *   - Week-snap nav buttons always anchor viewStart to a Monday; horizontal scroll is free-form.
 */
import React, { useState, useEffect, useLayoutEffect, useMemo, useRef, useCallback } from 'react';
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
const ROW_H = 30;   // height of one packed sub-row within a lane
const BAR_H = 24;
const BAR_PAD = (ROW_H - BAR_H) / 2;

const DAY_GRID_STYLE = {
    backgroundImage: 'linear-gradient(to right, rgba(0,0,0,0.06) 1px, transparent 1px)',
    backgroundSize: `${DAY_PX}px 100%`,
    backgroundRepeat: 'repeat'
};

function GanttChart({ filterComplete = false }) {
    const [teamsMeta, setTeamsMeta] = useState([]);   // [{ team, color }] in lane order
    const [releases, setReleases] = useState([]);     // flat list, each carries its server team
    const [loading, setLoading] = useState(true);
    const [initialLoad, setInitialLoad] = useState(true);
    const [error, setError] = useState(null);
    const [actionError, setActionError] = useState(null);
    const [hoveredItem, setHoveredItem] = useState(null);
    const [hoverPosition, setHoverPosition] = useState({ x: 0, y: 0 });
    const [overrides, setOverrides] = useState({});   // key -> { startDate, endDate, team }
    const [dragging, setDragging] = useState(false);
    const [dragKey, setDragKey] = useState(null);     // releaseKey of the bar being dragged
    const [dropTeam, setDropTeam] = useState(null);   // lane highlighted as the move target
    const [viewStart, setViewStart] = useState(() => mondayOf(todayIso()));
    const [datePickerOpen, setDatePickerOpen] = useState(false);
    const [datePickerValue, setDatePickerValue] = useState('');
    const scrollContainerRef = useRef(null);
    const bodyRef = useRef(null);
    const prevFirstDayRef = useRef(null);   // last chart origin, for scroll-anchoring on reflow
    const snapTimerRef = useRef(null);      // debounce for week-snapping free horizontal scroll
    const firstDayRef = useRef(null);       // live chart origin, read inside drag handlers
    const dragBoundsRef = useRef(null);     // wide date window pinned for the duration of a drag
    const snapSuppressUntilRef = useRef(0); // timestamp; skip scroll-snap until then (post-drop)
    const revealReleaseRef = useRef(null);  // {startDate,endDate} to scroll into view after a drop
    const scrollAnchorRef = useRef(null);   // {firstDay,scrollLeft} captured before a reflow, for exact restore
    // Set by nav handlers (and once after data loads) to request a scroll on the next render.
    // Drag-driven re-renders don't set this, so the chart never auto-scrolls mid-drag.
    const scrollIntentRef = useRef(null);

    const fetchData = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);

            const [ganttData, jobs] = await Promise.all([
                jobsApi.fetchGanttData(),
                filterComplete ? jobsApi.fetchAllJobs() : Promise.resolve([])
            ]);

            const teams = ganttData.teams || [];

            let nonCompleteJobs = null;
            if (filterComplete && jobs.length > 0) {
                nonCompleteJobs = new Set();
                jobs.forEach(job => {
                    if (job['Stage'] !== 'Complete') {
                        const jobNum = String(job['Job #'] || '').trim();
                        const releaseNum = String(job['Release #'] || '').trim();
                        if (jobNum && releaseNum) {
                            nonCompleteJobs.add(`${jobNum}-${releaseNum}`);
                        }
                    }
                });
            }

            const meta = teams.map(t => ({ team: t.team, color: t.color }));
            const flat = [];
            teams.forEach(t => {
                (t.releases || []).forEach(r => {
                    if (nonCompleteJobs) {
                        const jobKey = `${String(r.job).trim()}-${String(r.release).trim()}`;
                        if (!nonCompleteJobs.has(jobKey)) return;
                    }
                    flat.push({ ...r, color: t.color });
                });
            });

            setTeamsMeta(meta);
            setReleases(flat);
            setOverrides({});
        } catch (err) {
            setError(err.message || 'Failed to load timeline data');
        } finally {
            setLoading(false);
            setInitialLoad(false);
        }
    }, [filterComplete]);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    const releaseKey = (release) => `${release.job}-${release.release}`;

    const effective = useCallback((release) => {
        const o = overrides[releaseKey(release)];
        return {
            startDate: o?.startDate ?? release.startDate,
            endDate: o?.endDate ?? release.endDate,
            team: o?.team ?? release.team,
        };
    }, [overrides]);

    // chartRange spans every release (with overrides applied) plus padding, anchored to a
    // Monday, and always wide enough to include the snapped viewStart week.
    const chartRange = useMemo(() => {
        const viewEnd = addDays(viewStart, VIEW_DAYS - 1);
        let minDate = viewStart;
        let maxDate = viewEnd;
        releases.forEach(release => {
            const dates = effective(release);
            if (dates.startDate) minDate = minIso(minDate, dates.startDate);
            if (dates.endDate) maxDate = maxIso(maxDate, dates.endDate);
        });
        // While dragging, fold in a wide pinned window so the origin stays fixed
        // (no mid-drag reflow) and there's room to auto-scroll past the screen.
        if (dragging && dragBoundsRef.current) {
            minDate = minIso(minDate, dragBoundsRef.current.min);
            maxDate = maxIso(maxDate, dragBoundsRef.current.max);
        }
        const firstDay = mondayOf(addDays(minDate, -PAD_DAYS));
        const lastDay = addDays(maxDate, PAD_DAYS);
        const totalDays = daysBetween(firstDay, lastDay) + 1;
        return { firstDay, totalDays, totalPx: totalDays * DAY_PX };
    }, [releases, effective, viewStart, dragging]);

    // Keep the live origin available to imperative drag handlers (the closures
    // captured at drag-start would otherwise read a stale firstDay).
    firstDayRef.current = chartRange.firstDay;

    // When the chart origin (firstDay) shifts — e.g. dragging a bar into an earlier
    // week grows the chart on the left, or the pinned drag window collapses on drop —
    // every bar's pixel position moves with it. Restore the same content under the
    // viewport so it stays visually anchored instead of leaping sideways. Skipped when
    // a nav scroll intent is pending. Runs before paint.
    //
    // When the content SHRINKS the browser clamps scrollLeft before this runs, so a
    // relative `+= delta` would compound the clamp and slam the view to an edge. The
    // captured anchor (taken before the reflow) lets us set an ABSOLUTE target instead,
    // which is immune to that clamp. Falls back to the delta for uncaptured changes.
    useLayoutEffect(() => {
        const curr = chartRange.firstDay;
        const prev = prevFirstDayRef.current;
        prevFirstDayRef.current = curr;
        if (prev === null || prev === curr || scrollIntentRef.current) return;
        const el = scrollContainerRef.current;
        if (!el) return;
        const anchor = scrollAnchorRef.current;
        if (anchor) {
            scrollAnchorRef.current = null;
            el.scrollLeft = anchor.scrollLeft + daysBetween(curr, anchor.firstDay) * DAY_PX;
        } else {
            el.scrollLeft += daysBetween(curr, prev) * DAY_PX;
        }
    }, [chartRange.firstDay]);

    // After a drop, if the released bar ended up outside (or hard against) the
    // viewport — e.g. it was dragged out via edge auto-scroll — glide it back into
    // view, day-aligned. Runs after the anchor effect above so it reads the settled
    // scroll position. No-op when the bar is already comfortably visible.
    useLayoutEffect(() => {
        if (dragging) return;
        const target = revealReleaseRef.current;
        if (!target) return;
        revealReleaseRef.current = null;
        const el = scrollContainerRef.current;
        if (!el) return;
        const firstDay = chartRange.firstDay;
        const barLeftC = SIDEBAR_PX + daysBetween(firstDay, target.startDate) * DAY_PX;
        const barRightC = SIDEBAR_PX + (daysBetween(firstDay, target.endDate) + 1) * DAY_PX;
        const M = DAY_PX;   // breathing room added only when we actually scroll
        // Move ONLY when the bar is genuinely clipped by an edge. An in-view drop or
        // resize must not shift the viewport at all — so when nothing is clipped we
        // leave scrollLeft exactly as-is (no day-align, no scroll). Left check is last
        // so a bar wider than the viewport shows its start.
        let targetScroll = null;
        if (barRightC > el.scrollLeft + el.clientWidth) {
            targetScroll = barRightC - el.clientWidth + M;
        }
        if (barLeftC < (targetScroll ?? el.scrollLeft) + SIDEBAR_PX) {
            targetScroll = barLeftC - SIDEBAR_PX - M;
        }
        if (targetScroll === null) return;
        targetScroll = Math.max(0, Math.round(targetScroll / DAY_PX) * DAY_PX);
        if (Math.abs(targetScroll - el.scrollLeft) > 1) {
            el.scrollTo({ left: targetScroll, behavior: 'smooth' });
        }
    }, [dragging, chartRange.firstDay]);

    // Build lanes: one per configured team, with overlapping releases packed into sub-rows.
    const bands = useMemo(() => {
        let top = 0;
        const result = teamsMeta.map(({ team, color }) => {
            const laneReleases = releases
                .filter(r => effective(r).team === team)
                .map(r => ({ release: r, dates: effective(r) }))
                .sort((a, b) => {
                    // While dragging, pack the dragged release LAST so the rest keep
                    // their sub-rows fixed and don't shuffle under the cursor.
                    if (dragKey) {
                        const aDrag = releaseKey(a.release) === dragKey;
                        const bDrag = releaseKey(b.release) === dragKey;
                        if (aDrag !== bDrag) return aDrag ? 1 : -1;
                    }
                    return (a.dates.startDate || '').localeCompare(b.dates.startDate || '');
                });

            const rowEnds = []; // last endDate ISO per sub-row
            const items = laneReleases.map(({ release, dates }) => {
                let rowIndex = rowEnds.findIndex(end => dates.startDate && dates.startDate > end);
                if (rowIndex === -1) {
                    rowIndex = rowEnds.length;
                    rowEnds.push(dates.endDate || dates.startDate);
                } else {
                    rowEnds[rowIndex] = dates.endDate || dates.startDate;
                }
                return { release, dates, rowIndex };
            });

            const rows = Math.max(1, rowEnds.length);
            const height = rows * ROW_H;
            const band = { team, color, items, rows, height, top };
            top += height;
            return band;
        });
        return result;
    }, [teamsMeta, releases, effective, dragKey]);

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

    // Map a viewport X coordinate to a fractional day-index from the chart origin
    // (firstDay), accounting for the sticky sidebar and current horizontal scroll.
    const clientXToDayIndex = (clientX) => {
        const el = scrollContainerRef.current;
        if (!el) return 0;
        const rect = el.getBoundingClientRect();
        return (clientX - rect.left + el.scrollLeft - SIDEBAR_PX) / DAY_PX;
    };

    // Map a viewport Y coordinate to the team lane it falls within. Measures live
    // lane DOM rects so it stays correct as lanes flex-grow to fill or repack mid-drag.
    const teamAtY = (clientY) => {
        const el = bodyRef.current;
        if (!el) return null;
        const lanes = el.querySelectorAll('[data-lane-team]');
        if (lanes.length === 0) return null;
        for (const lane of lanes) {
            const r = lane.getBoundingClientRect();
            if (clientY >= r.top && clientY < r.bottom) return lane.getAttribute('data-lane-team');
        }
        const firstR = lanes[0].getBoundingClientRect();
        if (clientY < firstR.top) return lanes[0].getAttribute('data-lane-team');
        return lanes[lanes.length - 1].getAttribute('data-lane-team');
    };

    const persistChange = async (release, prevEffective, next) => {
        const startChanged = next.startDate !== prevEffective.startDate;
        const endChanged = next.endDate !== prevEffective.endDate;
        const teamChanged = next.team !== prevEffective.team;
        if (!startChanged && !endChanged && !teamChanged) return;

        const key = releaseKey(release);
        try {
            await jobsApi.updateTimelineBar(release.job, release.release, {
                startInstall: startChanged ? next.startDate : undefined,
                compEta: endChanged ? next.endDate : undefined,
                installer: teamChanged ? next.team : undefined,
            });
        } catch (err) {
            // Revert the optimistic override for this release.
            setOverrides(prev => {
                const copy = { ...prev };
                delete copy[key];
                return copy;
            });
            setActionError(
                `Failed to update ${release.job}-${release.release}: ${err.message || 'unknown error'}`
            );
        }
    };

    const startDrag = (e, release, mode) => {
        e.preventDefault();
        e.stopPropagation();

        const key = releaseKey(release);
        const initial = effective(release);

        // Offset (in days) between the cursor and the edge being moved, captured at
        // grab time. It's a pixel difference / DAY_PX, so it's origin-independent and
        // stays valid even as the chart origin shifts.
        const initialStartIdx = daysBetween(firstDayRef.current, initial.startDate);
        const initialEndIdx = daysBetween(firstDayRef.current, initial.endDate);
        const grabOffset = clientXToDayIndex(e.clientX)
            - (mode === 'resize-end' ? initialEndIdx : initialStartIdx);

        // Pin a wide window around the current data extent for the whole drag, so the
        // origin doesn't reflow mid-drag and the view can auto-scroll well past the
        // screen in either direction.
        let extMin = initial.startDate, extMax = initial.endDate;
        releases.forEach(r => {
            const d = effective(r);
            if (d.startDate && d.startDate < extMin) extMin = d.startDate;
            if (d.endDate && d.endDate > extMax) extMax = d.endDate;
        });
        dragBoundsRef.current = { min: addDays(extMin, -90), max: addDays(extMax, 90) };

        // Capture the exact view before the drag-start reflow widens the range, so the
        // anchor effect can restore it precisely (the content grows, so no clamp here,
        // but we keep both reflows symmetric).
        const sc = scrollContainerRef.current;
        scrollAnchorRef.current = sc ? { firstDay: firstDayRef.current, scrollLeft: sc.scrollLeft } : null;

        let lastClientX = e.clientX;
        let lastClientY = e.clientY;
        let lastKey = '';
        let current = { ...initial };
        let rafId = null;

        setDragging(true);
        setDragKey(key);
        setHoveredItem(null);
        if (mode === 'move') setDropTeam(initial.team);

        // Recompute the bar from the latest cursor position + live scroll/origin, and
        // snap to whole days. No-ops when nothing changed at day granularity.
        const apply = () => {
            const firstDay = firstDayRef.current;
            const targetIdx = Math.round(clientXToDayIndex(lastClientX) - grabOffset);

            let targetTeam = current.team;
            if (mode === 'move') targetTeam = teamAtY(lastClientY) || initial.team;

            let newStart = initial.startDate;
            let newEnd = initial.endDate;
            if (mode === 'move') {
                newStart = addDays(firstDay, targetIdx);
                newEnd = addDays(initial.endDate, daysBetween(initial.startDate, newStart));
            } else if (mode === 'resize-start') {
                newStart = addDays(firstDay, targetIdx);
                if (newStart > initial.endDate) newStart = initial.endDate;
            } else if (mode === 'resize-end') {
                newEnd = addDays(firstDay, targetIdx);
                if (newEnd < initial.startDate) newEnd = initial.startDate;
            }

            const sig = `${newStart}|${newEnd}|${targetTeam}`;
            if (sig === lastKey) return;
            lastKey = sig;
            current = { startDate: newStart, endDate: newEnd, team: targetTeam };
            if (mode === 'move') setDropTeam(targetTeam);
            setOverrides(prev => ({ ...prev, [key]: { ...current } }));
        };

        // Edge auto-scroll: while the cursor rests near a horizontal edge, pan the
        // chart so dragging past the screen keeps revealing further weeks. Runs every
        // frame; only scrolls (and recomputes) when in an edge zone.
        const EDGE = 56;   // px from edge that triggers panning
        const STEP = 16;   // px per frame
        const tick = () => {
            const el = scrollContainerRef.current;
            if (el) {
                const rect = el.getBoundingClientRect();
                let dir = 0;
                if (lastClientX > rect.right - EDGE) dir = 1;
                else if (lastClientX < rect.left + SIDEBAR_PX + EDGE) dir = -1;
                if (dir !== 0) {
                    const before = el.scrollLeft;
                    el.scrollLeft = before + dir * STEP;
                    if (el.scrollLeft !== before) apply();
                }
            }
            rafId = requestAnimationFrame(tick);
        };
        rafId = requestAnimationFrame(tick);

        const onMove = (moveEvent) => {
            lastClientX = moveEvent.clientX;
            lastClientY = moveEvent.clientY;
            apply();
        };

        const onUp = () => {
            window.removeEventListener('mousemove', onMove);
            window.removeEventListener('mouseup', onUp);
            if (rafId) cancelAnimationFrame(rafId);
            dragBoundsRef.current = null;
            // Capture the exact view BEFORE the drop reflow collapses the pinned window
            // and shrinks the content — the browser clamps scrollLeft on shrink, so the
            // anchor effect needs this to restore an absolute (clamp-proof) position.
            const sc = scrollContainerRef.current;
            scrollAnchorRef.current = sc ? { firstDay: firstDayRef.current, scrollLeft: sc.scrollLeft } : null;
            // The drop already positioned the view; don't let the post-drop reflow's
            // scroll-anchor adjustment trigger a snap that shifts it. The reveal effect
            // handles the one case we DO want to move: a release dropped out of view.
            snapSuppressUntilRef.current = Date.now() + 400;
            revealReleaseRef.current = { startDate: current.startDate, endDate: current.endDate };
            setDragging(false);
            setDragKey(null);
            setDropTeam(null);
            persistChange(release, initial, current);
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

    // Consume the scroll intent — runs after every render that might have made the intent's
    // target date land at a stable position. Drag re-renders never set an intent.
    useEffect(() => {
        const intent = scrollIntentRef.current;
        if (!intent || !scrollContainerRef.current) return;
        if (intent.targetWeek !== viewStart) return;
        const targetX = daysBetween(chartRange.firstDay, intent.targetWeek) * DAY_PX;
        scrollContainerRef.current.scrollTo({ left: targetX, behavior: intent.behavior });
        scrollIntentRef.current = null;
    }, [viewStart, chartRange.firstDay]);

    // Day-snap free horizontal scrolling: when the user stops scrolling, glide to the
    // nearest day boundary so the left edge never sits mid-day. Skipped mid-drag, while
    // a nav scroll intent settles, and for a short window after a drop — so dropping a
    // release doesn't yank the viewport; the drag-anchor leaves it where the user left it.
    const handleScrollSnap = () => {
        if (dragging) return;
        if (snapTimerRef.current) clearTimeout(snapTimerRef.current);
        snapTimerRef.current = setTimeout(() => {
            const el = scrollContainerRef.current;
            if (!el || dragging || scrollIntentRef.current || Date.now() < snapSuppressUntilRef.current) return;
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
            {actionError && (
                <div className="bg-red-50 border-l-4 border-red-500 text-red-700 px-4 py-2 text-sm flex items-start justify-between gap-3">
                    <span>{actionError}</span>
                    <button
                        onClick={() => setActionError(null)}
                        className="text-red-500 hover:text-red-700 font-bold"
                    >✕</button>
                </div>
            )}
            <div ref={scrollContainerRef} className="flex-1 overflow-auto h-full" onScroll={handleScrollSnap}>
                {loading && initialLoad && (
                    <div className="text-center py-12">
                        <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-accent-500 mb-4"></div>
                        <p className="text-gray-600 font-medium">Loading timeline data...</p>
                    </div>
                )}

                {error && (
                    <div className="bg-red-50 border-l-4 border-red-500 text-red-700 px-6 py-4 rounded-lg shadow-sm m-4">
                        <div className="flex items-start">
                            <span className="text-xl mr-3">⚠️</span>
                            <div>
                                <p className="font-semibold">Unable to load timeline data</p>
                                <p className="text-sm mt-1">{error}</p>
                            </div>
                        </div>
                    </div>
                )}

                {!initialLoad && !error && teamsMeta.length > 0 && (
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
                            {bands.map((band) => {
                                const isDropTarget = dragging && dropTeam === band.team;
                                return (
                                    <div
                                        key={band.team}
                                        data-lane-team={band.team}
                                        className="flex border-b border-gray-200"
                                        style={{ minHeight: band.height, flex: `1 1 ${band.height}px` }}
                                    >
                                        <div
                                            className={`sticky left-0 z-20 flex-shrink-0 border-r-2 border-gray-300 px-2 py-1 flex items-center gap-2 ${isDropTarget ? 'bg-accent-100' : 'bg-gray-50'}`}
                                            style={{ width: SIDEBAR_PX, height: '100%' }}
                                        >
                                            <span className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: band.color }} />
                                            <span className="text-sm font-bold text-gray-800 truncate">{band.team}</span>
                                            {band.items.length > 0 && (
                                                <span className="text-[10px] text-gray-500 ml-auto">{band.items.length}</span>
                                            )}
                                        </div>
                                        <div
                                            className={`relative flex-shrink-0 ${isDropTarget ? 'bg-accent-50/60' : 'bg-white'}`}
                                            style={{ width: chartRange.totalPx, height: '100%', ...DAY_GRID_STYLE }}
                                        >
                                            {/* Snapped-week tint */}
                                            <div
                                                className="absolute top-0 bottom-0 bg-accent-50/40 pointer-events-none"
                                                style={{ left: viewStartLeftPx, width: viewWindowWidthPx }}
                                            />
                                            {band.items.map(({ release, dates, rowIndex }) => {
                                                const bar = calculateBarPosition(dates.startDate, dates.endDate);
                                                if (!bar.visible) return null;
                                                const draggingThis = dragging && overrides[releaseKey(release)];
                                                return (
                                                    <div
                                                        key={`${release.job}-${release.release}`}
                                                        className={`absolute rounded shadow-sm flex items-center px-1 select-none ${dragging ? 'cursor-grabbing' : 'cursor-grab'}`}
                                                        style={{
                                                            left: bar.left,
                                                            width: bar.width,
                                                            top: rowIndex * ROW_H + BAR_PAD,
                                                            height: BAR_H,
                                                            backgroundColor: band.color,
                                                            opacity: draggingThis ? 1 : 0.85
                                                        }}
                                                        onMouseDown={(e) => startDrag(e, release, 'move')}
                                                        onMouseMove={(e) => handleMouseMove(e, {
                                                            type: 'release',
                                                            job: release.job,
                                                            release: release.release,
                                                            jobName: release.jobName,
                                                            description: release.description,
                                                            team: dates.team,
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
                                                );
                                            })}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                )}

                {!initialLoad && !error && teamsMeta.length === 0 && (
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
                        {hoveredItem.team && <div>Team: {hoveredItem.team}</div>}
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
