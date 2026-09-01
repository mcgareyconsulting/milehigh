/**
 * @milehigh-header
 * schema_version: 7
 * purpose: Release timeline and install-scheduling surface, mixing two lane shapes on one X-axis of day/week columns.
 *   Y-axis is a stack of lanes: two shipping-stage lanes (Shipping Planning, Shipping Completed) on
 *   top, then one lane per installer team. SHIPPING lanes are a DAY/WEEK-BUCKET BOARD ("the Trello
 *   board on its side"): each release is a POINT-EVENT card in the (lane, Start-install column) cell,
 *   cards in the same cell stack vertically, and the column IS the date so position never drifts.
 *   INSTALLER lanes are a classic GANTT: each release is a horizontal RANGE bar spanning
 *   start_install → comp_eta, packed into rows so overlapping installs never collide. A release that
 *   is both a shipping stage AND assigned mirrors into both lanes off the same raw row (1:1 data).
 *   Left of everything sits a PINNED UNASSIGNED TRAY: a frozen vertical column of releases the shop
 *   has finished with that nobody is scheduled to install. Dragging a card from the tray onto a
 *   crew's lane assigns that crew and stamps a hard Start install on the day under the pointer.
 *   A client selector over useReleases for reads; installer + Start install are its only writes.
 * exports:
 *   GanttChart: Day/week-bucket board with zoom that scales column granularity (day↔week), width,
 *     card size, per-cell cap, and card detail; whole-column zoom snapping, week-snap nav, jump-to-date,
 *     and admin drag-to-assign between the unassigned tray and the installer lanes.
 * imports_from: [react, @dnd-kit/core, ../services/jobsApi, ../context/ReleasesContext, ../constants/installerPalette, ../utils/formatters, ../utils/unassignedLane, ../utils/timelineDrop, ../utils/shipLaneDrop, ./ReleaseHubModal, ./PdfMarkupModal]
 * imported_by: [frontend/src/pages/PMBoardContent.jsx]
 * invariants:
 *   - CLICKING opens ReleaseHubModal — the SAME modal a Job Log row or card opens. One release, one
 *     identity, whichever surface you clicked it from: no timeline-only cockpit or read-only variant,
 *     and no lane-colored accent (the hub tints itself from the stage). Every entry point routes
 *     through openHub(); a material-order chip on the Shipping Planning lane opens that same hub
 *     scrolled to the release's Materials Ordered section.
 *   - DRAGGING is the timeline's one write, and it is ADMIN-ONLY (every draggable/droppable is
 *     `disabled` otherwise, so hook order is identical for both roles and non-admins get exactly the
 *     old read-only timeline). Dropping a card on an installer lane PATCHes installer + a hard
 *     Start install for the day under the pointer in one call; dropping it back on the tray clears
 *     the installer and leaves the date alone. Both land undoable ReleaseEvents rows. The update is
 *     applied optimistically via ReleasesContext.patchJob and rolled back if the request fails.
 *   - SHIPPING lanes accept drops too, and their write is the STAGE ONLY (Ship Planning ↔ Ship
 *     Complete, via the same /brain/update-stage the Job Log dropdown uses — cascades into job_comp,
 *     the Trello list, N5 date discipline and the scheduling recalc all included). No date is ever
 *     written from a shipping drop: a shipping lane's X is DERIVED (planning sits on the ship date,
 *     completed on the hard Start install), so honouring the drop column would move an install date
 *     the user never aimed at. Dropping onto the lane a release is already in is a no-op, and a drop
 *     onto Shipping Completed is REFUSED when the release has no hard Start install — the lane is
 *     anchored on that date and the backend blanks estimated dates on the way in, so the card would
 *     silently vanish off the board. Because the write leaves no mark at the drop point, hovering a
 *     shipping lane washes the whole lane and names the stage it will set.
 *   - Drag is @dnd-kit (MouseSensor 8px + TouchSensor 220ms press-and-hold), NOT native HTML5 drag.
 *     The Phase-5 native-drag interactions were removed 2026-07-12 because native drag is dead on
 *     iPad; iPad is now the stated target, so this is a rebuild on pointer sensors, not a revert.
 *   - Lanes = two fixed shipping-stage lanes (DB stage 'Ship Planning' → "Shipping Planning",
 *     'Ship Complete' → "Shipping Completed"), then the installer roster from /brain/installer-teams,
 *     then any off-roster installer present in the data (so no card is silently dropped).
 *   - A release lands in a shipping lane iff its Stage is 'Ship Planning'/'Ship Complete' (just a
 *     hard Start install date to position it). It ALSO MIRRORS into its installer's (person's) lane
 *     whenever an installer is assigned — regardless of stage or install hours. So one release can
 *     appear in two lanes (its shipping lane + its installer lane), both backed by the same raw row
 *     (1:1 data). A release with no shipping stage and no installer appears nowhere.
 *   - The UNASSIGNED TRAY holds rows with no installer whose Stage is Paint Complete / Store at MHMW /
 *     Ship Planning (utils/unassignedLane — the same set the Job Log's "Ready to Ship" quick filter
 *     uses, imported from one place so the two surfaces cannot drift). Deliberately not "any release
 *     with no installer": that pulls in every drafting and fab row and the tray stops being a work
 *     surface. A tray release in Ship Planning ALSO appears in its shipping lane, like the mirror.
 *     Tray cards show job-release, job name and description only — the qualifying stage is not
 *     repeated on the card (it's in the detail modal, and all three stages read as "ready").
 *   - Installer lane colors come from constants/installerPalette indexed by installer position (NOT
 *     overall lane position) so List and Timeline colors keep matching; shipping lanes use their own
 *     board colors.
 *   - SHIPPING-LANE bucket layout: cards are placed by Start-install COLUMN (a day or a week, per
 *     zoom) and stacked vertically within a lane×column cell (natural flow, never overlapping —
 *     position is the true date). Cards are natural height so name/description are NOT truncated at
 *     wrap zoom levels; these lane heights are MEASURED (useLayoutEffect) from the tallest cell. A
 *     cell over the zoom's cap renders (cap-1) cards plus a "+N more" chip. Counts are never dropped.
 *   - INSTALLER-LANE gantt layout: each release is an absolute-positioned RANGE bar from start_install
 *     to comp_eta (inclusive), width floored at MIN_BAR_PX so a same-day install stays clickable. Bars
 *     are greedily packed into rows (interval partitioning) so overlaps stack; the lane height is
 *     COMPUTED from the row count (contentH), not measured. Bars share the shipping card's raw row.
 *   - When filterComplete is true, releases whose Stage === 'Complete' are excluded.
 *   - Zoom presets target a whole number of VISIBLE COLUMNS (days when unit='day', weeks when
 *     unit='week'); column width is derived from the live viewport so exactly that many clean columns
 *     fill the chart. On zoom the viewport re-anchors on the same left-edge DATE (across day↔week
 *     switches) and snaps to a whole-column boundary. Week-snap nav anchors viewStart to a Monday.
 * updated_by_agent: 2026-09-01 (T1: shipping-lane drag = stage-only write, Ship Planning ↔ Ship Complete)
 */
