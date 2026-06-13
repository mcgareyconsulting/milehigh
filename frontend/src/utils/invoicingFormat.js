/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Shared formatting tokens and helpers for the invoicing report and its release-history
 *   modal — color families for stages/actions and Mountain-Time date/time prettifiers.
 * exports:
 *   TINT, DOT, KIND_META, ACTION_LABEL, actionLabel, stageTint, actionTint,
 *   splitDateTime, prettyDate, prettyTime
 * imports_from: [./stageProgress]
 * imported_by: [pages/InvoicingReport.jsx, components/ReleaseHistoryModal.jsx, components/Badge.jsx]
 * invariants:
 *   - Date helpers assume the backend "May 04, 2026 07:32:15 AM" Mountain-Time string format.
 */
import { isCompleteStage } from './stageProgress';

// ---------------------------------------------------------------------------
// Date formatting — the backend sends "May 04, 2026 07:32:15 AM" (Mountain).
// ---------------------------------------------------------------------------
export function splitDateTime(s) {
    if (!s) return { date: '', time: '' };
    const m = String(s).match(/^(.*?\d{4})\s+(.*)$/);
    return m ? { date: m[1], time: m[2] } : { date: String(s), time: '' };
}
// "May 04, 2026" -> "May 4, 2026"
export const prettyDate = (s) => splitDateTime(s).date.replace(/\b0(\d),/, '$1,');
// "07:32:15 AM" -> "7:32 AM"
export const prettyTime = (s) => splitDateTime(s).time.replace(/:\d{2}\s/, ' ').replace(/^0/, '');

// ---------------------------------------------------------------------------
// Color tokens — tinted, ring-bordered badges that work in light + dark.
// ---------------------------------------------------------------------------
export const TINT = {
    emerald: 'bg-emerald-50 text-emerald-700 ring-emerald-200/70 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/30',
    blue: 'bg-blue-50 text-blue-700 ring-blue-200/70 dark:bg-blue-500/10 dark:text-blue-300 dark:ring-blue-500/30',
    violet: 'bg-violet-50 text-violet-700 ring-violet-200/70 dark:bg-violet-500/10 dark:text-violet-300 dark:ring-violet-500/30',
    amber: 'bg-amber-50 text-amber-700 ring-amber-200/70 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/30',
    orange: 'bg-orange-50 text-orange-700 ring-orange-200/70 dark:bg-orange-500/10 dark:text-orange-300 dark:ring-orange-500/30',
    purple: 'bg-purple-50 text-purple-700 ring-purple-200/70 dark:bg-purple-500/10 dark:text-purple-300 dark:ring-purple-500/30',
    red: 'bg-red-50 text-red-700 ring-red-200/70 dark:bg-red-500/10 dark:text-red-300 dark:ring-red-500/30',
    slate: 'bg-slate-100 text-slate-600 ring-slate-200/80 dark:bg-slate-500/10 dark:text-slate-300 dark:ring-slate-500/30',
    accent: 'bg-accent-50 text-accent-600 ring-accent-200/70 dark:bg-accent-400/10 dark:text-accent-200 dark:ring-accent-400/30',
};

// Solid dot color per tint family — used as timeline nodes.
export const DOT = {
    emerald: 'bg-emerald-500', blue: 'bg-blue-500', violet: 'bg-violet-500',
    amber: 'bg-amber-500', orange: 'bg-orange-500', purple: 'bg-purple-500',
    red: 'bg-red-500', slate: 'bg-slate-400 dark:bg-slate-500', accent: 'bg-accent-500',
};

// Friendly labels for release event actions (Katie shouldn't read raw keys).
export const ACTION_LABEL = {
    update_stage: 'Stage',
    updated: 'Updated',
    list_move: 'Moved',
    update_installer: 'Installer',
    pickup_received: 'Pickup',
    create_card: 'Created',
    created: 'Created',
    update_name: 'Renamed',
    update_description: 'Description',
};
export const actionLabel = (a) => ACTION_LABEL[a] || (a || '').replace(/_/g, ' ');

// Solid dots used as section/legend markers.
export const KIND_META = {
    create: { label: 'Created', tint: 'emerald', dot: 'bg-emerald-500' },
    open: { label: 'Opened', tint: 'blue', dot: 'bg-blue-500' },
    close: { label: 'Closed', tint: 'slate', dot: 'bg-slate-400 dark:bg-slate-500' },
};

// Stage → color family, mirroring the Job Log's fab progression.
export function stageTint(stage) {
    const s = (stage || '').toLowerCase();
    if (isCompleteStage(stage)) return 'emerald';
    if (s.includes('hold')) return 'red';
    if (s.includes('install') || s.includes('ship')) return 'blue';
    if (s.includes('paint') || s.includes('store')) return 'violet';
    if (s.includes('weld') || s.includes('qc')) return 'amber';
    if (s.includes('fitup') || s.includes('cut') || s.includes('material')) return 'orange';
    return 'slate';
}

// Release event action → color family.
export function actionTint(action) {
    const a = (action || '').toLowerCase();
    if (a.startsWith('create')) return 'emerald';
    if (a.startsWith('delete')) return 'red';
    if (a.includes('stage')) return 'accent';
    if (a.includes('list_move')) return 'purple';
    if (a.includes('install') || a.includes('ship')) return 'blue';
    if (a.includes('pickup') || a.includes('received')) return 'amber';
    return 'slate';
}
