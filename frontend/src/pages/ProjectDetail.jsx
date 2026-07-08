/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Project detail (DEMO). Landing = the BB01-generated Project Brief, then a
 *   computed health dashboard, then tabbed child sections (Overview, Releases,
 *   Submittals, Schedule, Financials, Contacts & Docs, Activity). Demonstrates the
 *   "Project Brief is the default landing page" idea from the data-model spec.
 *   Static demo data only — replace tab-by-tab as ingestion comes online.
 * exports:
 *   ProjectDetail: detail page component (route /projects/:id)
 * imports_from: [react, react-router-dom, ../data/projectsDemo, ../components/projects/projectsShared]
 * imported_by: [frontend/src/App.jsx]
 */
import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getDemoProject } from '../data/projectsDemo';
import {
  StatusPill, HealthTile, SectionCard, ProgressBar, MetaRow,
} from '../components/projects/projectsShared';
import { fmtMoney, fmtPct } from '../components/projects/projectsFormat';

const TABS = ['Overview', 'Releases', 'Submittals', 'Schedule', 'Financials', 'Contacts & Docs', 'Activity'];

const RISK_TONE = {
  Low: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
  Medium: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  High: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
  'On Hold': 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300',
  Complete: 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300',
};

const STAGE_TONE = {
  complete: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
  active: 'bg-accent-100 text-accent-700 dark:bg-accent-900/50 dark:text-accent-300',
  upcoming: 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300',
  blocked: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
};

const SUBMITTAL_TONE = {
  Approved: 'text-green-600 dark:text-green-400',
  'In Review': 'text-accent-600 dark:text-accent-300',
  Draft: 'text-slate-500 dark:text-slate-400',
  Overdue: 'text-red-600 dark:text-red-400',
  'On Hold': 'text-slate-500 dark:text-slate-400',
};

function BriefBullets({ items, empty }) {
  if (!items || items.length === 0) {
    return <p className="text-sm text-gray-400 dark:text-slate-500 italic">{empty}</p>;
  }
  return (
    <ul className="space-y-1.5">
      {items.map((t, i) => (
        <li key={i} className="flex gap-2 text-sm text-gray-700 dark:text-slate-300">
          <span className="text-accent-400 mt-0.5 shrink-0">•</span>
          <span>{t}</span>
        </li>
      ))}
    </ul>
  );
}

