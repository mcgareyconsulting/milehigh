/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The panel body renderers for the Projects page — one component per box in
 *   docs/projects-page-mockup.html, transcribed from its row vocabulary (submittal flags,
 *   release tracker dots, schedule date blocks, budget bars, note cards, the six-column to-do
 *   table). Every list body respects the K2 size→density rule: taller genuinely means more
 *   rows, and what does not fit is announced rather than silently dropped.
 *   Split out from projectPanels.jsx purely so each file has one kind of export — the catalog
 *   exports builders, this exports components (react-refresh/only-export-components).
 * exports:
 *   More, EmptyNote, Avatar, Tracker, CarmenBanner, and one *Body component per panel
 * imports_from: [../grid/density, ./vocab]
 * imported_by: [components/projects/projectPanels.jsx]
 * invariants:
 *   - Dark-only hex by design; this surface does not participate in the app light/dark theme.
 */
import { listCapacity } from '../grid/density';
import { Badge, Row, Muted, ProgressBar, PanelFooter } from './vocab';

// ── shared bits ──────────────────────────────────────────────────────────────────────

// Panels whose rows are taller than the ~26px listCapacity() assumes get a scaled capacity,
// so a "Height 3" to-do panel doesn't promise nine rows and then hide four behind a scrollbar.
const capacity = (rows, rowPx = 26) => Math.max(1, Math.round(listCapacity(rows) * (26 / rowPx)));

export function More({ total, shown }) {
  const n = total - shown;
  if (n <= 0) return null;
  return <p className="mt-2 text-[10px] text-[#475569]">+{n} more — resize taller to see them</p>;
}

export function EmptyNote({ children, why }) {
  return (
    <div className="py-5 text-center">
      <p className="text-[11px] text-[#64748b]">{children}</p>
      {why && <p className="mt-1 text-[10px] text-[#fb923c]">{why}</p>}
    </div>
  );
}

export function Avatar({ initials, bg, fg, size = 32 }) {
  return (
    <span
      className="rounded-full flex items-center justify-center font-extrabold shrink-0"
      style={{ width: size, height: size, background: bg, color: fg, fontSize: size <= 20 ? 8 : 11 }}
    >
      {initials}
    </span>
  );
}

const DUE_TONE = { red: 'text-[#f87171]', yellow: 'text-[#fbbf24]' };

// ── panel bodies ─────────────────────────────────────────────────────────────────────

export function SubmittalsBody({ rows, project }) {
  const items = project.submittals;
  const shown = items.slice(0, capacity(rows, 36));
  return (
    <div>
      {rows >= 3 && (
        <div className="flex flex-wrap gap-1.5 mb-2.5">
          <Badge tone="green">Approved</Badge>
          <Badge tone="purple">Appr. as Noted</Badge>
          <Badge tone="orange">⏳ Out to GC</Badge>
          <Badge tone="red">⚠ Overdue</Badge>
          <Badge tone="yellow">Rev. &amp; Resubmit</Badge>
          <Badge tone="gray">In Prep</Badge>
        </div>
      )}
      {shown.map((s, i) => (
        <div key={s.name} className={`flex items-start justify-between gap-3 py-2
          ${i === shown.length - 1 ? '' : 'border-b border-[#1e293b]/40'}`}>
          <div className="min-w-0">
            <div className="text-[12px] font-medium text-[#f8fafc] truncate">{s.name}</div>
            <Muted className="block mt-0.5">{s.meta}</Muted>
          </div>
          <div className="flex flex-col items-end gap-[3px] shrink-0">
            {s.badge && <Badge tone={s.badge.tone}>{s.badge.text}</Badge>}
            {s.flag && (
              <span className={`rounded-md px-2 py-[3px] text-[10px] font-semibold border ${
                s.flag === 'overdue'
                  ? 'bg-[#2d1010] border-[#ef4444]/30 text-[#f87171]'
                  : 'bg-[#2d1a08] border-[#ea580c]/30 text-[#fb923c]'
              }`}>
                {s.flagText}
              </span>
            )}
            {s.days && (
              <span className={`text-[10px] text-right ${s.flag === 'overdue' ? 'text-[#f87171]' : 'text-[#64748b]'}`}>
                {s.days}
              </span>
            )}
          </div>
        </div>
      ))}
      <More total={items.length} shown={shown.length} />
      {rows >= 3 && (
        <PanelFooter>
          <span>{project.submittalSummary}</span>
          <span className="text-[#f87171]">1 overdue ⚠</span>
        </PanelFooter>
      )}
    </div>
  );
}

