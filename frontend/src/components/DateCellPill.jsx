/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Shared date "pill" for the Drafting Work Load date columns (DUE DATE, START INSTALL),
 *   rendered to match the Job Log Start Install control (StartInstallEditor 'pill' variant) so the
 *   two surfaces read identically: solid fill when set, a neutral clickable pill when empty.
 * exports:
 *   default DateCellPill: Props — value, tone ('green'|'yellow'|'red'|'neutral'), interactive, title, onClick.
 * imports_from: [react]
 * imported_by: [frontend/src/components/TableRow.jsx]
 * invariants:
 *   - Colors mirror StartInstallEditor: green = upcoming, yellow = past-due, red = urgent, neutral = unset.
 *     Exception: green uses dark text (not white) for readability on the DWL.
 *   - A pill always means "interactive" on the DWL; read-only/derived values render as plain text instead.
 */
import React from 'react';

// [fill+text, hover] — fills match StartInstallEditor's colorClass, except green uses
// dark text (text-gray-900) for readability: white-on-green was hard to read on the DWL.
const FILL = {
    green: ['bg-green-400 text-gray-900', 'hover:bg-green-500'],
    yellow: ['bg-yellow-400 text-gray-900', 'hover:bg-yellow-500'],
    red: ['bg-red-500 text-white', 'hover:bg-red-600'],
    neutral: [
        'bg-gray-50 dark:bg-slate-700/50 text-gray-900 dark:text-slate-100',
        'hover:bg-accent-50 dark:hover:bg-slate-600',
    ],
};

export default function DateCellPill({ value, tone = 'neutral', interactive = false, title, onClick }) {
    const [fill, hover] = FILL[tone] ?? FILL.neutral;
    const cls = `inline-flex items-center justify-center min-w-[60px] rounded px-2 py-0.5 text-xs font-semibold tabular-nums leading-none transition-colors ${fill} ${interactive ? `${hover} cursor-pointer` : 'cursor-default'}`;
    const display = value || '—';
    return interactive
        ? <button type="button" onClick={onClick} title={title} className={cls}>{display}</button>
        : <span className={cls} title={title}>{display}</span>;
}
