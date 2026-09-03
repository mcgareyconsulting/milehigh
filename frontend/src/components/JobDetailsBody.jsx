/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Details pane of the release hub — "dossier split": Photos / Notes / Materials on the
 *   left, a condensed Schedule + Details column on the right, Active to-dos full-width beneath.
 * exports:
 *   JobDetailsBody: Detail sections only (no dialog chrome) for a host modal
 *   formatInstallProg: Job Comp → display string (whole number + %, X, or —)
 * imports_from: [react, ../services/jobsApi, ../constants/columnHeaders, ../constants/stages,
 *   ../constants/releaseTags, ../utils/api, ../utils/formatters, ../utils/scheduling,
 *   ../utils/stageTint, ../utils/asap, ../utils/imageCompress, ./StartInstallDateModal,
 *   ./shared/ConfirmDialog]
 * imported_by: [frontend/src/components/ReleaseHubModal.jsx]
 * invariants:
 *   - Owns its own material-orders, photos and checklist fetches when mounted; photo
 *     upload / note / delete are raw fetches against the photo routes
 *   - Reads display keys ('Ship Date') with raw-key fallback ('ship_date')
 *   - External links live in the host header; Activity rail and banana row are host-owned
 *   - Start install AND ship date are edited ONLY through StartInstallDateModal — the same
 *     dialog the Job Log row opens, so ASAP, Clear hard date and the ship/install Break-Link
 *     rules have exactly one implementation. Never a bare date input.
 *   - Writes (stage, start install, ship date, installer, billing tag, mark-received) go
 *     through existing jobsApi paths, so the server cascades and event rows are identical
 *     to a Job Log edit. Every write asks the host to refetch via onJobUpdate.
 *   - The release's Notes are NOT edited here — that is the Activity rail's job. The note
 *     under the hero belongs to the selected photo (PATCH .../photos/<id>).
 *   - To-dos are read-only here; the checklist's meeting notes are not rendered.
 * updated_by_agent: 2026-09-03T00:00:00Z
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';

import { jobsApi } from '../services/jobsApi';
import { HEADER_OVERRIDES } from '../constants/columnHeaders';
import { RELEASE_TAGS } from '../constants/releaseTags';
import { STAGE_OPTIONS } from '../constants/stages';
import { API_BASE_URL } from '../utils/api';
import { toYmd, subtractBusinessDays } from '../utils/formatters';
import { installDays } from '../utils/scheduling';
import { stageTint } from '../utils/stageTint';
import { setAsapAndAssign } from '../utils/asap';
import { compressImage } from '../utils/imageCompress';
import { StartInstallDateModal } from './StartInstallDateModal';
import { ConfirmDialog } from './shared/ConfirmDialog';

const labelFor = (key) => HEADER_OVERRIDES[key] || key;

// Date-only ("2026-06-15") formatter that avoids the UTC-midnight off-by-one
// a bare new Date(...) would introduce in negative-offset timezones.
const formatDate = (dateString) => {
    if (!dateString) return null;
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(dateString));
    const date = m
        ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
        : new Date(dateString);
    if (isNaN(date)) return String(dateString);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
};

/** Short form for the schedule column, where the row is narrow: "Fri, Sep 4". */
const formatDateShort = (dateString) => {
    if (!dateString) return null;
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(dateString));
    const date = m
        ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
        : new Date(dateString);
    if (isNaN(date)) return String(dateString);
    return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
};

/** Timestamp form for photo telemetry: "Aug 12, 2026 · 7:36 AM". */
const formatDateTime = (value) => {
    if (!value) return null;
    const d = new Date(value);
    if (isNaN(d)) return String(value);
    const date = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const time = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    return `${date} · ${time}`;
};

const formatTimeAgo = (dateString) => {
    if (!dateString) return null;
    try {
        const diffMinutes = Math.floor((new Date() - new Date(dateString)) / 60000);
        const diffHours = Math.floor(diffMinutes / 60);
        const diffDays = Math.floor(diffHours / 24);
        if (diffDays > 0) return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
        if (diffHours > 0) return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
        if (diffMinutes > 0) return `${diffMinutes} minute${diffMinutes !== 1 ? 's' : ''} ago`;
        return 'just now';
    } catch {
        return null;
    }
};

/**
 * Install Prog (Job Comp) display:
 *   blank / O → null (caller renders —)
 *   X → "X"
 *   whole number → "75%" (no decimal handling)
 */
export function formatInstallProg(raw) {
    if (raw == null || raw === false) return null;
    const s = String(raw).trim();
    if (!s || s.toUpperCase() === 'O') return null;
    if (s.toUpperCase() === 'X') return 'X';
    // Whole digits only — reject decimals / junk.
    if (/^\d+$/.test(s)) return `${s}%`;
    return s;
}

/** Uppercase section rule. Optional `action` sits on the right of the same line. */
function SectionLabel({ children, action = null, style = null }) {
    return (
        <div
            className="flex items-center justify-between gap-2 border-b border-hairline-strong"
            style={{ paddingBottom: 6, ...(style || {}) }}
        >
            <span className="text-jl-label font-bold uppercase text-ink-3 min-w-0">
                {children}
            </span>
            {action}
        </div>
    );
}

/**
 * One label/value line at job-log density. `onClick` turns the whole row into a
 * button (used by the two schedule dates, which open StartInstallDateModal).
 */