function ProjectBrief({ brief }) {
  return (
    <SectionCard className="overflow-hidden">
      <div className="-m-4 mb-0 px-4 py-3 bg-gradient-to-r from-accent-500 to-accent-600 dark:from-accent-700 dark:to-accent-800">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-white">
            <span className="text-lg">🍌</span>
            <span className="font-semibold">BB01 Project Brief</span>
          </div>
          <div className="flex items-center gap-2">
            <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${RISK_TONE[brief.risk_level] || RISK_TONE.Low}`}>
              Risk: {brief.risk_level}
            </span>
          </div>
        </div>
      </div>

      <div className="pt-4">
        <p className="text-[15px] leading-relaxed text-gray-800 dark:text-slate-200">{brief.status_line}</p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4 mt-5">
          <div>
            <h4 className="text-xs font-bold uppercase tracking-wide text-gray-400 dark:text-slate-500 mb-2">Upcoming Deadlines</h4>
            <BriefBullets items={brief.upcoming} empty="No upcoming deadlines" />
          </div>
          <div>
            <h4 className="text-xs font-bold uppercase tracking-wide text-red-400 dark:text-red-400/80 mb-2">Open Risks</h4>
            <BriefBullets items={brief.risks} empty="No open risks flagged" />
          </div>
          <div>
            <h4 className="text-xs font-bold uppercase tracking-wide text-gray-400 dark:text-slate-500 mb-2">Pending Approvals</h4>
            <BriefBullets items={brief.approvals} empty="Nothing awaiting approval" />
          </div>
          <div>
            <h4 className="text-xs font-bold uppercase tracking-wide text-gray-400 dark:text-slate-500 mb-2">Forecast</h4>
            <p className="text-sm text-gray-700 dark:text-slate-300">{brief.forecast}</p>
          </div>
        </div>

        <div className="mt-5 pt-4 border-t border-gray-100 dark:border-slate-700">
          <h4 className="text-xs font-bold uppercase tracking-wide text-accent-500 dark:text-accent-300 mb-2">Required Next Actions</h4>
          <BriefBullets items={brief.next_actions} empty="No actions required" />
        </div>

        <p className="mt-4 text-[11px] text-gray-400 dark:text-slate-500">
          Generated {brief.generated_at} · computed from releases, submittals, contract & schedule
        </p>
      </div>
    </SectionCard>
  );
}

function Th({ children, className = '' }) {
  return <th className={`text-left font-medium text-gray-500 dark:text-slate-400 px-3 py-2 ${className}`}>{children}</th>;
}
function Td({ children, className = '' }) {
  return <td className={`px-3 py-2.5 text-gray-800 dark:text-slate-200 ${className}`}>{children}</td>;
}

function TabPanel({ tab, project }) {
  const money = project.financials;

  if (tab === 'Overview') {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <SectionCard title="Customer">
          <MetaRow label="General Contractor" value={project.customer.general_contractor} />
          <MetaRow label="Owner" value={project.customer.owner} />
          <MetaRow label="Architect" value={project.customer.architect} />
          <MetaRow label="Structural Engineer" value={project.customer.structural_engineer} />
        </SectionCard>
        <SectionCard title="Internal Team">
          <MetaRow label="Project Manager" value={project.team.project_manager} />
          <MetaRow label="Estimator" value={project.team.estimator} />
          <MetaRow label="Field Super" value={project.team.field_superintendent} />
          <MetaRow label="Drafting Lead" value={project.team.drafting_lead} />
          <MetaRow label="Account Manager" value={project.team.account_manager} />
        </SectionCard>
        <SectionCard title="Contract">
          <MetaRow label="Type" value={project.contract.contract_type} />
          <MetaRow label="Retainage" value={fmtPct(project.contract.retainage_pct)} />
          <MetaRow label="Payment Terms" value={project.contract.payment_terms} />
          <MetaRow label="Billing" value={project.contract.billing_schedule} />
          <MetaRow
            label="BB01 Review"
            value={project.contract.review_complete
              ? <span className="text-green-600 dark:text-green-400">Complete</span>
              : <span className="text-amber-600 dark:text-amber-400">Pending</span>}
          />
        </SectionCard>
        <SectionCard title="Production Quantities" className="lg:col-span-2">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <Metric label="Guardrail (LF)" value={project.production.linear_feet_guardrail.toLocaleString()} />
            <Metric label="Stairs" value={project.production.stairs} />
            <Metric label="Balconies" value={project.production.balconies} />
            <Metric label="Awnings" value={project.production.awnings} />
            <Metric label="Misc Metals" value={project.production.miscellaneous_metals} />
          </div>
        </SectionCard>
        <SectionCard title="Key Dates">
          <MetaRow label="Created" value={project.created_date} />
          <MetaRow label="Est. Start" value={project.estimated_start_date} />
          <MetaRow label="Est. Completion" value={project.estimated_completion_date} />
          <MetaRow label="Actual Completion" value={project.actual_completion_date} />
        </SectionCard>
      </div>
    );
  }

  if (tab === 'Releases') {
    return (
      <SectionCard title={`Releases (${project.releases.length})`}>
        <div className="overflow-x-auto -mx-4 -mb-4">
          <table className="w-full text-sm min-w-[640px]">
            <thead className="border-b border-gray-100 dark:border-slate-700">
              <tr><Th>Release</Th><Th>Description</Th><Th>Stage</Th><Th className="text-right">Hrs</Th><Th>Install</Th><Th className="w-32">Progress</Th></tr>
            </thead>
            <tbody className="divide-y divide-gray-50 dark:divide-slate-700/50">
              {project.releases.map(r => (
                <tr key={r.release}>
                  <Td className="font-mono text-xs font-semibold text-accent-600 dark:text-accent-300">{r.release}</Td>
                  <Td>{r.description}</Td>
                  <Td><span className="px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300">{r.stage}</span></Td>
                  <Td className="text-right tabular-nums">{r.hours || '—'}</Td>
                  <Td className="tabular-nums text-gray-500 dark:text-slate-400">{r.start_install}</Td>
                  <Td><div className="flex items-center gap-2"><ProgressBar pct={r.pct} className="flex-1" /><span className="text-xs tabular-nums text-gray-500 dark:text-slate-400 w-8 text-right">{r.pct}%</span></div></Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    );
  }

  if (tab === 'Submittals') {
    return (
      <SectionCard title={`Submittals (${project.submittals.length})`}>
        <div className="overflow-x-auto -mx-4 -mb-4">
          <table className="w-full text-sm min-w-[640px]">
            <thead className="border-b border-gray-100 dark:border-slate-700">
              <tr><Th>Rel</Th><Th>Title</Th><Th>Type</Th><Th>Status</Th><Th>Ball in Court</Th><Th>Due</Th></tr>
            </thead>
            <tbody className="divide-y divide-gray-50 dark:divide-slate-700/50">
              {project.submittals.map(s => (
                <tr key={s.rel}>
                  <Td className="font-mono text-xs font-semibold text-accent-600 dark:text-accent-300">{s.rel}</Td>
                  <Td>{s.title}</Td>
                  <Td className="text-gray-500 dark:text-slate-400">{s.type}</Td>
                  <Td><span className={`font-medium ${SUBMITTAL_TONE[s.status] || 'text-gray-600'}`}>{s.status}</span></Td>
                  <Td>{s.ball_in_court}</Td>
                  <Td className="tabular-nums text-gray-500 dark:text-slate-400">{s.due_date}</Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    );
  }

  if (tab === 'Schedule') {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <SectionCard title="Customer Schedule">
          <ScheduleList items={project.schedule.customer} />
        </SectionCard>
        <SectionCard title="Internal Schedule">
          <p className="text-xs text-gray-400 dark:text-slate-500 mb-3 -mt-1">Derived from the customer schedule + contract deadlines.</p>
          <ScheduleList items={project.schedule.internal} />
        </SectionCard>
      </div>
    );
  }

  if (tab === 'Financials') {
    const billedPct = Math.round((money.current_billed / money.forecast_invoice_value) * 100);
    return (
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <SectionCard title="Contract Value" className="lg:col-span-1">
          <MetaRow label="Original Contract" value={fmtMoney(money.original_contract_value)} />
          <MetaRow label="Approved COs" value={fmtMoney(money.approved_change_orders)} />
          <MetaRow label="Pending COs" value={fmtMoney(money.pending_change_orders)} />
          <div className="my-2 border-t border-gray-100 dark:border-slate-700" />
          <MetaRow label="Forecast Invoice" value={<span className="text-accent-600 dark:text-accent-300 font-semibold">{fmtMoney(money.forecast_invoice_value)}</span>} />
        </SectionCard>
        <SectionCard title="Billing & Cash" className="lg:col-span-1">
          <MetaRow label="Billed to Date" value={fmtMoney(money.current_billed)} />
          <MetaRow label="Payments Received" value={fmtMoney(money.payments_received)} />
          <MetaRow label="Retainage Held" value={fmtMoney(money.retainage)} />
          <div className="mt-3">
            <div className="flex justify-between text-xs mb-1"><span className="text-gray-500 dark:text-slate-400">Billed vs forecast</span><span className="font-medium">{billedPct}%</span></div>
            <ProgressBar pct={billedPct} />
          </div>
        </SectionCard>
        <SectionCard title="Note" className="lg:col-span-1">
          <p className="text-sm text-gray-500 dark:text-slate-400">
            In the live system these are <span className="font-medium text-gray-700 dark:text-slate-300">computed rollups</span> from
            invoices, change orders, and T&M — not hand-entered. Only contract value and retainage % are inputs.
          </p>
        </SectionCard>
      </div>
    );
  }

  if (tab === 'Contacts & Docs') {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SectionCard title={`Contacts (${project.contacts.length})`}>
          <ul className="divide-y divide-gray-50 dark:divide-slate-700/50 -my-1">
            {project.contacts.map((c, i) => (
              <li key={i} className="py-2.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-gray-900 dark:text-slate-100">{c.name}</span>
                  <span className="text-xs text-gray-400 dark:text-slate-500">{c.company}</span>
                </div>
                <div className="text-xs text-gray-500 dark:text-slate-400 mt-0.5">{c.role} · {c.email} · {c.phone}</div>
              </li>
            ))}
          </ul>
        </SectionCard>
        <div className="space-y-4">
          <SectionCard title={`Documents (${project.documents.length})`}>
            <ul className="divide-y divide-gray-50 dark:divide-slate-700/50 -my-1">
              {project.documents.map((d, i) => (
                <li key={i} className="py-2.5 flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm text-gray-800 dark:text-slate-200 truncate">📄 {d.name}</div>
                    <div className="text-xs text-gray-400 dark:text-slate-500">{d.doc_type}</div>
                  </div>
                  <span className="text-xs text-gray-400 dark:text-slate-500 shrink-0 tabular-nums">{d.date}</span>
                </li>
              ))}
            </ul>
          </SectionCard>
          {project.vendors.length > 0 && (
            <SectionCard title={`Vendors (${project.vendors.length})`}>
              <ul className="divide-y divide-gray-50 dark:divide-slate-700/50 -my-1">
                {project.vendors.map((v, i) => (
                  <li key={i} className="py-2.5 flex items-center justify-between gap-2 text-sm">
                    <span className="text-gray-800 dark:text-slate-200">{v.vendor}</span>
                    <span className={`text-xs font-medium ${v.material_ordered ? 'text-green-600 dark:text-green-400' : 'text-amber-600 dark:text-amber-400'}`}>
                      {v.material_ordered ? `Ordered · ETA ${v.expected_delivery}` : `Not ordered · need by ${v.expected_delivery}`}
                    </span>
                  </li>
                ))}
              </ul>
            </SectionCard>
          )}
        </div>
      </div>
    );
  }

  if (tab === 'Activity') {
    return (
      <SectionCard title="Activity Feed">
        <p className="text-xs text-gray-400 dark:text-slate-500 mb-3 -mt-1">A union view over release events, submittal events, and comments.</p>
        <ul className="space-y-0">
          {project.activity.map((a, i) => (
            <li key={i} className="flex gap-3 py-2.5 border-b border-gray-50 dark:border-slate-700/50 last:border-0">
              <span className="text-xs tabular-nums text-gray-400 dark:text-slate-500 w-24 shrink-0">{a.at}</span>
              <span className="text-sm text-gray-700 dark:text-slate-300"><span className="font-medium text-gray-900 dark:text-slate-100">{a.who}</span> — {a.text}</span>
            </li>
          ))}
        </ul>
      </SectionCard>
    );
  }

  return null;
}

function Metric({ label, value }) {
  return (
    <div className="rounded-lg bg-gray-50 dark:bg-slate-700/40 px-3 py-2">
      <div className="text-lg font-bold text-gray-900 dark:text-slate-100 tabular-nums">{value}</div>
      <div className="text-[11px] uppercase tracking-wide text-gray-400 dark:text-slate-500">{label}</div>
    </div>
  );
}

function ScheduleList({ items }) {
  return (
    <ul className="space-y-0 -my-1">
      {items.map((m, i) => (
        <li key={i} className="flex items-center justify-between gap-3 py-2.5 border-b border-gray-50 dark:border-slate-700/50 last:border-0">
          <span className="text-sm text-gray-800 dark:text-slate-200">{m.milestone}</span>
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-xs tabular-nums text-gray-500 dark:text-slate-400">{m.date}</span>
            <span className={`px-2 py-0.5 rounded-full text-[11px] font-medium capitalize ${STAGE_TONE[m.status] || STAGE_TONE.upcoming}`}>{m.status}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}

export default function ProjectDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [tab, setTab] = useState('Overview');
  const project = getDemoProject(id);

  if (!project) {
    return (
      <div className="flex-1 w-full bg-[#f8fafc] dark:bg-slate-900 flex flex-col items-center justify-center gap-3 py-20">
        <p className="text-gray-500 dark:text-slate-400">Project not found.</p>
        <button onClick={() => navigate('/projects')} className="px-4 py-2 text-sm font-medium rounded-lg bg-accent-500 text-white hover:bg-accent-600">
          Back to Projects
        </button>
      </div>
    );
  }

  return (
    <div className="flex-1 w-full bg-[#f8fafc] dark:bg-slate-900">
      <div className="max-w-7xl mx-auto px-4 lg:px-6 py-6 space-y-5">
        {/* Breadcrumb + hero */}
        <div>
          <button onClick={() => navigate('/projects')} className="text-sm text-gray-500 dark:text-slate-400 hover:text-accent-600 dark:hover:text-accent-300 transition-colors">
            ← Projects
          </button>
          <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono text-sm font-bold text-accent-600 dark:text-accent-300 bg-accent-50 dark:bg-accent-900/40 px-2 py-0.5 rounded">{project.job_number}</span>
                <StatusPill status={project.status} />
              </div>
              <h1 className="mt-2 text-2xl font-bold text-gray-900 dark:text-slate-100">{project.project_name}</h1>
              <p className="mt-1 text-sm text-gray-500 dark:text-slate-400">
                {project.customer.general_contractor} · PM {project.team.project_manager} · Est. completion {project.estimated_completion_date}
              </p>
            </div>
            <div className="text-right">
              <div className="text-2xl font-bold text-gray-900 dark:text-slate-100 tabular-nums">{fmtMoney(project.financials.forecast_invoice_value)}</div>
              <div className="text-xs text-gray-400 dark:text-slate-500">forecast invoice value</div>
              <div className="mt-2 w-40 ml-auto">
                <div className="flex justify-between text-xs mb-1"><span className="text-gray-500 dark:text-slate-400">{project.percent_complete}% complete</span></div>
                <ProgressBar pct={project.percent_complete} />
              </div>
            </div>
          </div>
        </div>

        {/* Project Brief */}
        <ProjectBrief brief={project.brief} />

        {/* Health dashboard */}
        <div>
          <h2 className="text-xs font-bold uppercase tracking-wide text-gray-400 dark:text-slate-500 mb-2">Project Health</h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-8 gap-2.5">
            {project.health.map(h => <HealthTile key={h.key} label={h.label} value={h.value} tone={h.tone} />)}
          </div>
        </div>

        {/* Tabs */}
        <div>
          <div className="flex gap-1 overflow-x-auto border-b border-gray-200 dark:border-slate-700 mb-4">
            {TABS.map(t => (
              <button
                key={t}
                type="button"
                onClick={() => setTab(t)}
                className={`px-3 py-2 text-sm font-medium whitespace-nowrap border-b-2 -mb-px transition-colors ${
                  tab === t
                    ? 'border-accent-500 text-accent-600 dark:text-accent-300'
                    : 'border-transparent text-gray-500 dark:text-slate-400 hover:text-gray-800 dark:hover:text-slate-200'
                }`}
              >
                {t}
              </button>
            ))}
          </div>
          <TabPanel tab={tab} project={project} />
        </div>
      </div>
    </div>
  );
}
