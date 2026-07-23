/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Demo project data in the shape the Projects page panels consume. #450 Sandstone
 *   Ranch is transcribed verbatim from docs/projects-page-mockup.html so the page can be
 *   compared side by side with Bill's template; 560 and 944 are thinner stand-ins that exist
 *   only to prove the D1 rule that switching project changes the DATA and never the LAYOUT.
 *   This is the seam D1 replaces: keep the shape, swap the source.
 * exports:
 *   DEMO_PROJECTS: array of project objects, richest first
 * imports_from: []
 * imported_by: [pages/GridDemo.jsx]
 * invariants:
 *   - `blocked` on a KPI means "no data source exists yet" — the value must stay '—'.
 *     Never invent a number for a metric the backend cannot produce (Pay Apps, T&M, COs).
 */

const SANDSTONE = {
  number: '450',
  name: 'Sandstone Ranch',
  gc: 'PermaCorp Group',
  pm: 'Danny Riddell',
  contract: '$487,200',
  start: 'Mar 2025',
  statuses: [
    { tone: 'blue', text: 'In Production' },
    { tone: 'yellow', text: 'Submittals: 4/6 Approved' },
    { tone: 'yellow', text: '2 Open RFIs' },
    { tone: 'red', text: '1 CO Pending GC' },
  ],
  // The mockup's 8-cell KPI strip. Four of these have no backing table in app/models.py yet
  // (no PayApp, Budget, ChangeOrder or TMTicket model), so they show the gap instead of a number.
  kpis: [
    { id: 'total_releases', label: 'Total Releases', value: '6', tone: 'accent' },
    { id: 'fc_released', label: 'FC Released', value: '4', tone: 'green' },
    { id: 'in_drafting', label: 'In Drafting', value: '2', tone: 'yellow' },
    { id: 'billed', label: 'Billed to Date', value: '—', tone: 'muted', blocked: 'needs Pay Apps' },
    { id: 'remaining', label: 'Remaining', value: '—', tone: 'muted', blocked: 'needs contract value' },
    { id: 'open_tm', label: 'Open T&M Tickets', value: '—', tone: 'muted', blocked: 'lands with A1' },
    { id: 'co_pending', label: 'CO Value Pending', value: '—', tone: 'muted', blocked: 'lands with A2' },
    { id: 'overdue', label: 'Overdue Item', value: '1', tone: 'purple' },
  ],
  submittals: [
    { name: 'Structural Steel', meta: 'Submitted Mar 12 · Returned Mar 24', badge: { tone: 'green', text: 'Approved' } },
    { name: 'Bld A Stair #1', meta: 'Submitted Apr 2 · Returned Apr 18', badge: { tone: 'purple', text: 'Appr. as Noted' } },
    { name: 'Bld A Stair #3', meta: 'Submitted Jul 13 · Awaiting GC response', flag: 'out', flagText: '⏳ Out to GC', days: '9 days · follow-up in 5 days' },
    { name: 'Bld A Balcony Rails', meta: 'Submitted Jul 6 · Awaiting GC response', flag: 'overdue', flagText: '⚠ Overdue', days: '16 days · BB01 follow-up sent Jul 20' },
    { name: 'Bld B Guardrails', meta: 'Returned Jul 15 · Revisions in progress', badge: { tone: 'yellow', text: 'Rev. & Resubmit' } },
    { name: 'Bld C Entry Gate', meta: 'Drafting in progress', badge: { tone: 'gray', text: 'In Prep' } },
    { name: 'Bld A Stair #2', meta: 'Submitted Apr 4 · Returned Apr 20', badge: { tone: 'green', text: 'Approved' } },
  ],
  submittalSummary: '3 approved · 2 out to GC · 1 revising',
  // `done` counts completed department stages; the 4 dots are Draft / Shop / Paint / Install.
  releases: [
    { code: '450-700', name: 'Structural Steel', done: 4, badge: { tone: 'green', text: 'Complete' } },
    { code: '450-760', name: 'Bld A Stair #1', done: 3, active: true, badge: { tone: 'blue', text: 'Installing' } },
    { code: '450-759', name: 'Bld A Stair #2', done: 2, active: true, badge: { tone: 'purple', text: 'In Paint' } },
    { code: '450-747', name: 'Bld A Stair #3', done: 1, active: true, badge: { tone: 'yellow', text: 'In Shop' } },
    { code: '450-344', name: 'Bld A Balcony Rails', done: 0, active: true, badge: { tone: 'gray', text: 'Drafting' } },
    { code: '450-381', name: 'Bld B Guardrails', done: 0, active: true, badge: { tone: 'orange', text: 'DRR Needed' } },
  ],
  schedule: [
    { month: 'Jul', day: '28', type: 'hard', title: 'Bld A Stair #1 Install', sub: 'Crew 1 · 450-760 · 2 days est.' },
    { month: 'Aug', day: '4', type: 'proj', title: 'Bld A Stair #2 Install', sub: 'Crew 1 · 450-759 · 2 days est.' },
    { month: 'Aug', day: '11', type: 'hard', title: 'Bld A Stair #3 Install', sub: 'Crew 2 · 450-747 · 2 days est.' },
    { month: 'Aug', day: '18', type: 'proj', title: 'Bld A Balcony Rails Install', sub: 'Crew 1 · 450-344 · 3 days est.' },
    { month: 'Sep', day: '8', type: 'proj', title: 'Bld B Guardrails Install', sub: 'Crew 2 · 450-381 · 2 days est.' },
  ],
  budget: {
    sections: [
      { label: 'Labor', pct: 68, tone: 'yellow', spent: '$89,200 spent', left: '$41,800 left' },
      { label: 'Materials', pct: 52, tone: 'green', spent: '$124,600 spent', left: '$115,400 left' },
      { label: 'Subcontractors', pct: 88, tone: 'red', spent: '$44,000 spent', left: '$6,000 left', leftTone: 'red' },
    ],
    contract: '$487,200',
    billed: '$312,400 (64%)',
  },
  tm: [
    { id: 'TM-001', desc: 'Extra blocking — Stair #1 landing', amount: '$1,840', badge: { tone: 'green', text: 'Approved' } },
    { id: 'TM-002', desc: 'Field weld — Stair #2 stringer', amount: '$620', badge: { tone: 'yellow', text: 'Pending GC' } },
    { id: 'TM-003', desc: 'Railing mod — Balcony B2', amount: '$2,100', badge: { tone: 'yellow', text: 'Pending GC' } },
    { id: 'TM-004', desc: 'Misc hardware — Stair #3', amount: '$390', badge: { tone: 'gray', text: 'Draft' } },
  ],
  tmTotal: '$4,950',
  rentals: [
    { name: 'Scissor Lift — 26ft', dates: 'Jul 14 – Aug 2 · United Rentals', cost: '$3,200' },
    { name: 'Boom Lift — 60ft', dates: 'Jul 28 – Aug 15 · Sunbelt', cost: '$5,800' },
    { name: 'Welding Machine', dates: 'Jul 1 – Aug 30 · MHMW Owned', badge: { tone: 'gray', text: 'Internal' } },
  ],
  rentalTotal: '$9,000',
  co: [
    { id: 'CO-001', desc: 'Stair #1 landing extension', amount: '$8,400', badge: { tone: 'green', text: 'Executed' } },
    { id: 'CO-002', desc: 'Balcony rail height revision', amount: '$12,600', badge: { tone: 'green', text: 'Executed' } },
    { id: 'CO-003', desc: 'Bld B scope addition', amount: '$28,400', badge: { tone: 'red', text: 'Pending GC' } },
  ],
  coExecuted: '$21,000',
  rfi: [
    { id: 'RFI-001', desc: 'Stair #3 top connection detail', days: 'Answered', badge: { tone: 'green', text: 'Closed' } },
    { id: 'RFI-002', desc: 'Balcony rail post embed depth', days: '8 days open', daysTone: 'yellow', badge: { tone: 'yellow', text: 'Open' } },
    { id: 'RFI-003', desc: 'Bld B guardrail height variance', days: '14 days open', daysTone: 'red', badge: { tone: 'red', text: 'Overdue' } },
  ],
  punch: [
    { done: true, desc: 'Touch-up paint — Stair #1 handrail', owner: 'Crew 1' },
    { done: true, desc: 'Tighten loose post — Stair #1 landing', owner: 'Crew 1' },
    { done: false, desc: 'Missing cap plate — Stair #2 top post', owner: 'Crew 2' },
    { done: false, desc: 'Grout anchor — Balcony B3 post', owner: 'Crew 1' },
    { done: false, desc: 'Final inspection sign-off — Stair #1', owner: 'Danny R.' },
  ],
  contacts: [
    { initials: 'DR', bg: '#1e3a5f', fg: '#60a5fa', name: 'Danny Riddell', role: 'MHMW Project Manager · driddell@mhmw.com' },
    { initials: 'SK', bg: '#14532d', fg: '#4ade80', name: 'Steve Kalynchuk', role: 'GC — PermaCorp President · 780-999-5725' },
    { initials: 'ST', bg: '#3b1f6e', fg: '#a78bfa', name: 'Scott Tatum', role: 'GC — Site Super · statum@permacorp.com' },
    { initials: 'BO', bg: '#78350f', fg: '#fbbf24', name: "Bill O'Neill", role: 'MHMW Director of Ops · boneill@mhmw.com' },
  ],
  drawings: {
    cover: {
      title: 'Sandstone Ranch',
      location: 'Frederick, CO · Project #450',
      facts: [
        ['GC: PermaCorp Group', 'Arch: Studio West'],
        ['Struct. Eng: RME', 'Rev: IFC Set 03-06-25'],
        ['Contract: $487,200', 'Sheets: 142'],
      ],
      sheets: 'S-001 · S-101 · S-102 · S-103',
      more: '+138 more',
    },
    sets: [
      { name: 'Structural Steel — IFC Set', badge: { tone: 'green', text: 'Current' } },
      { name: 'Architectural Plans — Full Set', badge: { tone: 'blue', text: 'Rev 08' } },
      { name: 'Geotechnical Report', badge: { tone: 'gray', text: 'Reference' } },
    ],
  },
  notes: [
    {
      type: '⚠ Follow-Up Required', typeColor: '#fb923c', meta: 'Jul 18 · Danny R.',
      bg: '#1c1408', border: '#ea580c44', accent: '#ea580c',
      body: 'GC confirmed closure plates for Bld A rails are delayed — back-order. Steve K. advised to proceed with install and return. Do not close out 450-344 until plates are installed.',
      badge: { tone: 'orange', text: 'Open' }, carmen: 'Carmen: flagged for billing review',
    },
    {
      type: '📋 Contract Note', typeColor: '#60a5fa', meta: 'Mar 5 · Bill O.',
      bg: '#0d1117', border: '#2a2d3e', accent: '#2563eb',
      body: 'O&P on T&M work is 15% overhead / 10% profit per Exhibit B, Section 4.2. All T&M must have GC rep signature on site — no exceptions.',
      badge: { tone: 'blue', text: 'Permanent' }, carmen: 'Carmen: applied to all T&M tickets',
    },
    {
      type: '📅 Schedule Note', typeColor: '#4ade80', meta: 'Jul 21 · Danny R.',
      bg: '#0d1117', border: '#2a2d3e', accent: '#22c55e',
      body: 'GC look-ahead (week of Jul 28): Stair #1 area open for install. Stair #2 area concrete in progress — do NOT schedule Crew 1 for Stair #2 until Aug 4. Confirmed with Scott T.',
      badge: { tone: 'green', text: 'Noted' }, carmen: 'Carmen: applied to schedule',
    },
    {
      type: '📦 Material Note', typeColor: '#c084fc', meta: 'Jul 15 · Danny R.',
      bg: '#0d1117', border: '#2a2d3e', accent: '#a855f7',
      body: 'Architect confirmed Ultralox infill panels are acceptable VE substitution for Bld B guardrails (CO-003 scope). Saves ~$4,200. Proceed with Ultralox for 450-381.',
      badge: { tone: 'purple', text: 'VE Approved' }, carmen: 'Carmen: linked to 450-381',
    },
  ],
  todo: [
    {
      task: 'Confirm closure plate delivery date with Steve K.', link: 'Linked: 450-344 · Bld A Balcony Rails',
      who: { initials: 'DR', bg: '#1e3a5f', fg: '#60a5fa', name: 'Danny R.' },
      due: '⚠ Jul 20 — Overdue', dueTone: 'red', overdue: true,
      priority: { tone: 'red', text: 'High' }, status: { tone: 'red', text: 'Overdue' },
    },
    {
      task: 'Submit CO-003 backup documentation to PermaCorp', link: 'Linked: CO-003 · Bld B scope addition',
      who: { initials: 'BO', bg: '#78350f', fg: '#fbbf24', name: 'Bill O.' },
      due: 'Jul 25', dueTone: 'yellow',
      priority: { tone: 'yellow', text: 'High' }, status: { tone: 'pink', text: 'Open' },
    },
    {
      task: 'Order Ultralox panels for 450-381 — confirm qty with David S.', link: 'Linked: 450-381 · Bld B Guardrails',
      who: { initials: 'DR', bg: '#1e3a5f', fg: '#60a5fa', name: 'Danny R.' },
      due: 'Jul 28',
      priority: { tone: 'gray', text: 'Medium' }, status: { tone: 'pink', text: 'Open' },
    },
    {
      task: 'Schedule final inspection sign-off with GC for Stair #1', link: 'Linked: 450-760 · Punch List',
      who: { initials: 'DR', bg: '#1e3a5f', fg: '#60a5fa', name: 'Danny R.' },
      due: 'Aug 1',
      priority: { tone: 'gray', text: 'Medium' }, status: { tone: 'pink', text: 'Open' },
    },
    {
      task: 'Verify Bld C Entry Gate scope with architect before DRR submission', link: 'Linked: Bld C Entry Gate · Submittals',
      who: { initials: 'DS', bg: '#14532d', fg: '#4ade80', name: 'David S.' },
      due: 'Aug 5',
      priority: { tone: 'gray', text: 'Medium' }, status: { tone: 'pink', text: 'Open' },
    },
    {
      done: true,
      task: 'Send Structural Steel submittal to PermaCorp', link: 'Completed Mar 12',
      who: { initials: 'DR', bg: '#1e3a5f', fg: '#60a5fa', name: 'Danny R.' },
      due: 'Mar 12',
      priority: { tone: 'green', text: 'Done' }, status: { tone: 'green', text: 'Complete' },
    },
  ],
  todoSummary: { open: 5, overdue: 1, completed: 1, assigned: 'Danny R. (3) · Bill O. (1) · David S. (1)' },
};