function Row({ label, value, mono = true, flag = null, onClick = null, title = null }) {
    const blank = value == null || value === '' || value === false;
    const interactive = typeof onClick === 'function';
    return (
        <div
            className={`flex items-center justify-between gap-3 border-b border-hairline ${
                interactive ? 'cursor-pointer hover:bg-surface-2 rounded-[5px]' : ''
            }`}
            style={{ padding: '6px 2px' }}
            onClick={onClick || undefined}
            role={interactive ? 'button' : undefined}
            tabIndex={interactive ? 0 : undefined}
            onKeyDown={interactive ? (e) => {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(); }
            } : undefined}
            title={title || undefined}
        >
            <span className="text-ink-2 shrink-0" style={{ fontSize: 13 }}>{label}</span>
            <span className="flex items-center gap-[7px] min-w-0">
                {flag}
                <span
                    className={`font-semibold text-right break-words ${mono ? 'font-mono' : ''} ${
                        blank ? 'text-ink-3' : 'text-ink'
                    }`}
                    style={{ fontSize: 13.5 }}
                >
                    {blank ? '—' : value}
                </span>
            </span>
        </div>
    );
}

/** A row whose value is a control (select), so the control owns the right edge. */
function ControlRow({ label, children, title = null }) {
    return (
        <div
            className="flex items-center justify-between gap-3 border-b border-hairline"
            style={{ padding: '6px 2px' }}
            title={title || undefined}
        >
            <span className="text-ink-2 shrink-0" style={{ fontSize: 13 }}>{label}</span>
            {children}
        </div>
    );
}

/** ASAP / HARD mini-flags beside a schedule date, reusing the table's flag tints. */
function MiniFlag({ kind }) {
    const cls = kind === 'ASAP' ? 'jl-flag-red' : 'jl-flag-green';
    return (
        <span
            className={`${cls} font-bold uppercase shrink-0`}
            style={{ fontSize: 10.5, letterSpacing: '.05em', padding: '2px 6px', borderRadius: 4, lineHeight: 1.25 }}
        >
            {kind}
        </span>
    );
}

// To-do pill palettes (bg / fg / ring). Kept literal rather than tokenised: these
// are the checklist vocabulary's own colors, not part of the job-log stage scale.
const STATUS_PILL = {
    done: { bg: '#d1fae5', fg: '#065f46', ring: '#a7f3d0' },
    accepted: { bg: '#fef3c7', fg: '#b45309', ring: '#fde68a' },
};
const TYPE_PILL = {
    needs_gc_update: { bg: '#fffbeb', fg: '#b45309', ring: '#fde68a' },
    risk: { bg: '#fef2f2', fg: '#b91c1c', ring: '#fecaca' },
    action: { bg: '#eff6ff', fg: '#1e40af', ring: '#bfdbfe' },
    decision: { bg: '#f5f3ff', fg: '#5b21b6', ring: '#ddd6fe' },
    fyi: { bg: '#f8fafc', fg: '#475569', ring: '#e2e8f0' },
};
const SLATE_PILL = { bg: '#f8fafc', fg: '#475569', ring: '#e2e8f0' };

function Pill({ palette, children, minWidth = null }) {
    return (
        <span
            className="inline-block font-semibold text-center"
            style={{
                minWidth: minWidth || undefined,
                padding: '4px 12px',
                borderRadius: 999,
                fontSize: 12.5,
                background: palette.bg,
                color: palette.fg,
                boxShadow: `inset 0 0 0 1px ${palette.ring}`,
                whiteSpace: 'nowrap',
            }}
        >
            {children}
        </span>
    );
}

