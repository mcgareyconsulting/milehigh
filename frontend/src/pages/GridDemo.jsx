/**
 * @milehigh-header
 * schema_version: 3
 * purpose: TEMPORARY harness for the K2 grid engine (route /grid-demo). Models the real D1
 *   contract: ONE project-page layout shared across every project (only the data changes), a
 *   CLOSED catalog of exactly the tiles Bill's spec lists, KPI tiles pinned to 1x1, and list
 *   panels whose size class controls how much information is shown. Dummy data only — this
 *   exists to validate feel and the size/density rules before D1 wires real sources.
 *   DELETE THIS FILE once the Projects page (D1) is bound to PanelGrid.
 * exports:
 *   GridDemo: demo page component (route /grid-demo)
 * imports_from: [react, ../components/grid/PanelGrid, ../components/grid/density]
 * imported_by: [frontend/src/App.jsx]
 */
import { useState } from 'react';
import PanelGrid from '../components/grid/PanelGrid';
import { listCapacity } from '../components/grid/density';

// ── Bill's KPI Summary Bar (design-spec-projects-page.md §KPI Summary Bar) ────────────
// Spec lists 7; the mockup shows an 8th (Overdue Items). `blocked` marks a tile whose data
// source does not exist yet — shown here so the gap is visible rather than faked.
const KPIS = [
  { id: 'kpi_total_releases', title: 'Total Releases', value: '6', tone: 'accent' },
  { id: 'kpi_fc_released', title: 'FC Released', value: '4', tone: 'green' },
  { id: 'kpi_in_drafting', title: 'In Drafting', value: '2', tone: 'accent' },
  { id: 'kpi_billed', title: 'Billed to Date', value: '—', tone: 'muted', blocked: 'needs Pay Apps' },
  { id: 'kpi_remaining', title: 'Remaining', value: '—', tone: 'muted', blocked: 'needs contract value' },
  { id: 'kpi_open_tm', title: 'Open T&M Tickets', value: '—', tone: 'muted', blocked: 'needs A1' },
  { id: 'kpi_co_pending', title: 'CO Value Pending', value: '—', tone: 'muted', blocked: 'needs A2' },
  { id: 'kpi_overdue', title: 'Overdue Items', value: '1', tone: 'red' },
];

const TONE_CLASS = {
  accent: 'text-accent-600 dark:text-accent-300',
  green: 'text-green-600 dark:text-green-400',
  red: 'text-red-600 dark:text-red-400',
  muted: 'text-gray-300 dark:text-slate-600',
};

// Longer lists than fit at any one size, so resizing visibly reveals more.
const DATA = {
  submittals: [
    ['Structural Steel', 'Approved'], ['Bld A Stair #1', 'Approved as Noted'],
    ['Bld A Stair #2', 'Approved'], ['Bld A Stair #3', 'Out to GC — 9 days'],
    ['Bld A Balcony Rails', 'Overdue — 16 days'], ['Bld B Guardrails', 'Rev. & Resubmit'],
    ['Bld C Entry Gate', 'In Prep'], ['Bld C Canopy', 'In Prep'],
    ['Bld D Handrails', 'Drafting'], ['Bld D Embeds', 'Drafting'],
  ],
  releases: [
    ['450-700', 'Structural Steel', 'Complete'], ['450-760', 'Bld A Stair #1', 'Installing'],
    ['450-759', 'Bld A Stair #2', 'In Paint'], ['450-747', 'Bld A Stair #3', 'In Shop'],
    ['450-344', 'Bld A Balcony Rails', 'Drafting'], ['450-381', 'Bld B Guardrails', 'DRR Needed'],
    ['450-392', 'Bld C Entry Gate', 'Drafting'], ['450-401', 'Bld C Canopy', 'Drafting'],
  ],
  schedule: [
    ['Jul 28', 'Bld A Stair #1 · Crew 1'], ['Aug 4', 'Bld A Stair #2 · Crew 1'],
    ['Aug 11', 'Bld A Stair #3 · Crew 2'], ['Aug 18', 'Bld A Balcony Rails · Crew 1'],
    ['Sep 8', 'Bld B Guardrails · Crew 2'], ['Sep 15', 'Bld C Entry Gate · Crew 1'],
  ],
  rentals: [
    ['Scissor Lift 19ft', 'On site'], ['Boom Lift 45ft', 'Returned'],
    ['Welder Trailer', 'On site'], ['Storage Container', 'On site'],
  ],
  punch: [
    ['Bld A Stair #1', 'Touch-up paint at landing'], ['Bld A Stair #2', 'Missing end cap'],
    ['Bld B Guardrail', 'Weld grind at post 4'],
  ],
  contacts: [
    ['Steve Kalynchuk', 'GC — Project Manager'], ['Scott Tatum', 'GC — Superintendent'],
    ['Dana Wu', 'Architect'], ['Luis Solano', 'MHMW — Field Super'],
  ],
  drawings: [
    ['A-201', 'Stair Sections · rev 4'], ['A-202', 'Guardrail Details · rev 2'],
    ['S-101', 'Embed Plan · rev 1'],
  ],
};

