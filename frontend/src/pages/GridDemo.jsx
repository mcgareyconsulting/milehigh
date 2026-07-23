/**
 * @milehigh-header
 * schema_version: 4
 * purpose: TEMPORARY harness for the Projects page (route /grid-demo), styled to match
 *   docs/projects-page-mockup.html: dark surface, project header, a fixed 8-cell KPI strip,
 *   and the mockup's twelve-panel dashboard running on the K2 grid engine. It also carries the
 *   D1 contract — ONE layout shared across every project (only the data changes) over a CLOSED
 *   panel catalog — which is why the project switcher is here: to show the arrangement never
 *   moves. DELETE THIS FILE once the real Projects page (D1) is bound to PanelGrid; the pieces
 *   worth keeping already live in components/projects/.
 * exports:
 *   GridDemo: demo page component (route /grid-demo)
 * imports_from: [react, ../components/grid/PanelGrid, ../components/projects/*]
 * imported_by: [frontend/src/App.jsx]
 * invariants:
 *   - Dark-only by design. Bill's whole UI package is dark; this page opts in explicitly via
 *     PanelGrid's theme="dark" rather than the app's global light/dark class.
 */
import { useState, useMemo, useCallback } from 'react';
import PanelGrid from '../components/grid/PanelGrid';
import { KpiBar, StatusBadge } from '../components/projects/vocab';
import { PanelModal } from '../components/projects/PanelModal';
import {
  buildProjectPanels,
  renderProjectModal,
  PROJECT_MODAL_TITLES,
} from '../components/projects/projectPanels';
import { DEMO_PROJECTS } from '../components/projects/demoProjects';

export default function GridDemo() {
  const [projectNumber, setProjectNumber] = useState(DEMO_PROJECTS[0].number);
  const [openPanel, setOpenPanel] = useState(null);
  const [toast, setToast] = useState(null);

  const project = DEMO_PROJECTS.find(p => p.number === projectNumber) || DEMO_PROJECTS[0];

  const fireAction = useCallback(label => {
    setToast(label);
    setTimeout(() => setToast(null), 1600);
  }, []);

  // Rebuilt when the project changes; the layout is keyed on the surface, not the project,
  // so the arrangement survives the switch.
  const panels = useMemo(
    () => buildProjectPanels(project, { onOpen: setOpenPanel, onAction: fireAction }),
    [project, fireAction],
  );

  return (
    <div className="flex-1 w-full bg-[#0a0c14] text-[#f8fafc] min-h-screen">
      {/* PROJECT HEADER — mockup `.proj-header` */}
      <div className="bg-[#0d1117] border-b border-[#1e293b] px-6 py-3.5">
        <div className="flex items-center gap-3 flex-wrap mb-2">
          <span className="text-[22px] font-extrabold text-[#60a5fa]">#{project.number}</span>
          <span className="text-[20px] text-[#475569]">—</span>
          <span className="text-[22px] font-bold text-[#f8fafc]">{project.name}</span>
          <div className="flex gap-2 flex-wrap ml-auto">
            {project.statuses.map(s => (
              <StatusBadge key={s.text} tone={s.tone}>{s.text}</StatusBadge>
            ))}
          </div>
        </div>
        <div className="flex gap-5 flex-wrap text-[12px] text-[#64748b]">
          <span><strong className="text-[#94a3b8]">GC:</strong> {project.gc}</span>
          <span><strong className="text-[#94a3b8]">PM:</strong> {project.pm}</span>
          <span><strong className="text-[#94a3b8]">Contract:</strong> {project.contract}</span>
          <span><strong className="text-[#94a3b8]">Start:</strong> {project.start}</span>
        </div>
      </div>

      {/* KPI BAR — fixed, not part of the draggable grid (mockup `.kpi-bar`) */}
      <KpiBar items={project.kpis} />

      {/* Harness-only: proves that switching project changes the data, never the layout. */}
      <div className="flex items-center gap-2 flex-wrap px-6 py-2 border-b border-[#1e293b] bg-[#0a0c14]">
        <span className="text-[10px] uppercase tracking-[0.4px] text-[#475569]">Demo · switch project</span>
        {DEMO_PROJECTS.map(p => (
          <button
            key={p.number}
            type="button"
            onClick={() => setProjectNumber(p.number)}
            className={`text-[11px] font-semibold px-2.5 py-1 rounded-md transition-colors ${
              p.number === project.number
                ? 'bg-[#2563eb] text-white'
                : 'bg-[#1e293b] text-[#94a3b8] hover:text-[#f8fafc]'
            }`}
          >
            {p.number} · {p.name}
          </button>
        ))}
        <span className="text-[10px] text-[#334155]">— layout stays put</span>
      </div>

      <div className="px-6 pt-3 pb-8">
        {/* Key is versioned because the catalog changed shape: the eight KPI tiles left the
            grid for the fixed strip above, so a layout saved against the old catalog would
            reconcile to a half-empty dashboard. Bumping starts everyone on the mockup order. */}
        <PanelGrid surfaceKey="projects:v2" panels={panels} columns={3} theme="dark" />
      </div>

      <PanelModal
        open={openPanel !== null}
        title={PROJECT_MODAL_TITLES[openPanel] || 'Detail'}
        onClose={() => setOpenPanel(null)}
      >
        {openPanel && renderProjectModal(openPanel, project)}
      </PanelModal>

      {toast && (
        <div className="fixed bottom-5 left-1/2 -translate-x-1/2 z-[600] px-3.5 py-2 rounded-lg
          bg-[#1e293b] border border-[#334155] text-[#f8fafc] text-[12px] shadow-lg">
          {toast} — action chip fired, modal stayed closed
        </div>
      )}
    </div>
  );
}
