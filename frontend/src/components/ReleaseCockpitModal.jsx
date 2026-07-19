/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Admin-only "cockpit" detail modal for a release, opened by clicking a timeline bar.
 *   A read-only WHAT-IF sandbox: a manifest-photo hero + filmstrip/lightbox, plus a live schedule
 *   cockpit where an admin can drag Start Install within a bounded window and step the crew size to
 *   preview how ship date / Comp. ETA move — all client-side. Reset/Apply manage a LOCAL preview only;
 *   nothing is written to the DB, Trello, or events. Non-admins get ReleaseDetailModal instead.
 * exports:
 *   ReleaseCockpitModal: Portal modal — manifest gallery + read-only schedule simulator.
 * imports_from: [react, react-dom, ../services/jobsApi, ../utils/api, ../utils/formatters, ../utils/scheduling, ../utils/auth, ./Badge, ./PdfVersionHistoryModal, ./PdfMarkupModal]
 * imported_by: [frontend/src/components/GanttChart.jsx]
 * invariants:
 *   - SIMULATE-ONLY: the crew/start dials never call a write endpoint. Reset reverts the preview to the
 *     release's real values; Apply re-baselines the in-modal comparison; closing discards everything.
 *     Every other section is GET-only enrichment, identical to ReleaseDetailModal.
 *   - Start Install is clamped to +/- START_WINDOW_BIZ business days of the current baseline.
 *   - Schedule math comes from utils/scheduling (the client mirror of the backend calculator), so the
 *     previewed dates equal what the server would compute.
 *   - Renders via createPortal to document.body to escape the timeline's overflow clipping.
 * updated_by_agent: 2026-07-19 (new: admin schedule cockpit)
 */
import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';

import { jobsApi } from '../services/jobsApi';
import { API_BASE_URL } from '../utils/api';
import { toYmd } from '../utils/formatters';
import { addBusinessDays, subtractBusinessDays } from '../utils/formatters';
import { installDays, installCompleteDate, shipEstimate, businessDaysBetween } from '../utils/scheduling';
import { checkAuth } from '../utils/auth';
import { Badge } from './Badge';
import { PdfVersionHistoryModal } from './PdfVersionHistoryModal';
import { PdfMarkupModal } from './PdfMarkupModal';

