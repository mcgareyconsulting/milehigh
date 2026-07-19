/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Non-component formatting helpers and tone constants for the Projects tab
 *   demo. Split from projectsShared.jsx so that file only exports components (satisfies
 *   the react-refresh/only-export-components lint rule).
 * exports:
 *   fmtMoney, fmtPct, toneClasses
 * imports_from: []
 * imported_by: [projectsShared.jsx, ../../pages/Projects.jsx, ../../pages/ProjectDetail.jsx]
 */

export function fmtMoney(n) {
  if (n == null) return '—';
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (Math.abs(n) >= 1_000) return `$${Math.round(n / 1_000)}k`;
  return `$${n.toLocaleString()}`;
}

export function fmtPct(n) {
  return n == null ? '—' : `${n}%`;
}

// Health tile tone → text/dot colors. good/warn/risk/neutral, plus an icon glyph
// so the state reads without relying on color alone.
export const toneClasses = {
  good:    { text: 'text-green-600 dark:text-green-400',  dot: 'bg-green-500',  glyph: '✓' },
  warn:    { text: 'text-amber-600 dark:text-amber-400',  dot: 'bg-amber-500',  glyph: '!' },
  risk:    { text: 'text-red-600 dark:text-red-400',      dot: 'bg-red-500',    glyph: '▲' },
  neutral: { text: 'text-slate-500 dark:text-slate-400',  dot: 'bg-slate-400',  glyph: '·' },
};
