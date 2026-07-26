/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Non-component formatting helpers and tone constants for the Projects tab
 *   demo. Split from projectsShared.jsx so that file only exports components (satisfies
 *   the react-refresh/only-export-components lint rule).
 * exports:
 *   fmtMoney, fmtPct, toneClasses, bandClasses,
 *   resolveHealthScore, resolveUpcoming (live-first, demo fallback)
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

// Composite health-score band → colors + a plain-language label. The 0–100 score maps
// to green/amber/red; neutral is for completed/paused/no-data projects (score "—").
export const bandClasses = {
  green:   { text: 'text-green-700 dark:text-green-300', dot: 'bg-green-500', bg: 'bg-green-50 dark:bg-green-900/15',  border: 'border-green-200 dark:border-green-800/50',  label: 'On Track' },
  amber:   { text: 'text-amber-700 dark:text-amber-300', dot: 'bg-amber-500', bg: 'bg-amber-50 dark:bg-amber-900/15',  border: 'border-amber-200 dark:border-amber-800/50',  label: 'Needs Attention' },
  red:     { text: 'text-red-700 dark:text-red-300',     dot: 'bg-red-500',   bg: 'bg-red-50 dark:bg-red-900/15',      border: 'border-red-200 dark:border-red-800/50',      label: 'At Risk' },
  neutral: { text: 'text-slate-600 dark:text-slate-300', dot: 'bg-slate-400', bg: 'bg-white dark:bg-slate-800',        border: 'border-gray-200 dark:border-slate-600',      label: '—' },
};

// Human label for a non-scored lifecycle state.
export const STATE_LABEL = { complete: 'Complete', on_hold: 'On Hold', no_data: 'No data yet' };

// Frontend mirror of the backend rubric weights, used only for the DEMO fallback when a
// project has no live `health_score` (backend is the source of truth for live data).
const DEMO_TONE_PENALTY = { risk: 12, warn: 6 };

function scoreFromTiles(project) {
  if (project.status === 'complete') return { state: 'complete', score: null, band: 'neutral', deductions: [] };
  if (project.status === 'on_hold')  return { state: 'on_hold',  score: null, band: 'neutral', deductions: [] };
  let score = 100;
  const deductions = [];
  for (const h of project.health || []) {
    const pts = DEMO_TONE_PENALTY[h.tone] || 0;
    if (pts) {
      score -= pts;
      deductions.push({ key: h.key, points: -pts, reason: `${h.label}: ${h.value}` });
    }
  }
  score = Math.max(0, score);
  const band = score >= 85 ? 'green' : score >= 65 ? 'amber' : 'red';
  deductions.sort((a, b) => a.points - b.points);
  return { state: 'scored', score, band, deductions };
}

// Live health_score if the backend supplied one; otherwise a demo fallback from tiles.
export function resolveHealthScore(project) {
  return project.health_score || scoreFromTiles(project);
}

// Non-complete install/ship dates within `withinDays`. Prefers the backend `upcoming`
// feed; falls back to deriving from the project's releases (demo scaffold).
function upcomingFromReleases(releases, withinDays = 21) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const horizon = new Date(today); horizon.setDate(horizon.getDate() + withinDays);
  const out = [];
  for (const r of releases || []) {
    if ((r.pct ?? 0) >= 100) continue;
    for (const [kind, iso] of [['install', r.start_install], ['ship', r.ship_date]]) {
      if (!iso) continue;
      const d = new Date(`${iso}T00:00:00`);
      if (d >= today && d <= horizon) {
        out.push({ kind, date: iso, release: r.release, description: r.description });
      }
    }
  }
  return out.sort((a, b) => a.date.localeCompare(b.date));
}

export function resolveUpcoming(project) {
  return project.upcoming || upcomingFromReleases(project.releases);
}