import React, { useState, useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import { jobsApi } from '../services/jobsApi';
import { useReleases } from '../context/ReleasesContext';
import {
    DndContext,
    DragOverlay,
    MouseSensor,
    TouchSensor,
    useSensor,
    useSensors,
    useDraggable,
    useDroppable,
} from '@dnd-kit/core';
import { INSTALLER_PALETTE } from '../constants/installerPalette';
import { selectUnassigned } from '../utils/unassignedLane';
import { dateAtDropX } from '../utils/timelineDrop';
import { shipLaneDropOutcome, shipLabelFor } from '../utils/shipLaneDrop';
import { localTodayStr as todayIso, subtractBusinessDays } from '../utils/formatters';
import { API_BASE_URL } from '../utils/api';
import { ReleaseHubModal } from './ReleaseHubModal';
import { PdfMarkupModal } from './PdfMarkupModal';
import { checkAuth } from '../utils/auth';

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
const PAD_DAYS = 14;
const SIDEBAR_PX = 192;
const STAGING_PX = 200;   // width of the pinned Unassigned staging column, frozen left of the lane sidebar
const HEADER_PX = 60;     // sticky header height — the staging tray hangs below it
const CARD_GUTTER = 5;    // horizontal inset within a column
const CARD_VGAP = 3;      // vertical gap between stacked cards in a cell
const CELL_PAD_TOP = 5;   // top padding inside a lane before the first card
const ORDER_ROW_PX = 26;  // height reserved at the bottom of the Shipping Planning lane for the PU/order overlay strip
const MIN_BAR_PX = 26;    // floor width for an installer range bar so a same-day install stays visible/clickable
const SHIP_PLANNING_LANE = 'Shipping Planning';
// Drop-target ids. Namespaced so an installer team literally named "staging" can't collide with
// the tray, and so onDragEnd can tell a lane drop from a send-back-to-unassigned drop.
const STAGING_DROP_ID = 'unassigned-tray';
const laneDropId = (lane) => `lane:${lane}`;
const laneOfDropId = (id) => (typeof id === 'string' && id.startsWith('lane:') ? id.slice(5) : null);
// Short badge + tooltip prefix per material-order kind for the shipping-lane overlay.
const ORDER_KIND_BADGE = { stock: 'PU', galvanizing: 'GALV', material: 'MAT' };

// Zoom presets, far-out → zoomed-in. Each level targets a whole number of VISIBLE COLUMNS
// (`cols`) at a granularity (`unit`): 'day' = one day per column, 'week' = one week per column.
// The column width is derived from the actual viewport so exactly `cols` clean columns fill the
// screen. Zooming out past 3 weeks (index 2) collapses days into week columns so you can see a
// quarter without microscopic days. Also scales card min-height, the per-cell cap (before a
// "+N more" chip), text wrap on/off, and `detail`. Default (index 4) is exactly one week.
// `imgH` = cover-photo thumbnail height on cards (0 = no thumbnail). Only the close/"weekly and
// sooner" levels show the manifest/cover-sheet photo (Trello-card style).
const ZOOM_LEVELS = [
    { unit: 'week', cols: 12, minCardH: 20, cap: 4, detail: 'min', wrap: false, imgH: 0 },  // ~a quarter
    { unit: 'week', cols: 6, minCardH: 22, cap: 5, detail: 'low', wrap: false, imgH: 0 },   // 6 weeks
    { unit: 'day', cols: 21, minCardH: 24, cap: 5, detail: 'low', wrap: false, imgH: 0 },   // 3 weeks
    { unit: 'day', cols: 14, minCardH: 40, cap: 6, detail: 'med', wrap: true, imgH: 0 },    // 2 weeks
    { unit: 'day', cols: 7, minCardH: 52, cap: 7, detail: 'high', wrap: true, imgH: 66 },   // 1 week (default)
    { unit: 'day', cols: 4, minCardH: 72, cap: 8, detail: 'full', wrap: true, imgH: 96 },
    { unit: 'day', cols: 2, minCardH: 96, cap: 9, detail: 'full', wrap: true, imgH: 128 },
];
const DEFAULT_ZOOM = 4;
const MIN_COL_PX = 40;    // floor so columns never collapse on a narrow screen (then it scrolls)

// The two shipping-stage lanes that sit above the installer lanes. `stage` is the
// exact DB Stage value (app/trello/list_mapper.py) a release must have to land here.
const SHIP_LANES = [
    { lane: 'Shipping Planning', stage: 'Ship Planning', color: 'rgb(245 158 11)' },
    { lane: 'Shipping Completed', stage: 'Ship Complete', color: 'rgb(139 92 246)' },
];
const STAGE_TO_SHIP_LANE = new Map(SHIP_LANES.map((s) => [s.stage, s.lane]));
// Reverse lookup: dropping on a shipping lane sets the release to that lane's stage.
const LANE_TO_SHIP_STAGE = new Map(SHIP_LANES.map((s) => [s.lane, s.stage]));

// Within a lane×column cell: ASAP rush jobs first, then by job # asc, then release # asc.
// Deterministic so the stack order is stable across polls/zoom.
function inCellSort(a, b) {
    const aAsap = a.raw && a.raw['start_install_asap'] === true ? 0 : 1;
    const bAsap = b.raw && b.raw['start_install_asap'] === true ? 0 : 1;
    if (aAsap !== bAsap) return aAsap - bAsap;
    const jobDiff = (Number(a.job) || 0) - (Number(b.job) || 0);
    if (jobDiff !== 0) return jobDiff;
    return String(a.release).localeCompare(String(b.release), undefined, { numeric: true });
}

// Classify a shared release row into timeline lanes, returning ZERO OR MORE bar objects
// (one per lane the release belongs to) so an assigned release MIRRORS across lanes:
//   - Its shipping-stage lane as a POINT card: Shipping Planning is positioned on the SHIP date
//     (explicit hard Ship Date when set, else estimated one business day before a hard Start
//     install); Shipping Completed is positioned on the hard Start install date, so moving a
//     release from planning to completed nudges its card forward from ship day to install day.
//   - Its installer (person) lane as a RANGE bar (start_install -> comp_eta) whenever an installer
//     is assigned - regardless of stage or install hours.
// A release that is both a shipping stage AND assigned therefore appears in BOTH lanes, backed by
// the same raw row (1:1 data). Each bar shares an `id` but differs by `lane`; card React keys are
// lane/cell-scoped so the duplicate id never collides.
function toBars(job, filterComplete) {
    if (filterComplete && job['Stage'] === 'Complete') return [];

    const shipLane = STAGE_TO_SHIP_LANE.get(job['Stage']);
    // A hard (non-formula) Start install anchors installer bars and the ship-date estimate.
    // Soft/projected dates never land on the timeline.
    const installDate = job['start_install_formulaTF'] === false ? dayPart(job['Start install']) : '';
    const team = (job.installer || '').trim();

    // Fields shared by every bar this release produces; per-bar position/flags added below.
    const base = {
        id: job['id'],
        job: job['Job #'],
        release: job['Release #'],
        jobName: job['Job'] || '',
        description: job['Description'] || '',
        stage: job['Stage'] || '',
        team,
        installDate,   // the hard Start install (may be '' for a ship-date-only planning card)
        pm: job['PM'] || '',
        by: job['BY'] || '',
        raw: job,      // full source row -> read-only detail modal on click
    };

    const bars = [];

    // --- Stage (shipping) lane: a point card. ---
    if (shipLane === SHIP_PLANNING_LANE) {
        // Ship on the explicit hard Ship Date, else estimate (install - 1 business day).
        const hardShip = dayPart(job['Ship Date']);
        const shipDate = hardShip || (installDate ? subtractBusinessDays(installDate, 1) : '');
        if (shipDate) {
            bars.push({
                ...base, lane: shipLane, isShip: true,
                shipEstimated: !hardShip, installAnchored: false,
                startDate: shipDate, endDate: shipDate,   // point event; no duration bar
            });
        }
    } else if (shipLane) {
        // Shipping Completed - anchored on the hard Start install date.
        if (installDate) {
            bars.push({
                ...base, lane: shipLane, isShip: true,
                shipEstimated: false, installAnchored: true,
                startDate: installDate, endDate: installDate,
            });
        }
    }

    // --- Installer (person) lane MIRROR: a range bar spanning start_install -> comp_eta. ---
    // Any assigned release with a hard install date shows here, regardless of stage/hours.
    if (team && installDate) {
        // comp_eta_effective is the serializer's canonical end (prefers comp_eta, else derives a
        // window). It can land BEFORE start_install (stale comp_eta); clamp so it's never negative.
        const rawEnd = dayPart(job['comp_eta_effective']) || dayPart(job['Comp. ETA']) || installDate;
        bars.push({
            ...base, lane: team, isShip: false,
            shipEstimated: false, installAnchored: false,
            startDate: installDate, endDate: maxIso(rawEnd, installDate),
        });
    }

    return bars;
}

const formatDate = (dateStr) => {
    if (!dateStr) return '';
    const date = new Date(dateStr + 'T00:00:00');
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
};

const shortDate = (dateStr) => {
    if (!dateStr) return '';
    const date = new Date(dateStr + 'T00:00:00');
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

// Progressive card content: the more we zoom in, the more of the release we surface.
// wrap=true (weekly and closer): name/description wrap to as many lines as needed — NO
// truncation. wrap=false (far zoom): single-line truncate to keep tiny cards tidy.
function CardBody({ release, detail, wrap }) {
    const jr = `${release.job}-${release.release}`;
    const nameSuffix = release.jobName ? ` · ${release.jobName}` : '';
    const flow = wrap ? 'break-words' : 'truncate';
    if (detail === 'min') {
        return <span className="block text-white text-[10px] font-bold truncate leading-none">{jr}</span>;
    }
    if (detail === 'low') {
        return (
            <span className="block text-white text-[11px] truncate leading-none">
                <span className="font-bold">{jr}</span>{nameSuffix}
            </span>
        );
    }
    // med / high / full: multi-line stacked card.
    return (
        <div className="flex flex-col gap-0.5 leading-tight">
            <span className={`block text-white text-xs font-bold ${flow}`}>
                {jr}{nameSuffix}
            </span>
            {release.description && (
                <span className={`block text-white/90 text-[11px] ${flow}`}>{release.description}</span>
            )}
            {(detail === 'high' || detail === 'full') && (
                <span className="block text-white/80 text-[10px] truncate">
                    {release.isShip
                        ? (release.installAnchored
                            ? `Installs ${shortDate(release.startDate)}`
                            : `${release.shipEstimated ? 'Est. ships' : 'Ships'} ${shortDate(release.startDate)}`)
                        : `${shortDate(release.startDate)} → ${shortDate(release.endDate)}`}
                </span>
            )}
            {detail === 'full' && (release.team || release.pm) && (
                <span className="block text-white/70 text-[10px] truncate">
                    {release.isShip ? release.stage : release.team}{release.pm ? ` · PM ${release.pm}` : ''}
                </span>
            )}
        </div>
    );
}

// One release sitting in the pinned staging column. It has no date yet — that is the whole point,
// the date is what dropping it onto a lane×day cell writes — so the card shows shop state instead:
// job-release, name, description, and the stage that qualified it for the column.
function StagingCard({ job, draggable, onClick, onMouseMove, onMouseLeave }) {
    const jr = `${job['Job #']}-${job['Release #']}`;
    const asap = job['start_install_asap'] === true;
    // `disabled` keeps the hook order stable for non-admins, who get the same card without a grab.
    const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
        id: `staging:${job.id}`,
        data: { row: job, fromLane: null },
        disabled: !draggable,
    });
    return (
        <div
            ref={setNodeRef}
            role="button"
            tabIndex={0}
            onClick={onClick}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(); } }}
            onMouseMove={onMouseMove}
            onMouseLeave={onMouseLeave}
            {...attributes}
            {...listeners}
            style={{ opacity: isDragging ? 0.35 : 1, touchAction: draggable ? 'manipulation' : undefined }}
            className={`rounded border bg-white px-2 py-1.5 shadow-sm select-none hover:border-accent-400 hover:shadow ${draggable ? 'cursor-grab active:cursor-grabbing' : 'cursor-pointer'} ${asap ? 'border-l-4 border-l-red-500 border-red-400 bg-red-50 ring-2 ring-red-300' : 'border-gray-300'}`}
        >
            {asap && (
                <span className="inline-block mb-1 px-1.5 py-0.5 rounded bg-red-600 text-white text-[10px] font-extrabold tracking-wide leading-none">
                    ASAP
                </span>
            )}
            <div className="text-sm font-bold text-gray-900 truncate leading-tight">{jr}</div>
            {job['Job'] && (
                <div className="text-xs text-gray-700 truncate leading-snug">{job['Job']}</div>
            )}
            {job['Description'] && (
                <div className="text-xs text-gray-500 truncate leading-snug">{job['Description']}</div>
            )}
        </div>
    );
}

