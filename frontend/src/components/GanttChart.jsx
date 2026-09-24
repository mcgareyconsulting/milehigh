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
 *   Left of everything sit TWO PINNED STAGING COLUMNS, frozen side by side: UNASSIGNED (releases the
 *   shop has finished with that nobody is scheduled to install) and, to its right, READY TO SHIP
 *   (releases that have no ship day yet). Dragging a card from Unassigned onto a crew's lane assigns
 *   that crew and stamps a hard Start install on the day under the pointer; dragging one from Ready
 *   to Ship onto the Shipping Planning lane stamps that day and moves the release into Ship Planning.
 *   A client selector over useReleases for reads; installer, Start install and Stage are its writes.
 * exports:
 *   GanttChart: Day/week-bucket board with zoom that scales column granularity (day↔week), width,
 *     card size, per-cell cap, and card detail; whole-column zoom snapping, week-snap nav, jump-to-date,
 *     and admin drag-to-assign between the unassigned tray and the installer lanes.
 * imports_from: [react, @dnd-kit/core, ../services/jobsApi, ../context/ReleasesContext, ../constants/installerPalette, ../utils/formatters, ../utils/installDateColor, ../utils/unassignedLane, ../utils/readyToShipColumn, ../utils/timelineDrop, ../utils/shipLaneDrop, ./ReleaseHubModal, ./PdfMarkupModal]
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
 *     the Trello list, N5 date discipline and the scheduling recalc all included). No date is
 *     written from a shipping drop onto a release that ALREADY HAS ONE: a shipping lane's X is
 *     DERIVED (planning sits on the ship date, completed on the hard Start install), so honouring
 *     the drop column would move an install date the user never aimed at. Dropping onto the lane a
 *     release is already in is a no-op, and a drop onto Shipping Completed is REFUSED when the
 *     release has no hard Start install — the lane is anchored on that date and the backend blanks
 *     estimated dates on the way in, so the card would silently vanish off the board. Because the
 *     write leaves no mark at the drop point, hovering a shipping lane washes the whole lane and
 *     names the stage it will set.
 *   - The ONE shipping drop that also writes a DATE is Shipping Planning onto an UNDATED release —
 *     the Ready-to-Ship column's exit. There is no date to protect, and a Ship Planning card with no
 *     date renders nowhere at all, so the drop supplies one and the hover hint shows the column
 *     highlight as well as the wash. The column is a SHIP day, not an install day (a planning card
 *     sits on ship = install − 1 business day), so the hard Start install written is the column plus
 *     one business day — which is both what makes the card land under the pointer and the rule as
 *     stated, "start_install = next business day" [bill-2026-09-16#L1336–L1358]. The DATE is written first: the
 *     backend rolls Store at MHMW / Paint Complete into Ship Planning off the back of it
 *     (ship_planning_roll.py) and links the two events, so the drop undoes as one bundle. Only a
 *     card from further upstream (a Fab or Paint ASAP, which gets no roll) needs the stage named
 *     explicitly afterwards — ROLLS_TO_SHIP_PLANNING is what decides, and it mirrors the server's set.
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
 *     uses, imported from one place so the two surfaces cannot drift) AND that already carry a hard
 *     Start install date (Ship Planning rows always qualify). Deliberately not "any release
 *     with no installer": that pulls in every drafting and fab row and the tray stops being a work
 *     surface. A tray release in Ship Planning ALSO appears in its shipping lane, like the mirror.
 *   - The READY TO SHIP COLUMN holds the rows the tray's date test excludes — Paint Complete / Store
 *     at MHMW with NO hard Start install, grouped Paint Complete then Store at MHMW (by card tint and
 *     order, no headers — each card names its own stage in its pill), each group sorted by date — plus a trailing, NON-DRAGGABLE block of ASAPs still in Fab or Paint, tagged
 *     "in Fab" / "in Paint", for visibility (utils/readyToShipColumn). The two columns are DISJOINT
 *     by construction, so no
 *     release is ever drawn in both: the pipeline reads left to right, Ready to Ship (needs a day) →
 *     dropped on Shipping Planning, which gives it one → Unassigned (needs a crew) → dropped on a
 *     crew lane. Unlike the tray, this column tests only the DATE, not the installer, and it is NOT
 *     a drop target: every write it knows about is a drop somewhere else.
 *     Tray cards show job-release, job name, description and the Start install date — hard or
 *     projected, the projection marked with a leading ~ so a guess never reads as a promise. The
 *     qualifying stage is not repeated on the card (it's in the detail modal, and all three stages
 *     read as "ready"). The tray is ordered by that date (ASAP first, undated last), so it is a
 *     queue of what to schedule next rather than a list by job number.
 *   - A tray card's BORDER is keyed to its date the same way the Job Log's Start install cell is
 *     (utils/installDateColor): red ASAP, amber a hard date gone by, green a hard date ahead, grey
 *     a projection or none. That colour is the TRAY's only — dropped onto a lane the card takes the
 *     lane's installer colour, since there the question is whose work it is, not when it is due.
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
 *     switches) and snaps to a whole-column boundary. That date is captured by the zoom BUTTON,
 *     before the state change — reading scrollLeft after the re-render cannot work, because a
 *     narrower chart has already had its scrollLeft clamped by the browser. Week-snap nav anchors
 *     viewStart to a Monday.
 * updated_by_agent: 2026-09-17 (Ready-to-Ship staging column + its Shipping Planning date-stamping drop)
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
    pointerWithin,
} from '@dnd-kit/core';
import { getEventCoordinates } from '@dnd-kit/utilities';
import { INSTALLER_PALETTE } from '../constants/installerPalette';
import { selectUnassigned } from '../utils/unassignedLane';
import { selectReadyToShip, READY_TO_SHIP_COLUMN_STAGES } from '../utils/readyToShipColumn';
import { dateAtDropX } from '../utils/timelineDrop';
import { shipLaneDropOutcome, shipLabelFor } from '../utils/shipLaneDrop';
import { localTodayStr as todayIso, subtractBusinessDays, addBusinessDays, formatDateShort } from '../utils/formatters';
import { classifyInstallDate } from '../utils/installDateColor';
import { installCompleteDate } from '../utils/scheduling';
import { API_BASE_URL } from '../utils/api';
import { ReleaseHubModal } from './ReleaseHubModal';
import { PdfMarkupModal } from './PdfMarkupModal';
import { StagePhotoGateModal } from './StagePhotoGateModal';
import { gateStageFor, stageGateFromError } from '../utils/stageGroups';
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
const STAGING_COLLAPSED_PX = 30;   // collapsed rail: wide enough to stay a drop target and click back open
const READY_PX = 200;     // width of the pinned Ready-to-Ship column, frozen between the tray and the lane sidebar
const READY_COLLAPSED_PX = 30;     // collapsed rail, same gesture and same width as the tray's
const LANE_COLLAPSED_PX = 26;      // collapsed lane: the sidebar strip only — name, colour and count survive
const LABEL_GUTTER_PX = 6;         // gap between the frozen chrome and a scroll-tracked bar label
const LANES_COLLAPSED_KEY = 'mhmw:timeline-lanes-collapsed';