// Thinner projects — same shape, different data. They exist to demonstrate that picking a
// different project never rearranges the dashboard.
const FOUNDRY = {
  number: '560',
  name: 'Foundry Lofts',
  gc: 'Alta Construction',
  pm: 'Danny Riddell',
  contract: '$318,500',
  start: 'Jan 2026',
  statuses: [
    { tone: 'blue', text: 'In Drafting' },
    { tone: 'green', text: 'Submittals: 5/5 Approved' },
  ],
  kpis: [
    { id: 'total_releases', label: 'Total Releases', value: '9', tone: 'accent' },
    { id: 'fc_released', label: 'FC Released', value: '6', tone: 'green' },
    { id: 'in_drafting', label: 'In Drafting', value: '3', tone: 'yellow' },
    { id: 'billed', label: 'Billed to Date', value: '—', tone: 'muted', blocked: 'needs Pay Apps' },
    { id: 'remaining', label: 'Remaining', value: '—', tone: 'muted', blocked: 'needs contract value' },
    { id: 'open_tm', label: 'Open T&M Tickets', value: '—', tone: 'muted', blocked: 'lands with A1' },
    { id: 'co_pending', label: 'CO Value Pending', value: '—', tone: 'muted', blocked: 'lands with A2' },
    { id: 'overdue', label: 'Overdue Item', value: '0', tone: 'green' },
  ],
  submittals: [
    { name: 'Bldg A Embeds', meta: 'Submitted Feb 2 · Returned Feb 14', badge: { tone: 'green', text: 'Approved' } },
    { name: 'Bldg B Embeds', meta: 'Submitted Feb 2 · Returned Feb 14', badge: { tone: 'green', text: 'Approved' } },
    { name: 'Bldg C Stairs', meta: 'Submitted Mar 20 · Returned Apr 1', badge: { tone: 'green', text: 'Approved' } },
    { name: 'Bldg D Steel', meta: 'Drafting in progress', badge: { tone: 'gray', text: 'In Prep' } },
  ],
  submittalSummary: '3 approved · 1 in prep',
  releases: [
    { code: '560-526', name: 'Bldg B–D Embeds', done: 4, badge: { tone: 'green', text: 'Complete' } },
    { code: '560-923', name: 'Bldg C Steel', done: 1, active: true, badge: { tone: 'yellow', text: 'In Shop' } },
    { code: '560-944', name: 'Bldg D Steel', done: 0, active: true, badge: { tone: 'gray', text: 'Drafting' } },
  ],
  schedule: [
    { month: 'Jul', day: '24', type: 'hard', title: 'Bldg C Steel Install', sub: 'Crew 2 · 560-923 · 4 days est.' },
    { month: 'Aug', day: '4', type: 'proj', title: 'Bldg D Steel Install', sub: 'Crew 2 · 560-944 · 4 days est.' },
  ],
  budget: null,
  tm: [],
  rentals: [
    { name: 'Boom Lift — 45ft', dates: 'Jul 20 – Aug 10 · Sunbelt', cost: '$4,100' },
  ],
  rentalTotal: '$4,100',
  co: [],
  rfi: [],
  punch: [],
  contacts: [
    { initials: 'DR', bg: '#1e3a5f', fg: '#60a5fa', name: 'Danny Riddell', role: 'MHMW Project Manager · driddell@mhmw.com' },
    { initials: 'JM', bg: '#14532d', fg: '#4ade80', name: 'Jordan Mata', role: 'GC — Alta Superintendent' },
  ],
  drawings: {
    cover: {
      title: 'Foundry Lofts', location: 'Denver, CO · Project #560',
      facts: [['GC: Alta Construction', 'Arch: Semple Brown'], ['Struct. Eng: KL&A', 'Rev: IFC 12-18-25'], ['Contract: $318,500', 'Sheets: 96']],
      sheets: 'S-100 · S-101 · S-201', more: '+93 more',
    },
    sets: [
      { name: 'Structural — IFC Set', badge: { tone: 'green', text: 'Current' } },
      { name: 'Architectural — Full Set', badge: { tone: 'blue', text: 'Rev 03' } },
    ],
  },
  notes: [
    {
      type: '📅 Schedule Note', typeColor: '#4ade80', meta: 'Jul 20 · Danny R.',
      bg: '#0d1117', border: '#2a2d3e', accent: '#22c55e',
      body: 'GC 3-week lookahead has Bldg C install on Jul 24, but 560-923 is still sitting on the 80.555 placeholder fab order — it has not been queued.',
      badge: { tone: 'orange', text: 'Open' }, carmen: 'Carmen: flagged schedule gap',
    },
  ],
  todo: [
    {
      task: 'Queue 560-923 fab order — still on 80.555 placeholder', link: 'Linked: 560-923 · Bldg C Steel',
      who: { initials: 'DR', bg: '#1e3a5f', fg: '#60a5fa', name: 'Danny R.' },
      due: 'Jul 23', dueTone: 'yellow',
      priority: { tone: 'red', text: 'High' }, status: { tone: 'pink', text: 'Open' },
    },
  ],
  todoSummary: { open: 1, overdue: 0, completed: 0, assigned: 'Danny R. (1)' },
};

