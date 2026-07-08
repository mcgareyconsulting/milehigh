/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Projects tab index (DEMO). Lists projects as cards with status, PM/GC,
 *   percent-complete, and a compact health strip, plus a status filter and search.
 *   Reads static demo data (frontend/src/data/projectsDemo.js) — no network yet.
 *   This is the "Project as top-level container" vision made visible for the client;
 *   real data lands section-by-section as ingestion matures.
 * exports:
 *   Projects: index page component (route /projects)
 * imports_from: [react, react-router-dom, ../data/projectsDemo, ../components/projects/projectsShared]
 * imported_by: [frontend/src/App.jsx]
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { DEMO_PROJECTS } from '../data/projectsDemo';
import { StatusPill, ProgressBar } from '../components/projects/projectsShared';
import { fmtMoney, toneClasses } from '../components/projects/projectsFormat';

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'active', label: 'Active' },
  { key: 'on_hold', label: 'On Hold' },
  { key: 'complete', label: 'Complete' },
];

// The three health signals worth surfacing at a glance on the card.
const CARD_HEALTH_KEYS = ['submittals_overdue', 'billing_available', 'installation_risk'];

function HealthChip({ metric }) {
  const t = toneClasses[metric.tone] || toneClasses.neutral;
  return (
    <div className="flex flex-col gap-0.5 min-w-0">
      <span className="text-[10px] font-medium uppercase tracking-wide text-gray-400 dark:text-slate-500 truncate">
        {metric.label}
      </span>
      <span className={`text-sm font-semibold truncate ${t.text}`}>{metric.value}</span>
    </div>
  );
}

function ProjectCard({ project, onOpen }) {
  const healthByKey = Object.fromEntries(project.health.map(h => [h.key, h]));
  return (
    <button
      type="button"
      onClick={onOpen}
      className="group text-left rounded-xl border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-800 hover:border-accent-400 dark:hover:border-accent-400 hover:shadow-md transition-all p-4 flex flex-col gap-3"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs font-bold text-accent-600 dark:text-accent-300 bg-accent-50 dark:bg-accent-900/40 px-1.5 py-0.5 rounded">
              {project.job_number}
            </span>
            <StatusPill status={project.status} />
          </div>
          <h3 className="mt-2 text-base font-semibold text-gray-900 dark:text-slate-100 leading-snug group-hover:text-accent-600 dark:group-hover:text-accent-300 transition-colors">
            {project.project_name}
          </h3>
          <p className="mt-0.5 text-xs text-gray-500 dark:text-slate-400 truncate">
            {project.customer.general_contractor} · PM {project.team.project_manager}
          </p>
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between text-xs mb-1">
          <span className="text-gray-500 dark:text-slate-400">{project.percent_complete}% complete</span>
          <span className="font-medium text-gray-700 dark:text-slate-300">{fmtMoney(project.financials.forecast_invoice_value)}</span>
        </div>
        <ProgressBar pct={project.percent_complete} />
      </div>

      <div className="grid grid-cols-3 gap-2 pt-2 border-t border-gray-100 dark:border-slate-700">
        {CARD_HEALTH_KEYS.map(k => healthByKey[k] && <HealthChip key={k} metric={healthByKey[k]} />)}
      </div>
    </button>
  );
}

export default function Projects() {
  const navigate = useNavigate();
  const [filter, setFilter] = useState('all');
  const [q, setQ] = useState('');

  const counts = useMemo(() => {
    const c = { all: DEMO_PROJECTS.length };
    for (const p of DEMO_PROJECTS) c[p.status] = (c[p.status] || 0) + 1;
    return c;
  }, []);

  const visible = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return DEMO_PROJECTS.filter(p => {
      if (filter !== 'all' && p.status !== filter) return false;
      if (!needle) return true;
      return (
        p.project_name.toLowerCase().includes(needle) ||
        p.job_number.toLowerCase().includes(needle) ||
        p.customer.general_contractor.toLowerCase().includes(needle)
      );
    });
  }, [filter, q]);

  return (
    <div className="flex-1 w-full bg-[#f8fafc] dark:bg-slate-900">
      <div className="max-w-7xl mx-auto px-4 lg:px-6 py-6">
        {/* Header */}
        <div className="flex flex-wrap items-end justify-between gap-4 mb-5">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-slate-100">Projects</h1>
              <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
                DEMO
              </span>
            </div>
            <p className="mt-1 text-sm text-gray-500 dark:text-slate-400">
              Each project is the top-level container for its releases, submittals, contract, schedule, and financials.
            </p>
          </div>
          <input
            type="text"
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder="Search projects, job #, GC…"
            className="w-full sm:w-72 px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-900 dark:text-slate-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-accent-500"
          />
        </div>

        {/* Filter chips */}
        <div className="flex flex-wrap gap-2 mb-5">
          {FILTERS.map(f => (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
                filter === f.key
                  ? 'bg-accent-500 text-white'
                  : 'bg-white dark:bg-slate-800 text-gray-700 dark:text-slate-200 border border-gray-200 dark:border-slate-600 hover:bg-gray-100 dark:hover:bg-slate-700'
              }`}
            >
              {f.label}
              <span className={`ml-1.5 ${filter === f.key ? 'text-white/80' : 'text-gray-400 dark:text-slate-500'}`}>
                {counts[f.key] || 0}
              </span>
            </button>
          ))}
        </div>

        {/* Grid */}
        {visible.length === 0 ? (
          <div className="text-center py-16 text-gray-500 dark:text-slate-400">No projects match.</div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {visible.map(p => (
              <ProjectCard key={p.id} project={p} onOpen={() => navigate(`/projects/${p.id}`)} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