// The pinned tray, doubling as the "send it back" drop target: dragging a scheduled release here
// clears its installer and returns it to the unassigned pool. The date is deliberately left alone —
// unassigning is not the same as un-scheduling, and throwing away a date the user typed elsewhere
// would be a second, unasked-for write.
function StagingTray({ enabled, className, style, children }) {
    const { setNodeRef, isOver } = useDroppable({ id: STAGING_DROP_ID, disabled: !enabled });
    return (
        <div
            ref={setNodeRef}
            data-staging-tray="1"
            className={`${className} ${isOver ? 'ring-2 ring-inset ring-accent-400 bg-accent-50' : ''}`}
            style={style}
        >
            {children}
        </div>
    );
}

// A lane's chart area, doubling as its drop target. One droppable per lane (not per lane×day cell):
// on an INSTALLER lane the exact DAY comes from where the pointer let go, so 90 columns cost one
// droppable each instead of hundreds, and `hintLeft` paints the column the drop would land on so
// the user aims at a date rather than guessing. A SHIPPING lane has no date to aim at — its X is
// derived, not chosen — so it gets `hintLabel` instead: a whole-lane wash naming the stage the drop
// will write, because a stage change is invisible at the drop point and must be announced first.
function LaneDropArea({ lane, enabled, registerRef, hintLeft, hintLabel, colPx, className, style, children }) {
    const { setNodeRef, isOver } = useDroppable({
        id: laneDropId(lane),
        data: { lane },
        disabled: !enabled,
    });
    return (
        <div
            ref={(el) => { registerRef(el); setNodeRef(el); }}
            className={`${className} ${isOver ? 'ring-2 ring-inset ring-accent-400' : ''}`}
            style={style}
        >
            {isOver && !hintLabel && hintLeft != null && (
                <div
                    className="absolute top-0 bottom-0 bg-accent-300/40 border-x-2 border-accent-500 pointer-events-none z-10"
                    style={{ left: hintLeft, width: colPx }}
                />
            )}
            {isOver && hintLabel && (
                <>
                    {/* Whole-lane wash: the drop applies to the LANE, not to a column. */}
                    <div className="absolute inset-0 bg-accent-300/25 pointer-events-none z-10" />
                    <div
                        data-ship-drop-hint="1"
                        className="absolute top-1/2 -translate-y-1/2 px-2 py-0.5 rounded-full bg-accent-600 text-white text-[11px] font-bold shadow whitespace-nowrap pointer-events-none z-10"
                        style={{ left: (hintLeft ?? 0) + colPx / 2, transform: 'translate(-50%, -50%)' }}
                    >
                        {hintLabel}
                    </div>
                </>
            )}
            {children}
        </div>
    );
}

// One release sitting in a shipping lane as a point card. Draggable so the shop can walk a release
// from Shipping Planning to Shipping Completed without leaving the board — that drop writes the
// STAGE ONLY. Unlike an installer lane, a shipping lane's X position is derived (planning sits on
// the ship date, completed on the hard Start install), never chosen, so the drop column is ignored.
function ShipCard({ release, lane, color, minCardH, imgH, detail, wrap, draggable, onClick, onMouseMove, onMouseLeave }) {
    const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
        id: `ship:${release.id}:${lane}`,
        data: { row: release.raw, fromLane: lane },
        disabled: !draggable,
    });
    return (
        <div
            ref={setNodeRef}
            role="button"
            tabIndex={0}
            className={`rounded shadow-sm px-1.5 py-1 overflow-hidden select-none text-center hover:opacity-100 ${draggable ? 'cursor-grab active:cursor-grabbing' : 'cursor-pointer'}`}
            style={{
                backgroundColor: color,
                opacity: isDragging ? 0.35 : 0.9,
                minHeight: minCardH,
                touchAction: draggable ? 'manipulation' : undefined,
            }}
            {...attributes}
            {...listeners}
            onClick={onClick}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(); } }}
            onMouseMove={onMouseMove}
            onMouseLeave={onMouseLeave}
        >
            {imgH > 0 && release.raw && release.raw.cover_photo_id && (
                <div className="relative mb-1 -mx-0.5">
                    <img
                        src={`${API_BASE_URL}/brain/releases/${release.id}/photos/${release.raw.cover_photo_id}/file`}
                        alt=""
                        loading="lazy"
                        draggable={false}
                        className="w-full object-cover rounded bg-black/10"
                        style={{ height: imgH }}
                    />
                    {release.raw.photo_count > 1 && (
                        <span className="absolute top-0.5 right-0.5 px-1 rounded bg-black/60 text-white text-[9px] font-semibold leading-tight">
                            📎 {release.raw.photo_count}
                        </span>
                    )}
                </div>
            )}
            <CardBody release={release} detail={detail} wrap={wrap} />
        </div>
    );
}