const readCollapsedLanes = () => {
    try {
        const raw = JSON.parse(localStorage.getItem(LANES_COLLAPSED_KEY) || '[]');
        return new Set(Array.isArray(raw) ? raw : []);
    } catch {
        return new Set();
    }
};
const TRAY_COLLAPSED_KEY = 'mhmw:timeline-tray-collapsed';
const READY_COLLAPSED_KEY = 'mhmw:timeline-ready-collapsed';

const readTrayCollapsed = () => {
    try {
        return localStorage.getItem(TRAY_COLLAPSED_KEY) === '1';
    } catch {
        return false;   // storage disabled — open is the safe default
    }
};

const readReadyCollapsed = () => {
    try {
        return localStorage.getItem(READY_COLLAPSED_KEY) === '1';
    } catch {
        return false;   // storage disabled — open is the safe default
    }
};
// Fallback sticky-header height, used only for the first paint and in environments without layout
// (jsdom). The real height is MEASURED — it grows with the toolbar's wrapping — and a guess that is
// too small hangs the pinned columns below the viewport, where their last card cannot be scrolled
// fully into view until the page itself is scrolled down.
const HEADER_PX = 60;
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
    { unit: 'day', cols: 21, minCardH: 24, cap: 5, detail: 'jr', wrap: false, imgH: 0 },    // 3 weeks
    { unit: 'day', cols: 14, minCardH: 28, cap: 6, detail: 'jr', wrap: true, imgH: 0 },     // 2 weeks
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
// Stages the BACKEND rolls into Ship Planning by itself the moment a hard Start install date lands
// on them (app/brain/job_log/features/start_install/ship_planning_roll.py). A drop that stamps a
// date onto one of these needs no second call — and must not make one, or the roll's event and a
// redundant stage event both land for a single gesture. Anything else (a Fab or Paint ASAP) is
// named explicitly. Keep this set identical to the server's ROLL_STAGES.
const ROLLS_TO_SHIP_PLANNING = new Set(READY_TO_SHIP_COLUMN_STAGES);

// The hard Start install a Shipping Planning drop writes, given the column it was dropped on.
//
// A Shipping Planning card is positioned on its SHIP date — the explicit hard one, else install
// minus one business day (`toBars`). So the column the user aimed at is a SHIP day, and writing it
// straight into start_install would render the card one business day LEFT of where they let go.
// The install is the business day after the ship, which is also the rule as stated:
// "a drop on Shipping Planning sets the stage and start_install = next business day"
// [bill-2026-09-16#L1336–L1358]. Invert the lane's own arithmetic and the card lands under the
// pointer, which is the only place it can honestly land.
const installDateForShipColumn = (shipColumnDate) => addBusinessDays(shipColumnDate, 1);
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
// wrap=true (weekly and closer): the header wraps to as many lines as needed — NO truncation.
// wrap=false (far zoom): single-line truncate to keep tiny cards tidy.
//
// The header is ONE bold run — job-release, job name, description — the way a Trello card title
// reads. Splitting them across weights made three competing lines out of what is really one label.
// "560-941 Wood Partners - Alta Metro Bld B Structural Steel": the number and the customer are one
// name (space), the scope is the part that gets set off (dash). Missing pieces drop out with their
// separator, so no card ever shows a dangling dash.
function CardBody({ release, detail, wrap }) {
    const jr = `${release.job}-${release.release}`;
    const header = [[jr, release.jobName].filter(Boolean).join(' '), release.description]
        .filter(Boolean).join(' - ');
    const flow = wrap ? 'break-words' : 'truncate';
    if (detail === 'min') {
        return <span className="block text-gray-900 text-[11px] font-bold truncate leading-none">{jr}</span>;
    }
    // Dense day columns: the identifier ALONE. At this width the name and description wrapped one
    // or two characters per line and the card became a vertical ribbon of syllables — unreadable,
    // and it buried the one thing the board is useless without. `anywhere` lets the identifier fall
    // to a second line at the hyphen rather than overflow a narrow column.
    if (detail === 'jr') {
        return (
            <span
                className="block text-gray-900 text-xs font-bold leading-tight"
                style={{ overflowWrap: 'anywhere' }}
            >{jr}</span>
        );
    }
    if (detail === 'low') {
        return <span className="block text-gray-900 text-xs font-bold truncate leading-none">{header}</span>;
    }
    // med / high / full: bold header, then PM.
    return (
        <div className="flex flex-col gap-0.5 leading-tight">
            <span className={`block text-gray-900 text-sm font-bold ${flow}`}>{header}</span>
            {release.pm && (
                <span className="block text-gray-500 text-[11px] truncate">{release.pm}</span>
            )}
        </div>
    );
}

// Hide / show control for a lane. Inline SVG because the project carries no icon package, and the
// state that needs to shout is HIDDEN — a folded lane must never read as an empty one.
function EyeIcon({ off }) {
    return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M1.5 12S5 5.5 12 5.5 22.5 12 22.5 12 19 18.5 12 18.5 1.5 12 1.5 12Z" />
            <circle cx="12" cy="12" r="3" />
            {off && <line x1="3" y1="21" x2="21" y2="3" />}
        </svg>
    );
}

// The colour a tray card's border carries, keyed to its Start install date the same way the Job
// Log's Start install cell is (utils/installDateColor, mirroring the backend's _classify_date), so
// a release reads the same on both surfaces:
//   red    ASAP — a rush flag, whatever the date says
//   amber  a hard date already in the past — the one that is a scored metric
//   green  a hard date still ahead
//   grey   no hard date: a projection, or nothing at all. Not a warning, just not a commitment.
// A card only wears this in the tray. Dropped onto a lane it takes that lane's installer colour,
// because there the question is whose work it is, not when it is due.
// The red a card carries when the release is ASAP, as an inline colour rather than a Tailwind class
// because both the ship-lane point card and the installer bar set `borderColor` inline from their
// lane palette. Same red as TRAY_BORDER.asap (red-500) so the tray and the lanes agree.
const ASAP_BORDER_COLOR = 'rgb(239 68 68)';

const TRAY_BORDER = {
    asap: 'border-red-400 border-l-4 border-l-red-500 bg-red-50 ring-2 ring-red-300',
    overdue: 'border-amber-400 border-l-4 border-l-amber-500 bg-amber-50',
    scheduled: 'border-emerald-400 border-l-4 border-l-emerald-500 bg-emerald-50',
    soft: 'border-gray-300 border-l-4 border-l-gray-300',
};

