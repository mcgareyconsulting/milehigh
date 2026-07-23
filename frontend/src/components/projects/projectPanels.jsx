/**
 * @milehigh-header
 * schema_version: 2
 * purpose: The Projects page's CLOSED panel catalog — the thirteen boxes from
 *   docs/projects-page-mockup.html expressed as K2 box-contract descriptors, plus the
 *   drill-through content for each. A panel and its detail view live together here so they
 *   cannot drift apart; the bodies themselves are in projectPanelBodies.jsx.
 * exports:
 *   buildProjectPanels(project, handlers): panel descriptors for PanelGrid
 *   renderProjectModal(panelId, project): the drill-through body for a panel
 *   PROJECT_MODAL_TITLES: panel id -> modal title
 * imports_from: [./vocab, ./PanelModal, ./projectPanelBodies]
 * imported_by: [pages/GridDemo.jsx]
 * invariants:
 *   - Every panel id here is stable — it is the layout persistence key.
 *   - A panel with no data source yet renders an explicit "why" (isEmpty + empty), never a
 *     fabricated number. Budget/T&M/CO have no backing model in app/models.py.
 *   - The modal is never sliced by size: the panel body is a summary, this is everything.
 *   - DEFAULT_HEIGHTS_TILE: the default `rows` values must leave NO empty cells in a
 *     3-column grid. Panel heights are quantized, so CSS grid can only start a full-width
 *     panel once every column has reached the same depth — if the per-column row totals do
 *     not agree, the browser leaves visible holes. `dense` packing does not rescue this: the
 *     holes land at the tail of the flow with no later panel small enough to backfill them.
 *     Budget and Drawings sit at 4 rather than 3 purely to make the columns balance.
 *     projectPanels.test.jsx replays the auto-placement algorithm and fails on any hole, so
 *     adding or resizing a panel here means re-checking that sum.
 */
import { Badge, PanelAction } from './vocab';
import { ModalSection, ModalRow } from './PanelModal';
import {
  EmptyNote,
  Tracker,
  CarmenBanner,
  SubmittalsBody,
  ReleasesBody,
  ScheduleBody,
  BudgetBody,
  TmBody,
  RentalsBody,
  CoBody,
  RfiBody,
  PunchBody,
  ContactsBody,
  DrawingsBody,
  NotesBody,
  TodoBody,
} from './projectPanelBodies';

// ── catalog ──────────────────────────────────────────────────────────────────────────

/**
 * Build the panel descriptors for one project.
 * @param project  a shape from demoProjects.js (D1 swaps this for live data)
 * @param onOpen   (panelId) => void — header click, opens the drill-through modal
 * @param onAction (label)   => void — the header action chip; must never drill through
 */