// A list panel shows as many rows as its height class allows, and says what it's hiding.
function DensityList({ rows, items, mono = true }) {
  const cap = listCapacity(rows);
  const shown = items.slice(0, cap);
  const hidden = items.length - shown.length;
  return (
    <div>
      <ul className="space-y-1.5">
        {shown.map(([left, right], i) => (
          <li key={i} className="flex items-center justify-between gap-3 text-sm">
            <span className={`${mono ? 'font-mono text-xs' : 'text-sm'} text-accent-600 dark:text-accent-300 shrink-0`}>
              {left}
            </span>
            <span className="text-gray-700 dark:text-slate-300 truncate text-right">{right}</span>
          </li>
        ))}
      </ul>
      {hidden > 0 && (
        <p className="mt-2 text-[11px] text-gray-400 dark:text-slate-500">
          +{hidden} more — resize taller to see them
        </p>
      )}
    </div>
  );
}

function ActionLink({ children, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-[11px] px-2 py-0.5 rounded bg-gray-100 dark:bg-slate-700 text-accent-600 dark:text-accent-300
        hover:bg-accent-500 hover:text-white dark:hover:bg-accent-600 transition-colors"
    >
      {children}
    </button>
  );
}

// Simulates "pick a different project" — same layout, different data.
const PROJECTS = [
  { id: '450', name: 'Alta Metro' },
  { id: '560', name: 'Foundry Lofts' },
  { id: '944', name: 'Rail Yard Phase II' },
];

