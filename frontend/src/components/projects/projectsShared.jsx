/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Shared presentational COMPONENTS for the Projects tab demo — status pills,
 *   health tiles, section cards, progress bars, meta rows. Theme-aware (light/dark) and
 *   semantic (color is never the only signal). Formatting helpers/constants live in
 *   projectsFormat.js so this file exports components only (react-refresh lint rule).
 * exports:
 *   StatusPill, HealthTile, SectionCard, ProgressBar, MetaRow
 * imports_from: [../../data/projectsDemo, ./projectsFormat]
 * imported_by: [frontend/src/pages/Projects.jsx, frontend/src/pages/ProjectDetail.jsx]
 */
import { PROJECT_STATUS } from '../../data/projectsDemo';
import { toneClasses } from './projectsFormat';

const STATUS_TONE = {
  green: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300 ring-green-600/20',
  amber: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300 ring-amber-600/20',
  slate: 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300 ring-slate-500/20',
  red:   'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300 ring-red-600/20',
};

export function StatusPill({ status }) {
  const meta = PROJECT_STATUS[status] || PROJECT_STATUS.active;
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ring-1 ring-inset ${STATUS_TONE[meta.tone]}`}>
      {meta.label}
    </span>
  );
}

export function HealthTile({ label, value, tone = 'neutral' }) {
  const t = toneClasses[tone] || toneClasses.neutral;
  return (
    <div className="rounded-lg border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2.5">
      <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-slate-400">
        <span className={`inline-block w-1.5 h-1.5 rounded-full ${t.dot}`} />
        {label}
      </div>
      <div className={`mt-1 text-lg font-bold tabular-nums ${t.text}`}>
        <span className="mr-1 text-xs align-middle" aria-hidden>{t.glyph}</span>
        {value}
      </div>
    </div>
  );
}

export function SectionCard({ title, action, children, className = '' }) {
  return (
    <section className={`rounded-xl border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-800 ${className}`}>
      {title && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-slate-700">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-slate-100">{title}</h3>
          {action}
        </div>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function ProgressBar({ pct, className = '' }) {
  const clamped = Math.max(0, Math.min(100, pct || 0));
  const color = clamped >= 100 ? 'bg-green-500' : 'bg-accent-500';
  return (
    <div className={`h-1.5 w-full rounded-full bg-gray-200 dark:bg-slate-700 overflow-hidden ${className}`}>
      <div className={`h-full rounded-full ${color}`} style={{ width: `${clamped}%` }} />
    </div>
  );
}

export function MetaRow({ label, value }) {
  return (
    <div className="flex justify-between gap-4 py-1.5 text-sm">
      <span className="text-gray-500 dark:text-slate-400 shrink-0">{label}</span>
      <span className="text-gray-900 dark:text-slate-100 text-right font-medium">{value ?? '—'}</span>
    </div>
  );
}