// The mockup's four tracker dots per release: Draft · Shop · Paint · Install.
export function Tracker({ done, active }) {
  return (
    <div className="flex gap-[3px] shrink-0">
      {[0, 1, 2, 3].map(i => (
        <span
          key={i}
          className={`w-2.5 h-2.5 rounded-full ${
            i < done ? 'bg-[#22c55e]' : i === done && active ? 'bg-[#3b82f6]' : 'bg-[#1e293b]'
          }`}
        />
      ))}
    </div>
  );
}

export function ReleasesBody({ rows, project }) {
  const items = project.releases;
  const shown = items.slice(0, capacity(rows, 30));
  return (
    <div>
      {shown.map((r, i) => (
        <div key={r.code} className={`flex items-center gap-2 py-[7px]
          ${i === shown.length - 1 ? '' : 'border-b border-[#1e293b]/40'}`}>
          <span className="text-[11px] font-bold text-[#60a5fa] min-w-[56px] shrink-0">{r.code}</span>
          <span className="text-[12px] text-[#f8fafc] flex-1 truncate">{r.name}</span>
          <Tracker done={r.done} active={r.active} />
          <Badge tone={r.badge.tone} className="ml-1.5">{r.badge.text}</Badge>
        </div>
      ))}
      <More total={items.length} shown={shown.length} />
      {rows >= 3 && (
        <div className="flex gap-3 mt-1 text-[9px] text-[#64748b]">
          <span>● Draft</span><span>● Shop</span><span>● Paint</span><span>● Install</span>
        </div>
      )}
    </div>
  );
}

export function ScheduleBody({ rows, project }) {
  const items = project.schedule;
  const shown = items.slice(0, capacity(rows, 38));
  return (
    <div>
      {shown.map((s, i) => (
        <div key={`${s.month}-${s.day}-${s.title}`} className={`flex items-center gap-2.5 py-[7px]
          ${i === shown.length - 1 ? '' : 'border-b border-[#1e293b]/40'}`}>
          <div className="text-center min-w-[40px] shrink-0">
            <div className="text-[9px] uppercase text-[#64748b]">{s.month}</div>
            <div className={`text-[18px] font-extrabold leading-none ${s.type === 'hard' ? 'text-[#4ade80]' : 'text-[#fbbf24]'}`}>
              {s.day}
            </div>
            <div className={`text-[8px] font-bold uppercase mt-px ${s.type === 'hard' ? 'text-[#4ade80]' : 'text-[#fbbf24]'}`}>
              {s.type === 'hard' ? 'Hard' : 'Proj'}
            </div>
          </div>
          <div className="min-w-0">
            <div className="text-[12px] font-medium text-[#f8fafc] truncate">{s.title}</div>
            <Muted className="block mt-px">{s.sub}</Muted>
          </div>
        </div>
      ))}
      <More total={items.length} shown={shown.length} />
    </div>
  );
}

export function BudgetBody({ project }) {
  const b = project.budget;
  return (
    <div>
      {b.sections.map(s => (
        <div key={s.label} className="mb-2.5">
          <div className="text-[11px] text-[#94a3b8] mb-1">{s.label}</div>
          <ProgressBar pct={s.pct} tone={s.tone} />
          <div className="flex justify-between text-[10px] mt-[3px]">
            <span className="text-[#64748b]">{s.spent}</span>
            <span className={s.leftTone === 'red' ? 'text-[#f87171]' : 'text-[#94a3b8]'}>{s.left}</span>
          </div>
        </div>
      ))}
      <hr className="border-0 border-t border-[#1e293b] my-2" />
      <div className="flex justify-between text-[13px] font-semibold">
        <span className="text-[#94a3b8]">Contract Total</span>
        <span className="text-[#f8fafc]">{b.contract}</span>
      </div>
      <div className="flex justify-between mt-1">
        <span className="text-[11px] text-[#64748b]">Billed to Date</span>
        <span className="text-[12px] font-semibold text-[#60a5fa]">{b.billed}</span>
      </div>
    </div>
  );
}