export function buildProjectPanels(project, { onOpen, onAction }) {
  const open = id => () => onOpen(id);
  const act = (label, text) => <PanelAction onClick={() => onAction(label)}>{text}</PanelAction>;

  return [
    {
      id: 'submittals', title: 'Submittals', dot: 'blue', rows: 4,
      onOpen: open('submittals'), headerAction: act('Submittals → View All', 'View All'),
      isEmpty: project.submittals.length === 0,
      empty: <EmptyNote>No submittals on this project</EmptyNote>,
      render: ({ rows }) => <SubmittalsBody rows={rows} project={project} />,
    },
    {
      id: 'releases', title: 'Releases', dot: 'green', rows: 3,
      onOpen: open('releases'), headerAction: act('Releases → View All', 'View All'),
      isEmpty: project.releases.length === 0,
      empty: <EmptyNote>No releases yet</EmptyNote>,
      render: ({ rows }) => <ReleasesBody rows={rows} project={project} />,
    },
    {
      id: 'schedule', title: 'Schedule', dot: 'yellow', rows: 3,
      onOpen: open('schedule'), headerAction: act('Schedule → Full Timeline', 'Full Timeline'),
      isEmpty: project.schedule.length === 0,
      empty: <EmptyNote>No installs scheduled</EmptyNote>,
      render: ({ rows }) => <ScheduleBody rows={rows} project={project} />,
    },
    {
      // rows:4 (not 3) is load-bearing for the tiling — see DEFAULT_HEIGHTS_TILE below.
      id: 'budget', title: 'Budget', dot: 'teal', rows: 4,
      onOpen: project.budget ? open('budget') : undefined,
      headerAction: project.budget ? act('Budget → Full Report', 'Full Report') : undefined,
      isEmpty: !project.budget,
      empty: <EmptyNote why="spec sources this from approved Pay App line items — no Pay App model exists yet">
        Budget unavailable
      </EmptyNote>,
      render: () => <BudgetBody project={project} />,
    },
    {
      id: 'tm', title: 'T&M Tickets', dot: 'purple', rows: 2,
      onOpen: project.tm.length ? open('tm') : undefined,
      headerAction: act('T&M → View All', 'View All'),
      isEmpty: project.tm.length === 0,
      empty: <EmptyNote why="lands with A1 (digital T&M)">No T&amp;M tickets</EmptyNote>,
      render: ({ rows }) => <TmBody rows={rows} project={project} />,
    },
    {
      id: 'rentals', title: 'Rentals', dot: 'orange', rows: 2,
      onOpen: project.rentals.length ? open('rentals') : undefined,
      headerAction: act('Rentals → Manage', 'Manage'),
      isEmpty: project.rentals.length === 0,
      empty: <EmptyNote>No active rentals</EmptyNote>,
      render: ({ rows }) => <RentalsBody rows={rows} project={project} />,
    },
    {
      id: 'co', title: 'Change Orders', dot: 'pink', rows: 2,
      onOpen: project.co.length ? open('co') : undefined,
      headerAction: act('Change Orders → View All', 'View All'),
      isEmpty: project.co.length === 0,
      empty: <EmptyNote why="lands with A2 (T&M → CO)">No change orders</EmptyNote>,
      render: ({ rows }) => <CoBody rows={rows} project={project} />,
    },
    {
      id: 'rfi', title: 'RFI Log', dot: 'cyan', rows: 2,
      onOpen: project.rfi.length ? open('rfi') : undefined,
      headerAction: act('RFI → View All', 'View All'),
      isEmpty: project.rfi.length === 0,
      empty: <EmptyNote why="revived as A6 in Bill's package">No RFIs logged</EmptyNote>,
      render: ({ rows }) => <RfiBody rows={rows} project={project} />,
    },
    {
      id: 'punch', title: 'Punch List', dot: 'green', rows: 2,
      onOpen: project.punch.length ? open('punch') : undefined,
      headerAction: act('Punch List → View All', 'View All'),
      isEmpty: project.punch.length === 0,
      empty: <EmptyNote>No punch items</EmptyNote>,
      render: ({ rows }) => <PunchBody rows={rows} project={project} />,
    },
    {
      id: 'contacts', title: 'Project Contacts', dot: 'indigo', rows: 2,
      onOpen: open('contacts'), headerAction: act('Contacts → Edit', 'Edit'),
      render: ({ rows }) => <ContactsBody rows={rows} project={project} />,
    },
    {
      // rows:4 (not 3) is load-bearing for the tiling — see DEFAULT_HEIGHTS_TILE below.
      id: 'drawings', title: 'Drawings', dot: 'blue', rows: 4,
      onOpen: open('drawings'), headerAction: act('Drawings → View All', 'View All'),
      render: ({ rows }) => <DrawingsBody rows={rows} project={project} />,
    },
    {
      id: 'notes', title: 'Project Notes', dot: 'yellow', span: 2, rows: 3,
      onOpen: open('notes'), headerAction: act('Notes → Add', '+ Add Note'),
      isEmpty: project.notes.length === 0,
      empty: <EmptyNote>No project notes</EmptyNote>,
      render: ({ span, rows }) => <NotesBody span={span} rows={rows} project={project} />,
    },
    {
      id: 'todo', title: 'Project To-Do', dot: 'pink', span: 3, rows: 3,
      onOpen: open('todo'), headerAction: act('To-Do → Add', '+ Add Task'),
      isEmpty: project.todo.length === 0,
      empty: <EmptyNote>Nothing on the list</EmptyNote>,
      render: ({ span, rows }) => <TodoBody span={span} rows={rows} project={project} />,
    },
  ];
}

