/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Card rendering a single job release for the card view of Job Log and Archive — a stage-colored header strip (FO / job-rel / Stage corners, name — desc below) over a bordered body holding a grid of the remaining table fields + Notes. Dense, no tap-anywhere, full table info.
 * exports:
 *   default JobLogCard: Card component. Props: job, onOpen (Details-button handler), onUpdate (refetch after edit), stageToGroup, stageGroupColors, stageGroupDupColors, duplicateFabOrders, isHighlighted, isAdmin, isDrafter, rowIndex, banded, compact (phone layout).
 * imports_from: [react, ./StartInstallEditor, ./JobsTableRow, ./ReleaseNumberLink, ../utils/stageProgress, ../utils/formatters]
 * imported_by: [frontend/src/components/JobLogCardGrid.jsx]
 * invariants:
 *   - When onUpdate is provided (Job Log), Stage / Fab Order / Notes are inline-editable by
 *     embedding single-column JobsTableRow editors so cascade, collision, and notes-history logic match the table.
 *     Without onUpdate (Archive) the card is fully read-only.
 *   - No tap-anywhere: the release number opens the FC drawing hub (ReleaseNumberLink) and the
 *     explicit Details button opens the parent's onOpen modal. Job Comp / Invoiced are read-only
 *     stats here — the table (or Details modal) is the edit surface for those.
 *   - compact=true is the PHONE layout and deliberately breaks both of the rules above, because on a
 *     handset they produce the wrong card. It embeds NO JobsTableRow editors: a table cell rendered
 *     inside a card inherits the table's own grey cell chrome, which is what made the Fab Order and
 *     Notes slots read as broken grey blocks on a phone. And it IS tap-anywhere — a 390px card has no
 *     room for a "Details →" affordance the thumb can reliably hit, and the modal is the edit surface
 *     anyway once the inline editors are gone. Interactive children (the Start install tile, the
 *     release-number link) stop propagation so they still do their own job.
 *   - The compact card drops Fab Order, Rel'd, Prog and Inv from the face of the card. They are desk
 *     fields; on a phone they cost a row each and the modal is one tap away. Prog/Inv still surface,
 *     but only as ticks when actually set, where they read as status rather than empty labels.
 *   - Layout: header strip tinted with the release's own stage-group color (`stageColorStyle`,
 *     same source as the table's Stage pill) — Fab Order upper-left, job-rel upper-middle,
 *     Stage upper-right, name — description centered below. The header has no border of its
 *     own (color is the separator); the body below it DOES have a border (`border-t-0` so it
 *     reads as one continuous box with the header) holding a 5-col grid of Start Install, Comp.
 *     ETA, PM, BY, Rel'd, Fab hrs, Install hrs, Paint, Prog, Inv, then Notes + Details.
 *   - Body background alternates white/blue exactly like the table's rows (rowIndex/banded
 *     props, kept in sync with JobsTableRow's rowBgClass); complete/install-complete rows get
 *     the same muted, receding treatment (header still shows the Complete stage's own color).
 */
import React from 'react';
import StartInstallEditor from './StartInstallEditor';
import { JobsTableRow } from './JobsTableRow';
import ReleaseNumberLink from './ReleaseNumberLink';
import { ASAP_PROPAGATED_ROW_CLASS } from './AsapPropagationTag';
import { PhotoBadge } from './PhotoBadge';
import { isCompleteStage } from '../utils/stageProgress';
import { formatDateShort, formatCellValue } from '../utils/formatters';

// Wraps a single-column JobsTableRow editor (which renders a <tr>) in its own table so it can live
// inside the card's flex layout. Stops click propagation so editing never opens the details modal.
function InlineEditor({ children, fullWidth = false }) {
    return (
        <span
            onClick={(e) => e.stopPropagation()}
            className={fullWidth ? 'block w-full' : 'inline-block'}
        >
            <table className={fullWidth ? 'w-full' : 'inline-table'} style={{ borderCollapse: 'collapse' }}>
                <tbody>{children}</tbody>
            </table>
        </span>
    );
}

const fmt = (v) => (v == null || v === '' ? '—' : String(v));
const fmtHrs = (v) => {
    if (v == null || v === '') return '—';
    const n = parseFloat(v);
    return Number.isFinite(n) ? n.toFixed(2) : '—';
};

// The stage-group color, shared with the table's Stage pill — used here as the whole header's tint.
function stageColorStyle(stage, stageToGroup, stageGroupColors) {
    const group = stageToGroup?.[stage];
    const c = stageGroupColors?.[group];
    if (!c) return null;
    return { backgroundColor: c.light, color: c.text };
}

// Label-over-value grid cell — the density workhorse of the body grid.
function GridCell({ label, children, title }) {
    return (
        <div className="min-w-0" title={title || label}>
            <div className="text-[9px] font-bold uppercase tracking-wide text-gray-400 dark:text-slate-500 truncate">{label}</div>
            <div className="text-xs font-semibold text-gray-800 dark:text-slate-200 truncate">{children}</div>
        </div>
    );
}

// Job Comp / Invoiced read as a ✓ when 'X', the raw value otherwise, muted em-dash when blank.
function progressValue(value) {
    const v = (value == null ? '' : String(value)).trim();
    if (!v) return <span className="text-gray-400 dark:text-slate-500 font-normal">—</span>;
    if (v.toLowerCase() === 'x') return <span className="text-emerald-600 dark:text-emerald-400">✓</span>;
    return v;
}


/** One muted meta item on the compact card — "PM RL", "Fab 1.00". */
function Meta({ label, value }) {
    if (value === '—' || value == null || value === '') return null;
    return (
        <span className="whitespace-nowrap">
            <span className="text-gray-400 dark:text-slate-500">{label}</span>{' '}
            <span className="font-semibold">{value}</span>
        </span>
    );
}

/**
 * Phone card. Same release, same stage colour, a tenth of the chrome: identity and stage up top,
 * the two dates that drive the day, then one muted meta line and the note. Everything else is a tap
 * away in the hub.
 */
function CompactCard({
    job, onOpen, onOpenDrawings, onUpdate, stageToGroup, stageGroupColors,
    isHighlighted, isAdmin, isDrafter,
}) {
    const jobNum = fmt(job['Job #']);
    const release = fmt(job['Release #']);
    const jobName = fmt(job['Job']);
    const description = (job['Description'] || '').toString().trim();
    const stage = job['Stage'] || 'Released';
    const compEta = formatDateShort(job['Comp. ETA']);
    const notes = (job['Notes'] || '').toString().trim();
    const photoCount = Number(job.photo_count) || 0;
    const complete = isCompleteStage(stage);
    const headerStyle = stageColorStyle(stage, stageToGroup, stageGroupColors);
    const jobComp = (job['Job Comp'] || '').toString().trim().toLowerCase() === 'x';
    const invoiced = (job['Invoiced'] || '').toString().trim().toLowerCase() === 'x';

    return (
        <div
            role="button"
            tabIndex={0}
            onClick={() => onOpen && onOpen(job)}
            onKeyDown={(e) => {
                if (onOpen && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); onOpen(job); }
            }}
            aria-label={`${jobNum}-${release} ${jobName}${description ? ` — ${description}` : ''}. Open details.`}
            className={`relative w-full rounded-xl overflow-hidden text-left transition-all active:scale-[0.995] ${
                isHighlighted ? 'shadow-lg ring-2 ring-amber-400 dark:ring-amber-500' : 'shadow-sm'
            } ${complete ? 'opacity-75' : ''} ${job._asapPropagated ? ASAP_PROPAGATED_ROW_CLASS : ''}`}
        >
            {/* Identity strip, tinted by the release's own stage group. */}
            <div className="px-3 py-2" style={headerStyle || undefined}>
                <div className="flex items-baseline justify-between gap-2">
                    <span className="font-mono text-base font-bold whitespace-nowrap">
                        {jobNum}
                        <span className="opacity-50">-</span>
                        <span onClick={(e) => e.stopPropagation()}>
                            <ReleaseNumberLink
                                value={release}
                                releaseId={job.id}
                                jobReleaseLabel={`${jobNum}-${release}`}
                                hasDrawing={job.has_drawing}
                                viewerUrl={job.viewer_url}
                                canMarkup={isAdmin || isDrafter}
                                onOpenHub={onOpenDrawings ? () => onOpenDrawings(job) : null}
                            />
                        </span>
                        <PhotoBadge count={photoCount} className="ml-1.5 opacity-70" />
                    </span>
                    <span className="text-xs font-bold text-right leading-tight">{stage}</span>
                </div>
                <div className="mt-0.5 text-sm leading-snug">
                    <span className="font-bold">{jobName}</span>
                    {description && <span className="opacity-70"> — {description}</span>}
                </div>
            </div>

            {/* The two dates that drive the day, side by side. */}
            <div className="px-3 py-2 bg-white dark:bg-slate-800 border-x border-b border-gray-200 dark:border-slate-600 rounded-b-xl">
                <div className="flex items-stretch gap-2">
                    <div className="flex-1 min-w-0" onClick={(e) => e.stopPropagation()}>
                        <StartInstallEditor row={job} onUpdate={onUpdate} variant="tile" />
                    </div>
                    <div className="flex-1 min-w-0 flex flex-col justify-center">
                        <div className="text-[9px] font-bold uppercase tracking-wide text-gray-400 dark:text-slate-500">Comp. ETA</div>
                        <div className="text-sm font-semibold text-gray-800 dark:text-slate-200">{compEta || '—'}</div>
                    </div>
                </div>

                <div className="mt-2 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-gray-700 dark:text-slate-300">
                    <Meta label="PM" value={fmt(job['PM'])} />
                    <Meta label="BY" value={fmt(job['BY'])} />
                    <Meta label="Fab" value={fmtHrs(job['Fab Hrs'])} />
                    <Meta label="Inst" value={fmtHrs(job['Install HRS'])} />
                    <Meta label="Paint" value={fmt(job['Paint color'])} />
                    {/* Only when set: an empty "Prog —" is a label earning no room. */}
                    {jobComp && <span className="text-emerald-600 dark:text-emerald-400 font-semibold whitespace-nowrap">✓ Installed</span>}
                    {invoiced && <span className="text-emerald-600 dark:text-emerald-400 font-semibold whitespace-nowrap">✓ Invoiced</span>}
                </div>

                {notes && (
                    <div className="mt-1.5 pt-1.5 border-t border-gray-100 dark:border-slate-700/60 text-[11px] text-gray-600 dark:text-slate-400 line-clamp-2">
                        {notes}
                    </div>
                )}
            </div>
        </div>
    );
}


