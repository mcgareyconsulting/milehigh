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
import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getDemoProject } from '../data/projectsDemo';
import { fetchProjectLive } from '../services/projectsApi';
import {
  StatusPill, HealthTile, HealthScore, SectionCard, ProgressBar, MetaRow,
} from '../components/projects/projectsShared';
import { fmtMoney, fmtPct, resolveHealthScore } from '../components/projects/projectsFormat';

const TABS = ['Overview', 'Releases', 'Submittals', 'Schedule', 'Financials', 'Contacts & Docs', 'Activity'];

// Build a project object for a live-only job (real DB data, no demo scaffold). Demo-only
// sections are left null/empty and the render guards mark them "not available yet".
function liveOnlyProject(live) {
  return {
    id: live.job_number,
    job_number: live.job_number,
    project_name: live.name,
    status: live.is_active === false ? 'complete' : 'active',
    live: true,
    percent_complete: live.percent_complete,
    created_date: null,
    estimated_start_date: null,
    estimated_completion_date: null,
    actual_completion_date: null,
    customer: { general_contractor: live.gc || '—', owner: '—', architect: '—', structural_engineer: '—' },
    team: { project_manager: live.pm || '—', estimator: '—', field_superintendent: '—', drafting_lead: '—', account_manager: '—' },
    contract: { contract_type: '—', retainage_pct: null, payment_terms: '—', billing_schedule: '—', review_complete: false },
    financials: null,
    production: null,
    schedule: null,
    releases: live.releases || [],
    submittals: live.submittals || [],
    contacts: [],
    documents: [],
    vendors: [],
    activity: live.activity || [],
    health: live.health || [],
    health_score: live.health_score,
    upcoming: live.upcoming || [],
    lookahead: live.lookahead || null,
    brief: null,
  };
}

// Tabs whose data comes from the live /brain/projects endpoint once a real project
// row matches this job_number. The rest stay on demo data (no backend source yet).
const LIVE_TABS = new Set(['Releases', 'Submittals', 'Activity']);

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