export function TmBody({ rows, project }) {
  const items = project.tm;
  const shown = items.slice(0, capacity(rows, 30));
  return (
    <div>
      {shown.map((t, i) => (
        <Row key={t.id} last={i === shown.length - 1}>
          <span className="min-w-0 truncate">
            <span className="text-[10px] font-bold text-[#60a5fa] mr-1.5">{t.id}</span>
            <span className="text-[12px] text-[#cbd5e1]">{t.desc}</span>
          </span>
          <span className="flex items-center gap-1.5 shrink-0">
            <span className="text-[12px] font-bold text-[#4ade80]">{t.amount}</span>
            <Badge tone={t.badge.tone}>{t.badge.text}</Badge>
          </span>
        </Row>
      ))}
      <More total={items.length} shown={shown.length} />
      <PanelFooter>
        <span>Total T&amp;M Value</span>
        <span className="text-[#4ade80] font-bold text-[12px]">{project.tmTotal}</span>
      </PanelFooter>
    </div>
  );
}

export function RentalsBody({ rows, project }) {
  const items = project.rentals;
  const shown = items.slice(0, capacity(rows, 34));
  return (
    <div>
      {shown.map((r, i) => (
        <Row key={r.name} last={i === shown.length - 1}>
          <span className="min-w-0">
            <span className="block text-[12px] font-medium text-[#f8fafc] truncate">{r.name}</span>
            <Muted className="block mt-px">{r.dates}</Muted>
          </span>
          {r.cost
            ? <span className="text-[12px] font-bold text-[#fbbf24] shrink-0">{r.cost}</span>
            : <Badge tone={r.badge.tone}>{r.badge.text}</Badge>}
        </Row>
      ))}
      <More total={items.length} shown={shown.length} />
      <PanelFooter>
        <span>Active Rental Cost</span>
        <span className="text-[#fbbf24] font-bold text-[12px]">{project.rentalTotal}</span>
      </PanelFooter>
    </div>
  );
}

export function CoBody({ rows, project }) {
  const items = project.co;
  const shown = items.slice(0, capacity(rows, 30));
  return (
    <div>
      {shown.map((c, i) => (
        <Row key={c.id} last={i === shown.length - 1}>
          <span className="min-w-0 truncate">
            <span className="text-[10px] font-bold text-[#ec4899] mr-1.5">{c.id}</span>
            <span className="text-[12px] text-[#cbd5e1]">{c.desc}</span>
          </span>
          <span className="flex items-center gap-1.5 shrink-0">
            <span className="text-[12px] font-bold text-[#f8fafc]">{c.amount}</span>
            <Badge tone={c.badge.tone}>{c.badge.text}</Badge>
          </span>
        </Row>
      ))}
      <More total={items.length} shown={shown.length} />
      <PanelFooter>
        <span>Executed CO Value</span>
        <span className="text-[#4ade80] font-bold text-[12px]">{project.coExecuted}</span>
      </PanelFooter>
    </div>
  );
}

export function RfiBody({ rows, project }) {
  const items = project.rfi;
  const shown = items.slice(0, capacity(rows, 30));
  return (
    <div>
      {shown.map((r, i) => (
        <Row key={r.id} last={i === shown.length - 1}>
          <span className="min-w-0 truncate">
            <span className="text-[10px] font-bold text-[#06b6d4] mr-1.5">{r.id}</span>
            <span className="text-[12px] text-[#cbd5e1]">{r.desc}</span>
          </span>
          <span className="flex items-center gap-1.5 shrink-0">
            <span className={`text-[10px] ${DUE_TONE[r.daysTone] || 'text-[#64748b]'}`}>{r.days}</span>
            <Badge tone={r.badge.tone}>{r.badge.text}</Badge>
          </span>
        </Row>
      ))}
      <More total={items.length} shown={shown.length} />
    </div>
  );
}

