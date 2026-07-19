/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Projects tab index (DEMO) — the portfolio command dashboard. Hero band with
 *   rolled-up financial KPIs (contract value, billed, left to bill, retainage, pending
 *   COs — the estimate-to-invoice engine from the Brain-Hive-Mind architecture), a
 *   "needs attention" radar built from per-project health signals, and rich project
 *   cards showing work-vs-billed meters, release codes (the [Job#]-[Release#] backbone),
 *   and key health chips. Reads static demo data (frontend/src/data/projectsDemo.js) —
 *   no network yet; real data lands section-by-section as ingestion matures.
 * exports:
 *   Projects: index page component (route /projects)
 * imports_from: [react, react-router-dom, ../data/projectsDemo, ../components/projects/projectsShared, ../components/projects/projectsFormat]
 * imported_by: [frontend/src/App.jsx]
 */
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { DEMO_PROJECTS } from '../data/projectsDemo';
import { StatusPill } from '../components/projects/projectsShared';
import { fmtMoney, toneClasses } from '../components/projects/projectsFormat';

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'active', label: 'Active' },
  { key: 'on_hold', label: 'On Hold' },
  { key: 'complete', label: 'Complete' },
];

const SORTS = [
  { key: 'risk', label: 'Needs attention first' },
  { key: 'value', label: 'Contract value' },
  { key: 'progress', label: 'Progress' },
  { key: 'job', label: 'Job number' },
];

// The estimate → invoice module flow from the client's Brain-Hive-Mind mind map.
const MODULE_FLOW = ['Estimate', 'Scope Sheet', 'Releases', 'Production', 'G703 Pay App', 'GC SOV'];

// The three health signals worth surfacing at a glance on the card, with labels
// short enough to survive the 3-column chip row without truncating.
const CARD_HEALTH_KEYS = ['submittals_overdue', 'billing_available', 'installation_risk'];
const CARD_HEALTH_LABELS = {
  submittals_overdue: 'Subm. Overdue',
  billing_available: 'Billing Avail.',
  installation_risk: 'Install Risk',
};

const RISK_RANK = { High: 0, Medium: 1, Low: 2, 'On Hold': 3, Complete: 4 };

const RISK_CHIP = {
  High: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
  Medium: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  Low: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
  'On Hold': 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300',
  Complete: 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300',
};

// Left edge of each card — echoes the risk chip so a scan down the grid reads instantly.
const RISK_BAR = {
  High: 'bg-red-500',
  Medium: 'bg-amber-400',
  Low: 'bg-green-500',
  'On Hold': 'bg-slate-400',
  Complete: 'bg-slate-300 dark:bg-slate-600',
};

// Release stage → dot color. The stage label always renders next to the dot,
// so color is never the only signal.
const STAGE_DOT = {
  'Install Complete': 'bg-green-500',
  Ship: 'bg-accent-400',
  Fabrication: 'bg-accent-400',
  'FC Complete': 'bg-accent-400',
  Detailing: 'bg-slate-400',
  Submittal: 'bg-slate-400',
  'Design Assist': 'bg-slate-400',
  'On Hold': 'bg-amber-500',
};

function clampPct(n, d) {
  return d ? Math.max(0, Math.min(100, Math.round((n / d) * 100))) : 0;
}

// Per-project financial rollups the card needs; all computed, never stored.
function derive(p) {
  const f = p.financials;
  return {
    contractValue: f.original_contract_value + f.approved_change_orders,
    billedPct: clampPct(f.current_billed, f.forecast_invoice_value),
    paidPct: clampPct(f.payments_received, f.forecast_invoice_value),
  };
}

function KpiTile({ label, value, caption }) {
  return (
    <div className="rounded-xl bg-white/10 ring-1 ring-inset ring-white/15 px-3.5 py-3">
      <div className="text-[11px] font-medium uppercase tracking-wider text-white/60 truncate">{label}</div>
      <div className="mt-1 text-xl font-bold tabular-nums text-white">{value}</div>
      {caption && <div className="mt-0.5 text-[11px] text-white/50 truncate">{caption}</div>}
    </div>
  );
}

/**
 * Thin labeled meter. `tick` (0–100) draws a marker on the track — used to show
 * payments received against the billed bar without a third row.
 */
