/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Shared Job Log column metadata and the Review-mode sort, extracted from JobLog.jsx so the persistent ReleasesLayout header and the JobLogContent table can both use them without duplication.
 * exports:
 *   columnOrder: explicit display order of table columns
 *   COLUMN_WIDTH_PERCENT: per-column width weights (normalized at render)
 *   FILTERABLE_COLUMNS / DATE_COLUMNS: Sets driving the column-header dropdowns
 *   reviewSort: PM → Job # → stage-completeness tie-break sort used by Review mode + print
 * imports_from: [./stageProgress]
 * imported_by: [../pages/ReleasesLayout.jsx, ../pages/JobLogContent.jsx]
 */
import { isCompleteStage } from './stageProgress';

// Stage completeness order (index 0 = least complete, higher = more complete).
// Canonical names — see app/api/helpers.py STAGE_PROGRESSION_RANK.
const STAGE_COMPLETENESS = {
    'Released':         0, 'Material Ordered': 1, 'Cut Start':       2, 'Cut Complete':     3,
    'Fitup Start':      4, 'Fitup Complete':   5, 'Weld Start':      6, 'Weld Complete':    7,
    'Welded QC':        9, 'Paint Start':     10, 'Paint Complete': 11,
    'Store at MHMW':   12, 'Ship Planning':   13, 'Ship Complete':  14,
    'Install Start':   15, 'Install Complete':16, 'Complete':       17,
};

const SHIP_COMPLETE_STAGE = 'Ship Complete';

// 'X' = installed (highest); percent strings rank by their numeric value;
// missing/blank ranks lowest so it sorts to the bottom of the ship-complete group.
const installProgRank = (val) => {
    if (val == null) return -1;
    const s = val.toString().trim();
    if (s === '') return -1;
    if (s.toLowerCase() === 'x') return 101;
    const n = parseFloat(s);
    return Number.isFinite(n) ? n : -1;
};

// Tie-break for two rows that share the same PM + Job #.
const compareSameJob = (a, b) => {
    const ca = isCompleteStage(a['Stage']);
    const cb = isCompleteStage(b['Stage']);
    if (ca !== cb) return ca ? 1 : -1;

    const sa = STAGE_COMPLETENESS[a['Stage']] ?? -1;
    const sb = STAGE_COMPLETENESS[b['Stage']] ?? -1;
    if (sa !== sb) return sb - sa;

    if (a['Stage'] === SHIP_COMPLETE_STAGE) {
        return installProgRank(b['Job Comp']) - installProgRank(a['Job Comp']);
    }
    const foA = a['Fab Order'] ?? Number.POSITIVE_INFINITY;
    const foB = b['Fab Order'] ?? Number.POSITIVE_INFINITY;
    return foA - foB;
};

// Review-mode sort: PM (alphabetical) → Job # (asc) → compareSameJob tie-break.
// Returns a new sorted array.
export const reviewSort = (jobs) => {
    const sorted = [...jobs];
    sorted.sort((a, b) => {
        const pmA = (a['PM'] || 'No PM').toString();
        const pmB = (b['PM'] || 'No PM').toString();
        if (pmA !== pmB) return pmA.toLowerCase().localeCompare(pmB.toLowerCase());
        const jobA = a['Job #'] || 0;
        const jobB = b['Job #'] || 0;
        if (jobA !== jobB) return jobA - jobB;
        return compareSameJob(a, b);
    });
    return sorted;
};

// Explicit table column order.
export const columnOrder = [
    'Job #',
    'Release #',
    'Job',
    'Description',
    'Fab Hrs',
    'Install HRS',
    'Paint color',
    'PM',
    'BY',
    'Released',
    'Fab Order',
    'Stage',
    'Urgency',
    'Start install',
    'Comp. ETA',
    'Job Comp',
    'Invoiced',
    'Notes',
];

/**
 * Job log column widths as percentage of table width; normalized so visible
 * columns always sum to 100%. Only columns listed here get custom widths; others
 * share the remainder equally. Tuned for ~1280–1700px desktop viewports — see the
 * detailed viewport-tuning notes that previously lived in JobLog.jsx.
 */
export const COLUMN_WIDTH_PERCENT = {
    'Job #': 3,
    'Release #': 3,
    'Job': 9,
    'Description': 8,
    'Fab Hrs': 3,
    'Install HRS': 3,
    'Paint color': 5,
    'PM': 3,
    'BY': 3,
    'Released': 4,
    'Fab Order': 4,
    'Stage': 6,
    'Urgency': 14,
    'Start install': 4,
    'Comp. ETA': 4,
    'Job Comp': 4,
    'Invoiced': 4,
    'Notes': 9,
    'Actions': 5,
};

// Columns that get an Excel-style header dropdown filter. Spreadsheet-style:
// every column except Urgency (composite Banana Code icons) and Notes (free text).
export const FILTERABLE_COLUMNS = new Set([
    'Job #', 'Release #', 'Job', 'Description', 'Fab Hrs', 'Install HRS',
    'Paint color', 'PM', 'BY', 'Released', 'Fab Order', 'Stage',
    'Start install', 'Comp. ETA', 'Job Comp', 'Invoiced',
]);

// Date-valued columns: their header dropdown sorts chronologically and shows
// "Newest → Oldest" / "Oldest → Newest" labels instead of A→Z / Z→A.
export const DATE_COLUMNS = new Set(['Released', 'Start install', 'Comp. ETA']);