export function PunchBody({ rows, project }) {
  const items = project.punch;
  const shown = items.slice(0, capacity(rows, 28));
  const done = items.filter(p => p.done).length;
  return (
    <div>
      {shown.map((p, i) => (
        <div key={p.desc} className={`flex items-center gap-2 py-1.5 text-[12px]
          ${i === shown.length - 1 ? '' : 'border-b border-[#1e293b]/40'}`}>
          <span className={`w-3.5 h-3.5 rounded-full border-2 shrink-0 ${
            p.done ? 'bg-[#22c55e] border-[#22c55e]' : 'border-[#334155]'
          }`} />
          <span className={`flex-1 truncate ${p.done ? 'text-[#475569] line-through' : 'text-[#cbd5e1]'}`}>
            {p.desc}
          </span>
          <Muted>{p.owner}</Muted>
        </div>
      ))}
      <More total={items.length} shown={shown.length} />
      <PanelFooter>
        <span>{done} of {items.length} complete</span>
        <span className="w-20"><ProgressBar pct={(done / items.length) * 100} tone="green" /></span>
      </PanelFooter>
    </div>
  );
}

export function ContactsBody({ rows, project }) {
  const items = project.contacts;
  const shown = items.slice(0, capacity(rows, 40));
  return (
    <div>
      {shown.map((c, i) => (
        <div key={c.name} className={`flex items-center gap-2.5 py-[7px]
          ${i === shown.length - 1 ? '' : 'border-b border-[#1e293b]/40'}`}>
          <Avatar {...c} />
          <div className="min-w-0">
            <div className="text-[12px] font-semibold text-[#f8fafc] truncate">{c.name}</div>
            <Muted className="block mt-px truncate">{c.role}</Muted>
          </div>
        </div>
      ))}
      <More total={items.length} shown={shown.length} />
    </div>
  );
}

export function DrawingsBody({ rows, project }) {
  const { cover, sets } = project.drawings;
  return (
    <div>
      {rows >= 3 && (
        <div className="bg-[#111827] border border-[#334155] rounded-md p-3 mb-2.5 font-mono">
          <div className="text-[9px] uppercase tracking-[1px] text-[#64748b] mb-1.5">
            Architectural Drawing Set — Cover Sheet
          </div>
          <div className="text-[13px] font-bold text-[#f8fafc] mb-1">{cover.title}</div>
          <div className="text-[10px] text-[#94a3b8] mb-2">{cover.location}</div>
          <div className="grid grid-cols-2 gap-[3px] text-[9px] text-[#64748b]">
            {cover.facts.flat().map(f => <span key={f}>{f}</span>)}
          </div>
          <div className="mt-2 pt-1.5 border-t border-[#1e293b] text-[9px] text-[#64748b]">
            {cover.sheets} <span className="text-[#60a5fa]">{cover.more}</span>
          </div>
        </div>
      )}
      <div className="flex flex-col gap-[5px]">
        {sets.map(s => (
          <div key={s.name} className="flex items-center justify-between gap-2 text-[12px]">
            <span className="text-[#cbd5e1] truncate">📄 {s.name}</span>
            <Badge tone={s.badge.tone}>{s.badge.text}</Badge>
          </div>
        ))}
      </div>
    </div>
  );
}