function Meter({ label, pct, barClass, display, tick }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-11 shrink-0 text-[10px] font-medium uppercase tracking-wide text-gray-400 dark:text-slate-500">
        {label}
      </span>
      <div className="relative flex-1 h-1.5 rounded-full bg-gray-200 dark:bg-slate-700">
        <div className={`absolute inset-y-0 left-0 rounded-full ${barClass}`} style={{ width: `${pct}%` }} />
        {tick != null && tick > 0 && (
          <span
            className="absolute -top-0.5 -bottom-0.5 w-0.5 rounded-full bg-gray-500 dark:bg-slate-300"
            style={{ left: `${tick}%` }}
          />
        )}
      </div>
      <span className="w-9 shrink-0 text-right text-[11px] font-semibold tabular-nums text-gray-600 dark:text-slate-300">
        {display}
      </span>
    </div>
  );
}

function ReleaseChip({ release }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md bg-gray-50 dark:bg-slate-700/60 border border-gray-200 dark:border-slate-600 px-1.5 py-0.5">
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${STAGE_DOT[release.stage] || 'bg-slate-400'}`} />
      <span className="font-mono text-[11px] font-semibold text-gray-700 dark:text-slate-200">{release.release}</span>
      <span className="text-[10px] text-gray-400 dark:text-slate-500">{release.stage}</span>
    </span>
  );
}

function HealthChip({ metric }) {
  const t = toneClasses[metric.tone] || toneClasses.neutral;
  return (
    <div className="flex flex-col gap-0.5 min-w-0">
      <span className="flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide text-gray-400 dark:text-slate-500 truncate">
        <span className={`inline-block w-1.5 h-1.5 rounded-full shrink-0 ${t.dot}`} />
        {CARD_HEALTH_LABELS[metric.key] || metric.label}
      </span>
      <span className={`text-sm font-semibold truncate ${t.text}`}>{metric.value}</span>
    </div>
  );
}

function ProjectCard({ project, onOpen }) {
  const d = derive(project);
  const healthByKey = Object.fromEntries(project.health.map(h => [h.key, h]));
  const risk = project.brief?.risk_level || 'Low';
  const shownReleases = project.releases.slice(0, 3);
  const moreReleases = project.releases.length - shownReleases.length;

  return (
    <button
      type="button"
      onClick={onOpen}
      className="group relative text-left rounded-xl border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-800 hover:border-accent-400 dark:hover:border-accent-400 hover:shadow-lg hover:-translate-y-0.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-400 transition-all p-4 pl-5 flex flex-col gap-3 overflow-hidden"
    >
      <span aria-hidden className={`absolute inset-y-0 left-0 w-1 ${RISK_BAR[risk] || RISK_BAR.Low}`} />

      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono text-xs font-bold text-accent-600 dark:text-accent-300 bg-accent-50 dark:bg-accent-900/40 px-1.5 py-0.5 rounded">
            {project.job_number}
          </span>
          <StatusPill status={project.status} />
        </div>
        <span className={`shrink-0 px-2 py-0.5 rounded-full text-[11px] font-semibold ${RISK_CHIP[risk] || RISK_CHIP.Low}`}>
          {risk === 'On Hold' || risk === 'Complete' ? risk : `${risk} risk`}
        </span>
      </div>

      <div className="min-w-0">
        <h3 className="text-base font-semibold text-gray-900 dark:text-slate-100 leading-snug group-hover:text-accent-600 dark:group-hover:text-accent-300 transition-colors">
          {project.project_name}
        </h3>
        <p className="mt-0.5 text-xs text-gray-500 dark:text-slate-400 truncate">
          {project.customer.general_contractor} · PM {project.team.project_manager}
        </p>
      </div>

      {/* Work done vs billed — the gap between the two bars is money on the table. */}
      <div className="space-y-1.5">
        <Meter label="Work" pct={project.percent_complete} barClass="bg-accent-400" display={`${project.percent_complete}%`} />
        <Meter label="Billed" pct={d.billedPct} barClass="bg-emerald-500" display={`${d.billedPct}%`} tick={d.paidPct} />
      </div>

      <div className="flex flex-wrap gap-1.5">
        {shownReleases.map(r => <ReleaseChip key={r.release} release={r} />)}
        {moreReleases > 0 && (
          <span className="inline-flex items-center rounded-md px-1.5 py-0.5 text-[11px] text-gray-400 dark:text-slate-500">
            +{moreReleases} more
          </span>
        )}
      </div>

      <div className="grid grid-cols-3 gap-2 pt-2.5 border-t border-gray-100 dark:border-slate-700">
        {CARD_HEALTH_KEYS.map(k => healthByKey[k] && <HealthChip key={k} metric={healthByKey[k]} />)}
      </div>

      <div className="flex items-center justify-between pt-2.5 border-t border-gray-100 dark:border-slate-700 text-xs">
        <span className="text-gray-400 dark:text-slate-500">
          Est. completion <span className="tabular-nums text-gray-600 dark:text-slate-300">{project.estimated_completion_date || '—'}</span>
        </span>
        <span className="font-semibold tabular-nums text-gray-800 dark:text-slate-200">
          {fmtMoney(project.financials.forecast_invoice_value)}
        </span>
      </div>
    </button>
  );
}

function AttentionChip({ item, onOpen }) {
  const isRisk = item.metric.tone === 'risk';
  return (
    <button
      type="button"
      onClick={onOpen}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-400 ${
        isRisk
          ? 'border-red-200 bg-red-50 text-red-800 hover:bg-red-100 dark:border-red-900/60 dark:bg-red-900/20 dark:text-red-300 dark:hover:bg-red-900/40'
          : 'border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100 dark:border-amber-900/60 dark:bg-amber-900/20 dark:text-amber-300 dark:hover:bg-amber-900/40'
      }`}
    >
      <span aria-hidden>{isRisk ? '▲' : '!'}</span>
      <span className="font-mono font-bold">{item.project.job_number}</span>
      <span className="opacity-80">{item.metric.label}: {item.metric.value}</span>
    </button>
  );
}