export function JobDetailsBody({
    job,
    releaseId = null,
    scrollToMaterials = false,
    onOrdersChanged = null,
    /** Ask the host to refetch the release row after a write lands. */
    onJobUpdate = null,
    /** Stage changed here — lets the host header pill + banana row follow. */
    onStageChange = null,
}) {
    const [materialOrders, setMaterialOrders] = useState([]);
    const [ordersLoading, setOrdersLoading] = useState(false);
    const [markAllBusy, setMarkAllBusy] = useState(false);
    const materialsRef = useRef(null);
    const [releaseTag, setReleaseTag] = useState(() => job?.release_tag || '');
    const [tagSaving, setTagSaving] = useState(false);
    const [tagError, setTagError] = useState(null);

    const [photos, setPhotos] = useState([]);
    const [photosLoading, setPhotosLoading] = useState(false);
    const [photoBusy, setPhotoBusy] = useState(false);
    const [heroId, setHeroId] = useState(null);
    const photoInputRef = useRef(null);
    const cameraInputRef = useRef(null);

    const [todos, setTodos] = useState([]);
    const [todosLoading, setTodosLoading] = useState(false);

    // Note editor for the photo currently in the hero (not the release's Notes,
    // which live on the Activity rail).
    const [noteEditing, setNoteEditing] = useState(false);
    const [noteDraft, setNoteDraft] = useState('');
    const [noteSaving, setNoteSaving] = useState(false);
    // id of the photo awaiting confirmation, and whether its delete is in flight
    const [pendingDeleteId, setPendingDeleteId] = useState(null);
    const [deleteBusy, setDeleteBusy] = useState(false);

    const [installerOptions, setInstallerOptions] = useState([]);
    const [savingField, setSavingField] = useState(null);   // 'stage' | 'installer' | null
    const [writeError, setWriteError] = useState(null);
    const [startInstallOpen, setStartInstallOpen] = useState(false);

    const jobId = job ? (job['Job #'] || job.job) : null;
    const relId = job ? (job['Release #'] || job.release) : null;
    const relPk = releaseId ?? job?.id ?? null;

    // Display key first, raw key second — Job Log rows carry the former, some
    // Timeline/API paths only the latter.
    const pick = useCallback((displayKey, rawKey) => {
        if (!job) return null;
        const v = job[displayKey];
        return v == null || v === '' ? job[rawKey] : v;
    }, [job]);

    // Optimistic mirrors of the fields this pane writes, so the UI settles before
    // the host's refetch comes back (and stays right if the host never refetches).
    const rowStage = pick('Stage', 'stage') || '';
    const rowStartInstall = pick('Start install', 'start_install');
    const rowShipDate = pick('Ship Date', 'ship_date');
    const [localStage, setLocalStage] = useState(rowStage);
    const [localInstaller, setLocalInstaller] = useState(job?.installer || '');
    const [localStartInstall, setLocalStartInstall] = useState(rowStartInstall);
    const [localShipDate, setLocalShipDate] = useState(rowShipDate);

    useEffect(() => { setLocalStage(rowStage); }, [rowStage]);
    useEffect(() => { setLocalInstaller(job?.installer || ''); }, [job?.installer]);
    useEffect(() => { setLocalStartInstall(rowStartInstall); }, [rowStartInstall]);
    useEffect(() => { setLocalShipDate(rowShipDate); }, [rowShipDate]);

    useEffect(() => {
        setReleaseTag(job?.release_tag || '');
        setTagError(null);
    }, [job?.id, job?.release_tag, jobId, relId]);

    useEffect(() => {
        if (jobId == null) return;
        let cancelled = false;
        setOrdersLoading(true);
        jobsApi.getMaterialOrders(jobId, relId)
            .then((data) => { if (!cancelled) setMaterialOrders(data?.orders || []); })
            .catch(() => { if (!cancelled) setMaterialOrders([]); })
            .finally(() => { if (!cancelled) setOrdersLoading(false); });
        return () => { cancelled = true; };
    }, [jobId, relId]);

    const loadPhotos = useCallback(async () => {
        if (relPk == null) return;
        setPhotosLoading(true);
        try {
            const list = await jobsApi.getReleasePhotos(relPk);
            setPhotos(list);
            setHeroId((prev) => (prev && list.some((p) => p.id === prev) ? prev : (list[0]?.id ?? null)));
        } catch {
            setPhotos([]);
        } finally {
            setPhotosLoading(false);
        }
    }, [relPk]);

    useEffect(() => {
        setHeroId(null);
        loadPhotos();
    }, [loadPhotos]);

    useEffect(() => {
        if (relPk == null) { setTodos([]); return undefined; }
        let cancelled = false;
        setTodosLoading(true);
        jobsApi.getReleaseChecklist(relPk)
            // Meeting notes are deliberately dropped from this modal — to-dos only.
            .then((data) => { if (!cancelled) setTodos(data?.todos || []); })
            .catch(() => { if (!cancelled) setTodos([]); })
            .finally(() => { if (!cancelled) setTodosLoading(false); });
        return () => { cancelled = true; };
    }, [relPk]);

    useEffect(() => {
        let cancelled = false;
        jobsApi.getInstallerTeams()
            .then((teams) => { if (!cancelled) setInstallerOptions(teams || []); })
            .catch(() => { if (!cancelled) setInstallerOptions([]); });
        return () => { cancelled = true; };
    }, []);

    // When opened from a material-order chip, bring the Materials section into
    // view once its data has settled.
    useEffect(() => {
        if (!scrollToMaterials || ordersLoading) return;
        const el = materialsRef.current;
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, [scrollToMaterials, ordersLoading]);

    const handleToggleReceived = async (order) => {
        const next = order.status !== 'received';
        try {
            const data = await jobsApi.markMaterialOrderReceived(order.id, next);
            setMaterialOrders((prev) =>
                prev.map((o) => (o.id === order.id ? (data?.order || o) : o))
            );
            if (onOrdersChanged) onOrdersChanged();
        } catch {
            // Leave the row unchanged (e.g. insufficient permissions).
        }
    };

    // Itemized orders only (not galvanizing/stock shipping_status rows).
    const pendingReceivable = materialOrders.filter(
        (o) => !o.shipping_status && o.status !== 'received'
    );

    const handleMarkAllReceived = async () => {
        if (!pendingReceivable.length || markAllBusy) return;
        setMarkAllBusy(true);
        try {
            const results = await Promise.all(
                pendingReceivable.map((o) =>
                    jobsApi.markMaterialOrderReceived(o.id, true)
                        .then((data) => ({ id: o.id, order: data?.order || { ...o, status: 'received' } }))
                        .catch(() => null)
                )
            );
            const byId = new Map(
                results.filter(Boolean).map((r) => [r.id, r.order])
            );
            if (byId.size > 0) {
                setMaterialOrders((prev) =>
                    prev.map((o) => (byId.has(o.id) ? byId.get(o.id) : o))
                );
                if (onOrdersChanged) onOrdersChanged();
            }
        } finally {
            setMarkAllBusy(false);
        }
    };

    const handleReleaseTagChange = async (next) => {
        if (!jobId || relId == null) return;
        const prev = releaseTag;
        setReleaseTag(next);
        setTagSaving(true);
        setTagError(null);
        try {
            await jobsApi.updateJobFields(jobId, relId, { release_tag: next || null });
            if (job) job.release_tag = next || null;
        } catch (err) {
            setReleaseTag(prev);
            setTagError(err.message || 'Could not update billing tag');
        } finally {
            setTagSaving(false);
        }
    };

    const handleStageChange = async (next) => {
        if (!jobId || relId == null || next === localStage) return;
        const prev = localStage;
        setLocalStage(next);            // optimistic
        onStageChange?.(next);
        setSavingField('stage');
        setWriteError(null);
        try {
            await jobsApi.updateStage(jobId, relId, next);
            onJobUpdate?.();
        } catch (err) {
            setLocalStage(prev);
            onStageChange?.(prev);
            setWriteError(err.message || 'Could not update stage');
        } finally {
            setSavingField(null);
        }
    };

    const handleInstallerChange = async (next) => {
        if (!jobId || relId == null || next === localInstaller) return;
        const prev = localInstaller;
        setLocalInstaller(next);        // optimistic
        setSavingField('installer');
        setWriteError(null);
        try {
            // Null date = installer-only change; the endpoint leaves the date alone.
            await jobsApi.updateStartInstall(jobId, relId, null, next);
            onJobUpdate?.();
        } catch (err) {
            setLocalInstaller(prev);
            setWriteError(err.message || 'Could not update installer');
        } finally {
            setSavingField(null);
        }
    };

    const uploadPhoto = async (file) => {
        if (!file || relPk == null) return;
        setPhotoBusy(true);
        setWriteError(null);
        try {
            // Shrink phone-camera shots before they hit LTE; see utils/imageCompress.js.
            const payload = await compressImage(file);
            const fd = new FormData();
            fd.append('file', payload);
            // Stamp the stage the release was in when the shot was taken, so a
            // photo carries its own point in the build, not just a date. The
            // route rejects anything that isn't a real stage name.
            if (localStage) fd.append('stage', localStage);
            const resp = await fetch(`${API_BASE_URL}/brain/releases/${relPk}/photos`, {
                method: 'POST',
                body: fd,
                credentials: 'include',
            });
            if (!resp.ok) {
                const body = await resp.text();
                throw new Error(`Photo upload failed (${resp.status}): ${body.slice(0, 200)}`);
            }
            await loadPhotos();
        } catch (err) {
            setWriteError(err?.message || 'Photo upload failed');
        } finally {
            setPhotoBusy(false);
        }
    };

    const savePhotoNote = async (photoId) => {
        if (photoId == null || relPk == null) return;
        setNoteSaving(true);
        setWriteError(null);
        try {
            const resp = await fetch(`${API_BASE_URL}/brain/releases/${relPk}/photos/${photoId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ note: noteDraft }),
                credentials: 'include',
            });
            if (!resp.ok) throw new Error(`Could not save the note (${resp.status})`);
            const updated = await resp.json();
            setPhotos((prev) => prev.map((p) => (p.id === photoId ? updated : p)));
            setNoteEditing(false);
        } catch (err) {
            setWriteError(err?.message || 'Could not save the note');
        } finally {
            setNoteSaving(false);
        }
    };

    const deletePhoto = async (photoId) => {
        if (photoId == null || relPk == null) return;
        setWriteError(null);
        setDeleteBusy(true);
        try {
            const resp = await fetch(`${API_BASE_URL}/brain/releases/${relPk}/photos/${photoId}`, {
                method: 'DELETE',
                credentials: 'include',
            });
            if (!resp.ok) throw new Error(`Delete failed (${resp.status})`);
            // Soft delete server-side; drop it here and fall through to the next
            // photo so the hero never lands on a removed row.
            setNoteEditing(false);
            setPhotos((prev) => {
                const next = prev.filter((p) => p.id !== photoId);
                setHeroId(next[0]?.id ?? null);
                return next;
            });
        } catch (err) {
            setWriteError(err?.message || 'Failed to delete photo');
        } finally {
            setDeleteBusy(false);
            setPendingDeleteId(null);
        }
    };

    // ── Start install / ship date — one dialog, the Job Log row's ─────────────
    // Every branch mirrors JobsTableRow's handlers so ASAP, Clear hard date and
    // the ship/install Break-Link rules behave identically from either surface.
    const handleStartInstallSave = async (dateValue, installer) => {
        const prevDate = localStartInstall;
        if (dateValue) setLocalStartInstall(dateValue);
        if (installer !== undefined) setLocalInstaller(installer || '');
        setStartInstallOpen(false);
        setWriteError(null);
        try {
            await jobsApi.updateStartInstall(jobId, relId, dateValue, installer);
            onJobUpdate?.();
        } catch (err) {
            setLocalStartInstall(prevDate);
            setWriteError(err.message || 'Could not update start install');
        }
    };

    const handleShipDateSave = async (shipDate) => {
        const prev = localShipDate;
        setLocalShipDate(shipDate);
        setWriteError(null);
        try {
            await jobsApi.updateShipDate(jobId, relId, shipDate);
            onJobUpdate?.();
        } catch (err) {
            setLocalShipDate(prev);
            setWriteError(err.message || 'Could not update ship date');
        }
    };

    const handleClearHardDate = async () => {
        const prevDate = localStartInstall;
        const prevShip = localShipDate;
        // Clearing the hard date also drops the tied ship date.
        setLocalStartInstall(null);
        setLocalShipDate(null);
        setStartInstallOpen(false);
        setWriteError(null);
        try {
            await jobsApi.clearStartInstallHardDate(jobId, relId);
            onJobUpdate?.();
        } catch (err) {
            setLocalStartInstall(prevDate);
            setLocalShipDate(prevShip);
            setWriteError(err.message || 'Could not clear hard date');
        }
    };

    const handleSetAsap = async (installer) => {
        setStartInstallOpen(false);
        setWriteError(null);
        try {
            const ok = await setAsapAndAssign(jobId, relId, installer);
            if (ok) onJobUpdate?.();
        } catch (err) {
            setWriteError(err.message || 'Could not set ASAP');
        }
    };

    const handleClearAsap = async () => {
        setStartInstallOpen(false);
        setWriteError(null);
        try {
            await jobsApi.setStartInstallAsap(jobId, relId, false);
            onJobUpdate?.();
        } catch (err) {
            setWriteError(err.message || 'Could not clear ASAP');
        }
    };

    if (!job) return null;

    const lastUpdatedAt = pick('Last Updated At', 'last_updated_at');
    const sourceOfUpdate = pick('Source Of Update', 'source_of_update');
    const isAsap = job.start_install_asap === true;
    // A hard date is an explicit commitment rather than a formula result — the
    // same test the Job Log's Start install cell uses to paint its green flag.
    const isHardDate = !isAsap
        && job.start_install_no_color !== true
        && job.start_install_formulaTF === false
        && Boolean(localStartInstall);
    const startInstallDisplay = isAsap ? 'ASAP' : formatDate(localStartInstall);
    const startFlag = isAsap
        ? <MiniFlag kind="ASAP" />
        : (isHardDate ? <MiniFlag kind="HARD" /> : null);

    // Ship rides one business day ahead of install unless a date was set outright.
    const startYmd = toYmd(localStartInstall);
    const shipEffective = localShipDate || (startYmd ? subtractBusinessDays(startYmd, 1) : null);

    const tint = stageTint(localStage);
    const installProg = formatInstallProg(pick('Job Comp', 'job_comp'));
    const installHrs = pick('Install HRS', 'install_hrs');
    const numGuys = job.num_guys;
    const workDays = installHrs ? installDays(installHrs, numGuys) : null;
    const scheduleFootnote = workDays
        ? `${workDays} work days · ${installHrs} hrs · crew of ${numGuys || 2}`
        : null;

    const heroPhoto = photos.find((p) => p.id === heroId) || photos[0] || null;
    const photoUrl = (pid) => `${API_BASE_URL}/brain/releases/${relPk}/photos/${pid}/file`;

    const controlCls = 'font-semibold text-right text-ink bg-transparent border border-hairline-strong rounded-md';
    const controlStyle = { fontSize: 13.5, padding: '3px 8px', minWidth: 140 };

    return (
        <div>
            {writeError && (
                <p
                    className="text-jl-2"
                    style={{ color: 'var(--fl-red-bg)', marginBottom: 10 }}
                    role="alert"
                >
                    {writeError}
                </p>
            )}

            {/* ── Dossier split: photos/notes/materials | schedule/details ─── */}
            <div className="grid" style={{ gridTemplateColumns: '1.25fr 1fr', columnGap: 24 }}>
                {/* LEFT ─────────────────────────────────────────────────── */}
                <div className="min-w-0">
                    <SectionLabel
                        action={relPk != null ? (
                            <div className="flex items-center gap-1.5 shrink-0">
                                <button
                                    type="button"
                                    onClick={() => photoInputRef.current?.click()}
                                    disabled={photoBusy}
                                    className="font-semibold border-0 cursor-pointer disabled:opacity-50"
                                    style={{
                                        fontSize: 11.5,
                                        padding: '4px 10px',
                                        borderRadius: 999,
                                        background: 'var(--accent-soft)',
                                        color: 'var(--accent)',
                                    }}
                                >
                                    {photoBusy ? 'Uploading…' : '+ Upload photo'}
                                </button>
                                <button
                                    type="button"
                                    onClick={() => cameraInputRef.current?.click()}
                                    disabled={photoBusy}
                                    className="font-semibold border border-hairline-strong bg-surface text-ink-2 cursor-pointer disabled:opacity-50"
                                    style={{ fontSize: 11.5, padding: '4px 10px', borderRadius: 999 }}
                                >
                                    📷 Take
                                </button>
                                <input
                                    ref={photoInputRef}
                                    type="file"
                                    accept="image/*"
                                    className="hidden"
                                    onChange={async (e) => {
                                        const file = e.target.files?.[0];
                                        if (file) await uploadPhoto(file);
                                        if (photoInputRef.current) photoInputRef.current.value = '';
                                    }}
                                />
                                <input
                                    ref={cameraInputRef}
                                    type="file"
                                    accept="image/*"
                                    capture="environment"
                                    className="hidden"
                                    onChange={async (e) => {
                                        const file = e.target.files?.[0];
                                        if (file) await uploadPhoto(file);
                                        if (cameraInputRef.current) cameraInputRef.current.value = '';
                                    }}
                                />
                            </div>
                        ) : null}
                    >
                        Photos{photos.length > 0 ? ` · ${photos.length}` : ''}
                    </SectionLabel>

                    <div style={{ marginTop: 10, marginBottom: 18 }}>
                        {photosLoading && photos.length === 0 ? (
                            <p className="text-jl-2 text-ink-3 italic">Loading…</p>
                        ) : !heroPhoto ? (
                            <div
                                className="grid place-items-center border border-hairline bg-surface-2 text-ink-3 text-jl-2 italic"
                                style={{ height: 230, borderRadius: 10 }}
                            >
                                No photos yet.
                            </div>
                        ) : (
                            <>
                                <a
                                    href={photoUrl(heroPhoto.id)}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="block border border-hairline overflow-hidden"
                                    style={{ borderRadius: 10 }}
                                    title={heroPhoto.note || heroPhoto.original_filename || 'photo'}
                                >
                                    <img
                                        src={photoUrl(heroPhoto.id)}
                                        alt={heroPhoto.original_filename || 'Release photo'}
                                        className="w-full"
                                        style={{ height: 230, objectFit: 'cover', display: 'block' }}
                                    />
                                </a>
                                {photos.length > 1 && (
                                    <div
                                        className="flex overflow-x-auto"
                                        style={{ gap: 8, marginTop: 8, paddingBottom: 2 }}
                                    >
                                        {photos.map((p) => (
                                            <button
                                                key={p.id}
                                                type="button"
                                                onClick={() => { setHeroId(p.id); setNoteEditing(false); }}
                                                className="shrink-0 overflow-hidden bg-surface-2 p-0 cursor-pointer"
                                                style={{
                                                    width: 88,
                                                    height: 60,
                                                    borderRadius: 6,
                                                    border: p.id === heroPhoto.id
                                                        ? '2px solid var(--accent)'
                                                        : '1px solid var(--border)',
                                                }}
                                                title={[
                                                    p.note || p.original_filename || 'photo',
                                                    p.stage || null,
                                                    p.uploaded_at ? formatDateTime(p.uploaded_at) : null,
                                                ].filter(Boolean).join(' · ')}
                                                aria-label="Show this photo"
                                            >
                                                <img
                                                    src={photoUrl(p.id)}
                                                    alt=""
                                                    loading="lazy"
                                                    className="w-full h-full"
                                                    style={{ objectFit: 'cover', display: 'block' }}
                                                />
                                            </button>
                                        ))}
                                    </div>
                                )}

                                {/* Provenance for the selected photo: when it was
                                    taken and what stage the release was in. */}
                                <div
                                    className="flex items-center flex-wrap text-ink-3"
                                    style={{ gap: 8, marginTop: 10, fontSize: 11.5 }}
                                >
                                    {heroPhoto.stage && (
                                        <span
                                            className="inline-block font-semibold"
                                            style={{
                                                padding: '2px 8px',
                                                borderRadius: 999,
                                                fontSize: 11,
                                                background: stageTint(heroPhoto.stage).bg,
                                                color: stageTint(heroPhoto.stage).fg,
                                            }}
                                            title={`Uploaded while the release was at ${heroPhoto.stage}`}
                                        >
                                            {heroPhoto.stage}
                                        </span>
                                    )}
                                    <span>
                                        {[
                                            heroPhoto.uploaded_at
                                                ? `Uploaded ${formatDateTime(heroPhoto.uploaded_at)}`
                                                : null,
                                            heroPhoto.uploaded_by?.name || null,
                                        ].filter(Boolean).join(' · ') || 'Upload details unavailable'}
                                    </span>
                                    {heroPhoto.last_edited_at && (
                                        <span className="italic">
                                            note edited {formatDateTime(heroPhoto.last_edited_at)}
                                            {heroPhoto.last_edited_by?.name ? ` by ${heroPhoto.last_edited_by.name}` : ''}
                                        </span>
                                    )}
                                </div>

                                {/* The selected photo's own note. The release's
                                    Notes live on the Activity rail, not here. */}
                                <div style={{ marginTop: 8 }}>
                                    {noteEditing ? (
                                        <div>
                                            <textarea
                                                value={noteDraft}
                                                onChange={(e) => setNoteDraft(e.target.value)}
                                                rows={2}
                                                autoFocus
                                                className="w-full border border-hairline-strong bg-surface text-ink rounded-md resize-y"
                                                style={{ fontSize: 13, padding: '7px 9px' }}
                                                placeholder="What does this photo show?"
                                            />
                                            <div className="flex items-center gap-2" style={{ marginTop: 6 }}>
                                                <button
                                                    type="button"
                                                    onClick={() => savePhotoNote(heroPhoto.id)}
                                                    disabled={noteSaving}
                                                    className="font-semibold border-0 cursor-pointer disabled:opacity-50"
                                                    style={{
                                                        fontSize: 12.5,
                                                        padding: '5px 12px',
                                                        borderRadius: 7,
                                                        background: 'var(--accent)',
                                                        color: 'var(--accent-ink)',
                                                    }}
                                                >
                                                    {noteSaving ? 'Saving…' : 'Save note'}
                                                </button>
                                                <button
                                                    type="button"
                                                    onClick={() => setNoteEditing(false)}
                                                    className="font-semibold border border-hairline-strong bg-surface text-ink-2 cursor-pointer"
                                                    style={{ fontSize: 12.5, padding: '5px 12px', borderRadius: 7 }}
                                                >
                                                    Cancel
                                                </button>
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="flex items-start justify-between gap-3">
                                            <p
                                                className={`min-w-0 break-words ${heroPhoto.note ? 'text-ink-2' : 'text-ink-3 italic'}`}
                                                style={{ fontSize: 13 }}
                                            >
                                                {heroPhoto.note || 'No note on this photo.'}
                                            </p>
                                            <span className="flex items-center shrink-0" style={{ gap: 10 }}>
                                                <button
                                                    type="button"
                                                    onClick={() => {
                                                        setNoteDraft(heroPhoto.note || '');
                                                        setNoteEditing(true);
                                                    }}
                                                    className="text-brand font-semibold bg-transparent border-0 cursor-pointer"
                                                    style={{ fontSize: 12.5 }}
                                                >
                                                    {heroPhoto.note ? 'Edit note' : '+ Add note'}
                                                </button>
                                                <span aria-hidden className="text-ink-3" style={{ opacity: .5 }}>·</span>
                                                {/* Named in full, and the only red thing in the
                                                    column, so it never reads as a peer of the
                                                    note action sitting next to it. */}
                                                <button
                                                    type="button"
                                                    onClick={() => setPendingDeleteId(heroPhoto.id)}
                                                    className="font-semibold bg-transparent border-0 cursor-pointer inline-flex items-center"
                                                    style={{ fontSize: 12.5, gap: 5, color: 'var(--fl-red-bg)' }}
                                                    title="Delete this photo"
                                                >
                                                    <svg
                                                        width="12" height="12" viewBox="0 0 24 24" fill="none"
                                                        stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"
                                                        strokeLinejoin="round" aria-hidden="true"
                                                    >
                                                        <path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14M10 11v6M14 11v6" />
                                                    </svg>
                                                    Delete photo
                                                </button>
                                            </span>
                                        </div>
                                    )}
                                </div>
                            </>
                        )}
                    </div>

                    <div ref={materialsRef}>
                        <SectionLabel
                            action={pendingReceivable.length > 0 ? (
                                <button
                                    type="button"
                                    onClick={handleMarkAllReceived}
                                    disabled={markAllBusy}
                                    className="text-brand font-semibold bg-transparent border-0 cursor-pointer disabled:opacity-50 shrink-0"
                                    style={{ fontSize: 12.5 }}
                                >
                                    {markAllBusy ? 'Marking…' : 'Mark all received'}
                                </button>
                            ) : null}
                        >
                            Materials ordered
                        </SectionLabel>
                        {ordersLoading ? (
                            <p className="text-jl-2 text-ink-3 italic" style={{ padding: '6px 2px' }}>Loading…</p>
                        ) : materialOrders.length === 0 ? (
                            <p className="text-jl-2 text-ink-3 italic" style={{ padding: '6px 2px' }}>None ordered.</p>
                        ) : (
                            materialOrders.map((o) => {
                                const isStatusOrder = Boolean(o.shipping_status);
                                const received = o.status === 'received';
                                const complete = o.shipping_status === 'complete';
                                const badgeLabel = isStatusOrder
                                    ? (complete ? 'Complete' : 'Planning')
                                    : (received ? 'Received' : 'Ordered');
                                const done = isStatusOrder ? complete : received;
                                const pillColors = done
                                    ? { bg: 'var(--st-green-bg)', fg: 'var(--st-green-fg)' }
                                    : { bg: 'var(--st-amber-bg)', fg: 'var(--st-amber-fg)' };
                                const meta = [o.supplier, o.po_number ? `PO ${o.po_number}` : null]
                                    .filter(Boolean).join(' · ');
                                return (
                                    <div key={o.id} className="border-b border-hairline" style={{ padding: '6px 2px' }}>
                                        <div className="flex items-center justify-between gap-3">
                                            <span className="text-ink-2 min-w-0 truncate" style={{ fontSize: 13 }}>
                                                {o.quantity != null ? `(${o.quantity}) ` : ''}{o.description}
                                            </span>
                                            <span className="flex items-center gap-2 shrink-0">
                                                {!isStatusOrder && (
                                                    <button
                                                        onClick={() => handleToggleReceived(o)}
                                                        className="text-jl-2 text-brand hover:underline"
                                                    >
                                                        {received ? 'Mark ordered' : 'Mark received'}
                                                    </button>
                                                )}
                                                <span
                                                    className="inline-block font-semibold"
                                                    style={{
                                                        padding: '2px 8px',
                                                        borderRadius: 5,
                                                        fontSize: 12.5,
                                                        background: pillColors.bg,
                                                        color: pillColors.fg,
                                                    }}
                                                >
                                                    {badgeLabel}
                                                </span>
                                            </span>
                                        </div>
                                        {(meta || o.ordered_by || o.ordered_at) && (
                                            <p className="text-jl-2 text-ink-3 mt-0.5">
                                                {[meta, o.ordered_by ? `Ordered by ${o.ordered_by}` : null,
                                                    o.ordered_at ? formatDate(o.ordered_at) : null]
                                                    .filter(Boolean).join(' · ')}
                                            </p>
                                        )}
                                    </div>
                                );
                            })
                        )}
                    </div>
                </div>

                {/* RIGHT ────────────────────────────────────────────────── */}
                <div className="min-w-0">
                    <SectionLabel>Schedule</SectionLabel>
                    <Row label="Released" value={formatDate(pick('Released', 'released'))} />
                    <Row
                        label="Ship Date (est)"
                        value={formatDateShort(shipEffective)}
                        onClick={() => setStartInstallOpen(true)}
                        title="Edit ship / start install — same dialog as the Job Log row"
                    />
                    <Row
                        label="Start Install"
                        value={startInstallDisplay}
                        flag={startFlag}
                        onClick={() => setStartInstallOpen(true)}
                        title="Edit start install — ASAP, hard date and ship link"
                    />
                    <Row
                        label="Comp. ETA"
                        value={formatDateShort(pick('Comp. ETA', 'comp_eta') || job.comp_eta_effective)}
                    />
                    <Row label="Install Prog" value={installProg} />
                    {scheduleFootnote && (
                        <p className="text-ink-3" style={{ fontSize: 11.5, marginTop: 6 }}>
                            {scheduleFootnote}
                        </p>
                    )}

                    <SectionLabel style={{ marginTop: 18 }}>Details</SectionLabel>
                    <Row
                        label="PM / By"
                        value={[pick('PM', 'pm'), pick('BY', 'by')].filter(Boolean).join(' · ')}
                        mono={false}
                    />
                    <ControlRow label="Installer">
                        <select
                            value={localInstaller || ''}
                            onChange={(e) => handleInstallerChange(e.target.value)}
                            disabled={savingField === 'installer'}
                            className={controlCls}
                            style={controlStyle}
                            aria-label="Installer"
                        >
                            <option value="">— unassigned —</option>
                            {/* Keep a legacy/free-text installer selectable even when it is
                                not (or no longer) an installer-team row. */}
                            {localInstaller && !installerOptions.some((t) => (t.name || t) === localInstaller) && (
                                <option value={localInstaller}>{localInstaller}</option>
                            )}
                            {installerOptions.map((t) => {
                                const name = t.name || t;
                                return <option key={t.id ?? name} value={name}>{name}</option>;
                            })}
                        </select>
                    </ControlRow>
                    <Row
                        label="Crew · Install Hrs"
                        value={[numGuys, installHrs].filter((v) => v != null && v !== '').join(' · ')}
                    />
                    <ControlRow label={labelFor('Stage')}>
                        <select
                            value={localStage || ''}
                            onChange={(e) => handleStageChange(e.target.value)}
                            disabled={savingField === 'stage'}
                            className="font-semibold rounded-md border"
                            style={{
                                ...controlStyle,
                                background: tint.bg,
                                color: tint.fg,
                                borderColor: 'var(--border-strong)',
                            }}
                            aria-label="Stage"
                        >
                            {/* A stage the option list doesn't carry (legacy rows) still shows. */}
                            {localStage && !STAGE_OPTIONS.some((o) => o.value === localStage) && (
                                <option value={localStage}>{localStage}</option>
                            )}
                            {STAGE_OPTIONS.map((o) => (
                                <option key={o.value} value={o.value}>{o.label}</option>
                            ))}
                        </select>
                    </ControlRow>
                    <ControlRow
                        label="Billing tag"
                        title="Contracted / Change Order / MHMW Cost — not shown on the job log row"
                    >
                        <select
                            value={releaseTag || ''}
                            onChange={(e) => handleReleaseTagChange(e.target.value)}
                            disabled={tagSaving}
                            className={controlCls}
                            style={controlStyle}
                            aria-label="Billing tag"
                        >
                            <option value="">— unset —</option>
                            {RELEASE_TAGS.map((t) => (
                                <option key={t.value} value={t.value}>{t.label}</option>
                            ))}
                        </select>
                    </ControlRow>
                    {tagError && (
                        <p className="text-jl-2" style={{ color: 'var(--fl-red-bg)', padding: '4px 2px' }}>{tagError}</p>
                    )}
                    <Row label={labelFor('Fab Order')} value={pick('Fab Order', 'fab_order')} />
                    <Row label={labelFor('Fab Hrs')} value={pick('Fab Hrs', 'fab_hrs')} />
                    <Row label={labelFor('Invoiced')} value={pick('Invoiced', 'invoiced')} />
                    <Row label={labelFor('Paint color')} value={pick('Paint color', 'paint_color')} mono={false} />
                </div>
            </div>

            {/* ── Active to-dos (full width) ─────────────────────────────── */}
            <div style={{ marginTop: 22 }}>
                <SectionLabel>Active to-dos</SectionLabel>
                <div style={{ marginTop: 10 }}>
                    {todosLoading && todos.length === 0 ? (
                        <p className="text-jl-2 text-ink-3 italic">Loading…</p>
                    ) : todos.length === 0 ? (
                        <p className="text-jl-2 text-ink-3 italic">No active to-dos.</p>
                    ) : (
                        <div className="flex flex-col" style={{ gap: 10 }}>
                            {todos.map((t) => (
                                <div
                                    key={t.id}
                                    className="border border-hairline grid"
                                    style={{
                                        borderRadius: 10,
                                        padding: '12px 16px',
                                        gridTemplateColumns: 'minmax(0,1fr) auto',
                                        gap: '8px 16px',
                                        alignItems: 'start',
                                    }}
                                >
                                    <span className="text-ink" style={{ fontSize: 14.5, lineHeight: 1.45 }}>
                                        {t.title}
                                    </span>
                                    <Pill palette={STATUS_PILL[t.status] || SLATE_PILL} minWidth={88}>
                                        {t.status}
                                    </Pill>
                                    <div
                                        className="grid items-center text-ink-3"
                                        style={{
                                            gridColumn: '1 / -1',
                                            gridTemplateColumns: '158px 140px 120px minmax(0,1fr)',
                                            columnGap: 14,
                                            fontSize: 12.5,
                                        }}
                                    >
                                        <span className="truncate whitespace-nowrap">
                                            {t.item_type && (
                                                <Pill palette={TYPE_PILL[t.item_type] || SLATE_PILL}>
                                                    {t.item_type}
                                                </Pill>
                                            )}
                                        </span>
                                        <span className="truncate whitespace-nowrap">
                                            {t.owner_name ? `👤 ${t.owner_name}` : ''}
                                        </span>
                                        <span className="truncate whitespace-nowrap">
                                            {t.due_date ? `🗓 ${formatDate(t.due_date)}` : ''}
                                        </span>
                                        <span className="truncate whitespace-nowrap italic">
                                            {t.meeting_title ? `from “${t.meeting_title}”` : ''}
                                        </span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {lastUpdatedAt && (
                <p className="text-jl-2 text-ink-3" style={{ marginTop: 18 }}>
                    Updated {formatTimeAgo(lastUpdatedAt)}
                    {sourceOfUpdate ? ` · Source ${sourceOfUpdate}` : ''}
                </p>
            )}

            <ConfirmDialog
                isOpen={pendingDeleteId != null}
                title="Delete this photo?"
                message="It comes off the release for everyone. The change is recorded in the Change Log."
                confirmLabel="Delete photo"
                busy={deleteBusy}
                onConfirm={() => deletePhoto(pendingDeleteId)}
                onCancel={() => setPendingDeleteId(null)}
            />

            {/* The Job Log row's dialog, verbatim — ASAP, Clear hard date, Break/Link.
                Portaled out: it positions itself `fixed`, and the hub's blurred
                backdrop makes that fixed box resolve against the panel, so left
                in place it would be clipped by the pane's overflow. */}
            {startInstallOpen && createPortal(
                <StartInstallDateModal
                    isOpen={startInstallOpen}
                    onClose={() => setStartInstallOpen(false)}
                    currentDate={localStartInstall}
                    currentShipDate={localShipDate}
                    currentInstaller={localInstaller}
                    onSave={handleStartInstallSave}
                    onSaveShipDate={handleShipDateSave}
                    onClearHardDate={handleClearHardDate}
                    onSetAsap={handleSetAsap}
                    onClearAsap={handleClearAsap}
                    jobNumber={jobId}
                    releaseNumber={relId}
                    startInstallFormulaTF={job['start_install_formulaTF']}
                    isAsap={isAsap}
                    stage={localStage}
                />,
                document.body,
            )}
        </div>
    );
}

export default JobDetailsBody;
