/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The Projects page's shared visual vocabulary, transcribed from
 *   docs/projects-page-mockup.html. Every panel body in Bill's template is built from the same
 *   handful of primitives — a status badge, a coloured dot, a header action chip, a KPI cell,
 *   a two-line list row — and they repeat across a dozen panels. Defining them once keeps the
 *   panels honest to the template and stops each one from re-inventing 10px/#64748b by hand.
 * exports:
 *   Badge, StatusBadge, PanelAction, KpiBar, Row, Money, Muted, ProgressBar
 * imports_from: []
 * imported_by: [components/projects/projectPanels.jsx, pages/GridDemo.jsx]
 * invariants:
 *   - This surface is dark-only (see docs/projects-page-mockup.html), so the hex values here
 *     are literal by design, unlike the grid shell which is token-driven for both themes.
 */

// `.badge-*` from the mockup: 10px/600, 10px radius, dark tint + bright text.
const BADGE = {
  green: 'bg-[#0d2010] text-[#4ade80]',
  yellow: 'bg-[#2d2010] text-[#fbbf24]',
  red: 'bg-[#2d1010] text-[#f87171]',
  blue: 'bg-[#0d1a2d] text-[#60a5fa]',
  purple: 'bg-[#1e0d3a] text-[#c084fc]',
  orange: 'bg-[#2d1408] text-[#fb923c]',
  gray: 'bg-[#1e293b] text-[#94a3b8]',
  pink: 'bg-[#2d0a1a] text-[#f472b6]',
};

export function Badge({ tone = 'gray', children, className = '' }) {
  return (
    <span className={`inline-block text-[10px] font-semibold px-2 py-0.5 rounded-[10px] whitespace-nowrap
      ${BADGE[tone] || BADGE.gray} ${className}`}>
      {children}
    </span>
  );
}

// `.sbadge-*` — the larger pills in the project header.
const STATUS = {
  blue: 'bg-[#1e3a5f] text-[#60a5fa]',
  yellow: 'bg-[#2d2010] text-[#fbbf24]',
  red: 'bg-[#2d1010] text-[#f87171]',
  green: 'bg-[#0d2010] text-[#4ade80]',
};

export function StatusBadge({ tone = 'blue', children }) {
  return (
    <span className={`text-[11px] font-semibold px-2.5 py-[3px] rounded-xl whitespace-nowrap
      ${STATUS[tone] || STATUS.blue}`}>
      {children}
    </span>
  );
}

// `.panel-action` — the right-hand header chip ("View All", "+ Add Note"). It lives in the
// Panel's headerAction slot, which already stops propagation, so it never drills through.
export function PanelAction({ onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-[11px] px-2 py-0.5 rounded-[5px] bg-[#1e293b] text-[#3b82f6]
        hover:bg-[#2563eb] hover:text-white transition-colors"
    >
      {children}
    </button>
  );
}

const KPI_TONE = {
  accent: 'text-[#60a5fa]',
  green: 'text-[#4ade80]',
  yellow: 'text-[#fbbf24]',
  red: 'text-[#f87171]',
  purple: 'text-[#c084fc]',
  muted: 'text-[#334155]',
};

/**
 * The mockup's `.kpi-bar`: a fixed strip above the dashboard, not part of the draggable grid.
 * The 1px gap over a #1e293b background is what draws the hairline dividers between cells.
 * `blocked` marks a metric whose data source does not exist yet — shown as a dash with the
 * reason rather than a fabricated number.
 */
export function KpiBar({ items }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-px bg-[#1e293b] border-y border-[#1e293b]">
      {items.map(k => (
        <div key={k.id} className="bg-[#0d1117] px-4 py-3 text-center">
          <div className={`text-[20px] font-extrabold leading-tight tabular-nums ${KPI_TONE[k.tone] || KPI_TONE.accent}`}>
            {k.value}
          </div>
          <div className="text-[10px] uppercase tracking-[0.4px] text-[#64748b] mt-0.5">
            {k.label}
          </div>
          {k.blocked && (
            <div className="text-[9px] text-[#fb923c] mt-0.5 truncate" title={k.blocked}>
              {k.blocked}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// The hairline between list rows in every panel body (`border-bottom:1px solid #1e293b11`).
export function Row({ children, className = '', last = false }) {
  return (
    <div className={`flex items-center justify-between gap-2 py-[7px]
      ${last ? '' : 'border-b border-[#1e293b]/40'} ${className}`}>
      {children}
    </div>
  );
}

export function Money({ tone = 'default', children }) {
  const cls = {
    default: 'text-[#f8fafc]',
    green: 'text-[#4ade80]',
    yellow: 'text-[#fbbf24]',
    red: 'text-[#f87171]',
  }[tone];
  return <span className={`text-[12px] font-bold ${cls}`}>{children}</span>;
}

export function Muted({ children, className = '' }) {
  return <span className={`text-[10px] text-[#64748b] ${className}`}>{children}</span>;
}

// `.budget-bar-wrap` + `.fill-*`
export function ProgressBar({ pct, tone = 'green', height = 6 }) {
  const fill = { green: 'bg-[#22c55e]', yellow: 'bg-[#eab308]', red: 'bg-[#ef4444]' }[tone];
  return (
    <div className="bg-[#1e293b] rounded" style={{ height }}>
      <div className={`${fill} rounded h-full`} style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
    </div>
  );
}

// The footer summary line every list panel ends with in the mockup.
export function PanelFooter({ children }) {
  return (
    <div className="mt-2 pt-1.5 border-t border-[#1e293b] flex items-center justify-between gap-2 text-[11px] text-[#64748b]">
      {children}
    </div>
  );
}