// One release on an installer lane. Draggable so an already-scheduled install can be moved to
// another day or handed to another crew — the same gesture, the same write.
function InstallerBar({ release, lane, color, barH, twoLine, draggable, onClick, onMouseMove, onMouseLeave }) {
    const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
        id: `bar:${release.id}:${lane}`,
        data: { row: release.raw, fromLane: lane },
        disabled: !draggable,
    });
    return (
        <div
            ref={setNodeRef}
            role="button"
            className={`absolute rounded shadow-sm px-1.5 flex items-center overflow-hidden select-none hover:opacity-100 ${draggable ? 'cursor-grab active:cursor-grabbing' : 'cursor-pointer'}`}
            style={{
                left: release.left,
                top: release.top,
                width: release.width,
                height: barH,
                backgroundColor: color,
                opacity: isDragging ? 0.35 : 0.9,
                touchAction: draggable ? 'manipulation' : undefined,
            }}
            {...attributes}
            {...listeners}
            onClick={onClick}
            onMouseMove={onMouseMove}
            onMouseLeave={onMouseLeave}
        >
            <div className="min-w-0 w-full text-center leading-tight">
                <span className="block text-white text-[11px] font-semibold truncate">
                    <span className="font-bold">{release.job}-{release.release}</span>
                    {release.jobName ? ` · ${release.jobName}` : ''}
                </span>
                {twoLine && release.description && (
                    <span className="block text-white/90 text-[10px] truncate">{release.description}</span>
                )}
            </div>
        </div>
    );
}