const LA_STATUS = {
  complete:    { label: 'Delivered',   cls: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300' },
  on_track:    { label: 'On track',    cls: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300' },
  slip:        { label: 'Slipped',     cls: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300' },
  in_drafting: { label: 'In drafting', cls: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300' },
  no_record:   { label: 'No release',  cls: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300' },
};
const LA_SCOPE = { steel: 'Structural Steel', embed: 'Embeds' };
const LA_SEV_RANK = { high: 0, medium: 1, ok: 2 };

// Dedupe identical activity rows (the export lists a resourced + summary copy of some items).
function dedupeActivities(activities) {
  const seen = new Set();
  const out = [];
  for (const a of activities) {
    const key = `${a.building}|${a.scope}|${a.gc_need}|${a.status}|${a.matched_ref}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(a);
  }
  return out;
}

// The GC Lookahead cross-check panel — each GC metal activity matched to our record, with
// our date vs the GC need date and the resulting gap. Sourced (for now) from the forwarded
// email's sample schedule; the math + health impact are real.
function GcLookaheadPanel({ data }) {
  const rows = dedupeActivities(data.activities).sort(
    (a, b) => (LA_SEV_RANK[a.severity] ?? 9) - (LA_SEV_RANK[b.severity] ?? 9)
  );
  const gaps = rows.filter(r => r.severity !== 'ok').length;
  return (
    <SectionCard className="overflow-hidden">
      <div className="-m-4 mb-0 px-4 py-3 bg-gradient-to-r from-slate-700 to-slate-800 dark:from-slate-800 dark:to-slate-900">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2 text-white">
            <span>📋</span>
            <span className="font-semibold">GC Lookahead · {data.gc}</span>
            {gaps > 0 && (
              <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-red-400/90 text-red-950">
                {gaps} gap{gaps === 1 ? '' : 's'}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-white/70">issued {data.issued}</span>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wide bg-amber-300/90 text-amber-950">
              Mock · email
            </span>
          </div>
        </div>
      </div>
      <div className="pt-4">
        <p className="text-xs text-gray-400 dark:text-slate-500 mb-3">
          From the forwarded email “{data.subject}” — GC need dates cross-checked live against our releases.
        </p>
        <div className="overflow-x-auto -mx-4 -mb-4">
          <table className="w-full text-sm min-w-[680px]">
            <thead className="border-b border-gray-100 dark:border-slate-700">
              <tr><Th>Scope</Th><Th>Building</Th><Th>GC Need</Th><Th>Our Record</Th><Th>Our Date</Th><Th>Status</Th></tr>
            </thead>
            <tbody className="divide-y divide-gray-50 dark:divide-slate-700/50">
              {rows.map((a, i) => {
                const st = LA_STATUS[a.status] || LA_STATUS.on_track;
                return (
                  <tr key={`${a.wbs_id}-${i}`}>
                    <Td className="font-medium">{LA_SCOPE[a.scope] || a.scope}</Td>
                    <Td className="text-gray-500 dark:text-slate-400">{a.building}</Td>
                    <Td className="tabular-nums">{a.gc_need}</Td>
                    <Td className="font-mono text-xs">
                      {a.matched_ref
                        ? <span className="text-accent-600 dark:text-accent-300 font-semibold">{a.matched_kind === 'submittal' ? `DRR ${a.matched_ref}` : a.matched_ref}</span>
                        : <span className="text-red-500">none</span>}
                    </Td>
                    <Td className="tabular-nums text-gray-500 dark:text-slate-400">
                      {a.our_date || '—'}
                      {a.slip_days > 0 && <span className="text-amber-600 dark:text-amber-400"> +{a.slip_days}d late</span>}
                      {a.slip_days < 0 && <span className="text-green-600 dark:text-green-400"> {-a.slip_days}d early</span>}
                    </Td>
                    <Td><span className={`px-2 py-0.5 rounded-full text-xs font-medium ${st.cls}`}>{st.label}</span></Td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
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
    // Live-only job: show what the job log actually knows, not a wall of empty demo fields.
    if (project.live) {
      const openSubs = project.submittals.filter(s => (s.status || '').toLowerCase() === 'open').length;
      return (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <SectionCard title="Job Facts">
            <MetaRow label="General Contractor" value={project.customer.general_contractor} />
            <MetaRow label="Job Number" value={project.job_number} />
            <MetaRow label="Releases" value={project.releases.length} />
            <MetaRow label="Submittals" value={`${project.submittals.length} (${openSubs} open)`} />
            <MetaRow label="Production" value={`${project.percent_complete}% complete`} />
          </SectionCard>
          <SectionCard title="Team, Contract & Dates" className="lg:col-span-2">
            <p className="text-sm text-gray-500 dark:text-slate-400">
              Owner, architect, internal team, contract terms, and key dates aren’t in the job log —
              they land here with the ingestion pipeline. Everything on this page now (releases,
              submittals, activity, health, GC lookahead) is live.
            </p>
          </SectionCard>
        </div>
      );
    }
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
        {project.production && (
          <SectionCard title="Production Quantities" className="lg:col-span-2">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <Metric label="Guardrail (LF)" value={project.production.linear_feet_guardrail.toLocaleString()} />
              <Metric label="Stairs" value={project.production.stairs} />
              <Metric label="Balconies" value={project.production.balconies} />
              <Metric label="Awnings" value={project.production.awnings} />
              <Metric label="Misc Metals" value={project.production.miscellaneous_metals} />
            </div>
          </SectionCard>
        )}
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
              {project.releases.map((r, i) => (
                <tr key={r.release ?? i}>
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
              {project.submittals.map((s, i) => (
                <tr key={s.rel ?? i}>
                  <Td className="font-mono text-xs font-semibold text-accent-600 dark:text-accent-300">{s.rel ?? '—'}</Td>
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
    if (!project.schedule) return <UnavailablePanel label="Schedule" />;
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
    if (!money) return <UnavailablePanel label="Financials" />;
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
        <SectionCard title="Change Orders & T&M" className="lg:col-span-1">
          <div className="flex items-center gap-2 mb-2">
            <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
              Coming soon
            </span>
          </div>
          <p className="text-sm text-gray-500 dark:text-slate-400">
            Open change orders and T&amp;M tickets will land here — computed from the
            <span className="font-medium text-gray-700 dark:text-slate-300"> T&amp;M ingestion pipeline</span> (in progress),
            not hand-entered. Until then contract value and retainage % are the only inputs; everything else is a
            <span className="font-medium text-gray-700 dark:text-slate-300"> computed rollup</span>.
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

// Placeholder for a demo-only section on a live job that has no backend source yet.
function UnavailablePanel({ label }) {
  return (
    <SectionCard>
      <div className="py-8 text-center">
        <p className="text-sm text-gray-500 dark:text-slate-400">
          {label} isn’t wired for live jobs yet.
        </p>
        <p className="mt-1 text-xs text-gray-400 dark:text-slate-500">
          This job is pulled from the job log (releases, submittals, activity). {label} lands with the ingestion pipeline.
        </p>
      </div>
    </SectionCard>
  );
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

// Non-blocking banner communicating where the data on screen comes from.
function DataSourceBanner({ status, jobNumber, health }) {
  if (status === 'loading') {
    return (
      <div className="rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-xs text-gray-500 dark:text-slate-400 flex items-center gap-2">
        <span className="inline-block w-2 h-2 rounded-full bg-gray-300 dark:bg-slate-500 animate-pulse" />
        Checking the live database for job {jobNumber}…
      </div>
    );
  }
  if (status === 'live') {
    return (
      <div className="rounded-lg border border-green-200 dark:border-green-800/60 bg-green-50 dark:bg-green-900/20 px-3 py-2 text-xs text-green-800 dark:text-green-300 flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="inline-block w-2 h-2 rounded-full bg-green-500" />
        <span className="font-semibold">Live data</span>
        <span className="text-green-700/80 dark:text-green-300/80">
          — Releases, Submittals, Activity & Health come from the live database
          {health != null && ` (${health.releaseCount} releases · ${health.submittalCount} submittals)`}.
          Financials & Contract land with the ingestion pipeline.
        </span>
      </div>
    );
  }
  if (status === 'error') {
    return (
      <div className="rounded-lg border border-amber-200 dark:border-amber-800/60 bg-amber-50 dark:bg-amber-900/20 px-3 py-2 text-xs text-amber-800 dark:text-amber-300 flex items-center gap-2">
        <span className="inline-block w-2 h-2 rounded-full bg-amber-500" />
        Couldn’t reach the live endpoint — showing demo data.
      </div>
    );
  }
  return (
    <div className="rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-xs text-gray-500 dark:text-slate-400 flex items-center gap-2">
      <span className="inline-block w-2 h-2 rounded-full bg-gray-300 dark:bg-slate-500" />
      No live project matches job {jobNumber} yet — showing demo data.
    </div>
  );
}

export default function ProjectDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [tab, setTab] = useState('Overview');
  const demoProject = getDemoProject(id);

  // Live overlay: fetch the real rollup by job_number and merge the sections that have
  // a backend source over the demo scaffold. Demo sections (financials/contract/etc.)
  // are untouched. status: 'loading' | 'live' | 'none' | 'error'.
  const [live, setLive] = useState(null);
  const [status, setStatus] = useState('loading');

  useEffect(() => {
    let cancelled = false;
    setStatus('loading');
    // A demo project fetches by its job_number; a live-only route (e.g. /projects/560)
    // treats the route id itself as the job number.
    const jobNumber = demoProject ? demoProject.job_number : id;
    fetchProjectLive(jobNumber)
      .then(data => {
        if (cancelled) return;
        if (data) { setLive(data); setStatus('live'); }
        else { setStatus(demoProject ? 'none' : 'notfound'); }
      })
      .catch(() => { if (!cancelled) setStatus(demoProject ? 'error' : 'notfound'); });
    return () => { cancelled = true; };
  }, [demoProject, id]);

  // Three cases: demo overlaid with live, demo-only, or a live-only job (no demo scaffold).
  let project;
  if (demoProject && live) {
    project = {
      ...demoProject,
      percent_complete: live.percent_complete,
      releases: live.releases,
      submittals: live.submittals,
      activity: live.activity,
      health: live.health,
      health_score: live.health_score,
      upcoming: live.upcoming,
      lookahead: live.lookahead,
    };
  } else if (demoProject) {
    project = demoProject;
  } else if (live) {
    project = liveOnlyProject(live);
  } else {
    project = null;
  }

  // Live health_score when the backend supplied one; demo fallback otherwise.
  const healthScore = project ? resolveHealthScore(project) : null;

  const liveMeta = live
    ? { releaseCount: live.releases.length, submittalCount: live.submittals.length }
    : null;

  if (!project) {
    const loading = status === 'loading';
    return (
      <div className="flex-1 w-full bg-[#f8fafc] dark:bg-slate-900 flex flex-col items-center justify-center gap-3 py-20">
        <p className="text-gray-500 dark:text-slate-400">
          {loading ? `Loading job ${id}…` : 'Project not found.'}
        </p>
        {!loading && (
          <button onClick={() => navigate('/projects')} className="px-4 py-2 text-sm font-medium rounded-lg bg-accent-500 text-white hover:bg-accent-600">
            Back to Projects
          </button>
        )}
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
                {project.live && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-bold uppercase tracking-wide bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                    Live from job log
                  </span>
                )}
              </div>
              <h1 className="mt-2 text-2xl font-bold text-gray-900 dark:text-slate-100">{project.project_name}</h1>
              <p className="mt-1 text-sm text-gray-500 dark:text-slate-400">
                {project.customer.general_contractor}
                {project.team.project_manager && project.team.project_manager !== '—' && <> · PM {project.team.project_manager}</>}
                {project.estimated_completion_date && <> · Est. completion {project.estimated_completion_date}</>}
              </p>
            </div>
            <div className="text-right">
              {project.financials && (
                <>
                  <div className="text-2xl font-bold text-gray-900 dark:text-slate-100 tabular-nums">{fmtMoney(project.financials.forecast_invoice_value)}</div>
                  <div className="text-xs text-gray-400 dark:text-slate-500">forecast invoice value</div>
                </>
              )}
              <div className="mt-2 w-40 ml-auto">
                <div className="flex justify-between text-xs mb-1"><span className="text-gray-500 dark:text-slate-400">{project.percent_complete}% complete</span></div>
                <ProgressBar pct={project.percent_complete} />
              </div>
            </div>
          </div>
        </div>

        {/* Where the data comes from */}
        <DataSourceBanner status={status} jobNumber={project.job_number} health={liveMeta} />

        {/* Project Brief (demo scaffold only; a live-only job has no BB01 brief yet) */}
        {project.brief && <ProjectBrief brief={project.brief} />}

        {/* Health dashboard — composite score (the rating) + its tile breakdown */}
        <div>
          <h2 className="text-xs font-bold uppercase tracking-wide text-gray-400 dark:text-slate-500 mb-2">Project Health</h2>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
            <HealthScore data={healthScore} className="lg:col-span-1" />
            <div className="lg:col-span-2 grid grid-cols-2 sm:grid-cols-3 gap-2.5 content-start">
              {project.health.map(h => <HealthTile key={h.key} label={h.label} value={h.value} tone={h.tone} />)}
            </div>
          </div>
        </div>

        {/* GC Lookahead cross-check (present when the job is wired to a lookahead) */}
        {project.lookahead && <GcLookaheadPanel data={project.lookahead} />}

        {/* Tabs */}
        <div>
          <div className="flex gap-1 overflow-x-auto border-b border-gray-200 dark:border-slate-700 mb-4">
            {TABS.map(t => {
              const isLive = status === 'live' && LIVE_TABS.has(t);
              return (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTab(t)}
                  className={`px-3 py-2 text-sm font-medium whitespace-nowrap border-b-2 -mb-px transition-colors flex items-center gap-1.5 ${
                    tab === t
                      ? 'border-accent-500 text-accent-600 dark:text-accent-300'
                      : 'border-transparent text-gray-500 dark:text-slate-400 hover:text-gray-800 dark:hover:text-slate-200'
                  }`}
                >
                  {t}
                  {isLive && (
                    <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-500" title="Live data" />
                  )}
                </button>
              );
            })}
          </div>
          <TabPanel tab={tab} project={project} />
        </div>
      </div>
    </div>
  );
}