export default function Projects() {
  const navigate = useNavigate();
  const [filter, setFilter] = useState('all');
  const [sort, setSort] = useState('risk');
  const [q, setQ] = useState('');

  const counts = useMemo(() => {
    const c = { all: DEMO_PROJECTS.length };
    for (const p of DEMO_PROJECTS) c[p.status] = (c[p.status] || 0) + 1;
    return c;
  }, []);

  // Portfolio rollups over open (non-complete) projects — the numbers Bill's
  // estimate-to-invoice engine exists to move.
  const kpis = useMemo(() => {
    const open = DEMO_PROJECTS.filter(p => p.status !== 'complete');
    const sum = fn => open.reduce((acc, p) => acc + fn(p), 0);
    const contract = sum(p => p.financials.original_contract_value + p.financials.approved_change_orders);
    const billed = sum(p => p.financials.current_billed);
    const forecast = sum(p => p.financials.forecast_invoice_value);
    return {
      openCount: open.length,
      onHold: open.filter(p => p.status === 'on_hold').length,
      contract,
      billed,
      billedPct: clampPct(billed, forecast),
      leftToBill: Math.max(0, forecast - billed),
      retainage: sum(p => p.financials.retainage),
      pendingCOs: sum(p => p.financials.pending_change_orders),
      pendingCOCount: open.filter(p => p.financials.pending_change_orders > 0).length,
    };
  }, []);

  // Every warn/risk health signal across the portfolio, risks first — the radar.
  const attention = useMemo(() => {
    const items = [];
    for (const p of DEMO_PROJECTS) {
      for (const h of p.health) {
        if (h.tone === 'risk' || h.tone === 'warn') items.push({ project: p, metric: h });
      }
    }
    return items.sort((a, b) =>
      a.metric.tone === b.metric.tone ? 0 : a.metric.tone === 'risk' ? -1 : 1
    );
  }, []);

  const visible = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const filtered = DEMO_PROJECTS.filter(p => {
      if (filter !== 'all' && p.status !== filter) return false;
      if (!needle) return true;
      return (
        p.project_name.toLowerCase().includes(needle) ||
        p.job_number.toLowerCase().includes(needle) ||
        p.customer.general_contractor.toLowerCase().includes(needle) ||
        p.team.project_manager.toLowerCase().includes(needle)
      );
    });
    const byRisk = (a, b) =>
      (RISK_RANK[a.brief?.risk_level] ?? 2) - (RISK_RANK[b.brief?.risk_level] ?? 2);
    const sorters = {
      risk: byRisk,
      value: (a, b) => derive(b).contractValue - derive(a).contractValue,
      progress: (a, b) => b.percent_complete - a.percent_complete,
      job: (a, b) => Number(a.job_number) - Number(b.job_number),
    };
    return [...filtered].sort(sorters[sort] || byRisk);
  }, [filter, sort, q]);

  return (
    <div className="flex-1 w-full bg-[#f8fafc] dark:bg-slate-900">
      <div className="max-w-7xl mx-auto px-4 lg:px-6 py-6">
        {/* Hero — portfolio command band */}
        <div className="rounded-2xl bg-gradient-to-br from-accent-600 via-accent-700 to-accent-800 dark:from-slate-800 dark:via-slate-800 dark:to-slate-900 dark:ring-1 dark:ring-slate-700 p-5 lg:p-6 mb-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold text-white">Projects</h1>
                <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-300/90 text-amber-950">
                  DEMO
                </span>
              </div>
              <p className="mt-1 text-sm text-white/60">
                Every project is the top-level container for its releases, submittals, contract, schedule, and financials.
              </p>
              <div className="mt-2.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px] text-white/50">
                {MODULE_FLOW.map((m, i) => (
                  <span key={m} className="flex items-center gap-1.5">
                    {i > 0 && <span aria-hidden>→</span>}
                    <span className="rounded bg-white/10 px-1.5 py-0.5 font-medium text-white/70">{m}</span>
                  </span>
                ))}
              </div>
            </div>
            <input
              type="text"
              value={q}
              onChange={e => setQ(e.target.value)}
              placeholder="Search projects, job #, GC, PM…"
              className="w-full sm:w-72 px-3 py-2 text-sm rounded-lg bg-white/10 ring-1 ring-inset ring-white/20 text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-white/50"
            />
          </div>

          <div className="mt-5 grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-2.5">
            <KpiTile
              label="Open Projects"
              value={kpis.openCount}
              caption={kpis.onHold ? `${kpis.onHold} on hold` : 'all moving'}
            />
            <KpiTile label="Portfolio Value" value={fmtMoney(kpis.contract)} caption="contract + approved COs" />
            <KpiTile label="Billed to Date" value={fmtMoney(kpis.billed)} caption={`${kpis.billedPct}% of forecast`} />
            <KpiTile label="Left to Bill" value={fmtMoney(kpis.leftToBill)} caption="remaining to invoice" />
            <KpiTile label="Retainage Held" value={fmtMoney(kpis.retainage)} caption="releases at closeout" />
            <KpiTile
              label="Pending COs"
              value={fmtMoney(kpis.pendingCOs)}
              caption={`across ${kpis.pendingCOCount} project${kpis.pendingCOCount === 1 ? '' : 's'}`}
            />
          </div>
        </div>

        {/* Needs attention — every warn/risk signal across the portfolio */}
        {attention.length > 0 && (
          <div className="mb-5">
            <h2 className="text-xs font-bold uppercase tracking-wide text-gray-400 dark:text-slate-500 mb-2">
              Needs Attention ({attention.length})
            </h2>
            <div className="flex flex-wrap gap-1.5">
              {attention.map((item, i) => (
                <AttentionChip key={i} item={item} onOpen={() => navigate(`/projects/${item.project.id}`)} />
              ))}
            </div>
          </div>
        )}

        {/* Filters + sort */}
        <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
          <div className="flex flex-wrap gap-2">
            {FILTERS.map(f => (
              <button
                key={f.key}
                type="button"
                onClick={() => setFilter(f.key)}
                className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-400 ${
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
          <label className="flex items-center gap-2 text-sm text-gray-500 dark:text-slate-400">
            Sort
            <select
              value={sort}
              onChange={e => setSort(e.target.value)}
              className="px-2.5 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-700 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-accent-400"
            >
              {SORTS.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          </label>
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