export default function JobLogCard({
    job,
    onOpen,
    // Tapping the release number opens the same hub as the card itself, on the
    // Drawings & Photos tab. Falls back to ReleaseNumberLink's own modals if unset.
    onOpenDrawings = null,
    onUpdate,
    stageToGroup,
    stageGroupColors,
    stageGroupDupColors = null,
    duplicateFabOrders = null,
    isHighlighted = false,
    isAdmin = false,
    isDrafter = false,
    rowIndex = 0,
    banded = false,
    compact = false,
}) {
    if (compact) {
        return (
            <CompactCard
                job={job}
                onOpen={onOpen}
                onOpenDrawings={onOpenDrawings}
                onUpdate={onUpdate}
                stageToGroup={stageToGroup}
                stageGroupColors={stageGroupColors}
                isHighlighted={isHighlighted}
                isAdmin={isAdmin}
                isDrafter={isDrafter}
            />
        );
    }

    const jobNum = fmt(job['Job #']);
    const release = fmt(job['Release #']);
    const jobName = fmt(job['Job']);
    const description = (job['Description'] || '').toString().trim();
    const stage = job['Stage'] || 'Released';
    const compEta = formatDateShort(job['Comp. ETA']);
    const released = formatDateShort(job['Released']);
    const notes = (job['Notes'] || '').toString().trim();
    // Comes down with the row (batched server-side), so the card can say a release has
    // photos without anyone opening it to find out.
    const photoCount = Number(job.photo_count) || 0;
    const complete = isCompleteStage(stage);
    // Same background rule as the table (JobsTableRow's rowBgClass — keep in sync): complete
    // rows are muted + receding, otherwise alternate white/blue banding. Applies to the BODY
    // only — the header strip is tinted by the stage color instead (see stageColorStyle).
    const bodyBgClass = complete
        ? 'bg-gray-200 dark:bg-slate-950'
        : (banded ? (rowIndex % 2 === 0 ? 'bg-white dark:bg-slate-800' : 'bg-blue-300 dark:bg-slate-600') : 'bg-white dark:bg-slate-800');
    const bodyTextClass = complete ? 'text-gray-500 dark:text-slate-500' : 'text-gray-800 dark:text-slate-200';
    const headerStyle = stageColorStyle(stage, stageToGroup, stageGroupColors);

    // Editing is enabled only when the parent passes onUpdate (Job Log). Archive cards stay read-only.
    const editable = !!onUpdate;
    const sharedRowProps = {
        row: job,
        formatCellValue,
        formatDate: formatDateShort,
        rowIndex: 0,
        onDragStart: () => {},
        onDragOver: () => {},
        onDragLeave: () => {},
        onDrop: () => {},
        isDragging: null,
        dragOverIndex: null,
        onUpdate,
        onCascadeRecalculating: null,
        stageToGroup,
        stageGroupColors,
        stageGroupDupColors,
        isJumpToHighlight: false,
        isAdmin: false,
        isDrafter: false,
        onDelete: null,
        tableScrollRef: null,
        duplicateFabOrders,
    };

    return (
        <div
            className={`relative w-full rounded-lg overflow-hidden transition-all ${
                isHighlighted
                    ? 'shadow-lg ring-2 ring-amber-400 dark:ring-amber-500'
                    : 'shadow-sm'
            } ${job._asapPropagated ? ASAP_PROPAGATED_ROW_CLASS : ''}`}
        >
            {/* Header strip — tinted with the stage's own color (no border of its own; the
                color IS the separator from the body below). FO upper-left, job-rel upper-
                middle, Stage upper-right; name — description centered below. */}
            <div
                className="px-3 pt-1.5 pb-2 bg-gray-100 dark:bg-slate-700"
                style={headerStyle || undefined}
            >
                <div className="flex items-start justify-between gap-2">
                    <span className="shrink-0">
                        {editable ? (
                            <InlineEditor>
                                <JobsTableRow {...sharedRowProps} columns={['Fab Order']} compact />
                            </InlineEditor>
                        ) : (
                            <span className="text-xs font-semibold opacity-80" title="Fab Order">{fmt(job['Fab Order'])}</span>
                        )}
                    </span>
                    <span className="font-mono text-sm font-bold whitespace-nowrap" title={`${jobNum}-${release}`}>
                        {jobNum}
                        <span className="opacity-50">-</span>
                        <ReleaseNumberLink
                            value={release}
                            releaseId={job.id}
                            jobReleaseLabel={`${jobNum}-${release}`}
                            hasDrawing={job.has_drawing}
                            viewerUrl={job.viewer_url}
                            canMarkup={isAdmin || isDrafter}
                            onOpenHub={onOpenDrawings ? () => onOpenDrawings(job) : null}
                        />
                    </span>
                    <span className="shrink-0">
                        {editable ? (
                            <InlineEditor>
                                <JobsTableRow {...sharedRowProps} columns={['Stage']} compact />
                            </InlineEditor>
                        ) : (
                            <span className="text-xs font-bold whitespace-nowrap" title={`Stage: ${stage}`}>{stage}</span>
                        )}
                    </span>
                </div>
                <div
                    className="mt-0.5 text-center text-sm truncate"
                    title={`${description ? `${jobName} — ${description}` : jobName}${photoCount ? (photoCount === 1 ? ' · 1 photo' : ` · ${photoCount} photos`) : ''}`}
                >
                    <PhotoBadge count={photoCount} className="mr-1 opacity-70" />
                    <span className="font-bold">{jobName}</span>
                    {description && <span className="opacity-70"> — {description}</span>}
                </div>
            </div>

            {/* Body — bordered box (the header's color is its own separator, so no border-top
                here) holding the remaining table fields as a real grid, then Notes + Details. */}
            <div className={`px-3 py-2 border border-t-0 border-gray-200 dark:border-slate-600 rounded-b-lg ${bodyBgClass}`}>
                <div className={`grid grid-cols-3 sm:grid-cols-5 gap-x-2 gap-y-1.5 ${bodyTextClass}`}>
                    <div className="col-span-1">
                        <StartInstallEditor row={job} onUpdate={onUpdate} variant="tile" />
                    </div>
                    <GridCell label="ETA" title="Comp. ETA">{compEta || '—'}</GridCell>
                    <GridCell label="PM">{fmt(job['PM'])}</GridCell>
                    <GridCell label="BY">{fmt(job['BY'])}</GridCell>
                    <GridCell label="Rel'd" title="Released">{released || '—'}</GridCell>
                    <GridCell label="Fab Hrs" title="Fab hours">{fmtHrs(job['Fab Hrs'])}</GridCell>
                    <GridCell label="Inst Hrs" title="Install hours">{fmtHrs(job['Install HRS'])}</GridCell>
                    <GridCell label="Paint" title="Paint color">{fmt(job['Paint color'])}</GridCell>
                    <GridCell label="Prog" title="Install progress (Job Comp)">{progressValue(job['Job Comp'])}</GridCell>
                    <GridCell label="Inv" title="Invoiced">{progressValue(job['Invoiced'])}</GridCell>
                </div>

                {/* Notes — inline editable when editable; read-only otherwise; hidden when empty+read-only — + Details link */}
                <div className="mt-2 pt-1.5 border-t border-gray-100 dark:border-slate-700/60 flex items-start justify-between gap-2">
                    {editable ? (
                        <div className="flex-1 min-w-0">
                            <InlineEditor fullWidth>
                                <JobsTableRow {...sharedRowProps} columns={['Notes']} />
                            </InlineEditor>
                        </div>
                    ) : (
                        <div className="flex-1 min-w-0 text-xs text-gray-700 dark:text-slate-300">
                            {notes && (
                                <>
                                    <span className="text-gray-400 dark:text-slate-500 mr-1">Notes</span>
                                    <span className="line-clamp-2">{notes}</span>
                                </>
                            )}
                        </div>
                    )}
                    {onOpen && (
                        <button
                            type="button"
                            onClick={() => onOpen(job)}
                            className="shrink-0 text-[11px] font-semibold text-accent-600 dark:text-accent-400 hover:underline whitespace-nowrap"
                            title="Open full details"
                        >
                            Details →
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
}