export function CarmenBanner() {
  return (
    <div className="flex items-center gap-2 bg-[#1a1d2f] border border-[#2563eb]/20 rounded-md
      px-2.5 py-[7px] mb-3 text-[11px] text-[#60a5fa]">
      🤖 <span><strong>Carmen Miranda</strong> monitors all project notes and surfaces them during
      reviews, billing cycles, and follow-up actions.</span>
    </div>
  );
}

export function NotesBody({ span, rows, project }) {
  const items = project.notes;
  // Note cards are ~110px tall and lay out two-up at span 2+, so capacity is a card count,
  // not a row count.
  const perRow = span >= 2 ? 2 : 1;
  const shown = items.slice(0, Math.max(1, (rows - 1) * perRow));
  return (
    <div>
      {rows >= 3 && <CarmenBanner />}
      <div className={`grid gap-2 ${perRow === 2 ? 'grid-cols-1 md:grid-cols-2' : 'grid-cols-1'}`}>
        {shown.map(n => (
          <div
            key={n.type + n.meta}
            className="rounded-md px-3 py-2.5"
            style={{ background: n.bg, border: `1px solid ${n.border}`, borderLeft: `3px solid ${n.accent}` }}
          >
            <div className="flex justify-between gap-2">
              <span className="text-[10px] font-bold uppercase tracking-[0.4px]" style={{ color: n.typeColor }}>
                {n.type}
              </span>
              <Muted>{n.meta}</Muted>
            </div>
            <p className="text-[12px] text-[#cbd5e1] leading-[1.5] mt-1.5">{n.body}</p>
            <div className="mt-1.5 flex gap-1.5 items-center flex-wrap">
              <Badge tone={n.badge.tone}>{n.badge.text}</Badge>
              <Muted>{n.carmen}</Muted>
            </div>
          </div>
        ))}
      </div>
      <More total={items.length} shown={shown.length} />
    </div>
  );
}

const TODO_COLS = '24px minmax(0,1fr) 110px 100px 80px 75px';

export function TodoBody({ span, rows, project }) {
  const items = project.todo;
  const shown = items.slice(0, capacity(rows, 34));
  const s = project.todoSummary;
  // The six-column table only fits at full width; narrower, it collapses to task + status.
  const wide = span >= 3;
  return (
    <div>
      {rows >= 3 && (
        <div className="flex flex-wrap gap-1.5 mb-2.5 text-[11px]">
          <span className="px-2.5 py-[3px] rounded-xl bg-[#1e293b] text-[#64748b]">All</span>
          <span className="px-2.5 py-[3px] rounded-xl bg-[#2d1a26] text-[#f472b6]">Open</span>
          <span className="px-2.5 py-[3px] rounded-xl bg-[#2d1010] text-[#f87171]">Overdue</span>
          <span className="px-2.5 py-[3px] rounded-xl bg-[#0d2010] text-[#4ade80]">Completed</span>
          <span className="px-2.5 py-[3px] rounded-xl bg-[#0d1a2d] text-[#60a5fa]">My Tasks</span>
        </div>
      )}
      {wide && (
        <div className="grid gap-0 text-[10px] text-[#475569] px-1 pb-1.5 border-b border-[#1e293b]"
          style={{ gridTemplateColumns: TODO_COLS }}>
          <span /><span>Task</span><span>Assigned To</span><span>Due Date</span><span>Priority</span><span>Status</span>
        </div>
      )}
      {shown.map(t => (
        <div
          key={t.task}
          className={`grid gap-0 items-center px-1 py-[7px] border-b border-[#0d1117] ${t.done ? 'opacity-45' : ''}`}
          style={{ gridTemplateColumns: wide ? TODO_COLS : '24px minmax(0,1fr) 75px' }}
        >
          <span className={`w-3.5 h-3.5 rounded-full border-2 flex items-center justify-center shrink-0 ${
            t.done ? 'bg-[#22c55e] border-[#22c55e]' : t.overdue ? 'border-[#f87171]' : 'border-[#f472b6]'
          }`}>
            {t.done && <span className="text-black text-[9px] font-black leading-none">✓</span>}
          </span>
          <div className="min-w-0">
            <div className={`text-[12px] font-medium truncate ${t.done ? 'text-[#475569] line-through' : 'text-[#f8fafc]'}`}>
              {t.task}
            </div>
            <div className="text-[10px] text-[#475569] truncate">{t.link}</div>
          </div>
          {wide && (
            <>
              <span className="flex items-center gap-1.5 min-w-0">
                <Avatar {...t.who} size={20} />
                <span className="text-[11px] text-[#94a3b8] truncate">{t.who.name}</span>
              </span>
              <span className={`text-[11px] ${DUE_TONE[t.dueTone] || (t.done ? 'text-[#475569]' : 'text-[#94a3b8]')}`}>
                {t.due}
              </span>
              <span><Badge tone={t.priority.tone}>{t.priority.text}</Badge></span>
            </>
          )}
          <span><Badge tone={t.status.tone}>{t.status.text}</Badge></span>
        </div>
      ))}
      <More total={items.length} shown={shown.length} />
      <div className="mt-2 pt-2 border-t border-[#1e293b] flex justify-between gap-3 text-[11px] text-[#475569] flex-wrap">
        <span>{s.open} open · <span className="text-[#f87171]">{s.overdue} overdue</span> · {s.completed} completed</span>
        <span>Assigned: {s.assigned}</span>
      </div>
    </div>
  );
}
