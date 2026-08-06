/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Shared presentational COMPONENTS for the Projects tab demo — status pills,
 *   health tiles, section cards, progress bars, meta rows. Theme-aware (light/dark) and
 *   semantic (color is never the only signal). Formatting helpers/constants live in
 *   projectsFormat.js so this file exports components only (react-refresh lint rule).
 * exports:
 *   StatusPill, HealthTile, HealthScore, SectionCard, ProgressBar, MetaRow
 * imports_from: [../../data/projectsDemo, ./projectsFormat]
 * imported_by: [frontend/src/pages/Projects.jsx, frontend/src/pages/ProjectDetail.jsx]
 */
import { PROJECT_STATUS } from '../../data/projectsDemo';
import { toneClasses, bandClasses, STATE_LABEL } from './projectsFormat';

const STATUS_TONE = {
  green: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300 ring-green-600/20',
  amber: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300 ring-amber-600/20',
  slate: 'bg-surface-2 text-ink-2 ring-hairline',
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
    <div className="rounded-lg border border-hairline bg-surface px-3 py-2.5">
      <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-3">
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

/**
 * Composite project-health score: a big 0–100 number + band, with the itemized
 * deductions listed beneath (the "why" behind the number). Non-scored states
 * (complete / on hold / no data) render "—" with the state label instead.
 * `data` is the backend `health_score` shape: {score, band, state, deductions[]}.
 */
export function HealthScore({ data, className = '' }) {
  const band = bandClasses[data?.band] || bandClasses.neutral;
  const scored = data?.state === 'scored' && data?.score != null;
  const deductions = data?.deductions || [];

  return (
    <div className={`rounded-xl border ${band.border} ${band.bg} p-4 ${className}`}>
      <div className="flex items-center gap-4">
        <div className="flex items-baseline gap-1 shrink-0">
          <span className={`text-4xl font-bold tabular-nums ${band.text}`}>
            {scored ? data.score : '—'}
          </span>
          {scored && <span className="text-sm text-ink-3">/100</span>}
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className={`inline-block w-2.5 h-2.5 rounded-full shrink-0 ${band.dot}`} />
            <span className={`text-sm font-semibold ${band.text}`}>
              {scored ? band.label : (STATE_LABEL[data?.state] || '—')}
            </span>
          </div>
          <div className="text-[11px] uppercase tracking-wide text-ink-3 mt-0.5">
            Project Health
          </div>
        </div>
      </div>

      {scored && deductions.length > 0 && (
        <ul className="mt-3 pt-3 border-t border-hairline space-y-1.5">
          {deductions.map(d => (
            <li key={d.key} className="flex items-start gap-2 text-xs">
              <span className={`font-bold tabular-nums w-7 shrink-0 text-right ${band.text}`}>{d.points}</span>
              <span className="text-ink-2 leading-snug">{d.reason}</span>
            </li>
          ))}
        </ul>
      )}
      {scored && deductions.length === 0 && (
        <p className="mt-3 pt-3 border-t border-hairline text-xs text-green-600 dark:text-green-400">
          No open risk signals — full marks.
        </p>
      )}
    </div>
  );
}

export function SectionCard({ title, action, children, className = '' }) {
  return (
    <section className={`rounded-xl border border-hairline bg-surface ${className}`}>
      {title && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-hairline">
          <h3 className="text-sm font-semibold text-ink">{title}</h3>
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
    <div className={`h-1.5 w-full rounded-full bg-surface-2 overflow-hidden ${className}`}>
      <div className={`h-full rounded-full ${color}`} style={{ width: `${clamped}%` }} />
    </div>
  );
}

export function MetaRow({ label, value }) {
  return (
    <div className="flex justify-between gap-4 py-1.5 text-sm">
      <span className="text-ink-3 shrink-0">{label}</span>
      <span className="text-ink text-right font-medium">{value ?? '—'}</span>
    </div>
  );
}