const ITEM_TYPE_TINT = { action: 'blue', needs_gc_update: 'amber', decision: 'violet', risk: 'red', fyi: 'slate' };
const STATUS_TINT = { accepted: 'amber', done: 'emerald' };
const START_WINDOW_BIZ = 10;   // Start Install is nudgeable +/- this many business days (~2 weeks each way)
const EDGE_MARGIN = 2;         // pan the axis only when the start comes within this many columns of an edge
const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// ---- tiny date helpers (YYYY-MM-DD) ----
const parseYmd = (ymd) => { const [y, m, d] = ymd.split('-').map(Number); return new Date(y, m - 1, d); };
const ymdOf = (dt) => `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
const addCal = (ymd, n) => { const d = parseYmd(ymd); d.setDate(d.getDate() + n); return ymdOf(d); };
const calBetween = (a, b) => Math.round((parseYmd(b) - parseYmd(a)) / 86400000);
const isWeekendYmd = (ymd) => { const w = parseYmd(ymd).getDay(); return w === 0 || w === 6; };
const fmtLong = (ymd) =>(ymd ? `${DOW[parseYmd(ymd).getDay()]} ${MON[parseYmd(ymd).getMonth()]} ${parseYmd(ymd).getDate()}` : '—');
const fmtShort = (ymd) => (ymd ? `${MON[parseYmd(ymd).getMonth()]} ${parseYmd(ymd).getDate()}` : '—');
const fmtFull = (v) => { const s = toYmd(v); return s ? `${MON[parseYmd(s).getMonth()]} ${parseYmd(s).getDate()}, ${parseYmd(s).getFullYear()}` : '—'; };

function Field({ label, children }) {
    return (
        <div>
            <dt className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-slate-500">{label}</dt>
            <dd className="text-sm text-gray-800 dark:text-slate-200">{children || '—'}</dd>
        </div>
    );
}
function SectionSpinner() {
    return (
        <div className="flex items-center gap-2 text-xs text-gray-400 dark:text-slate-500 py-2">
            <span className="inline-block animate-spin rounded-full h-3.5 w-3.5 border-b-2 border-accent-500" /> Loading…
        </div>
    );
}
function DeltaChip({ n, unit = 'day', suffix }) {
    const tone = n > 0 ? 'text-amber-700 bg-amber-100 dark:text-amber-300 dark:bg-amber-900/40'
        : n < 0 ? 'text-emerald-700 bg-emerald-100 dark:text-emerald-300 dark:bg-emerald-900/40'
            : 'text-gray-500 bg-gray-100 dark:text-slate-400 dark:bg-slate-700';
    const txt = n === 0 ? 'On plan' : `${n > 0 ? '+' : ''}${n} ${unit}${Math.abs(n) === 1 ? '' : 's'}${suffix ? ' ' + suffix : ''}`;
    return <span className={`font-mono text-[11px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap ${tone}`}>{txt}</span>;
}

// The ship → start → comp date flow, with the gaps between stops. Reused by the cockpit readout and
// the Apply confirmation. Pass pre-formatted date strings; accent flags highlight moved stops.
function DateFlow({ ship, start, comp, days, startAccent = false, compAccent = false }) {
    const stop = (label, val, accent) => (
        <div className="flex-1 min-w-0">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-gray-400 dark:text-slate-500">{label}</div>
            <div className={`font-mono text-sm font-semibold tabular-nums truncate ${accent ? 'text-accent-600 dark:text-accent-400' : 'text-gray-800 dark:text-slate-100'}`}>{val}</div>
        </div>
    );
    const gap = (txt) => (
        <div className="flex flex-col items-center justify-center shrink-0 px-0.5 -mt-1">
            <span className="text-gray-300 dark:text-slate-600 text-base leading-none">→</span>
            <span className="text-[9px] text-gray-400 dark:text-slate-500 mt-0.5 whitespace-nowrap">{txt}</span>
        </div>
    );
    return (
        <div className="flex items-stretch gap-1 text-center">
            {stop('Ship (est)', ship, false)}
            {gap('1 day')}
            {stop('Start install', start, startAccent)}
            {gap(`${days || '—'}-day`)}
            {stop('Comp. ETA', comp, compAccent)}
        </div>
    );
}

// showInstallWindow gates the drag-to-simulate install-window cockpit. It only makes
// sense for installer/mirror cards (Timeline installer lanes); shipping planning/completed
// cards pass false so the cockpit is hidden and the modal shows facts/enrichment only.
export function ReleaseCockpitModal({ isOpen, onClose, release, accentColor, showInstallWindow = true }) {
    const releaseId = release?.id;
    const accent = accentColor || '#6d4aff';

    // enrichment (GET-only, mirrors ReleaseDetailModal)
    const [enrichment, setEnrichment] = useState({ todos: [], meetings: [] });
    const [photos, setPhotos] = useState([]);
    const [drawings, setDrawings] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const [canMarkup, setCanMarkup] = useState(false);
    const [drawingHubOpen, setDrawingHubOpen] = useState(false);
    const [markupOpen, setMarkupOpen] = useState(false);
    const [markupVersionId, setMarkupVersionId] = useState(null);
    const [markupMode, setMarkupMode] = useState('view');

    // lightbox
    const [lbOpen, setLbOpen] = useState(false);
    const [lbIndex, setLbIndex] = useState(0);
    const [confirmOpen, setConfirmOpen] = useState(false);   // Apply → summary confirmation dialog

    // ---- release-derived scheduling inputs ----
    const installHrs = Number(release?.['Install HRS'] ?? release?.install_hrs);
    const realStart = release?.['start_install_formulaTF'] === false ? toYmd(release?.['Start install']) : '';
    const realCrew = (() => { const n = Number(release?.num_guys); return Number.isFinite(n) && n > 0 ? n : 2; })();
    const hardShip = toYmd(release?.['Ship Date'] ?? release?.ship_date);
    const canSimulate = !!realStart;

    // ---- cockpit state: preview + baseline (both discarded on close) ----
    const [startYmd, setStartYmd] = useState('');
    const [crew, setCrew] = useState(2);
    const [savedStart, setSavedStart] = useState('');
    const [savedCrew, setSavedCrew] = useState(2);
    const [dragging, setDragging] = useState(false);
    const [viewAnchor, setViewAnchor] = useState('');   // date the visible gantt axis is centered on (recenters between interactions, frozen during a drag)

    // Seed everything when a different release opens.
    useEffect(() => {
        setStartYmd(realStart);
        setSavedStart(realStart);
        setCrew(realCrew);
        setSavedCrew(realCrew);
        setViewAnchor(realStart);
        setLbOpen(false);
        setLbIndex(0);
        setConfirmOpen(false);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [release]);

    useEffect(() => {
        if (!isOpen) return;
        const onKey = (e) => { if (e.key === 'Escape') { if (confirmOpen) setConfirmOpen(false); else if (lbOpen) setLbOpen(false); else onClose(); } };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [isOpen, onClose, lbOpen, confirmOpen]);

    useEffect(() => {
        if (!isOpen) return;
        let cancelled = false;
        checkAuth().then((u) => { if (!cancelled) setCanMarkup(!!(u?.is_admin || u?.is_drafter)); }).catch(() => {});
        return () => { cancelled = true; };
    }, [isOpen]);

    useEffect(() => {
        if (!isOpen || !releaseId) return;
        let cancelled = false;
        setLoading(true); setError(null);
        setEnrichment({ todos: [], meetings: [] }); setPhotos([]); setDrawings([]);
        Promise.allSettled([
            jobsApi.getReleaseChecklist(releaseId),
            jobsApi.getReleasePhotos(releaseId),
            jobsApi.getReleaseDrawings(releaseId),
        ]).then(([checklist, photoList, drawingList]) => {
            if (cancelled) return;
            if (checklist.status === 'fulfilled') setEnrichment({ todos: checklist.value?.todos || [], meetings: checklist.value?.meetings || [] });
            if (photoList.status === 'fulfilled') setPhotos(photoList.value || []);
            if (drawingList.status === 'fulfilled') setDrawings(drawingList.value || []);
            if (checklist.status === 'rejected' && photoList.status === 'rejected' && drawingList.status === 'rejected') setError('Failed to load release details.');
            setLoading(false);
        });
        return () => { cancelled = true; };
    }, [isOpen, releaseId]);

    // ---- allowed start slots (business days within +/- window of the baseline) ----
    const slots = useMemo(() => {
        if (!savedStart) return [];
        const out = [];
        for (let k = -START_WINDOW_BIZ; k <= START_WINDOW_BIZ; k++) {
            out.push(k < 0 ? subtractBusinessDays(savedStart, -k) : addBusinessDays(savedStart, k));
        }
        return out;
    }, [savedStart]);

    // ---- gantt axis geometry: a compact ~2-week window CENTERED on viewAnchor (not the whole ±window
    //      clamp, which would be too wide). viewAnchor recenters between interactions, so dragging the
    //      start toward an edge and releasing brings the next stretch into view. ----
    const geom = useMemo(() => {
        if (!canSimulate || !viewAnchor) return null;
        const anchorShip = shipEstimate(viewAnchor) || viewAnchor;                                  // ~1 day before start
        const anchorComp = installCompleteDate(viewAnchor, installHrs > 0 ? installHrs : 8, savedCrew) || viewAnchor;
        const axisStart = addCal(anchorShip, -2);      // a little room left of the ship marker
        const axisEnd = addCal(anchorComp, 7);         // ~a week of reslot room past completion
        const axisDays = Math.max(10, calBetween(axisStart, axisEnd) + 1);
        return { axisStart, axisDays };
    }, [canSimulate, viewAnchor, installHrs, savedCrew]);

    const geomRef = useRef({ geom: null, slots: [] });
    useEffect(() => { geomRef.current = { geom, slots }; }, [geom, slots]);

    // drag refs/helpers (declared before the early return so hook order stays stable)
    const ganttRef = useRef(null);
    const draggingRef = useRef(false);   // guard read synchronously (no state-update race mid-drag)
    const grabOffsetRef = useRef(0);     // axis-columns between the pointer and the bar's left edge at grab
    // Slot whose start column is nearest a target column on the axis (clamped to the window).
    const nearestSlot = useCallback((targetCol) => {
        const { geom: g, slots: s } = geomRef.current;
        if (!g) return 0;
        let best = 0, bd = Infinity;
        s.forEach((slot, i) => { const d = Math.abs(calBetween(g.axisStart, slot) - targetCol); if (d < bd) { bd = d; best = i; } });
        return best;
    }, []);

    if (!isOpen || !release) return null;

    // ---- derived preview values ----
    // In the what-if, the ship estimate tracks the simulated start (one work day before it), even if
    // the release has a stored hard Ship Date — moving the install moves when it must ship.
    const ship = shipEstimate(startYmd);
    const comp = installCompleteDate(startYmd, installHrs, crew);
    const savedComp = installCompleteDate(savedStart, installHrs, savedCrew);
    const days = installDays(installHrs, crew);
    const startDelta = businessDaysBetween(savedStart, startYmd);      // start shift
    const crewDelta = installDays(installHrs, crew) - installDays(installHrs, savedCrew); // duration change
    const netDelta = businessDaysBetween(savedComp, comp);            // net comp shift
    const dirty = startYmd !== savedStart || crew !== savedCrew;

    const slotIndex = slots.indexOf(startYmd);
    const colPct = geom ? 100 / geom.axisDays : 0;
    const dayIdx = (ymd) => (geom ? calBetween(geom.axisStart, ymd) : 0);

    const setStartToIndex = (i) => { const s = geomRef.current.slots; const j = Math.max(0, Math.min(s.length - 1, i)); if (s[j]) setStartYmd(s[j]); return s[j]; };
    // Pan the axis ONLY when the start reaches within EDGE_MARGIN columns of a visible edge — normal
    // tweaks leave the view put; pushing toward an edge slides the next stretch into view.
    const maybePan = (ns) => {
        const g = geomRef.current.geom;
        if (!g || !ns) return;
        const idx = calBetween(g.axisStart, ns);
        if (idx < EDGE_MARGIN || idx > g.axisDays - 1 - EDGE_MARGIN) setViewAnchor(ns);
    };
    const nudgeStart = (dir) => { const cur = slots.indexOf(startYmd) < 0 ? START_WINDOW_BIZ : slots.indexOf(startYmd); const t = setStartToIndex(cur + dir); maybePan(t); };
    const stepCrew = (dir) => setCrew((c) => Math.max(1, Math.min(8, c + dir)));
    const applyPreview = () => { setSavedStart(startYmd); setSavedCrew(crew); };
    const resetPreview = () => { setStartYmd(realStart); setSavedStart(realStart); setCrew(realCrew); setSavedCrew(realCrew); setViewAnchor(realStart); };

    // ---- grab the install bar and drag it to reslot Start Install (relative grab; snaps to work-day
    //      slots). A min bar width keeps it grabbable even when a big crew shrinks the install to a day. ----
    const pointerCol = (clientX) => { const el = ganttRef.current; if (!el) return 0; const r = el.getBoundingClientRect(); return ((clientX - r.left) / r.width) * (geomRef.current.geom?.axisDays || 1); };
    const onBarDown = (e) => {
        if (!canSimulate) return;
        draggingRef.current = true; setDragging(true);
        try { e.currentTarget.setPointerCapture(e.pointerId); } catch { /* noop */ }
        grabOffsetRef.current = pointerCol(e.clientX) - dayIdx(startYmd);
        e.preventDefault(); e.stopPropagation();
    };
    const onBarMove = (e) => { if (!draggingRef.current) return; setStartToIndex(nearestSlot(pointerCol(e.clientX) - grabOffsetRef.current)); };
    const onBarUp = (e) => { if (!draggingRef.current) return; draggingRef.current = false; setDragging(false); maybePan(startYmd); try { e.currentTarget.releasePointerCapture(e.pointerId); } catch { /* noop */ } };

    // ---- photos ----
    const photoUrl = (pid) => `${API_BASE_URL}/brain/releases/${releaseId}/photos/${pid}/file`;
    const coverId = release.cover_photo_id || photos[0]?.id || null;
    const openLb = (i) => { setLbIndex(i); setLbOpen(true); };

    const job = release['Job #'] ?? release.job;
    const rel = release['Release #'] ?? release.release;
    const jobName = release['Job'] || release.job_name || '';
    const description = release['Description'] || release.description || '';
    const stage = release['Stage'] || release.stage;
    const stageGroup = release['Stage Group'] || release.stage_group;
    const installer = release.installer;
    const pm = release['PM'] || release.pm;
    const by = release['BY'] || release.by;
    const notes = release['Notes'] || release.notes;
    const projectId = release.procore_project_id || '';
    const submittalId = release.procore_submittal_id || '';
    const procoreUrl = projectId && submittalId ? `https://app.procore.com/webclients/host/companies/18521/projects/${projectId}/tools/submittals/${submittalId}` : null;
    const trelloUrl = release.trello_card_id ? `https://trello.com/c/${release.trello_card_id}` : null;
    const viewerUrl = release.viewer_url || null;
    const { todos, meetings } = enrichment;

    // ---- gantt column decorations ----
    const columns = geom ? Array.from({ length: geom.axisDays }, (_, i) => {
        const ymd = addCal(geom.axisStart, i);
        return { ymd, weekend: isWeekendYmd(ymd), dow: DOW[parseYmd(ymd).getDay()][0], day: parseYmd(ymd).getDate() };
    }) : [];
    const barLeft = geom ? dayIdx(startYmd) * colPct : 0;
    const barWidth = geom ? (calBetween(startYmd, comp) + 1) * colPct : 0;
    const ghostLeft = geom ? dayIdx(savedStart) * colPct : 0;
    const ghostWidth = geom ? (calBetween(savedStart, savedComp) + 1) * colPct : 0;
    const shipIdx = geom && ship ? dayIdx(ship) : 0;

    const modalContent = (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" onClick={onClose}>
            <div className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl max-w-2xl w-full mx-4 flex flex-col max-h-[92vh]" onClick={(e) => e.stopPropagation()}>

                {/* ---- manifest hero ---- */}
                <div className="relative h-52 shrink-0 rounded-t-xl overflow-hidden">
                    {coverId ? (
                        <>
                            <img src={photoUrl(coverId)} alt="Manifest" className="absolute inset-0 w-full h-full object-cover" />
                            <button className="absolute inset-0 cursor-zoom-in" aria-label="Open manifest photos"
                                onClick={() => openLb(Math.max(0, photos.findIndex((p) => p.id === coverId)))} />
                        </>
                    ) : (
                        <div className="absolute inset-0 flex items-center justify-center"
                            style={{ backgroundImage: `repeating-linear-gradient(-45deg, ${accent}1a 0 11px, ${accent}0d 11px 22px)` }}>
                            <span className="text-sm font-semibold text-gray-500 dark:text-slate-400">No manifest photo</span>
                        </div>
                    )}
                    <div className="absolute inset-0 pointer-events-none" style={{ background: 'linear-gradient(180deg, rgba(10,7,20,.1) 0%, rgba(10,7,20,0) 34%, rgba(10,7,20,.62) 82%, rgba(8,5,16,.88) 100%)' }} />
                    <div className="absolute top-3.5 left-4 right-3.5 flex items-start justify-between gap-2">
                        {stage ? <span className="text-white text-xs font-semibold px-3 py-1.5 rounded-full shadow" style={{ backgroundColor: accent }}>{stage}</span> : <span />}
                        <div className="flex items-center gap-2">
                            {photos.length > 0 && (
                                <button onClick={() => openLb(0)} className="font-mono text-[11px] text-white bg-black/40 backdrop-blur border border-white/20 rounded-full px-2.5 py-1 hover:bg-black/60">📷 {photos.length}</button>
                            )}
                            <button onClick={onClose} aria-label="Close" className="w-8 h-8 rounded-full bg-black/40 backdrop-blur border border-white/20 text-white grid place-items-center hover:bg-black/60">✕</button>
                        </div>
                    </div>
                    <div className="absolute left-5 right-5 bottom-4 text-white">
                        <h2 className="text-lg font-bold truncate" style={{ textShadow: '0 1px 12px rgba(0,0,0,.4)' }}>{job}-{rel}{jobName ? ` · ${jobName}` : ''}</h2>
                        {description && <p className="text-[13px] text-white/80 truncate">{description}</p>}
                    </div>
                </div>

                {/* ---- filmstrip ---- */}
                {photos.length > 0 && (
                    <div className="flex gap-2 px-5 py-3 overflow-x-auto shrink-0 border-b border-gray-100 dark:border-slate-700">
                        {photos.map((p, i) => (
                            <button key={p.id} onClick={() => openLb(i)} title={p.note || p.original_filename}
                                className="relative flex-none w-24 h-16 rounded-lg overflow-hidden border border-gray-200 dark:border-slate-600 hover:border-accent-500 cursor-zoom-in">
                                <img src={photoUrl(p.id)} alt={p.original_filename || ''} loading="lazy" className="w-full h-full object-cover" />
                            </button>
                        ))}
                    </div>
                )}

                {/* ---- scrollable body ---- */}
                <div className="p-5 space-y-5 overflow-y-auto">

                    {/* cockpit — install-window simulation; installer/mirror cards only */}
                    {showInstallWindow && (
                    <section className="rounded-2xl border border-gray-200 dark:border-slate-600 bg-gray-50 dark:bg-slate-700/40 p-4">
                        <div className="flex items-center gap-2 mb-2.5">
                            <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-gray-400 dark:text-slate-500">Install window · {installer || 'unassigned'}</span>
                            <span className="ml-auto font-mono text-[10px] text-gray-400 dark:text-slate-500 flex items-center gap-1.5">
                                <span className="w-1.5 h-1.5 rounded-full bg-amber-400" /> Simulation · not saved
                            </span>
                        </div>

                        {canSimulate && geom ? (
                            <>
                                {/* gantt */}
                                <div ref={ganttRef} className="relative h-[92px] rounded-lg overflow-hidden bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 select-none" style={{ touchAction: 'pan-y' }}>
                                    {columns.map((c, i) => (
                                        <React.Fragment key={c.ymd}>
                                            {c.weekend && <div className="absolute top-0 bottom-0 bg-slate-400/10" style={{ left: `${i * colPct}%`, width: `${colPct}%` }} />}
                                            {i > 0 && <div className="absolute top-0 bottom-0 w-px bg-gray-100 dark:bg-slate-700" style={{ left: `${i * colPct}%` }} />}
                                            <div className="absolute bottom-1 -translate-x-1/2 font-mono text-[9px] text-gray-400 dark:text-slate-500 whitespace-nowrap" style={{ left: `${(i + 0.5) * colPct}%` }}>{c.dow} {c.day}</div>
                                        </React.Fragment>
                                    ))}
                                    {/* ghost = saved plan */}
                                    {dirty && <div className="absolute rounded-md border-[1.5px] border-dashed border-gray-400 dark:border-slate-500" style={{ top: 32, height: 24, left: `${ghostLeft}%`, width: `${ghostWidth}%` }} />}
                                    {/* ship diamond */}
                                    {ship && <>
                                        <div className="absolute font-mono text-[9px] font-semibold text-slate-500 dark:text-slate-300 -translate-x-1/2" style={{ top: 18, left: `${(shipIdx + 0.5) * colPct}%` }}>Ship</div>
                                        <div className="absolute w-2.5 h-2.5 bg-slate-500 dark:bg-slate-300 -translate-x-1/2 rotate-45" style={{ top: 33, left: `${(shipIdx + 0.5) * colPct}%`, transition: dragging ? 'none' : 'left .2s' }} />
                                    </>}
                                    {/* draggable install bar */}
                                    <div role="slider" tabIndex={0} aria-label="Start install date" aria-valuemin={0} aria-valuemax={slots.length - 1} aria-valuenow={slotIndex < 0 ? START_WINDOW_BIZ : slotIndex} aria-valuetext={fmtLong(startYmd)}
                                        onPointerDown={onBarDown} onPointerMove={onBarMove} onPointerUp={onBarUp} onPointerCancel={onBarUp}
                                        onKeyDown={(e) => { if (e.key === 'ArrowLeft') { nudgeStart(-1); e.preventDefault(); } else if (e.key === 'ArrowRight') { nudgeStart(1); e.preventDefault(); } }}
                                        className="absolute flex items-center gap-1.5 px-1.5 rounded-md text-white overflow-hidden select-none"
                                        style={{ top: 31, height: 26, left: `${barLeft}%`, width: `${barWidth}%`, minWidth: 32, backgroundColor: accent, cursor: dragging ? 'grabbing' : 'grab', touchAction: 'none', boxShadow: '0 4px 12px -4px rgba(0,0,0,.4)', transition: dragging ? 'none' : 'left .2s, width .2s' }}>
                                        <span className="flex gap-0.5 flex-none"><i className="w-0.5 h-3 rounded bg-white/60" /><i className="w-0.5 h-3 rounded bg-white/60" /></span>
                                        <span className="font-mono text-[10px] font-semibold truncate">{fmtShort(startYmd)} → {fmtShort(comp)}</span>
                                    </div>
                                </div>

                                {/* controls */}
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3.5">
                                    {/* start */}
                                    <div className="rounded-xl border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-800 p-3">
                                        <div className="flex items-center justify-between mb-2">
                                            <span className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-slate-500">Start install</span>
                                            <DeltaChip n={startDelta} />
                                        </div>
                                        <div className="flex items-stretch border border-gray-300 dark:border-slate-600 rounded-lg overflow-hidden">
                                            <button onClick={() => nudgeStart(-1)} disabled={slotIndex <= 0} className="w-10 h-10 text-xl text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-700 disabled:text-gray-300 dark:disabled:text-slate-600 disabled:cursor-not-allowed">−</button>
                                            <div className="flex-1 grid place-items-center border-x border-gray-200 dark:border-slate-600 font-mono text-sm font-semibold text-gray-800 dark:text-slate-100 tabular-nums">{fmtLong(startYmd)}</div>
                                            <button onClick={() => nudgeStart(1)} disabled={slotIndex >= slots.length - 1} className="w-10 h-10 text-xl text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-700 disabled:text-gray-300 dark:disabled:text-slate-600 disabled:cursor-not-allowed">+</button>
                                        </div>
                                        <div className="mt-2 text-xs text-gray-500 dark:text-slate-400">Nudge ± {START_WINDOW_BIZ} work days, or drag the bar</div>
                                    </div>
                                    {/* crew */}
                                    <div className="rounded-xl border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-800 p-3">
                                        <div className="flex items-center justify-between mb-2">
                                            <span className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-slate-500">Crew</span>
                                            <DeltaChip n={crewDelta} />
                                        </div>
                                        <div className="flex items-stretch border border-gray-300 dark:border-slate-600 rounded-lg overflow-hidden">
                                            <button onClick={() => stepCrew(-1)} disabled={crew <= 1} className="w-10 h-10 text-xl text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-700 disabled:text-gray-300 dark:disabled:text-slate-600 disabled:cursor-not-allowed">−</button>
                                            <div className="flex-1 grid place-items-center border-x border-gray-200 dark:border-slate-600 font-mono text-lg font-semibold text-gray-800 dark:text-slate-100 tabular-nums">{crew}</div>
                                            <button onClick={() => stepCrew(1)} disabled={crew >= 8} className="w-10 h-10 text-xl text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-700 disabled:text-gray-300 dark:disabled:text-slate-600 disabled:cursor-not-allowed">+</button>
                                        </div>
                                        <div className="mt-2 text-xs text-gray-500 dark:text-slate-400"><b className="font-mono text-gray-800 dark:text-slate-200">{days || '—'}</b>-day install · {Number.isFinite(installHrs) ? installHrs : '—'} hrs</div>
                                    </div>
                                </div>

                                {/* date breakdown: ship → start → comp, with the gaps between them */}
                                <div className="mt-3.5 pt-3.5 border-t border-dashed border-gray-300 dark:border-slate-600">
                                    <DateFlow ship={fmtLong(ship)} start={fmtLong(startYmd)} comp={fmtLong(comp)} days={days} startAccent={startDelta !== 0} compAccent={netDelta !== 0} />
                                    <div className="flex items-center gap-3 mt-3">
                                        <DeltaChip n={netDelta} suffix={netDelta > 0 ? 'later' : netDelta < 0 ? 'sooner' : ''} />
                                        <span className="text-[12px] text-gray-500 dark:text-slate-400">
                                            {!dirty ? 'Matches the current plan.'
                                                : netDelta === 0 ? 'Same finish as the current plan.'
                                                    : `Finishes ${Math.abs(netDelta)} work ${Math.abs(netDelta) === 1 ? 'day' : 'days'} ${netDelta > 0 ? 'later' : 'sooner'} than the ${fmtShort(savedComp)} plan.`}
                                        </span>
                                        {dirty && (
                                            <div className="ml-auto flex gap-2">
                                                <button onClick={resetPreview} className="text-[12.5px] font-semibold px-3 py-1.5 rounded-lg border border-gray-300 dark:border-slate-600 text-gray-500 dark:text-slate-300 hover:text-gray-800 dark:hover:text-white">Reset</button>
                                                <button onClick={() => setConfirmOpen(true)} className="text-[12.5px] font-semibold px-3.5 py-1.5 rounded-lg text-white bg-accent-600 hover:bg-accent-700">Apply…</button>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </>
                        ) : (
                            <div className="text-[13px] text-gray-500 dark:text-slate-400 py-1">
                                This release has no hard install date to simulate. Set Start Install in the Job Log, then the crew and date dials appear here.
                                <dl className="grid grid-cols-3 gap-3 mt-3">
                                    <Field label="Ship (est)">{fmtFull(hardShip || release['Ship Date'])}</Field>
                                    <Field label="Start install">{fmtFull(release['Start install'])}</Field>
                                    <Field label="Comp. ETA">{fmtFull(release['comp_eta_effective'] || release['Comp. ETA'])}</Field>
                                </dl>
                            </div>
                        )}
                    </section>
                    )}

                    {/* facts */}
                    <section>
                        <dl className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-3">
                            <Field label="Stage">{stage ? <Badge tint="slate">{stage}</Badge> : '—'}</Field>
                            <Field label="Stage Group">{stageGroup}</Field>
                            <Field label="Installer">{installer}</Field>
                            <Field label="PM">{pm}</Field>
                            <Field label="By">{by}</Field>
                            <Field label="Install Hrs">{Number.isFinite(installHrs) ? installHrs : '—'}</Field>
                        </dl>
                        {notes && (
                            <div className="mt-4">
                                <dt className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-slate-500 mb-1">Notes</dt>
                                <p className="text-sm text-gray-700 dark:text-slate-300 whitespace-pre-wrap bg-gray-50 dark:bg-slate-700/50 rounded p-2.5 border-l-2 border-accent-500">{notes}</p>
                            </div>
                        )}
                    </section>

                    {error && <div className="text-xs text-red-600 dark:text-red-400">{error}</div>}

                    {/* to-dos */}
                    <section>
                        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-slate-400 mb-2">Active To-dos</h3>
                        {loading && todos.length === 0 ? <SectionSpinner /> : todos.length === 0 ? (
                            <p className="text-xs text-gray-400 dark:text-slate-500">No active to-dos.</p>
                        ) : (
                            <ul className="space-y-2">
                                {todos.map((t) => (
                                    <li key={t.id} className="rounded-lg border border-gray-100 dark:border-slate-600 bg-white dark:bg-slate-700/40 px-3 py-2">
                                        <div className="flex items-start justify-between gap-2">
                                            <span className="text-sm text-gray-800 dark:text-slate-200">{t.title}</span>
                                            <Badge tint={STATUS_TINT[t.status] || 'slate'} className="shrink-0">{t.status}</Badge>
                                        </div>
                                        <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-gray-500 dark:text-slate-400">
                                            <Badge tint={ITEM_TYPE_TINT[t.item_type] || 'slate'}>{t.item_type}</Badge>
                                            {t.owner_name && <span>👤 {t.owner_name}</span>}
                                            {t.due_date && <span>📅 {fmtFull(t.due_date)}</span>}
                                            {t.meeting_title && <span className="italic truncate">from “{t.meeting_title}”</span>}
                                        </div>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </section>

                    {/* meetings */}
                    <section>
                        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-slate-400 mb-2">Meeting Notes</h3>
                        {loading && meetings.length === 0 ? <SectionSpinner /> : meetings.length === 0 ? (
                            <p className="text-xs text-gray-400 dark:text-slate-500">No linked meetings.</p>
                        ) : (
                            <div className="space-y-3">
                                {meetings.map((m) => (
                                    <div key={m.id} className="rounded-lg border border-gray-100 dark:border-slate-600 bg-gray-50 dark:bg-slate-700/40 px-3 py-2">
                                        <div className="flex items-center justify-between gap-2 mb-1">
                                            <span className="text-sm font-medium text-gray-800 dark:text-slate-200 truncate">{m.title}</span>
                                            <span className="text-[11px] text-gray-400 dark:text-slate-500 shrink-0">{fmtFull(m.occurred_at)}</span>
                                        </div>
                                        {m.summary ? <p className="text-xs text-gray-600 dark:text-slate-300 whitespace-pre-wrap">{m.summary}</p> : <p className="text-xs text-gray-400 dark:text-slate-500 italic">No summary.</p>}
                                    </div>
                                ))}
                            </div>
                        )}
                    </section>

                    {/* drawings (photos live in the hero/filmstrip) */}
                    <section>
                        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-slate-400 mb-2">Drawings</h3>
                        {loading && drawings.length === 0 ? <SectionSpinner /> : drawings.length === 0 ? (
                            <p className="text-xs text-gray-400 dark:text-slate-500">No drawings.</p>
                        ) : (
                            <ul className="space-y-1">
                                {drawings.map((v) => (
                                    <li key={v.id}>
                                        <a href={`${API_BASE_URL}/brain/releases/${releaseId}/drawing/versions/${v.id}/file`} target="_blank" rel="noopener noreferrer"
                                            className="text-sm text-accent-600 dark:text-accent-400 hover:underline inline-flex items-center gap-2">
                                            📄 v{v.version_number} · {v.original_filename}
                                            <span className="text-[11px] text-gray-400 dark:text-slate-500">{fmtFull(v.uploaded_at)}</span>
                                        </a>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </section>
                </div>

                {/* footer */}
                <div className="bg-gray-50 dark:bg-slate-700 px-5 py-4 rounded-b-xl border-t border-gray-200 dark:border-slate-600 flex gap-3 shrink-0">
                    {(canMarkup || release.has_drawing) ? (
                        <button onClick={() => setDrawingHubOpen(true)} className="flex-1 px-4 py-2 bg-accent-600 text-white rounded-lg font-medium hover:bg-accent-700 text-center">Drawing</button>
                    ) : viewerUrl ? (
                        <a href={viewerUrl} target="_blank" rel="noopener noreferrer" className="flex-1 px-4 py-2 bg-accent-600 text-white rounded-lg font-medium hover:bg-accent-700 text-center">Drawing</a>
                    ) : (
                        <button disabled className="flex-1 px-4 py-2 bg-gray-300 dark:bg-slate-500 text-white rounded-lg font-medium cursor-not-allowed">Drawing</button>
                    )}
                    {procoreUrl ? (
                        <a href={procoreUrl} target="_blank" rel="noopener noreferrer" className="flex-1 px-4 py-2 bg-purple-600 text-white rounded-lg font-medium hover:bg-purple-700 text-center">Procore</a>
                    ) : (
                        <button disabled className="flex-1 px-4 py-2 bg-gray-300 dark:bg-slate-500 text-white rounded-lg font-medium cursor-not-allowed">Procore</button>
                    )}
                    {trelloUrl ? (
                        <a href={trelloUrl} target="_blank" rel="noopener noreferrer" className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 text-center">Trello</a>
                    ) : (
                        <button disabled className="flex-1 px-4 py-2 bg-gray-300 dark:bg-slate-500 text-white rounded-lg font-medium cursor-not-allowed">Trello</button>
                    )}
                </div>
            </div>

            {/* lightbox */}
            {lbOpen && photos.length > 0 && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/90 p-6" onClick={(e) => { e.stopPropagation(); setLbOpen(false); }}>
                    <button className="absolute top-4 right-5 w-10 h-10 rounded-full bg-white/15 border border-white/20 text-white text-lg" onClick={(e) => { e.stopPropagation(); setLbOpen(false); }} aria-label="Close photos">✕</button>
                    <div className="w-[min(880px,94vw)]" onClick={(e) => e.stopPropagation()}>
                        <div className="relative w-full rounded-xl overflow-hidden bg-slate-900" style={{ aspectRatio: '16 / 10' }}>
                            <img src={photoUrl(photos[lbIndex].id)} alt={photos[lbIndex].original_filename || ''} className="absolute inset-0 w-full h-full object-contain" />
                            {photos.length > 1 && <>
                                <button className="absolute left-3 top-1/2 -translate-y-1/2 w-11 h-11 rounded-full bg-white/15 border border-white/20 text-white text-xl" onClick={() => setLbIndex((lbIndex - 1 + photos.length) % photos.length)} aria-label="Previous">‹</button>
                                <button className="absolute right-3 top-1/2 -translate-y-1/2 w-11 h-11 rounded-full bg-white/15 border border-white/20 text-white text-xl" onClick={() => setLbIndex((lbIndex + 1) % photos.length)} aria-label="Next">›</button>
                            </>}
                        </div>
                        <div className="flex items-baseline gap-3 mt-3 text-white">
                            <span className="text-sm font-semibold truncate">{photos[lbIndex].note || photos[lbIndex].original_filename || `Photo ${lbIndex + 1}`}</span>
                            <span className="ml-auto font-mono text-xs text-white/60">{lbIndex + 1} / {photos.length}</span>
                        </div>
                    </div>
                </div>
            )}

            {/* Apply confirmation — summarizes the previewed changes before committing them to the
                on-screen plan. Still simulate-only: Confirm re-baselines the preview, it doesn't save. */}
            {confirmOpen && (
                <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/55 p-4" onClick={(e) => { e.stopPropagation(); setConfirmOpen(false); }}>
                    <div className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl max-w-md w-full p-6" onClick={(e) => e.stopPropagation()}>
                        <h3 className="text-lg font-bold text-black dark:text-white">Confirm schedule change</h3>
                        <p className="text-xs text-black dark:text-slate-200 mt-1.5 flex items-center gap-1.5">
                            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" /> Preview only — updates the on-screen plan, not saved to the release.
                        </p>

                        {crew !== savedCrew && (
                            <div className="flex items-center justify-between mt-5">
                                <span className="text-[11px] font-bold uppercase tracking-wide text-black dark:text-white">Crew</span>
                                <span className="font-mono text-base text-black dark:text-white tabular-nums">{savedCrew}<span className="mx-2">→</span><b>{crew}</b> guys</span>
                            </div>
                        )}

                        {/* Was / Now schedule comparison */}
                        <div className="mt-4 rounded-lg border border-gray-200 dark:border-slate-600 p-3.5">
                            <div className="grid gap-x-2 gap-y-2.5 items-center" style={{ gridTemplateColumns: 'auto 1fr 1fr 1fr' }}>
                                <div />
                                <div className="text-[10px] font-bold uppercase tracking-wide text-black dark:text-white text-center">Ship est</div>
                                <div className="text-[10px] font-bold uppercase tracking-wide text-black dark:text-white text-center">Start</div>
                                <div className="text-[10px] font-bold uppercase tracking-wide text-black dark:text-white text-center">Comp ETA</div>

                                <div className="text-[10px] font-bold uppercase tracking-wide text-black dark:text-white">Was</div>
                                <div className="font-mono text-[13px] text-black dark:text-white text-center tabular-nums">{fmtLong(shipEstimate(savedStart))}</div>
                                <div className="font-mono text-[13px] text-black dark:text-white text-center tabular-nums">{fmtLong(savedStart)}</div>
                                <div className="font-mono text-[13px] text-black dark:text-white text-center tabular-nums">{fmtLong(savedComp)}</div>

                                <div className="text-[10px] font-bold uppercase tracking-wide text-black dark:text-white">Now</div>
                                <div className="font-mono text-[13px] font-bold text-black dark:text-white text-center tabular-nums">{fmtLong(ship)}</div>
                                <div className="font-mono text-[13px] font-bold text-black dark:text-white text-center tabular-nums">{fmtLong(startYmd)}</div>
                                <div className="font-mono text-[13px] font-bold text-black dark:text-white text-center tabular-nums">{fmtLong(comp)}</div>

                                <div />
                                <div className="flex justify-center">{startDelta !== 0 && <DeltaChip n={startDelta} />}</div>
                                <div className="flex justify-center">{startDelta !== 0 && <DeltaChip n={startDelta} />}</div>
                                <div className="flex justify-center">{netDelta !== 0 && <DeltaChip n={netDelta} />}</div>
                            </div>
                        </div>

                        <div className="flex gap-2 mt-6">
                            <button onClick={() => setConfirmOpen(false)} className="flex-1 text-sm font-semibold px-4 py-2.5 rounded-lg border border-gray-300 dark:border-slate-600 text-black dark:text-white hover:bg-gray-50 dark:hover:bg-slate-700">Cancel</button>
                            <button onClick={() => { applyPreview(); setConfirmOpen(false); }} className="flex-1 text-sm font-semibold px-4 py-2.5 rounded-lg text-white bg-accent-600 hover:bg-accent-700">Confirm</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );

    return (
        <>
            {createPortal(modalContent, document.body)}
            <PdfVersionHistoryModal isOpen={drawingHubOpen} releaseId={releaseId} title={`${job}-${rel}`} viewerUrl={viewerUrl || ''}
                onClose={() => setDrawingHubOpen(false)}
                onOpenVersion={(vid, mode) => { setDrawingHubOpen(false); setMarkupVersionId(vid); setMarkupMode(canMarkup ? mode : 'view'); setMarkupOpen(true); }} />
            <PdfMarkupModal isOpen={markupOpen} releaseId={releaseId} versionId={markupVersionId} mode={markupMode} onClose={() => setMarkupOpen(false)} />
        </>
    );
}

export default ReleaseCockpitModal;