export default function GridDemo() {
  const [modal, setModal] = useState(null);
  const [toast, setToast] = useState(null);
  const [projectId, setProjectId] = useState('450');

  function fireAction(label) {
    setToast(label);
    setTimeout(() => setToast(null), 1600);
  }

  // KPI tiles: pinned 1x1 — a single number has no denser state, so no resize chips.
  const kpiPanels = KPIS.map(k => ({
    id: k.id,
    title: k.title,
    variant: 'kpi',
    sizes: [1],
    rowSizes: [1],
    render: () => (
      <div>
        <div className={`text-2xl font-bold tabular-nums ${TONE_CLASS[k.tone]}`}>{k.value}</div>
        <div className="text-[11px] uppercase tracking-wide text-gray-400 dark:text-slate-500 mt-0.5 truncate">
          {k.title}
        </div>
        {k.blocked && (
          <div className="text-[10px] text-amber-600 dark:text-amber-400 mt-0.5 truncate">{k.blocked}</div>
        )}
      </div>
    ),
  }));

  // The closed catalog of detail panels, straight from Bill's Projects-page spec.
  const detailPanels = [
    {
      id: 'submittals', title: 'Submittals', dot: 'blue', rows: 3,
      onOpen: () => setModal('Submittals'),
      headerAction: <ActionLink onClick={() => fireAction('Submittals → View All')}>View All</ActionLink>,
      render: ({ rows }) => <DensityList rows={rows} items={DATA.submittals} mono={false} />,
    },
    {
      id: 'releases', title: 'Releases', dot: 'green', rows: 3,
      onOpen: () => setModal('Releases'),
      headerAction: <ActionLink onClick={() => fireAction('Releases → View All')}>View All</ActionLink>,
      render: ({ rows }) => (
        <DensityList rows={rows} items={DATA.releases.map(([a, b, c]) => [a, `${b} · ${c}`])} />
      ),
    },
    {
      id: 'schedule', title: 'Schedule', dot: 'yellow', rows: 3,
      onOpen: () => setModal('Schedule'),
      render: ({ rows }) => <DensityList rows={rows} items={DATA.schedule} mono={false} />,
    },
    {
      id: 'budget', title: 'Budget', dot: 'teal', rows: 2,
      isEmpty: true,
      empty: (
        <div className="py-4 text-center">
          <p className="text-xs text-gray-400 dark:text-slate-500">Pending source</p>
          <p className="mt-1 text-[11px] text-amber-600 dark:text-amber-400">
            spec says “approved Pay App line items” — no Pay App data exists yet
          </p>
        </div>
      ),
      render: () => null,
    },
    {
      id: 'tm', title: 'T&M Tickets', dot: 'purple', rows: 2,
      isEmpty: true,
      empty: (
        <div className="py-4 text-center">
          <p className="text-xs text-gray-400 dark:text-slate-500">No T&M tickets</p>
          <p className="mt-1 text-[11px] text-amber-600 dark:text-amber-400">lands with A1</p>
        </div>
      ),
      render: () => null,
    },
    {
      id: 'co', title: 'Change Orders', dot: 'pink', rows: 2,
      isEmpty: true,
      empty: (
        <div className="py-4 text-center">
          <p className="text-xs text-gray-400 dark:text-slate-500">No change orders</p>
          <p className="mt-1 text-[11px] text-amber-600 dark:text-amber-400">lands with A2</p>
        </div>
      ),
      render: () => null,
    },
    {
      id: 'rentals', title: 'Rentals', dot: 'orange', rows: 2,
      onOpen: () => setModal('Rentals'),
      headerAction: <ActionLink onClick={() => fireAction('Rentals → Manage')}>Manage</ActionLink>,
      render: ({ rows }) => <DensityList rows={rows} items={DATA.rentals} mono={false} />,
    },
    {
      id: 'rfis', title: 'RFI Log', dot: 'red', rows: 2,
      isEmpty: true,
      empty: <p className="py-6 text-center text-xs text-gray-400 dark:text-slate-500">No open RFIs</p>,
      headerAction: <ActionLink onClick={() => fireAction('RFI → Add')}>+ Add RFI</ActionLink>,
      render: () => null,
    },
    {
      id: 'punch', title: 'Punch List', dot: 'yellow', rows: 2,
      onOpen: () => setModal('Punch List'),
      render: ({ rows }) => <DensityList rows={rows} items={DATA.punch} mono={false} />,
    },
    {
      id: 'contacts', title: 'Project Contacts', dot: 'gray', rows: 2,
      onOpen: () => setModal('Project Contacts'),
      headerAction: <ActionLink onClick={() => fireAction('Contacts → Manage')}>Manage</ActionLink>,
      render: ({ rows }) => <DensityList rows={rows} items={DATA.contacts} mono={false} />,
    },
    {
      id: 'drawings', title: 'Drawings', dot: 'gray', rows: 2,
      onOpen: () => setModal('Drawings'),
      render: ({ rows }) => <DensityList rows={rows} items={DATA.drawings} />,
    },
    {
      id: 'notes', title: 'Project Notes', dot: 'purple', span: 2, rows: 2,
      onOpen: () => setModal('Project Notes'),
      headerAction: <ActionLink onClick={() => fireAction('Notes → Add')}>+ Add Note</ActionLink>,
      render: () => (
        <div className="space-y-2 text-sm text-gray-700 dark:text-slate-300">
          <p>GC pushed Bld C install a week — confirm crew availability.</p>
          <p>Paint color change approved verbally, waiting on written CO.</p>
        </div>
      ),
    },
    {
      id: 'todo', title: 'Project To-Do', dot: 'teal', span: 2, rows: 2,
      onOpen: () => setModal('Project To-Do'),
      headerAction: <ActionLink onClick={() => fireAction('To-Do → Add')}>+ Add Task</ActionLink>,
      render: () => (
        <div className="space-y-2 text-sm text-gray-700 dark:text-slate-300">
          <p>Send Bld B guardrail submittal to GC · due Jul 25</p>
          <p>Confirm embed layout with structural engineer · due Jul 29</p>
        </div>
      ),
    },
  ];

  const panels = [...kpiPanels, ...detailPanels];
  const project = PROJECTS.find(p => p.id === projectId);

  return (
    <div className="flex-1 w-full bg-[#f8fafc] dark:bg-slate-900">
      <div className="max-w-7xl mx-auto px-4 lg:px-6 py-6">
        <div className="mb-4">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-xl font-bold text-gray-900 dark:text-slate-100">K2 Grid Engine</h1>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wide
              bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
              Temporary harness
            </span>
          </div>

          {/* One layout, many projects: switching project changes data, never the arrangement. */}
          <div className="mt-3 flex items-center gap-2 flex-wrap">
            <span className="text-xs text-gray-500 dark:text-slate-400">Project:</span>
            {PROJECTS.map(p => (
              <button
                key={p.id}
                type="button"
                onClick={() => setProjectId(p.id)}
                className={`text-xs font-medium px-2.5 py-1 rounded-lg transition-colors ${
                  projectId === p.id
                    ? 'bg-accent-500 text-white'
                    : 'bg-gray-100 dark:bg-slate-700 text-gray-600 dark:text-slate-300 hover:bg-gray-200 dark:hover:bg-slate-600'
                }`}
              >
                {p.id} · {p.name}
              </button>
            ))}
            <span className="text-[11px] text-gray-400 dark:text-slate-500">
              — layout stays put; only the data would change
            </span>
          </div>

          <p className="mt-2.5 text-sm text-gray-500 dark:text-slate-400">
            <strong className="text-gray-700 dark:text-slate-200">Edit layout:</strong> ↔ width and
            ↕ height. On list panels, <em>bigger means more rows</em>, not just a bigger box —
            watch the “+N more” line. KPI tiles are pinned 1×1 (no chips) since a number has no
            denser state; you can still move or remove them. The catalog is closed — the tray only
            re-offers what Bill’s spec lists.
          </p>
        </div>

        <PanelGrid surfaceKey="projects" panels={panels} columns={4} />

        <p className="mt-4 text-[11px] text-gray-400 dark:text-slate-500">
          Layout is saved once under <code>projects</code> — shared by every project, per user.
          Currently viewing {project.id} · {project.name}.
        </p>
      </div>

      {modal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => setModal(null)}
        >
          <div
            className="w-full max-w-md rounded-lg bg-white dark:bg-slate-800 shadow-xl p-5"
            onClick={e => e.stopPropagation()}
          >
            <h2 className="text-base font-semibold text-gray-900 dark:text-slate-100">{modal} — detail modal</h2>
            <p className="mt-2 text-sm text-gray-500 dark:text-slate-400">
              This is the drill-through target — the full list, regardless of tile size.
            </p>
            <button
              type="button"
              onClick={() => setModal(null)}
              className="mt-4 px-3 py-1.5 text-sm font-medium rounded-lg bg-accent-500 text-white hover:bg-accent-600"
            >
              Close
            </button>
          </div>
        </div>
      )}

      {toast && (
        <div className="fixed bottom-5 left-1/2 -translate-x-1/2 z-50 px-3.5 py-2 rounded-lg
          bg-slate-900 dark:bg-slate-700 text-white text-sm shadow-lg">
          {toast} — action slot fired, modal stayed closed
        </div>
      )}
    </div>
  );
}