// Ready-to-Ship section tints. Only the neutral ('soft') card takes one — an ASAP keeps its red,
// which is the one signal that must read the same in every column.
const READY_SECTION_TONE = {
    paint: 'border-sky-300 border-l-4 border-l-sky-500 bg-sky-50',
    store: 'border-violet-300 border-l-4 border-l-violet-500 bg-violet-50',
};

// Which of the four a release falls into, plus how its date should read.
function trayDateState(job) {
    const { isAsap, isHardDate, isHardDatePast } = classifyInstallDate({
        stage: job['Stage'],
        asap: job['start_install_asap'],
        noColor: job['start_install_no_color'],
        formulaTF: job['start_install_formulaTF'],
        installDate: job['Start install'],
    });
    const kind = isAsap ? 'asap' : isHardDatePast ? 'overdue' : isHardDate ? 'scheduled' : 'soft';
    const hard = job['start_install_formulaTF'] === false && !!job['Start install'];
    return {
        kind,
        // A projected date is shown too — it is the Brain's answer for when this is wanted, and it
        // is what the tray now sorts on — but it is marked, so nobody reads a guess as a promise.
        label: formatDateShort(job['Start install']),
        projected: !hard && !!job['Start install'],
        title: !job['Start install']
            ? 'No start install date'
            : hard
                ? (isAsap ? 'ASAP — hard start install date' : 'Hard start install date')
                : 'Projected start install date',
    };
}

// One release sitting in one of the two pinned staging columns: job-release, name, description, the
// Start install date it is waiting on, and a border keyed to that date. The date is shown BECAUSE
// the card is unscheduled — it is the projection or hard date the work is wanted against, and
// dropping the card onto a lane×day cell is what replaces it with the day you chose.
//
// `dragIdPrefix` namespaces the draggable id per column. The two columns are disjoint by
// construction, so ids could not actually collide today — but a shared id would make any future
// overlap a silent, undebuggable drag bug, and the prefix costs nothing.
//
// Short stage labels for the card's top-right pill. Only the ones too long for a 200px column are
// abbreviated; anything unlisted shows verbatim (and truncates if it has to).
const STAGE_PILL_LABEL = {
    'Store at MHMW': 'Store',
    'Paint Complete': 'Paint Comp',
    'Ship Planning': 'Ship Plan',
    'Ship Complete': 'Shipped',
    'Fit Up Complete': 'Fit Up',
    'Material Ordered': 'Mat Ord',
};