// ── drill-through ────────────────────────────────────────────────────────────────────

export const PROJECT_MODAL_TITLES = {
  submittals: '📋 Submittals — Full Detail',
  releases: '🔩 Releases — Full Detail',
  schedule: '📅 Schedule — Full Timeline',
  budget: '💰 Budget — Full Report',
  tm: '🔧 T&M Tickets — Full Detail',
  rentals: '🏗 Rentals — Full Detail',
  co: '📝 Change Orders — Full Detail',
  rfi: '❓ RFI Log — Full Detail',
  punch: '✅ Punch List — Full Detail',
  contacts: '👥 Project Contacts',
  drawings: '📐 Drawings — Full Set',
  notes: '📌 Project Notes — Full View',
  todo: '✏️ Project To-Do — All Tasks',
};

/**
 * The modal body for a panel. Unlike the panel body this is never sliced by size — the whole
 * point of the drill-through is that it shows everything regardless of how small the tile is.
 */
export function renderProjectModal(id, project) {
  // Budget is the one section backed by a source that does not exist yet, so it is the one
  // that can legitimately be absent. The panel header is inert in that case, but the modal
  // must not depend on that to stay safe — a future caller opening it directly would crash.
  if (id === 'budget' && !project.budget) {
    return (
      <ModalSection title="Budget">
        <ModalRow label="Status">
          Unavailable — the spec sources this from approved Pay App line items, and no Pay App
          data exists yet.
        </ModalRow>
      </ModalSection>
    );
  }

  switch (id) {
    case 'submittals':
      return (
        <ModalSection title="Submittal Status Overview">
          {project.submittals.map(s => (
            <ModalRow key={s.name} label={s.name}>
              {s.badge
                ? <Badge tone={s.badge.tone}>{s.badge.text}</Badge>
                : <Badge tone={s.flag === 'overdue' ? 'red' : 'orange'}>{s.flagText}</Badge>}
              <span className="text-[#64748b] text-[12px]">{s.days || s.meta}</span>
            </ModalRow>
          ))}
        </ModalSection>
      );
    case 'releases':
      return (
        <>
          <ModalSection title="Release Status">
            {project.releases.map(r => (
              <ModalRow key={r.code} label={`${r.code} ${r.name}`}>
                <Badge tone={r.badge.tone}>{r.badge.text}</Badge>
                <Tracker done={r.done} active={r.active} />
              </ModalRow>
            ))}
          </ModalSection>
          <ModalSection title="Department Progress Legend">
            <ModalRow label="● Draft">Drafting &amp; DRR complete</ModalRow>
            <ModalRow label="● Shop">Fabrication complete</ModalRow>
            <ModalRow label="● Paint">Paint &amp; finish complete</ModalRow>
            <ModalRow label="● Install">Field installation complete</ModalRow>
          </ModalSection>
        </>
      );
    case 'schedule':
      return (
        <ModalSection title="Upcoming Install Dates">
          {project.schedule.map(s => (
            <ModalRow
              key={s.title}
              label={`${s.month} ${s.day} — ${s.type === 'hard' ? 'HARD DATE' : 'Projected'}`}
              labelClass={s.type === 'hard' ? 'text-[#4ade80]' : 'text-[#fbbf24]'}
            >
              {s.title} · {s.sub}
            </ModalRow>
          ))}
        </ModalSection>
      );
    case 'budget':
      return (
        <>
          <ModalSection title="Budget Breakdown">
            {project.budget.sections.map(s => (
              <ModalRow key={s.label} label={s.label}>
                {s.spent} ({s.pct}%) · {s.left}
              </ModalRow>
            ))}
          </ModalSection>
          <ModalSection title="Billing Summary">
            <ModalRow label="Contract Total">{project.budget.contract}</ModalRow>
            <ModalRow label="Billed to Date">
              <span className="text-[#60a5fa]">{project.budget.billed}</span>
            </ModalRow>
          </ModalSection>
        </>
      );
    case 'tm':
      return (
        <>
          <ModalSection title="Active Tickets">
            {project.tm.map(t => (
              <ModalRow key={t.id} label={`${t.id} — ${t.desc}`}>
                {t.amount} <Badge tone={t.badge.tone}>{t.badge.text}</Badge>
              </ModalRow>
            ))}
          </ModalSection>
          <ModalSection title="O&P Structure (per contract Exhibit B, Sec 4.2)">
            <ModalRow label="Overhead">15%</ModalRow>
            <ModalRow label="Profit">10%</ModalRow>
            <ModalRow label="GC Signature Required">
              <span className="text-[#4ade80]">Yes — on-site, no exceptions</span>
            </ModalRow>
          </ModalSection>
        </>
      );
    case 'rentals':
      return (
        <ModalSection title="Active Equipment Rentals">
          {project.rentals.map(r => (
            <ModalRow key={r.name} label={r.name}>
              {r.cost ? `${r.cost} · ${r.dates}` : r.dates}
            </ModalRow>
          ))}
        </ModalSection>
      );
    case 'co':
      return (
        <ModalSection title="Change Order Log">
          {project.co.map(c => (
            <ModalRow key={c.id} label={`${c.id} — ${c.desc}`}>
              {c.amount} <Badge tone={c.badge.tone}>{c.badge.text}</Badge>
            </ModalRow>
          ))}
        </ModalSection>
      );
    case 'rfi':
      return (
        <ModalSection title="RFI Status">
          {project.rfi.map(r => (
            <ModalRow key={r.id} label={`${r.id} — ${r.desc}`}>
              <Badge tone={r.badge.tone}>{r.badge.text}</Badge>
              <span className="text-[#64748b] text-[12px]">{r.days}</span>
            </ModalRow>
          ))}
        </ModalSection>
      );
    case 'punch':
      return (
        <ModalSection title="Punch Items">
          {project.punch.map(p => (
            <ModalRow
              key={p.desc}
              label={p.desc}
              labelClass={p.done ? 'text-[#475569] line-through' : ''}
            >
              <Badge tone={p.done ? 'green' : 'yellow'}>{p.done ? 'Done' : 'Open'}</Badge>
              <span className="text-[#64748b] text-[12px]">{p.owner}</span>
            </ModalRow>
          ))}
        </ModalSection>
      );
    case 'contacts':
      return (
        <ModalSection title="Project Team">
          {project.contacts.map(c => (
            <ModalRow key={c.name} label={c.name}>{c.role}</ModalRow>
          ))}
        </ModalSection>
      );
    case 'drawings':
      return (
        <>
          <ModalSection title="Active Drawing Sets">
            {project.drawings.sets.map(s => (
              <ModalRow key={s.name} label={s.name}>
                <Badge tone={s.badge.tone}>{s.badge.text}</Badge>
              </ModalRow>
            ))}
          </ModalSection>
          <ModalSection title="Cover Sheet Info">
            <ModalRow label="Project">{project.drawings.cover.location}</ModalRow>
            {project.drawings.cover.facts.flat().map(f => {
              const [k, ...rest] = f.split(':');
              return <ModalRow key={f} label={k}>{rest.join(':').trim()}</ModalRow>;
            })}
          </ModalSection>
        </>
      );
    case 'notes':
      return (
        <>
          <CarmenBanner />
          <ModalSection title="All Notes">
            {project.notes.map(n => (
              <ModalRow key={n.type + n.meta} label={`${n.type} — ${n.meta}`} labelClass="shrink-0">
                <span className="text-[12px] font-normal text-left">{n.body}</span>
              </ModalRow>
            ))}
          </ModalSection>
        </>
      );
    case 'todo':
      return (
        <>
          <ModalSection title="Open Tasks">
            {project.todo.filter(t => !t.done).map(t => (
              <ModalRow key={t.task} label={`${t.task} — ${t.who.name}`}>
                <Badge tone={t.status.tone}>{t.due}</Badge>
              </ModalRow>
            ))}
          </ModalSection>
          {project.todo.some(t => t.done) && (
            <ModalSection title="Completed">
              {project.todo.filter(t => t.done).map(t => (
                <ModalRow key={t.task} label={`${t.task} — ${t.who.name}`} labelClass="text-[#475569] line-through">
                  <Badge tone="green">Done — {t.due}</Badge>
                </ModalRow>
              ))}
            </ModalSection>
          )}
        </>
      );
    default:
      return null;
  }
}