const RAILYARD = {
  number: '944',
  name: 'Rail Yard Phase II',
  gc: 'Hensel Phelps',
  pm: 'Bill O\'Neill',
  contract: '$1,120,000',
  start: 'Jun 2026',
  statuses: [{ tone: 'yellow', text: 'Pre-Construction' }],
  kpis: [
    { id: 'total_releases', label: 'Total Releases', value: '2', tone: 'accent' },
    { id: 'fc_released', label: 'FC Released', value: '0', tone: 'yellow' },
    { id: 'in_drafting', label: 'In Drafting', value: '2', tone: 'yellow' },
    { id: 'billed', label: 'Billed to Date', value: '—', tone: 'muted', blocked: 'needs Pay Apps' },
    { id: 'remaining', label: 'Remaining', value: '—', tone: 'muted', blocked: 'needs contract value' },
    { id: 'open_tm', label: 'Open T&M Tickets', value: '—', tone: 'muted', blocked: 'lands with A1' },
    { id: 'co_pending', label: 'CO Value Pending', value: '—', tone: 'muted', blocked: 'lands with A2' },
    { id: 'overdue', label: 'Overdue Item', value: '0', tone: 'green' },
  ],
  submittals: [
    { name: 'Platform Guardrails', meta: 'Drafting in progress', badge: { tone: 'gray', text: 'In Prep' } },
  ],
  submittalSummary: '1 in prep',
  releases: [
    { code: '944-101', name: 'Platform Guardrails', done: 0, active: true, badge: { tone: 'gray', text: 'Drafting' } },
    { code: '944-102', name: 'Egress Stairs', done: 0, active: true, badge: { tone: 'orange', text: 'DRR Needed' } },
  ],
  schedule: [],
  budget: null,
  tm: [],
  rentals: [],
  rentalTotal: '$0',
  co: [],
  rfi: [],
  punch: [],
  contacts: [
    { initials: 'BO', bg: '#78350f', fg: '#fbbf24', name: "Bill O'Neill", role: 'MHMW Director of Ops · boneill@mhmw.com' },
  ],
  drawings: {
    cover: {
      title: 'Rail Yard Phase II', location: 'Denver, CO · Project #944',
      facts: [['GC: Hensel Phelps', 'Arch: Gensler'], ['Struct. Eng: Martin/Martin', 'Rev: 50% DD'], ['Contract: $1,120,000', 'Sheets: 310']],
      sheets: 'S-000 · S-001', more: '+308 more',
    },
    sets: [{ name: 'Structural — 50% DD', badge: { tone: 'yellow', text: 'Not IFC' } }],
  },
  notes: [],
  todo: [],
  todoSummary: { open: 0, overdue: 0, completed: 0, assigned: '—' },
};

export const DEMO_PROJECTS = [SANDSTONE, FOUNDRY, RAILYARD];