// `tone` tints a neutral card by its Ready-to-Ship section; ASAP / overdue / scheduled cards ignore it.
// `origin` ('Fab' / 'Paint') is set only on the column's upstream ASAPs: it answers "this is marked
// rush and it's in my shipping queue — where actually IS it?"
function StagingCard({ job, draggable, dragIdPrefix = 'staging', tone, onClick, onMouseMove, onMouseLeave }) {
    const jr = `${job['Job #']}-${job['Release #']}`;
    const asap = job['start_install_asap'] === true;
    const origin = job['_asapOrigin'] || '';
    const stage = String(job['Stage'] ?? '').trim();
    const date = trayDateState(job);
    // `disabled` keeps the hook order stable for non-admins, who get the same card without a grab.
    const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
        id: `${dragIdPrefix}:${job.id}`,
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
            // bg-white only on a plain card: it would otherwise fight a tint's bg-* and win or lose on
            // stylesheet order (it beat bg-violet-50 but lost to bg-sky-50).
            className={`rounded border px-2 py-1.5 shadow-sm select-none hover:shadow ${draggable ? 'cursor-grab active:cursor-grabbing' : 'cursor-pointer'} ${date.kind === 'soft' ? (tone || `bg-white ${TRAY_BORDER.soft}`) : TRAY_BORDER[date.kind]}`}
        >
            {/* Top row, on EVERY card — the stage pill keeps it occupied when there is no ASAP, so a
                card is the same height in both columns and the two lists read as one system. */}
            <div className="mb-1 flex items-center gap-1 min-h-[16px]">
                {asap && (
                    <span className="inline-block px-1.5 py-0.5 rounded bg-red-600 text-white text-[10px] font-extrabold tracking-wide leading-none">
                        ASAP
                    </span>
                )}
                {origin && (
                    <span
                        className="inline-block px-1.5 py-0.5 rounded bg-gray-700 text-white text-[10px] font-bold tracking-wide leading-none"
                        title={`Still in ${origin} — ${stage || 'unknown stage'}`}
                    >
                        {`in ${origin}`}
                    </span>
                )}
                {stage && (
                    <span
                        className="ml-auto shrink-0 max-w-[60%] truncate px-1.5 py-0.5 rounded bg-gray-200 text-gray-700 text-[10px] font-bold tracking-wide leading-none"
                        title={stage}
                    >
                        {STAGE_PILL_LABEL[stage] || stage}
                    </span>
                )}
            </div>
            <div className="text-sm font-bold text-gray-900 truncate leading-tight">{jr}</div>
            {job['Job'] && (
                <div className="text-xs text-gray-700 truncate leading-snug">{job['Job']}</div>
            )}
            {job['Description'] && (
                <div className="text-xs text-gray-500 truncate leading-snug">{job['Description']}</div>
            )}
            <div
                className={`mt-1 text-[11px] font-semibold leading-none ${date.projected ? 'text-gray-500 italic font-normal' : 'text-gray-800'}`}
                title={date.title}
            >
                {job['Start install'] ? (date.projected ? `~ ${date.label}` : date.label) : 'No date'}
            </div>
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
// the user aims at a date rather than guessing. A SHIPPING lane usually has no date to aim at — its
// X is derived, not chosen — so it gets `hintLabel` instead: a whole-lane wash naming the stage the
// drop will write, because a stage change is invisible at the drop point and must be announced
// first. `hintDate` is the case where it is BOTH: a Shipping Planning drop onto an undated release
// writes a date off the drop column as well as the stage, so the column highlight comes back
// alongside the wash — hiding it would leave the user aiming a date they cannot see.
function LaneDropArea({ lane, enabled, registerRef, hintLeft, hintLabel, hintDate, colPx, className, style, children }) {
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
            {isOver && (!hintLabel || hintDate) && hintLeft != null && (
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
//
// BUG-27: a ship-lane card wears its lane's colour EXCEPT when the release is ASAP, which overrides
// it in red. The lane colour answers "where is this in shipping"; ASAP answers "this one is a
// rush", and the rush has to survive the pull out of the Unassigned tray — a release that lost its
// red the moment it reached Shipping Planning was exactly the card nobody expedited. The flag is
// read off the row on every render, so the red survives drag, reorder, refresh and filters, and
// disappears by itself when `asap_drop` clears the flag at Ship Complete.
function ShipCard({ release, lane, color, minCardH, imgH, detail, wrap, draggable, onClick, onMouseMove, onMouseLeave }) {
    const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
        id: `ship:${release.id}:${lane}`,
        data: { row: release.raw, fromLane: lane },
        disabled: !draggable,
    });
    const isAsap = !!release.raw && trayDateState(release.raw).kind === 'asap';
    return (
        <div
            ref={setNodeRef}
            role="button"
            tabIndex={0}
            title={isAsap ? 'ASAP — rush release' : undefined}
            className={`rounded border-2 shadow-sm hover:shadow px-2 py-1.5 overflow-hidden select-none text-left ${isAsap ? 'bg-red-50 ring-2 ring-red-300' : 'bg-gray-50'} ${draggable ? 'cursor-grab active:cursor-grabbing' : 'cursor-pointer'}`}
            style={{
                borderColor: isAsap ? ASAP_BORDER_COLOR : color,
                opacity: isDragging ? 0.35 : 1,
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
//
// The label TRACKS THE SCROLL. On a bar spanning weeks, scrolling to the far end used to leave the
// name parked at the bar's true left edge, far off screen, so the visible span was anonymous. The
// label now slides right to stay just clear of the frozen sidebar, and stops at the bar's own left
// edge once that scrolls back into view.
//
// This is padding driven by a CSS variable (--tl-sx, the live scrollLeft, written by the scroll
// handler), NOT position:sticky. Sticky would need the bar to drop `overflow-hidden` — an overflow
// ancestor becomes the sticky element's scroll container, which never scrolls — and the unclipped
// label would then spill past the bar's right edge by exactly the amount it slid, which is worst in
// the very case this fixes. Padding keeps the bar clipping its own text.
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
            className={`absolute rounded border-2 bg-gray-50 shadow-sm hover:shadow px-1.5 flex items-center overflow-hidden select-none ${draggable ? 'cursor-grab active:cursor-grabbing' : 'cursor-pointer'}`}
            style={{
                left: release.left,
                top: release.top,
                width: release.width,
                height: barH,
                borderColor: color,
                opacity: isDragging ? 0.35 : 1,
                touchAction: draggable ? 'manipulation' : undefined,
            }}
            {...attributes}
            {...listeners}
            onClick={onClick}
            onMouseMove={onMouseMove}
            onMouseLeave={onMouseLeave}
        >
            <div
                className="min-w-0 w-full text-left leading-tight"
                style={{
                    // Slide the label to the frozen chrome's right edge, but never past the bar's
                    // own end (leave room for a few characters) and never left of its start.
                    //
                    // The chrome width does NOT appear here and must not: `release.left` is measured
                    // from the chart origin, which itself sits behind the frozen chrome, so the two
                    // offsets cancel. Adding it shoved every label a sidebar-width to the right.
                    paddingLeft: `clamp(0px, calc(var(--tl-sx, 0px) + ${LABEL_GUTTER_PX}px - ${Math.round(release.left)}px), calc(100% - 36px))`,
                }}
            >
                <span className="block text-gray-900 text-xs font-bold truncate">
                    {[[`${release.job}-${release.release}`, release.jobName].filter(Boolean).join(' '),
                        release.description].filter(Boolean).join(' - ')}
                </span>
                {twoLine && release.pm && (
                    <span className="block text-gray-500 text-[11px] truncate">{release.pm}</span>
                )}
            </div>
        </div>
    );
}

function GanttChart({ filterComplete = false }) {
    const { jobs, loading, patchJob, refreshMaterialSummary, refetch } = useReleases();
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
    const [pendingGate, setPendingGate] = useState(null);           // a ship-lane drop waiting on its handoff photo: {job, release, releaseId, stage, requestedStage, commit(note)}
    const [trayCollapsed, setTrayCollapsed] = useState(readTrayCollapsed);   // tray folded to a rail, giving the width back to the chart
    const [readyCollapsed, setReadyCollapsed] = useState(readReadyCollapsed); // Ready-to-Ship column folded to a rail, same deal
    const [collapsedLanes, setCollapsedLanes] = useState(readCollapsedLanes);   // lanes folded to their sidebar strip
    const [containerW, setContainerW] = useState(0);                // measured scroll-viewport width → derives colPx
    const [containerH, setContainerH] = useState(0);                // measured scroll-viewport height → caps the staging tray
    const [headerH, setHeaderH] = useState(HEADER_PX);              // measured sticky-header height → where the pinned columns hang from
    const [viewStart, setViewStart] = useState(() => mondayOf(todayIso()));
    const [navNonce, setNavNonce] = useState(0);   // bumps each nav so the scroll fires even when viewStart is unchanged
    const [datePickerOpen, setDatePickerOpen] = useState(false);
    const [datePickerValue, setDatePickerValue] = useState('');
    const [zoomIdx, setZoomIdx] = useState(DEFAULT_ZOOM);
    const [laneHeights, setLaneHeights] = useState({});   // measured px height per lane
    const scrollContainerRef = useRef(null);
    // Callback ref, not useRef: the header does not exist on the first render (the chart is still
    // loading), so a plain ref would leave the measure effect nothing to read and the pinned columns
    // stuck on the HEADER_PX fallback. This measures the moment the header mounts instead.
    const headerRef = useRef(null);
    const headerObserverRef = useRef(null);
    const attachHeader = (el) => {
        headerRef.current = el;
        if (!el) return;
        if (el.offsetHeight) setHeaderH(el.offsetHeight);
        if (headerObserverRef.current) headerObserverRef.current.observe(el);   // it wraps at narrow widths
    };
    const bodyRef = useRef(null);
    const laneChartRefs = useRef({});      // lane name → chart-area DOM node, for height measurement
    const prevFirstDayRef = useRef(null);   // last chart origin, for scroll-anchoring on reflow
    const prevColPxRef = useRef(null);      // last column width, for scroll-anchoring on zoom
    const prevColDaysRef = useRef(null);    // last days-per-column, so day↔week zoom keeps the left-edge date
    const zoomAnchorRef = useRef(null);     // left-edge DATE captured at the zoom click, restored after the re-render
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
    // Every frozen-left offset measures off this, so collapsing the tray genuinely hands the
    // pixels to the chart rather than just hiding its contents.
    const stagingPx = trayCollapsed ? STAGING_COLLAPSED_PX : STAGING_PX;
    const readyPx = readyCollapsed ? READY_COLLAPSED_PX : READY_PX;
    // Everything frozen to the left of the date columns, as one number. Both staging columns and the
    // lane sidebar measure their sticky offsets off this, so folding either one genuinely hands the
    // pixels to the chart rather than just hiding its contents.
    const chromePx = stagingPx + readyPx + SIDEBAR_PX;

    const toggleTray = () => {
        setTrayCollapsed((prev) => {
            const next = !prev;
            try { localStorage.setItem(TRAY_COLLAPSED_KEY, next ? '1' : '0'); } catch { /* preference is best-effort */ }
            return next;
        });
    };

    const toggleReady = () => {
        setReadyCollapsed((prev) => {
            const next = !prev;
            try { localStorage.setItem(READY_COLLAPSED_KEY, next ? '1' : '0'); } catch { /* preference is best-effort */ }
            return next;
        });
    };

    // Fold a lane down to its sidebar strip. Trello collapses a LIST to a vertical rail; our lanes
    // run horizontally, so the same gesture gives back HEIGHT — more crews on screen at once — and
    // the name stays upright instead of rotating.
    const toggleLane = (lane) => {
        setCollapsedLanes((prev) => {
            const next = new Set(prev);
            if (next.has(lane)) next.delete(lane); else next.add(lane);
            try { localStorage.setItem(LANES_COLLAPSED_KEY, JSON.stringify([...next])); } catch { /* best-effort */ }
            return next;
        });
    };

    const chartViewportW = Math.max((containerW || 1280) - chromePx, 320);
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
        const measure = () => {
            setContainerW(el.clientWidth);
            setContainerH(el.clientHeight);
            const h = headerRef.current?.offsetHeight;
            if (h) setHeaderH(h);
            headerObserverRef.current = ro ?? null;
        };
        let ro;
        if (typeof ResizeObserver !== 'undefined') {
            ro = new ResizeObserver(measure);
            ro.observe(el);
            if (headerRef.current) ro.observe(headerRef.current);   // the header wraps at narrow widths
        }
        headerObserverRef.current = ro ?? null;
        measure();
        window.addEventListener('resize', measure);
        return () => {
            if (ro) ro.disconnect();
            headerObserverRef.current = null;
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

    // The second pinned column: releases that still need a SHIP DAY. Membership lives in
    // utils/readyToShipColumn, which is disjoint from selectUnassigned by construction — the tray
    // keeps the dated rows, this column the undated ones, so no release is ever shown twice. These
    // rows are NOT in `releases` either: with no hard date and no shipping stage they produce no
    // bars, which is exactly why they need a column of their own to be visible at all.
    const readyToShip = useMemo(() => selectReadyToShip(jobs), [jobs]);
    // Only the in-shop holds need a ship date; the upstream ASAPs are there to be seen.
    const readyNeedsDate = useMemo(() => readyToShip.filter((r) => r._rtsSection !== 'upstream').length, [readyToShip]);

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
    // changes), then snap to a whole-column boundary.
    //
    // The date comes from the zoom handler, which captured it BEFORE the state change. It cannot be
    // recovered here: this effect runs after React has committed the new column width, and zooming
    // out makes the chart narrower — so the browser has already clamped scrollLeft to the new,
    // smaller maximum, and any px→date math on that value lands somewhere arbitrary (BUG-21). Width
    // changes with no zoom (viewport resize, tray toggle) carry no anchor and keep the px math,
    // which is sound for them: the old scrollLeft is still the one that was on screen.
    useLayoutEffect(() => {
        const prevPx = prevColPxRef.current;
        const prevCD = prevColDaysRef.current;
        const anchorDate = zoomAnchorRef.current;
        prevColPxRef.current = colPx;
        prevColDaysRef.current = colDays;
        zoomAnchorRef.current = null;
        if (prevPx === null || (prevPx === colPx && prevCD === colDays)) return;
        const el = scrollContainerRef.current;
        if (!el) return;
        const daysFromFirst = anchorDate
            ? daysBetween(chartRange.firstDay, anchorDate)
            : (el.scrollLeft / prevPx) * prevCD;   // date offset (days) at old left edge
        const x = (daysFromFirst / colDays) * colPx;
        el.scrollLeft = Math.max(0, Math.round(x / colPx) * colPx);
    }, [colPx, colDays, chartRange.firstDay]);

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
    // collapsedLanes is a dep because a folded lane renders no cells: without it, expanding one
    // would keep the height measured while it was empty and clip the stack.
    }, [bands, colPx, colDays, detail, wrap, fallbackLaneH, collapsedLanes]);   // eslint-disable-line react-hooks/exhaustive-deps

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

    // BUG-26 (1): weekend columns as overlays the LANE BODIES paint, not just the header strip.
    // Before this the only weekend cue was a faint tint on the date header — inside the chart
    // Sat and Sun looked like any other working day, which is how installs kept getting planned
    // across them without anyone noticing. Day zoom only: a week column is not a weekend.
    const weekendCols = useMemo(
        () => (colDays === 1 ? columns.filter((c) => c.isWeekend) : []),
        [columns, colDays],
    );

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

    // Zooming keeps the left-edge date. Capture it HERE, while the current column width is still
    // the one on screen — the re-anchor effect runs too late to read it (see that effect).
    const changeZoom = (delta) => {
        const next = Math.min(ZOOM_LEVELS.length - 1, Math.max(0, zoomIdx + delta));
        if (next === zoomIdx) return;
        const el = scrollContainerRef.current;
        if (el) {
            const daysFromFirst = Math.round((el.scrollLeft / colPx) * colDays);
            zoomAnchorRef.current = addDays(chartRange.firstDay, daysFromFirst);
        }
        setZoomIdx(next);
    };
    const zoomOut = () => changeZoom(-1);
    const zoomIn = () => changeZoom(1);

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
    const handleScrollSnap = (e) => {
        // Range-bar labels read this to stay on screen. Written straight to the DOM rather than
        // held in state: it changes every scroll frame and must not re-render every bar.
        e.currentTarget.style.setProperty('--tl-sx', `${e.currentTarget.scrollLeft}px`);
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

    // The drop date and the column highlight are both read off the POINTER, but DragOverlay draws
    // the held card at the grabbed element's origin plus the drag delta — i.e. offset left of the
    // pointer by wherever inside the card you grabbed it. Grabbing a card mid-body put the card a
    // column to the left of the highlight it was about to land in. Pin the card's LEFT edge to the
    // pointer (vertically centred on it) so the card always starts in the highlighted column.
    const pinCardToPointer = ({ activatorEvent, draggingNodeRect, overlayNodeRect, transform }) => {
        const start = activatorEvent && getEventCoordinates(activatorEvent);
        if (!start || !draggingNodeRect) return transform;
        const cardH = overlayNodeRect?.height ?? draggingNodeRect.height;
        return {
            ...transform,
            x: transform.x + start.x - draggingNodeRect.left,
            y: transform.y + start.y - draggingNodeRect.top - cardH / 2,
        };
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
            // A shipping drop normally writes no date, so the column under the pointer only
            // positions the label. The one exception is Shipping Planning onto an undated release
            // (the Ready-to-Ship column's exit): there the column IS the choice, so the hint names
            // the day and paints the column the way a crew-lane drop does.
            const row = active?.data?.current?.row ?? null;
            const writesDate = shipLaneDropOutcome(row, shipStage).writesDate && !!date;
            // The column is the SHIP day (it is where the card will sit); the date WRITTEN is the
            // install, a business day later. The highlight follows the column so the card lands
            // under the pointer, and the chip names the install date so the number the user is
            // committing to is the number they are shown.
            const installDate = writesDate ? installDateForShipColumn(date) : null;
            setDropHint({
                lane,
                date: installDate,
                leftPx: date ? xOfDate(date) : 0,
                label: shipLabelFor(row, shipStage, installDate ? `install ${shortDate(installDate)}` : undefined),
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
            start_install_no_color: row.start_install_no_color ?? null,
            Stage: row['Stage'] ?? null,
            comp_eta_effective: row.comp_eta_effective ?? null,
        };

        const toShipStage = toLane ? LANE_TO_SHIP_STAGE.get(toLane) : undefined;

        let optimistic;
        let call;
        if (toShipStage) {
            // A shipping lane normally writes the STAGE and nothing else. Where the card lands
            // horizontally is derived (planning → ship date, completed → hard Start install), so
            // honouring the drop column would silently move an install date the user never aimed at.
            const outcome = shipLaneDropOutcome(row, toShipStage);
            if (outcome.kind === 'noop') return;
            if (outcome.kind === 'blocked') {
                setDropError(`Can't mark ${job}-${release} ${toShipStage} — ${outcome.reason}.`);
                return;
            }
            // The gate dialog's "no photo available" reason rides along only when there is one,
            // so an ordinary drop still makes the same call the Job Log dropdown does.
            const writeStage = (gateNote) => (gateNote
                ? jobsApi.updateStage(job, release, toShipStage, { gateExceptionNote: gateNote })
                : jobsApi.updateStage(job, release, toShipStage));
            const shipColumn = outcome.writesDate ? dropDateFor(toLane, activatorEvent, delta) : null;
            if (outcome.writesDate && !shipColumn) return;   // geometry not ready — write nothing
            const dropDate = shipColumn ? installDateForShipColumn(shipColumn) : null;
            if (dropDate) {
                // The Ready-to-Ship column's exit: this release has no hard date to protect, and a
                // Ship Planning card with no date renders nowhere, so the drop supplies the day it
                // was aimed at. The DATE goes first on purpose — the backend rolls a Ready-to-Ship
                // stage into Ship Planning off the back of it (ship_planning_roll.py) and links the
                // two events, so the whole drop undoes as one. A card from further upstream (a Fab
                // or Paint ASAP) gets no such roll, so the stage is named explicitly afterwards;
                // `updateStage` is a no-op there if the roll already landed it.
                optimistic = {
                    Stage: toShipStage,
                    'Start install': dropDate,
                    start_install_formulaTF: false,
                    start_install_no_color: false,
                    comp_eta_effective: installCompleteDate(dropDate, row['Install HRS'], row.num_guys) || dropDate,
                };
                call = async (gateNote = null) => {
                    await jobsApi.updateStartInstall(job, release, dropDate);
                    if (ROLLS_TO_SHIP_PLANNING.has(String(row['Stage'] ?? '').trim())) return;
                    try {
                        await writeStage(gateNote);
                    } catch (stageErr) {
                        // The DATE landed, and it is the write the drop was aimed at. Letting this
                        // throw would roll the whole drop back optimistically and paint a state the
                        // database does not have. Keep the date, say plainly what didn't happen, and
                        // let the 30s poll bring the real stage back.
                        setDropError(
                            `Scheduled ${job}-${release} for ${shortDate(dropDate)}, but couldn't `
                            + `set its stage to ${toShipStage}: ${stageErr?.message || 'the update was rejected'}`
                        );
                        console.error('Timeline ship-lane stage write failed:', job, release, stageErr);
                    }
                };
            } else {
                optimistic = { Stage: toShipStage };
                call = (gateNote = null) => writeStage(gateNote);
            }
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
            // The bar's end comes from comp_eta_effective, so patching only the start left the
            // old end in place until the next poll — a drop across a weekend read as a bar of
            // the wrong length, which is the "install hours don't compute on a weekend drop"
            // defect. Recompute it here with the same math the server will (utils/scheduling
            // mirrors calculate_install_complete_date), so the bar is right on the first frame
            // and spans its work days CONTINUOUSLY through the weekend it bridges.
            const optimisticEnd = installCompleteDate(date, row['Install HRS'], row.num_guys);
            optimistic = {
                installer: toLane,
                'Start install': date,
                start_install_formulaTF: false,
                comp_eta_effective: optimisticEnd || date,
            };
            call = () => jobsApi.updateStartInstall(job, release, date, toLane);
        }

        const commit = async (gateNote = null) => {
            patchJob(row.id, optimistic);
            try {
                await call(gateNote);
            } catch (err) {
                patchJob(row.id, before);   // put the card back where it came from
                // The server's gate can still say no (a stale row, say): ask for the
                // photo rather than only reporting the bounce.
                const gate = stageGateFromError(err);
                if (gate) {
                    setPendingGate({ job, release, releaseId: row.id, ...gate, commit });
                    return;
                }
                const verb = toShipStage ? 'move' : 'schedule';
                setDropError(
                    `Couldn't ${verb} ${job}-${release}: ${err?.message || 'the update was rejected'}`
                );
                console.error('Timeline drag failed:', job, release, err);
            }
        };

        // Department photo gate (T13): a ship-lane drop that crosses into the next department
        // (Paint → Ship, Ship → Install) owes that department's handoff photo. Ask BEFORE
        // writing anything — the date-first path above would otherwise land the date and
        // bounce the stage, leaving a half-done drop. Cancel writes nothing; the card never moved.
        const gate = toShipStage ? gateStageFor(before.Stage, toShipStage) : null;
        if (gate) {
            setPendingGate({ job, release, releaseId: row.id, stage: gate, requestedStage: toShipStage, commit });
            return;
        }
        await commit();
    };

    return (
        <>
            <DndContext
                sensors={sensors}
                // Lane under the POINTER, matching the date math — the default rect-intersection
                // test used the held card's box, which could pick the lane next door.
                collisionDetection={pointerWithin}
                onDragStart={handleDragStart}
                onDragMove={handleDragMove}
                onDragCancel={handleDragCancel}
                onDragEnd={handleDragEnd}
            >
            <div ref={scrollContainerRef} data-timeline-scroll className="flex-1 overflow-auto h-full" onScroll={handleScrollSnap}>
                {initialLoad && (
                    <div className="text-center py-12">
                        <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-accent-500 mb-4"></div>
                        <p className="text-gray-600 font-medium">Loading timeline data...</p>
                    </div>
                )}

                {!initialLoad && bands.length > 0 && (
                    <div className="flex flex-col" style={{ width: chromePx + totalPx, minHeight: '100%' }}>
                        {/* Sticky header. z-40, above the staging columns' z-30: a FOLDED column is a
                            full-height rail with no top offset, so on vertical scroll it slides up
                            under the header — at an equal z it painted over it (later in the DOM)
                            and hid the ▶ expand control. */}
                        <div ref={attachHeader} className="sticky top-0 z-40 bg-gray-100 border-b-2 border-gray-300 flex" style={{ minHeight: HEADER_PX }}>
                            {/* Staging-column header — frozen furthest left, above the tray. */}
                            <div
                                className="sticky left-0 z-50 flex-shrink-0 border-r-2 border-gray-400 bg-gray-200 flex flex-col justify-center"
                                style={{ width: stagingPx }}
                            >
                                {trayCollapsed ? (
                                    <button
                                        type="button"
                                        onClick={toggleTray}
                                        title={`Show unassigned (${unassigned.length} ready to schedule)`}
                                        aria-label="Show unassigned column"
                                        aria-expanded={false}
                                        className="w-full h-full flex flex-col items-center justify-center gap-1 hover:bg-gray-300"
                                    >
                                        <span className="text-[11px] leading-none text-gray-700">▶</span>
                                        {unassigned.length > 0 && (
                                            <span className="text-[10px] font-extrabold text-gray-700 leading-none tabular-nums">
                                                {unassigned.length}
                                            </span>
                                        )}
                                    </button>
                                ) : (
                                    <div className="px-2 py-2 flex items-start gap-1">
                                        <div className="min-w-0 flex-1">
                                            <span className="block text-[11px] font-extrabold text-gray-800 uppercase tracking-wide">Unassigned</span>
                                            <span className="block text-[10px] text-gray-600">
                                                {unassigned.length} ready to schedule
                                            </span>
                                        </div>
                                        <button
                                            type="button"
                                            onClick={toggleTray}
                                            title="Collapse unassigned column"
                                            aria-label="Collapse unassigned column"
                                            aria-expanded={true}
                                            className="shrink-0 px-1 py-0.5 rounded text-[11px] leading-none text-gray-600 hover:bg-gray-300"
                                        >◀</button>
                                    </div>
                                )}
                            </div>
                            {/* Ready-to-Ship header — frozen just right of the tray, above its column. */}
                            <div
                                className="sticky z-50 flex-shrink-0 border-r-2 border-gray-400 bg-gray-200 flex flex-col justify-center"
                                style={{ width: readyPx, left: stagingPx }}
                            >
                                {readyCollapsed ? (
                                    <button
                                        type="button"
                                        onClick={toggleReady}
                                        title={`Show ready to ship (${readyNeedsDate} waiting on a ship date)`}
                                        aria-label="Show ready to ship column"
                                        aria-expanded={false}
                                        className="w-full h-full flex flex-col items-center justify-center gap-1 hover:bg-gray-300"
                                    >
                                        <span className="text-[11px] leading-none text-gray-700">▶</span>
                                        {readyNeedsDate > 0 && (
                                            <span className="text-[10px] font-extrabold text-gray-700 leading-none tabular-nums">
                                                {readyNeedsDate}
                                            </span>
                                        )}
                                    </button>
                                ) : (
                                    <div className="px-2 py-2 flex items-start gap-1">
                                        <div className="min-w-0 flex-1">
                                            <span className="block text-[11px] font-extrabold text-gray-800 uppercase tracking-wide">Ready to Ship</span>
                                            <span className="block text-[10px] text-gray-600">
                                                {readyNeedsDate} need a ship date
                                            </span>
                                        </div>
                                        <button
                                            type="button"
                                            onClick={toggleReady}
                                            title="Collapse ready to ship column"
                                            aria-label="Collapse ready to ship column"
                                            aria-expanded={true}
                                            className="shrink-0 px-1 py-0.5 rounded text-[11px] leading-none text-gray-600 hover:bg-gray-300"
                                        >◀</button>
                                    </div>
                                )}
                            </div>
                            <div
                                className="sticky z-40 flex-shrink-0 border-r-2 border-gray-300 bg-gray-100 px-2 py-2 flex flex-col justify-center gap-1"
                                style={{ width: SIDEBAR_PX, left: stagingPx + readyPx }}
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
                                        className={`absolute border-r border-gray-300 text-center py-1 flex flex-col items-center justify-center ${col.isWeekend ? 'bg-gray-400/45' : ''} ${col.isToday ? 'bg-accent-200' : ''}`}
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
                                style={trayCollapsed ? {
                                    // Folded, the tray has no content to give it height — without an
                                    // explicit stretch the rail stops below the header and the lane
                                    // rows show through the gap on the far left.
                                    width: stagingPx,
                                    alignSelf: 'stretch',
                                } : {
                                    width: stagingPx,
                                    top: headerH,
                                    maxHeight: containerH ? Math.max(containerH - headerH, 120) : undefined,
                                    overflowY: 'auto',
                                }}
                            >
                                <div className={trayCollapsed ? 'hidden' : 'p-1.5 space-y-1.5'}>
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

                            {/* Pinned Ready-to-Ship column, frozen immediately right of the tray.
                                Same shape and same gesture as the tray, one question earlier in the
                                pipeline: these releases have no ship day yet. Deliberately NOT a
                                drop target — every write this column knows how to make is a drop
                                somewhere ELSE (Shipping Planning stamps the date, a crew lane
                                schedules it), and a card dropped back here would have to mean
                                "un-set the date", which is a different gesture with a different
                                blast radius. */}
                            <div
                                data-ready-to-ship="1"
                                className="sticky z-30 flex-shrink-0 border-r-2 border-gray-400 bg-gray-100"
                                style={readyCollapsed ? {
                                    // Folded, the column has no content to give it height — without
                                    // an explicit stretch the rail stops below the header and the
                                    // lane rows show through the gap.
                                    width: readyPx,
                                    left: stagingPx,
                                    alignSelf: 'stretch',
                                } : {
                                    width: readyPx,
                                    left: stagingPx,
                                    top: headerH,
                                    maxHeight: containerH ? Math.max(containerH - headerH, 120) : undefined,
                                    overflowY: 'auto',
                                }}
                            >
                                <div className={readyCollapsed ? 'hidden' : 'p-1.5 space-y-1.5'}>
                                    {readyToShip.length === 0 ? (
                                        <p className="text-[10px] text-gray-500 text-center py-6 leading-snug">
                                            Nothing waiting.<br />Everything ready to ship has a date.
                                        </p>
                                    ) : readyToShip.map((row) => (
                                        <StagingCard
                                            key={row.id}
                                            job={row}
                                            draggable={canDrag && row._rtsSection !== 'upstream'}
                                            dragIdPrefix="ready"
                                            tone={READY_SECTION_TONE[row._rtsSection]}
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
                            </div>

                            <div className="flex flex-col" style={{ width: SIDEBAR_PX + totalPx }}>
                            {bands.map((band) => {
                                // Reserve a bottom strip on the Shipping Planning lane for the PU/order overlay.
                                const laneCollapsed = collapsedLanes.has(band.lane);
                                const laneOrders = laneCollapsed || band.lane !== SHIP_PLANNING_LANE ? [] : placedOrders;
                                const laneH = laneCollapsed
                                    ? LANE_COLLAPSED_PX
                                    : (laneHeights[band.lane] || fallbackLaneH)
                                        + (laneOrders.length ? ORDER_ROW_PX + CARD_VGAP : 0);
                                return (
                                    <div
                                        key={band.lane}
                                        data-lane={band.lane}
                                        className={`flex flex-shrink-0 border-b ${band.isShip ? 'border-gray-300' : 'border-gray-200'}`}
                                        style={{ minHeight: laneH }}
                                    >
                                        <div
                                            className={`sticky z-20 flex-shrink-0 border-r-2 border-gray-300 px-2 flex items-center gap-2 ${laneCollapsed ? 'py-0 bg-gray-200' : `py-1 ${band.isShip ? 'bg-gray-100' : 'bg-gray-50'}`}`}
                                            style={{ width: SIDEBAR_PX, left: stagingPx + readyPx }}
                                        >
                                            <span className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: band.color }} />
                                            <span className={`truncate ${laneCollapsed ? 'text-xs' : 'text-sm'} ${band.isShip ? 'font-extrabold text-gray-900' : 'font-bold text-gray-800'}`}>{band.lane}</span>
                                            {band.count > 0 && (
                                                <span className="text-[10px] text-gray-500 ml-auto tabular-nums">{band.count}</span>
                                            )}
                                            <button
                                                type="button"
                                                onClick={() => toggleLane(band.lane)}
                                                title={laneCollapsed ? `Show ${band.lane}` : `Hide ${band.lane}`}
                                                aria-label={laneCollapsed ? `Show ${band.lane}` : `Hide ${band.lane}`}
                                                aria-expanded={!laneCollapsed}
                                                className={`shrink-0 grid place-items-center w-6 h-6 rounded border shadow-sm transition-colors ${
                                                    laneCollapsed
                                                        ? 'border-gray-400 bg-white text-gray-900 hover:bg-gray-100'
                                                        : 'border-gray-300 bg-white text-gray-400 hover:bg-gray-100 hover:text-gray-700'
                                                } ${band.count > 0 ? '' : 'ml-auto'}`}
                                            >
                                                <EyeIcon off={laneCollapsed} />
                                            </button>
                                        </div>
                                        <LaneDropArea
                                            lane={band.lane}
                                            enabled={canDrag}
                                            registerRef={(el) => { laneChartRefs.current[band.lane] = el; }}
                                            hintLeft={dropHint?.lane === band.lane ? dropHint.leftPx : null}
                                            hintLabel={dropHint?.lane === band.lane ? dropHint.label : null}
                                            hintDate={dropHint?.lane === band.lane ? !!dropHint.date : false}
                                            colPx={colPx}
                                            className={`relative flex-shrink-0 ${laneCollapsed ? 'bg-gray-200/60' : 'bg-white'}`}
                                            style={{ width: totalPx, height: laneH, ...colGridStyle }}
                                        >
                                            {/* Weekend columns — drawn first so everything else sits on top. */}
                                            {weekendCols.map((col) => (
                                                <div
                                                    key={`wk-${col.key}`}
                                                    className="absolute top-0 bottom-0 bg-gray-400/30 pointer-events-none"
                                                    style={{ left: col.leftPx, width: colPx }}
                                                />
                                            ))}
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
                                            {!laneCollapsed && band.cells && band.cells.map((cell) => (
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
                                            {!laneCollapsed && band.bars && band.bars.map((release) => (
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
            <DragOverlay dropAnimation={null} modifiers={[pinCardToPointer]}>
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
            {/* Department photo gate for a ship-lane drop: the drop is parked in pendingGate
                until a photo is attached or a reason given, then committed as it would have been. */}
            {pendingGate && (
                <StagePhotoGateModal
                    isOpen
                    releaseId={pendingGate.releaseId}
                    title={`${pendingGate.job}-${pendingGate.release}`}
                    gateStage={pendingGate.stage}
                    requestedStage={pendingGate.requestedStage}
                    onConfirmStage={(gateNote) => {
                        const pg = pendingGate;
                        setPendingGate(null);
                        pg.commit(gateNote);
                    }}
                    onClose={() => setPendingGate(null)}
                />
            )}
            {hoveredItem && (
                <div
                    className="fixed bg-gray-900 text-white text-xs rounded-lg shadow-xl p-3 z-50 pointer-events-none"
                    // Flip toward the roomier side of the cursor: a card low in the viewport (the
                    // bottom of the Ready-to-Ship column) would otherwise open its tooltip off-screen.
                    style={{
                        ...(hoverPosition.x > window.innerWidth / 2
                            ? { right: `${window.innerWidth - hoverPosition.x + 10}px` }
                            : { left: `${hoverPosition.x + 10}px` }),
                        ...(hoverPosition.y > window.innerHeight / 2
                            ? { bottom: `${window.innerHeight - hoverPosition.y + 10}px` }
                            : { top: `${hoverPosition.y + 10}px` }),
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
                // Silent: a hub edit (crew size, dates, stage) merges the changed row in place.
                // A bare `refetch` passed no arg → non-silent → loading flip redrew the whole view.
                onJobUpdate={() => refetch(true)}
                isOpen={!!hubJob}
                job={hubJob}
                releaseId={hubJob?.id}
                viewerUrl={hubJob?.viewer_url}
                initialTab="details"
                scrollToMaterials={hubScrollToMaterials}
                onOrdersChanged={refreshMaterialSummary}
                onClose={closeHub}
                onOpenVersion={(vid, mode, vReleaseId) => {
                    setMarkup({
                        releaseId: vReleaseId ?? hubJob?.id,
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