function GanttChart({ filterComplete = false }) {
    const { jobs, loading, patchJob, refreshMaterialSummary } = useReleases();
    const [installerTeams, setInstallerTeams] = useState([]);
    const [teamsLoaded, setTeamsLoaded] = useState(false);
    const [planningOrders, setPlanningOrders] = useState([]);  // PU/stock/galv orders still to bring in
    const [hoveredItem, setHoveredItem] = useState(null);
    const [hoverPosition, setHoverPosition] = useState({ x: 0, y: 0 });
    // The release whose hub is open, and how it was opened. ONE modal for every entry point —
    // a lane card, a staging card, or a material-order chip — matching what a Job Log row opens.
    const [hubJob, setHubJob] = useState(null);              // full release row
    const [hubScrollToMaterials, setHubScrollToMaterials] = useState(false);
    const openHub = (row, { scrollToMaterials = false } = {}) => {
        setHubJob(row);
        setHubScrollToMaterials(scrollToMaterials);
    };
    const closeHub = () => { setHubJob(null); setHubScrollToMaterials(false); };
    const [isAdmin, setIsAdmin] = useState(false);                  // admins get the schedule cockpit; others the read-only detail modal
    const [markup, setMarkup] = useState(null);                     // {releaseId, versionId, mode} — drawing opened from the hub

    // A material-order chip only carries job/release digits; the hub's Drawings
    // tab needs the release row's id (and viewer_url). Look the row up in the
    // shared dataset, falling back to the bare digits if it isn't loaded.
    const openOrderHub = (o) => {
        const row = jobs.find(
            (j) =>
                String(j['Job #'] ?? j.job) === String(o.job) &&
                String(j['Release #'] ?? j.release ?? '') === String(o.release ?? '')
        );
        openHub(row || { job: o.job, release: o.release }, { scrollToMaterials: true });
    };
    const [dragRow, setDragRow] = useState(null);                   // raw release row currently under the pointer (drives DragOverlay)
    const [dropHint, setDropHint] = useState(null);                 // {lane, date, leftPx} — the day the drop would write
    const [dropError, setDropError] = useState(null);               // message shown when a scheduling write is rejected
    const [containerW, setContainerW] = useState(0);                // measured scroll-viewport width → derives colPx
    const [containerH, setContainerH] = useState(0);                // measured scroll-viewport height → caps the staging tray
    const [viewStart, setViewStart] = useState(() => mondayOf(todayIso()));
    const [navNonce, setNavNonce] = useState(0);   // bumps each nav so the scroll fires even when viewStart is unchanged
    const [datePickerOpen, setDatePickerOpen] = useState(false);
    const [datePickerValue, setDatePickerValue] = useState('');
    const [zoomIdx, setZoomIdx] = useState(DEFAULT_ZOOM);
    const [laneHeights, setLaneHeights] = useState({});   // measured px height per lane
    const scrollContainerRef = useRef(null);
    const bodyRef = useRef(null);
    const laneChartRefs = useRef({});      // lane name → chart-area DOM node, for height measurement
    const prevFirstDayRef = useRef(null);   // last chart origin, for scroll-anchoring on reflow
    const prevColPxRef = useRef(null);      // last column width, for scroll-anchoring on zoom
    const prevColDaysRef = useRef(null);    // last days-per-column, so day↔week zoom keeps the left-edge date
    const snapTimerRef = useRef(null);      // debounce for column-snapping free horizontal scroll
    const didInitialScrollRef = useRef(false); // initial scroll-to-this-Monday done once per mount
    // Set by nav handlers (and once after data loads) to request a scroll on the next render.
    const scrollIntentRef = useRef(null);

    const zoom = ZOOM_LEVELS[zoomIdx];
    const { minCardH, cap, detail, wrap, imgH } = zoom;
    const colDays = zoom.unit === 'week' ? 7 : 1;   // calendar days spanned by one column
    // Column width is derived from the live viewport so exactly `cols` columns fill the chart area
    // (viewport minus the sticky lane sidebar). Falls back to a sane width pre-measure.
    // Both frozen columns (the staging tray and the lane sidebar) sit over the scroll viewport, so
    // the space actually left for date columns is what remains after both.
    const chartViewportW = Math.max((containerW || 1280) - STAGING_PX - SIDEBAR_PX, 320);
    const colPx = Math.max(chartViewportW / zoom.cols, MIN_COL_PX);
    const fallbackLaneH = minCardH + CELL_PAD_TOP * 2;
    const colGridStyle = {
        backgroundImage: 'linear-gradient(to right, rgba(0,0,0,0.06) 1px, transparent 1px)',
        backgroundSize: `${colPx}px 100%`,
        backgroundRepeat: 'repeat'
    };

    // Who's viewing → whether drag-to-assign is enabled, and whether a drawing opens in markup or
    // view mode. The modal itself no longer varies by role. One fetch.
    useEffect(() => {
        let cancelled = false;
        checkAuth().then((u) => { if (!cancelled) setIsAdmin(!!u?.is_admin); }).catch(() => {});
        return () => { cancelled = true; };
    }, []);

    // Installer team roster → lane order. Read-only config; one fetch.
    useEffect(() => {
        let cancelled = false;
        jobsApi.getInstallerTeams()
            .then((teams) => { if (!cancelled) setInstallerTeams(teams); })
            .catch((err) => console.error('Failed to load installer teams:', err))
            .finally(() => { if (!cancelled) setTeamsLoaded(true); });
        return () => { cancelled = true; };
    }, []);

    // Shipping-planning material orders (PU/pickup, stock, galvanizing "ready to ship") —
    // a READ-ONLY overlay on the Shipping Planning lane, unioned in from the material-orders
    // read-model. Never touches Releases rows. One fetch on mount.
    useEffect(() => {
        let cancelled = false;
        fetch(`${API_BASE_URL}/brain/material-orders/shipping-planning`, { credentials: 'include' })
            .then((r) => (r.ok ? r.json() : { orders: [] }))
            .then((d) => { if (!cancelled) setPlanningOrders(Array.isArray(d.orders) ? d.orders : []); })
            .catch(() => { if (!cancelled) setPlanningOrders([]); });
        return () => { cancelled = true; };
    }, []);

    // Track the scroll-viewport size: the width sizes columns to fit a whole number of them, the
    // height caps the pinned staging tray so it scrolls internally instead of running off-screen.
    // Re-measures on resize (ResizeObserver + window resize as a fallback).
    useLayoutEffect(() => {
        const el = scrollContainerRef.current;
        if (!el) return;
        const measure = () => { setContainerW(el.clientWidth); setContainerH(el.clientHeight); };
        measure();
        let ro;
        if (typeof ResizeObserver !== 'undefined') {
            ro = new ResizeObserver(measure);
            ro.observe(el);
        }
        window.addEventListener('resize', measure);
        return () => {
            if (ro) ro.disconnect();
            window.removeEventListener('resize', measure);
        };
    }, []);

    // Eligible release cards, selected client-side from the shared dataset. A single release can
    // yield multiple bars (its shipping lane + its installer's mirror lane), so flat-map.
    const releases = useMemo(
        () => jobs.flatMap((j) => toBars(j, filterComplete)),
        [jobs, filterComplete]
    );

    // The pinned staging column: releases the shop has finished with that nobody is scheduled to
    // install yet. Membership lives in utils/unassignedLane so the Job Log's "Ready to Ship" quick
    // filter and this column can never drift apart. These rows are NOT in `releases` — a release
    // with no installer and no shipping stage produces no bars, and one in Ship Planning appears in
    // its shipping lane as well as here (same raw row, like the installer mirror).
    const unassigned = useMemo(() => selectUnassigned(jobs), [jobs]);

    // Lane order: the two shipping lanes first, then the configured installer roster,
    // then any off-roster installer present in the data (so no eligible card is silently
    // dropped). Installer colors index by installer position so List and Timeline match.
    const lanesMeta = useMemo(() => {
        const shipMeta = SHIP_LANES.map(({ lane, color }) => ({ lane, color, isShip: true }));

        const installers = [...installerTeams];
        const seen = new Set(installers);
        releases.forEach((r) => {
            if (!r.isShip && r.lane && !seen.has(r.lane)) { seen.add(r.lane); installers.push(r.lane); }
        });
        const installerMeta = installers.map((lane, i) => ({
            lane, color: INSTALLER_PALETTE[i % INSTALLER_PALETTE.length], isShip: false,
        }));

        return [...shipMeta, ...installerMeta];
    }, [installerTeams, releases]);

    const initialLoad = (loading && jobs.length === 0) || !teamsLoaded;

    // chartRange spans every release plus padding, anchored to a Monday (so week columns align),
    // and always wide enough to include the snapped viewStart week. Column count/width are derived
    // from the zoom granularity in the body (below), not here.
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
        return { firstDay, totalDays };
    }, [releases, viewStart]);

    const totalCols = Math.ceil(chartRange.totalDays / colDays);
    const totalPx = totalCols * colPx;
    // Left px of a date (fractional within its column) — used for scroll/highlight positioning.
    const xOfDate = (iso) => (daysBetween(chartRange.firstDay, iso) / colDays) * colPx;

    // Planning orders placed on the Shipping Planning lane by date (ready_at → ordered_at).
    // Undated orders can't be positioned, so they're dropped from the overlay (rare).
    const placedOrders = useMemo(
        () => planningOrders
            .filter((o) => o.date)
            .map((o) => ({ ...o, left: xOfDate(o.date) })),
        // eslint-disable-next-line react-hooks/exhaustive-deps
        [planningOrders, colPx, colDays, chartRange.firstDay],
    );

    // When the chart origin (firstDay) shifts — e.g. a polled update introduces an earlier release
    // and grows the chart on the left — every card's pixel position moves with it. Restore the same
    // content under the viewport so it stays anchored. Skipped when a nav scroll intent is pending.
    useLayoutEffect(() => {
        const curr = chartRange.firstDay;
        const prev = prevFirstDayRef.current;
        prevFirstDayRef.current = curr;
        if (prev === null || prev === curr || scrollIntentRef.current) return;
        const el = scrollContainerRef.current;
        if (!el) return;
        el.scrollLeft += (daysBetween(curr, prev) / colDays) * colPx;
    }, [chartRange.firstDay, colPx, colDays]);

    // On zoom, keep the same DATE pinned under the left edge (works across day↔week granularity
    // changes via the previous days-per-column), then snap to a whole-column boundary.
    useLayoutEffect(() => {
        const prevPx = prevColPxRef.current;
        const prevCD = prevColDaysRef.current;
        prevColPxRef.current = colPx;
        prevColDaysRef.current = colDays;
        if (prevPx === null || (prevPx === colPx && prevCD === colDays)) return;
        const el = scrollContainerRef.current;
        if (!el) return;
        const daysFromFirst = (el.scrollLeft / prevPx) * prevCD;   // date offset (days) at old left edge
        const x = (daysFromFirst / colDays) * colPx;
        el.scrollLeft = Math.round(x / colPx) * colPx;
    }, [colPx, colDays]);

    // Build each lane. Two shapes share the timeline:
    //   - SHIPPING lanes: day/week-bucket point cards — group releases by Start-install COLUMN and
    //     stack within the cell (heights MEASURED after layout, since cards are natural-height).
    //   - INSTALLER lanes: horizontal RANGE bars spanning start_install → comp_eta. Bars are packed
    //     into rows by greedy interval partitioning so overlapping installs never collide, and the
    //     lane height is computed directly from the row count (`contentH`, no measurement needed).
    const bands = useMemo(() => {
        const firstDay = chartRange.firstDay;
        const cardWidth = Math.max(colPx - CARD_GUTTER * 2, 8);
        const pxOfDate = (iso) => (daysBetween(firstDay, iso) / colDays) * colPx;
        // At readable zooms (med and closer) a range bar is tall enough for a second line
        // (the release description); far zooms stay a single slim line.
        const barTwoLine = detail === 'med' || detail === 'high' || detail === 'full';
        const barH = barTwoLine
            ? Math.max(34, Math.min(minCardH, 46))
            : Math.max(22, Math.min(minCardH, 28));

        return lanesMeta.map(({ lane, color, isShip }) => {
            const laneReleases = releases.filter((r) => r.lane === lane);

            if (isShip) {
                const byCol = new Map();
                laneReleases.forEach((r) => {
                    const col = Math.floor(daysBetween(firstDay, r.startDate) / colDays);
                    if (!byCol.has(col)) byCol.set(col, []);
                    byCol.get(col).push(r);
                });

                const cells = [];
                byCol.forEach((list, col) => {
                    list.sort(inCellSort);
                    const overflow = list.length > cap;
                    cells.push({
                        key: col,
                        left: col * colPx + CARD_GUTTER,
                        width: cardWidth,
                        shown: overflow ? list.slice(0, cap - 1) : list,
                        extra: overflow ? list.length - (cap - 1) : 0,
                    });
                });

                return { lane, color, isShip, cells, bars: null, barH, twoLine: barTwoLine, contentH: null, count: laneReleases.length };
            }

            // Installer lane: one range bar per release, packed into non-overlapping rows.
            const sorted = [...laneReleases].sort((a, b) => {
                if (a.startDate !== b.startDate) return a.startDate < b.startDate ? -1 : 1;
                return inCellSort(a, b);
            });
            const rowEnds = [];   // right-edge px of the last bar placed in each row
            const bars = sorted.map((r) => {
                const left = pxOfDate(r.startDate);
                // +1 day so the bar covers the whole comp_eta day (inclusive end).
                const right = pxOfDate(addDays(r.endDate, 1));
                const width = Math.max(right - left - CARD_GUTTER, MIN_BAR_PX);
                let row = rowEnds.findIndex((end) => left >= end + CARD_GUTTER);
                if (row === -1) { row = rowEnds.length; rowEnds.push(0); }
                rowEnds[row] = left + CARD_GUTTER / 2 + width;
                return {
                    ...r,
                    left: left + CARD_GUTTER / 2,
                    width,
                    top: CELL_PAD_TOP + row * (barH + CARD_VGAP),
                };
            });
            const rowCount = rowEnds.length;
            const contentH = Math.max(
                CELL_PAD_TOP * 2 + rowCount * barH + Math.max(rowCount - 1, 0) * CARD_VGAP,
                fallbackLaneH,
            );

            return { lane, color, isShip, cells: null, bars, barH, twoLine: barTwoLine, contentH, count: laneReleases.length };
        });
    }, [lanesMeta, releases, colPx, colDays, cap, chartRange.firstDay, minCardH, detail, fallbackLaneH]);

    // Set each lane's height. Installer lanes carry a precomputed `contentH` (row-packed bars).
    // Shipping lanes are measured: their tallest cell of natural-height point cards fixes the height.
    // Guarded so it only sets state when a height actually changes — no render loop.
    useLayoutEffect(() => {
        const next = {};
        let changed = false;
        bands.forEach((band) => {
            let h;
            if (band.contentH != null) {
                h = band.contentH;
            } else {
                const el = laneChartRefs.current[band.lane];
                let maxCell = 0;
                if (el) {
                    el.querySelectorAll('[data-cell]').forEach((cell) => {
                        maxCell = Math.max(maxCell, cell.offsetHeight);
                    });
                }
                h = Math.max(CELL_PAD_TOP * 2 + maxCell, fallbackLaneH);
            }
            next[band.lane] = h;
            if (laneHeights[band.lane] !== h) changed = true;
        });
        if (changed || Object.keys(next).length !== Object.keys(laneHeights).length) {
            setLaneHeights(next);
        }
    }, [bands, colPx, colDays, detail, wrap, fallbackLaneH]);   // eslint-disable-line react-hooks/exhaustive-deps

    // Column headers. Day granularity → one header per day (weekday / day / month). Week granularity
    // → one header per week, labelled by the week's Monday.
    const columns = useMemo(() => {
        const todayStr = todayIso();
        const out = [];
        for (let i = 0; i < totalCols; i++) {
            const startIso = addDays(chartRange.firstDay, i * colDays);
            const d = new Date(startIso + 'T00:00:00');
            if (colDays === 1) {
                const isWeekend = d.getDay() === 0 || d.getDay() === 6;
                out.push({
                    key: startIso, leftPx: i * colPx, isWeek: false,
                    weekday: d.toLocaleDateString('en-US', { weekday: 'short' }),
                    dayNum: d.getDate(),
                    month: d.toLocaleDateString('en-US', { month: 'short' }),
                    isToday: startIso === todayStr,
                    isWeekend,
                });
            } else {
                const endIso = addDays(startIso, colDays - 1);
                const ed = new Date(endIso + 'T00:00:00');
                const startMon = d.toLocaleDateString('en-US', { month: 'short' });
                const endMon = ed.toLocaleDateString('en-US', { month: 'short' });
                out.push({
                    key: startIso, leftPx: i * colPx, isWeek: true,
                    // e.g. "Jun 4 - Jun 9" (month always on both ends)
                    rangeLabel: `${startMon} ${d.getDate()} - ${endMon} ${ed.getDate()}`,
                    isToday: todayStr >= startIso && todayStr <= endIso,
                    isWeekend: false,
                });
            }
        }
        return out;
    }, [chartRange.firstDay, totalCols, colPx, colDays]);

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

    const zoomOut = () => setZoomIdx((i) => Math.max(0, i - 1));
    const zoomIn = () => setZoomIdx((i) => Math.min(ZOOM_LEVELS.length - 1, i + 1));

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

    // On first render with real data, snap the view so the current week's Monday sits at the left
    // edge. Done directly (not via the nav scroll-intent) because that path only fires when firstDay
    // changes — which it doesn't when every release is in the future. Once per mount.
    useLayoutEffect(() => {
        if (initialLoad || didInitialScrollRef.current) return;
        if (bands.length === 0 || !scrollContainerRef.current) return;
        didInitialScrollRef.current = true;
        const targetX = xOfDate(mondayOf(todayIso()));
        scrollContainerRef.current.scrollLeft = Math.max(0, Math.round(targetX / colPx) * colPx);
    }, [initialLoad, bands.length, chartRange.firstDay, colPx, colDays]);   // eslint-disable-line react-hooks/exhaustive-deps

    // Consume the scroll intent — runs after every render that might have made the intent's target
    // date land at a stable position.
    useEffect(() => {
        const intent = scrollIntentRef.current;
        if (!intent || !scrollContainerRef.current) return;
        if (intent.targetWeek !== viewStart) return;
        const targetX = xOfDate(intent.targetWeek);
        scrollContainerRef.current.scrollTo({ left: Math.max(0, Math.round(targetX / colPx) * colPx), behavior: intent.behavior });
        scrollIntentRef.current = null;
    }, [viewStart, chartRange.firstDay, navNonce, colPx, colDays]);   // eslint-disable-line react-hooks/exhaustive-deps

    // Column-snap free horizontal scrolling: when the user stops scrolling, glide to the nearest
    // column boundary so the left edge never sits mid-column. Skipped while a nav intent settles.
    const handleScrollSnap = () => {
        if (snapTimerRef.current) clearTimeout(snapTimerRef.current);
        snapTimerRef.current = setTimeout(() => {
            const el = scrollContainerRef.current;
            if (!el || scrollIntentRef.current) return;
            const snapped = Math.round(el.scrollLeft / colPx) * colPx;
            if (Math.abs(snapped - el.scrollLeft) > 1) {
                el.scrollTo({ left: snapped, behavior: 'smooth' });
            }
        }, 140);
    };

    useEffect(() => () => clearTimeout(snapTimerRef.current), []);

    const viewStartLeftPx = xOfDate(viewStart);
    const viewWindowWidthPx = (VIEW_DAYS / colDays) * colPx;   // one week wide, in whatever unit

    // ==========================================================================================
    // Drag to assign — the timeline's one write.
    //
    // Dropping a card on a crew's lane sets that release's installer AND a hard Start install on
    // the day under the pointer, in a single PATCH. That is a real scheduling write: it drives
    // comp_eta, moves the mirror Trello card, and lands an undoable ReleaseEvents row. Dragging a
    // card back to the tray clears the installer and leaves the date alone.
    //
    // Shipping lanes stay read-only — a stage change cascades into job_comp and the Trello list,
    // and that is not what "assign the cards and the dates into individual people" asked for.
    //
    // Non-admins keep the untouched read-only timeline: every draggable/droppable is `disabled`,
    // which keeps hook order identical for both roles.
    // ==========================================================================================
    const canDrag = isAdmin;

    // Mouse drags start after 8px of travel, the same threshold the Board uses. Touch needs a
    // 220ms press-and-hold instead: on iPad the chart scrolls under your finger, so an immediate
    // touch-drag would make the timeline impossible to pan. Press-and-hold is the only gesture
    // that can mean "pick this up" on a surface that also scrolls both ways.
    const sensors = useSensors(
        useSensor(MouseSensor, { activationConstraint: { distance: 8 } }),
        useSensor(TouchSensor, { activationConstraint: { delay: 220, tolerance: 8 } }),
    );

    // Viewport X where the pointer currently is: the activator event's X plus the drag delta.
    const pointerX = (activatorEvent, delta) => {
        const startX = activatorEvent?.clientX ?? activatorEvent?.touches?.[0]?.clientX;
        if (startX == null) return null;
        return startX + (delta?.x ?? 0);
    };

    // The date a drop on `lane` would write, measured against that lane's LIVE rect so mid-drag
    // scrolling can't stale the answer.
    const dropDateFor = (lane, activatorEvent, delta) => {
        const el = laneChartRefs.current[lane];
        const x = pointerX(activatorEvent, delta);
        if (!el || x == null) return null;
        return dateAtDropX(x, el.getBoundingClientRect().left, {
            colPx, colDays, firstDay: chartRange.firstDay, totalCols,
        });
    };

    const handleDragStart = ({ active }) => {
        setDropError(null);
        setDragRow(active?.data?.current?.row ?? null);
        setHoveredItem(null);   // the hover tooltip would otherwise follow the card around
    };

    const handleDragMove = ({ active, over, activatorEvent, delta }) => {
        const lane = laneOfDropId(over?.id);
        if (!lane) { setDropHint(null); return; }
        const date = dropDateFor(lane, activatorEvent, delta);
        const shipStage = LANE_TO_SHIP_STAGE.get(lane);
        if (shipStage) {
            // The date under the pointer only positions the label — a shipping drop writes no date.
            const row = active?.data?.current?.row ?? null;
            setDropHint({
                lane,
                date: null,
                leftPx: date ? xOfDate(date) : 0,
                label: shipLabelFor(row, shipStage),
            });
            return;
        }
        if (!date) { setDropHint(null); return; }
        setDropHint({ lane, date, leftPx: xOfDate(date), label: null });
    };

    const handleDragCancel = () => { setDragRow(null); setDropHint(null); };

    const handleDragEnd = async ({ active, over, activatorEvent, delta }) => {
        const row = active?.data?.current?.row ?? null;
        const fromLane = active?.data?.current?.fromLane ?? null;
        setDragRow(null);
        setDropHint(null);
        if (!row || !over) return;

        const toLane = laneOfDropId(over.id);
        const toTray = over.id === STAGING_DROP_ID;
        if (!toLane && !toTray) return;

        const job = row['Job #'];
        const release = row['Release #'];
        // Everything the optimistic patch overwrites, so a failed write can put it all back.
        const before = {
            installer: row.installer ?? null,
            'Start install': row['Start install'] ?? null,
            start_install_formulaTF: row.start_install_formulaTF,
            Stage: row['Stage'] ?? null,
        };

        const toShipStage = toLane ? LANE_TO_SHIP_STAGE.get(toLane) : undefined;

        let optimistic;
        let call;
        if (toShipStage) {
            // A shipping lane writes the STAGE and nothing else. Where the card lands horizontally
            // is derived (planning → ship date, completed → hard Start install), so honouring the
            // drop column here would silently move an install date the user never aimed at.
            const outcome = shipLaneDropOutcome(row, toShipStage);
            if (outcome.kind === 'noop') return;
            if (outcome.kind === 'blocked') {
                setDropError(`Can't mark ${job}-${release} ${toShipStage} — ${outcome.reason}.`);
                return;
            }
            optimistic = { Stage: toShipStage };
            call = () => jobsApi.updateStage(job, release, toShipStage);
        } else if (toTray) {
            if (!before.installer) return;   // already unassigned — nothing to write
            optimistic = { installer: null };
            call = () => jobsApi.updateStartInstall(job, release, null, '');
        } else {
            const date = dropDateFor(toLane, activatorEvent, delta);
            if (!date) return;
            // Same crew, same day — the user put it back where it was.
            if (fromLane === toLane && dayPart(before['Start install']) === date
                && before.start_install_formulaTF === false) return;
            optimistic = { installer: toLane, 'Start install': date, start_install_formulaTF: false };
            call = () => jobsApi.updateStartInstall(job, release, date, toLane);
        }

        patchJob(row.id, optimistic);
        try {
            await call();
        } catch (err) {
            patchJob(row.id, before);   // put the card back where it came from
            const verb = toShipStage ? 'move' : 'schedule';
            setDropError(
                `Couldn't ${verb} ${job}-${release}: ${err?.message || 'the update was rejected'}`
            );
            console.error('Timeline drag failed:', job, release, err);
        }
    };

    return (
        <>
            <DndContext
                sensors={sensors}
                onDragStart={handleDragStart}
                onDragMove={handleDragMove}
                onDragCancel={handleDragCancel}
                onDragEnd={handleDragEnd}
            >
            <div ref={scrollContainerRef} className="flex-1 overflow-auto h-full" onScroll={handleScrollSnap}>
                {initialLoad && (
                    <div className="text-center py-12">
                        <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-accent-500 mb-4"></div>
                        <p className="text-gray-600 font-medium">Loading timeline data...</p>
                    </div>
                )}

                {!initialLoad && bands.length > 0 && (
                    <div className="flex flex-col" style={{ width: STAGING_PX + SIDEBAR_PX + totalPx, minHeight: '100%' }}>
                        {/* Sticky header */}
                        <div className="sticky top-0 z-30 bg-gray-100 border-b-2 border-gray-300 flex" style={{ minHeight: HEADER_PX }}>
                            {/* Staging-column header — frozen furthest left, above the tray. */}
                            <div
                                className="sticky left-0 z-50 flex-shrink-0 border-r-2 border-gray-400 bg-gray-200 px-2 py-2 flex flex-col justify-center"
                                style={{ width: STAGING_PX }}
                            >
                                <span className="text-[11px] font-extrabold text-gray-800 uppercase tracking-wide">Unassigned</span>
                                <span className="text-[10px] text-gray-600">
                                    {unassigned.length} ready to schedule
                                </span>
                            </div>
                            <div
                                className="sticky z-40 flex-shrink-0 border-r-2 border-gray-300 bg-gray-100 px-2 py-2 flex flex-col justify-center gap-1"
                                style={{ width: SIDEBAR_PX, left: STAGING_PX }}
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
                                <div className="flex items-center gap-1">
                                    <span className="text-[10px] text-gray-600 font-medium flex-1 truncate">{weekLabel}</span>
                                    <button
                                        onClick={zoomOut}
                                        disabled={zoomIdx === 0}
                                        className="px-1.5 py-0.5 text-xs rounded bg-white border border-gray-300 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
                                        title="Zoom out"
                                    >−</button>
                                    <button
                                        onClick={zoomIn}
                                        disabled={zoomIdx === ZOOM_LEVELS.length - 1}
                                        className="px-1.5 py-0.5 text-xs rounded bg-white border border-gray-300 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
                                        title="Zoom in"
                                    >+</button>
                                </div>
                            </div>
                            <div className="relative flex-shrink-0" style={{ width: totalPx, minHeight: '60px' }}>
                                {/* Snapped-week highlight */}
                                <div
                                    className="absolute top-0 bottom-0 bg-accent-100/60 border-x border-accent-400 pointer-events-none"
                                    style={{ left: viewStartLeftPx, width: viewWindowWidthPx }}
                                />
                                {columns.map((col) => (
                                    <div
                                        key={col.key}
                                        className={`absolute border-r border-gray-300 text-center py-1 flex flex-col items-center justify-center ${col.isWeekend ? 'bg-gray-200/40' : ''} ${col.isToday ? 'bg-accent-200' : ''}`}
                                        style={{
                                            left: col.leftPx,
                                            width: colPx,
                                            height: '100%'
                                        }}
                                    >
                                        {col.isWeek ? (
                                            <span className="text-xs font-bold text-gray-800 leading-tight px-1 whitespace-nowrap">
                                                {col.rangeLabel}
                                            </span>
                                        ) : (
                                            <>
                                                <span className="text-[10px] font-semibold text-gray-600 uppercase">{col.weekday}</span>
                                                <span className="text-sm font-bold text-gray-800">{col.dayNum}</span>
                                                <span className="text-[9px] text-gray-500">{col.month}</span>
                                            </>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Lanes (shipping lanes, then one per installer team). Each lane is
                            measured to its busiest column; cards sit in columns and stack
                            vertically. Lanes never shrink (would clip stacks). */}
                        <div ref={bodyRef} className="flex-1 flex items-start">
                            {/* Pinned staging tray. Sticks to the left edge horizontally and hangs
                                just below the sticky header vertically, so a card is always beside
                                the lanes you might drop it on — however far you scroll. Its own
                                list scrolls internally once the backlog outgrows the viewport. */}
                            <StagingTray
                                enabled={canDrag}
                                className="sticky left-0 z-30 flex-shrink-0 border-r-2 border-gray-400 bg-gray-100"
                                style={{
                                    width: STAGING_PX,
                                    top: HEADER_PX,
                                    maxHeight: containerH ? Math.max(containerH - HEADER_PX, 120) : undefined,
                                    overflowY: 'auto',
                                }}
                            >
                                <div className="p-1.5 space-y-1.5">
                                    {unassigned.length === 0 ? (
                                        <p className="text-[10px] text-gray-500 text-center py-6 leading-snug">
                                            Nothing waiting.<br />Everything ready to ship has a crew.
                                        </p>
                                    ) : unassigned.map((row) => (
                                        <StagingCard
                                            key={row.id}
                                            job={row}
                                            draggable={canDrag}
                                            onClick={() => openHub(row)}
                                            onMouseMove={(e) => handleMouseMove(e, {
                                                type: 'release',
                                                job: row['Job #'],
                                                release: row['Release #'],
                                                jobName: row['Job'] || '',
                                                description: row['Description'] || '',
                                                stage: row['Stage'] || '',
                                                pm: row['PM'] || '',
                                                by: row['BY'] || '',
                                            })}
                                            onMouseLeave={handleMouseLeave}
                                        />
                                    ))}
                                </div>
                            </StagingTray>

                            <div className="flex flex-col" style={{ width: SIDEBAR_PX + totalPx }}>
                            {bands.map((band) => {
                                // Reserve a bottom strip on the Shipping Planning lane for the PU/order overlay.
                                const laneOrders = band.lane === SHIP_PLANNING_LANE ? placedOrders : [];
                                const laneH = (laneHeights[band.lane] || fallbackLaneH)
                                    + (laneOrders.length ? ORDER_ROW_PX + CARD_VGAP : 0);
                                return (
                                    <div
                                        key={band.lane}
                                        data-lane={band.lane}
                                        className={`flex flex-shrink-0 border-b ${band.isShip ? 'border-gray-300' : 'border-gray-200'}`}
                                        style={{ minHeight: laneH }}
                                    >
                                        <div
                                            className={`sticky z-20 flex-shrink-0 border-r-2 border-gray-300 px-2 py-1 flex items-center gap-2 ${band.isShip ? 'bg-gray-100' : 'bg-gray-50'}`}
                                            style={{ width: SIDEBAR_PX, left: STAGING_PX }}
                                        >
                                            <span className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: band.color }} />
                                            <span className={`text-sm truncate ${band.isShip ? 'font-extrabold text-gray-900' : 'font-bold text-gray-800'}`}>{band.lane}</span>
                                            {band.count > 0 && (
                                                <span className="text-[10px] text-gray-500 ml-auto">{band.count}</span>
                                            )}
                                        </div>
                                        <LaneDropArea
                                            lane={band.lane}
                                            enabled={canDrag}
                                            registerRef={(el) => { laneChartRefs.current[band.lane] = el; }}
                                            hintLeft={dropHint?.lane === band.lane ? dropHint.leftPx : null}
                                            hintLabel={dropHint?.lane === band.lane ? dropHint.label : null}
                                            colPx={colPx}
                                            className="relative flex-shrink-0 bg-white"
                                            style={{ width: totalPx, height: laneH, ...colGridStyle }}
                                        >
                                            {/* Snapped-week tint */}
                                            <div
                                                className="absolute top-0 bottom-0 bg-accent-50/40 pointer-events-none"
                                                style={{ left: viewStartLeftPx, width: viewWindowWidthPx }}
                                            />
                                            {/* PU / material-order overlay — read-only cards pinned to the bottom
                                                strip of the Shipping Planning lane, positioned by ready/ordered date.
                                                Dashed outline distinguishes an incoming order from a solid release card. */}
                                            {laneOrders.map((o) => {
                                                const label = o.po_number || o.supplier || (o.job ? `${o.job}-${o.release ?? ''}` : 'Order');
                                                const badge = ORDER_KIND_BADGE[o.order_kind] || 'ORD';
                                                return (
                                                    <div
                                                        key={`ord-${o.id}`}
                                                        role="button"
                                                        tabIndex={0}
                                                        onClick={() => o.job && openOrderHub(o)}
                                                        onKeyDown={(e) => {
                                                            if ((e.key === 'Enter' || e.key === ' ') && o.job) {
                                                                e.preventDefault();
                                                                openOrderHub(o);
                                                            }
                                                        }}
                                                        className="absolute rounded border border-dashed border-amber-500 bg-amber-50/95 hover:bg-amber-100 text-amber-900 text-[11px] leading-none px-1.5 flex items-center gap-1 overflow-hidden whitespace-nowrap shadow-sm cursor-pointer"
                                                        style={{ left: o.left + CARD_GUTTER, bottom: 3, height: ORDER_ROW_PX, maxWidth: Math.max(colPx * 1.6, 110) }}
                                                        title={`${badge}: ${o.supplier || ''} ${o.po_number || ''}${o.description ? ' — ' + o.description : ''}${o.date ? ' (' + o.date + ')' : ''}`.trim()}
                                                    >
                                                        <span className="font-extrabold">{badge}</span>
                                                        <span className="truncate">{label}</span>
                                                    </div>
                                                );
                                            })}
                                            {band.cells && band.cells.map((cell) => (
                                                <div
                                                    key={cell.key}
                                                    data-cell="1"
                                                    className="absolute flex flex-col"
                                                    style={{ left: cell.left, top: CELL_PAD_TOP, width: cell.width, gap: CARD_VGAP }}
                                                >
                                                    {cell.shown.map((release) => (
                                                        <ShipCard
                                                            key={`${release.job}-${release.release}`}
                                                            release={release}
                                                            lane={band.lane}
                                                            color={band.color}
                                                            minCardH={minCardH}
                                                            imgH={imgH}
                                                            detail={detail}
                                                            wrap={wrap}
                                                            draggable={canDrag}
                                                            onClick={() => openHub(release.raw)}
                                                            onMouseMove={(e) => handleMouseMove(e, {
                                                                type: 'release',
                                                                job: release.job,
                                                                release: release.release,
                                                                jobName: release.jobName,
                                                                description: release.description,
                                                                stage: release.stage,
                                                                team: release.team,
                                                                startDate: release.startDate,
                                                                endDate: release.endDate,
                                                                pm: release.pm,
                                                                by: release.by
                                                            })}
                                                            onMouseLeave={handleMouseLeave}
                                                        />
                                                    ))}
                                                    {cell.extra > 0 && (
                                                        <div
                                                            className="rounded border border-dashed border-gray-400 bg-gray-50 flex items-center justify-center text-[10px] font-semibold text-gray-600 select-none"
                                                            style={{ minHeight: 18 }}
                                                        >
                                                            +{cell.extra} more
                                                        </div>
                                                    )}
                                                </div>
                                            ))}
                                            {/* Installer lane: horizontal range bars spanning start_install → comp_eta,
                                                packed into rows so overlapping installs never collide. Same raw row as
                                                the shipping card (the mirror), so click/hover parity is preserved. */}
                                            {band.bars && band.bars.map((release) => (
                                                <InstallerBar
                                                    key={`${release.job}-${release.release}`}
                                                    release={release}
                                                    lane={band.lane}
                                                    color={band.color}
                                                    barH={band.barH}
                                                    twoLine={band.twoLine}
                                                    draggable={canDrag}
                                                    onClick={() => openHub(release.raw)}
                                                    onMouseMove={(e) => handleMouseMove(e, {
                                                        type: 'release',
                                                        job: release.job,
                                                        release: release.release,
                                                        jobName: release.jobName,
                                                        description: release.description,
                                                        stage: release.stage,
                                                        team: release.team,
                                                        startDate: release.startDate,
                                                        endDate: release.endDate,
                                                        pm: release.pm,
                                                        by: release.by
                                                    })}
                                                    onMouseLeave={handleMouseLeave}
                                                />
                                            ))}
                                        </LaneDropArea>
                                    </div>
                                );
                            })}
                            </div>
                        </div>
                    </div>
                )}

                {!initialLoad && bands.length === 0 && (
                    <div className="text-center py-12">
                        <p className="text-gray-600 font-medium">No releases to show on the timeline.</p>
                    </div>
                )}
            </div>
            {/* The card follows the pointer at its tray size, so what you're holding stays legible
                even when it came off a two-week-wide gantt bar. */}
            <DragOverlay dropAnimation={null}>
                {dragRow && (
                    <div className="rounded border border-accent-500 bg-white px-1.5 py-1 shadow-lg text-[11px] w-40 cursor-grabbing">
                        <div className="font-bold text-gray-900 truncate">
                            {dragRow['Job #']}-{dragRow['Release #']}
                        </div>
                        {dragRow['Job'] && <div className="text-[10px] text-gray-600 truncate">{dragRow['Job']}</div>}
                        {dropHint && (
                            <div className="text-[10px] font-semibold text-accent-700 truncate mt-0.5">
                                {dropHint.lane} · {shortDate(dropHint.date)}
                            </div>
                        )}
                    </div>
                )}
            </DragOverlay>
            </DndContext>
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
            {/* A rejected scheduling write is never silent: the card has already snapped back, so say
                why. Dismissed by clicking it, or by the next drag. */}
            {dropError && (
                <div
                    role="alert"
                    onClick={() => setDropError(null)}
                    className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 max-w-md px-4 py-2.5 rounded-lg shadow-xl bg-red-600 text-white text-xs font-medium cursor-pointer"
                >
                    {dropError}
                    <span className="ml-2 opacity-70">(dismiss)</span>
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
                        {hoveredItem.stage && <div>Stage: {hoveredItem.stage}</div>}
                        {hoveredItem.team && <div>Team: {hoveredItem.team}</div>}
                        {hoveredItem.isShip && !hoveredItem.installAnchored ? (
                            <>
                                <div>
                                    {hoveredItem.shipEstimated ? 'Ship Date (est): ' : 'Ship Date: '}
                                    {formatDate(hoveredItem.startDate)}
                                </div>
                                {hoveredItem.installDate && (
                                    <div>Start Install: {formatDate(hoveredItem.installDate)}</div>
                                )}
                            </>
                        ) : hoveredItem.isShip ? (
                            <div>Start Install: {formatDate(hoveredItem.startDate)}</div>
                        ) : (
                            <>
                                <div>Start Install: {formatDate(hoveredItem.startDate)}</div>
                                <div>Comp ETA: {formatDate(hoveredItem.endDate)}</div>
                            </>
                        )}
                        {hoveredItem.pm && <div>PM: {hoveredItem.pm}</div>}
                        {hoveredItem.by && <div>BY: {hoveredItem.by}</div>}
                    </div>
                </div>
            )}
            {/* The SAME modal a Job Log row opens. A release must not have two identities depending
                on which surface you clicked it from, so the Timeline deliberately has no modal of
                its own — no cockpit, no read-only variant, no lane-colored accent (the hub derives
                its own tint from the stage). */}
            <ReleaseHubModal
                isOpen={!!hubJob}
                job={hubJob}
                releaseId={hubJob?.id}
                viewerUrl={hubJob?.viewer_url}
                initialTab="details"
                scrollToMaterials={hubScrollToMaterials}
                onOrdersChanged={refreshMaterialSummary}
                onClose={closeHub}
                onOpenVersion={(vid, mode) => {
                    setMarkup({
                        releaseId: hubJob?.id,
                        versionId: vid,
                        mode: isAdmin ? mode : 'view',
                    });
                    closeHub();
                }}
            />
            <PdfMarkupModal
                isOpen={markup != null}
                releaseId={markup?.releaseId}
                versionId={markup?.versionId}
                mode={markup?.mode || 'view'}
                onClose={() => setMarkup(null)}
            />
        </>
    );
}

export default GanttChart;
