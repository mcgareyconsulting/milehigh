/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Static demo data for the Projects tab prototype. Shapes a Project as the
 *   top-level container (identity, team, contract, schedule, financials, production,
 *   child releases/submittals, contacts, vendors, documents, activity, computed health,
 *   and a BB01-generated Project Brief) so the client can see the target UX before any
 *   real ingestion is wired. NOTHING here is live — replace section-by-section as the
 *   pipeline matures. Mirrors docs/projects-data-model-v2 (refined model).
 * exports:
 *   DEMO_PROJECTS: array of fully-populated demo projects
 *   getDemoProject(id): lookup helper by project id or job_number
 *   PROJECT_STATUS: status enum + display metadata
 * imports_from: []
 * imported_by: [frontend/src/pages/Projects.jsx, frontend/src/pages/ProjectDetail.jsx]
 * invariants:
 *   - Demo-only; no network. Values are internally coherent (billed <= contract, etc.).
 */

// Coarse project status — distinct from Releases.stage_group (a finer production axis).
export const PROJECT_STATUS = {
  active:    { label: 'Active',    tone: 'green' },
  on_hold:   { label: 'On Hold',   tone: 'amber' },
  complete:  { label: 'Complete',  tone: 'slate' },
  cancelled: { label: 'Cancelled', tone: 'red' },
};

// Health metric tone semantics: 'good' green, 'warn' amber, 'risk' red, 'neutral' slate.
// Each tile is a COMPUTED rollup in the real system — never a stored input column.

const projects = [
  {
    id: 1,
    job_number: '290',
    project_name: 'Confluence Station Parking Garage',
    customer_project_number: 'MORT-2024-0413',
    contract_number: 'C-290153',
    status: 'active',
    percent_complete: 62,
    created_date: '2025-11-04',
    estimated_start_date: '2026-01-12',
    estimated_completion_date: '2026-09-30',
    actual_completion_date: null,

    customer: {
      general_contractor: 'Mortenson Construction',
      owner: 'Confluence Development Partners',
      architect: 'Shears Adkins Rockmore',
      structural_engineer: 'KL&A Engineers',
    },
    team: {
      project_manager: 'Doug Whitfield',
      estimator: 'Ray Sandoval',
      field_superintendent: 'Marcus Lee',
      drafting_lead: 'Katie Brennan',
      account_manager: 'Bill Hargrove',
      executive_owner: 'Bill Hargrove',
    },
    contract: {
      uploaded: true,
      review_complete: true,
      contract_type: 'Lump Sum Subcontract',
      retainage_pct: 10,
      payment_terms: 'Net 30',
      billing_schedule: 'Monthly — 25th',
    },
    financials: {
      original_contract_value: 1_842_000,
      approved_change_orders: 74_500,
      pending_change_orders: 31_200,
      current_billed: 1_180_400,
      payments_received: 1_040_900,
      retainage: 118_040,
      forecast_invoice_value: 1_916_500,
    },
    production: {
      linear_feet_guardrail: 4820,
      stairs: 6,
      balconies: 0,
      awnings: 0,
      miscellaneous_metals: 14,
    },
    schedule: {
      customer: [
        { milestone: 'Level 2 deck pour', date: '2026-05-18', status: 'complete' },
        { milestone: 'Guardrail install start', date: '2026-07-14', status: 'upcoming' },
        { milestone: 'Substantial completion', date: '2026-09-30', status: 'upcoming' },
      ],
      internal: [
        { milestone: 'Required submittal date', date: '2026-02-02', status: 'complete' },
        { milestone: 'Required FC date', date: '2026-06-06', status: 'complete' },
        { milestone: 'Material order date', date: '2026-06-20', status: 'complete' },
        { milestone: 'Fabrication start', date: '2026-07-01', status: 'active' },
        { milestone: 'Required ship date', date: '2026-07-09', status: 'upcoming' },
        { milestone: 'Required install date', date: '2026-07-14', status: 'upcoming' },
      ],
    },
    releases: [
      { release: '290-153', description: 'Levels 1–3 perimeter guardrail', stage: 'Fabrication', hours: 210, start_install: '2026-07-14', pct: 55 },
      { release: '290-158', description: 'Stair towers A & B rails', stage: 'FC Complete', hours: 138, start_install: '2026-07-28', pct: 20 },
      { release: '290-162', description: 'Level 4–5 perimeter guardrail', stage: 'Detailing', hours: 176, start_install: '2026-08-11', pct: 8 },
    ],
    submittals: [
      { rel: 412, title: 'Guardrail shop drawings — Lvl 1–3', type: 'GC Approval', status: 'Approved', ball_in_court: 'MHMW', due_date: '2026-02-02' },
      { rel: 418, title: 'Stair rail assemblies', type: 'For Construction', status: 'In Review', ball_in_court: 'Mortenson', due_date: '2026-07-10' },
      { rel: 421, title: 'Handrail bracket details', type: 'For Record', status: 'Overdue', ball_in_court: 'KL&A Engineers', due_date: '2026-06-28' },
    ],
    contacts: [
      { name: 'Doug Whitfield', company: 'MHMW', role: 'Project Manager', phone: '303-555-0142', email: 'doug@mhmw.com' },
      { name: 'Sarah Kim', company: 'Mortenson', role: 'GC Project Engineer', phone: '303-555-0188', email: 'skim@mortenson.com' },
      { name: 'Tom Reyes', company: 'KL&A Engineers', role: 'Structural EOR', phone: '303-555-0170', email: 'treyes@klaeng.com' },
    ],
    vendors: [
      { vendor: 'Drexel Metals (tube steel)', notified: true, material_ordered: true, expected_delivery: '2026-06-30' },
      { vendor: 'Valmont (galvanizing)', notified: true, material_ordered: false, expected_delivery: '2026-07-18' },
    ],
    documents: [
      { doc_type: 'Contract', name: 'Mortenson Subcontract — executed.pdf', date: '2025-11-06' },
      { doc_type: 'FC Drawings', name: '290-153 FC Set Rev C.pdf', date: '2026-06-06' },
      { doc_type: 'Customer Schedule', name: 'Confluence Baseline Schedule.pdf', date: '2026-01-09' },
      { doc_type: 'Submittal', name: 'Guardrail Shop Drawings.pdf', date: '2026-01-28' },
    ],
    activity: [
      { at: '2026-07-06', who: 'Katie Brennan', text: 'Released 290-162 to detailing' },
      { at: '2026-07-02', who: 'System', text: 'Submittal Rel 421 flagged overdue (ball-in-court: KL&A)' },
      { at: '2026-06-30', who: 'Doug Whitfield', text: 'Tube steel order confirmed with Drexel' },
      { at: '2026-06-06', who: 'System', text: 'FC set Rev C uploaded' },
    ],
    health: [
      { key: 'submittals_overdue', label: 'Submittals Overdue', value: '1', tone: 'risk' },
      { key: 'pending_change_orders', label: 'Pending COs', value: '$31.2k', tone: 'warn' },
      { key: 'billing_available', label: 'Billing Available', value: '$142k', tone: 'good' },
      { key: 'materials_at_risk', label: 'Materials at Risk', value: 'None', tone: 'good' },
      { key: 'fabrication_delay', label: 'Fab Delay', value: 'On track', tone: 'good' },
      { key: 'installation_risk', label: 'Install Risk', value: 'Low', tone: 'good' },
      { key: 'cashflow_forecast', label: 'Cashflow Forecast', value: '+$118k', tone: 'good' },
      { key: 'forecast_accuracy', label: 'Forecast Accuracy', value: '94%', tone: 'good' },
    ],
    brief: {
      risk_level: 'Low',
      generated_at: '2026-07-07 06:00',
      status_line: 'On schedule and on budget. Fabrication is underway for the Levels 1–3 guardrail release with install starting July 14.',
      upcoming: [
        'Guardrail install starts Jul 14 (Level 1–3)',
        'Required ship date Jul 9 — 2 days out',
        'Level 4–5 detailing due into fab by Aug 11',
      ],
      risks: [
        'Submittal Rel 421 (handrail brackets) is overdue with the EOR — could delay stair rail fabrication if not returned by Jul 10.',
      ],
      approvals: ['Stair rail assemblies (Rel 418) in review with Mortenson'],
      forecast: 'Forecast completion Sep 30 (no change). Forecast invoice value $1.92M, +$74.5k over base from approved COs.',
      next_actions: [
        'Chase KL&A on overdue bracket submittal (Rel 421)',
        'Confirm galvanizing slot with Valmont before ship date',
        'Submit July billing ($142k available) by the 25th',
      ],
    },
  },

  {
    id: 2,
    job_number: '580',
    project_name: 'RiNo Art District Mixed-Use',
    customer_project_number: 'SAUN-25-118',
    contract_number: 'C-580659',
    status: 'active',
    percent_complete: 38,
    created_date: '2026-02-19',
    estimated_start_date: '2026-04-06',
    estimated_completion_date: '2026-11-20',
    actual_completion_date: null,

    customer: {
      general_contractor: 'Saunders Construction',
      owner: 'RiNo Ventures LLC',
      architect: 'Tryba Architects',
      structural_engineer: 'Martin/Martin',
    },
    team: {
      project_manager: 'Doug Whitfield',
      estimator: 'Ray Sandoval',
      field_superintendent: 'Anthony Cruz',
      drafting_lead: 'Katie Brennan',
      account_manager: 'Bill Hargrove',
      executive_owner: 'Bill Hargrove',
    },
    contract: {
      uploaded: true,
      review_complete: false,
      contract_type: 'GMP Subcontract',
      retainage_pct: 5,
      payment_terms: 'Net 45',
      billing_schedule: 'Monthly — 20th',
    },
    financials: {
      original_contract_value: 967_500,
      approved_change_orders: 0,
      pending_change_orders: 52_800,
      current_billed: 318_200,
      payments_received: 302_290,
      retainage: 15_910,
      forecast_invoice_value: 1_020_300,
    },
    production: {
      linear_feet_guardrail: 1240,
      stairs: 3,
      balconies: 22,
      awnings: 2,
      miscellaneous_metals: 9,
    },
    schedule: {
      customer: [
        { milestone: 'Podium deck complete', date: '2026-06-30', status: 'complete' },
        { milestone: 'Balcony install start', date: '2026-08-04', status: 'upcoming' },
        { milestone: 'Topping out', date: '2026-10-15', status: 'upcoming' },
      ],
      internal: [
        { milestone: 'Required submittal date', date: '2026-05-01', status: 'complete' },
        { milestone: 'Required FC date', date: '2026-07-18', status: 'active' },
        { milestone: 'Material order date', date: '2026-07-25', status: 'upcoming' },
        { milestone: 'Fabrication start', date: '2026-08-08', status: 'upcoming' },
        { milestone: 'Required install date', date: '2026-08-04', status: 'upcoming' },
      ],
    },
    releases: [
      { release: '580-659', description: 'Level 2–4 balcony rails (22 ea)', stage: 'Detailing', hours: 264, start_install: '2026-08-04', pct: 30 },
      { release: '580-664', description: 'Lobby feature stair', stage: 'Submittal', hours: 190, start_install: '2026-09-15', pct: 10 },
    ],
    submittals: [
      { rel: 503, title: 'Balcony rail shop drawings', type: 'GC Approval', status: 'In Review', ball_in_court: 'Saunders', due_date: '2026-07-12' },
      { rel: 509, title: 'Feature stair design assist', type: 'DRR', status: 'Draft', ball_in_court: 'MHMW', due_date: '2026-07-22' },
    ],
    contacts: [
      { name: 'Doug Whitfield', company: 'MHMW', role: 'Project Manager', phone: '303-555-0142', email: 'doug@mhmw.com' },
      { name: 'Priya Nair', company: 'Saunders', role: 'Project Manager', phone: '720-555-0311', email: 'pnair@saunders.com' },
    ],
    vendors: [
      { vendor: 'Drexel Supply (deck & angle)', notified: true, material_ordered: false, expected_delivery: '2026-08-01' },
    ],
    documents: [
      { doc_type: 'Contract', name: 'Saunders GMP Subcontract.pdf', date: '2026-02-21' },
      { doc_type: 'Customer Schedule', name: 'RiNo Baseline v2.pdf', date: '2026-03-30' },
    ],
    activity: [
      { at: '2026-07-05', who: 'Katie Brennan', text: 'Balcony rail detailing 30% complete' },
      { at: '2026-07-01', who: 'System', text: 'Pending CO logged: $52.8k (added canopy scope)' },
      { at: '2026-06-30', who: 'Anthony Cruz', text: 'Podium deck confirmed complete on site' },
    ],
    health: [
      { key: 'submittals_overdue', label: 'Submittals Overdue', value: 'None', tone: 'good' },
      { key: 'pending_change_orders', label: 'Pending COs', value: '$52.8k', tone: 'warn' },
      { key: 'billing_available', label: 'Billing Available', value: '$61k', tone: 'good' },
      { key: 'materials_at_risk', label: 'Materials at Risk', value: 'Deck steel', tone: 'warn' },
      { key: 'fabrication_delay', label: 'Fab Delay', value: 'At risk', tone: 'warn' },
      { key: 'installation_risk', label: 'Install Risk', value: 'Medium', tone: 'warn' },
      { key: 'cashflow_forecast', label: 'Cashflow Forecast', value: '+$53k', tone: 'good' },
      { key: 'forecast_accuracy', label: 'Forecast Accuracy', value: '88%', tone: 'good' },
    ],
    brief: {
      risk_level: 'Medium',
      generated_at: '2026-07-07 06:00',
      status_line: 'Early production. Balcony rail detailing is on track but FC release and material order are on the critical path for the Aug 4 balcony install.',
      upcoming: [
        'Required FC date Jul 18 — this week',
        'Balcony install starts Aug 4',
        'Deck steel order needs release by Jul 25',
      ],
      risks: [
        'Contract review not yet complete — retainage and CO markup terms unconfirmed by BB01.',
        'Deck steel not yet ordered; Drexel lead time puts Aug 4 install at risk if the FC set slips past Jul 18.',
      ],
      approvals: ['Balcony rail shop drawings (Rel 503) in review with Saunders'],
      forecast: 'Forecast completion Nov 20. Forecast invoice value $1.02M pending the $52.8k canopy CO.',
      next_actions: [
        'Finish BB01 contract review to lock markup/retainage terms',
        'Release FC set by Jul 18 to protect the material order',
        'Push Saunders to approve balcony rail drawings',
      ],
    },
  },

  {
    id: 3,
    job_number: '610',
    project_name: 'Belleview Station Tower 3',
    customer_project_number: 'PCL-6620',
    contract_number: 'C-610204',
    status: 'on_hold',
    percent_complete: 15,
    created_date: '2026-03-11',
    estimated_start_date: '2026-06-01',
    estimated_completion_date: '2027-02-28',
    actual_completion_date: null,

    customer: {
      general_contractor: 'PCL Construction',
      owner: 'Belleview Station Metro District',
      architect: 'Gensler',
      structural_engineer: 'S.A. Miro',
    },
    team: {
      project_manager: 'Doug Whitfield',
      estimator: 'Ray Sandoval',
      field_superintendent: 'TBD',
      drafting_lead: 'Katie Brennan',
      account_manager: 'Bill Hargrove',
      executive_owner: 'Bill Hargrove',
    },
    contract: {
      uploaded: true,
      review_complete: true,
      contract_type: 'Lump Sum Subcontract',
      retainage_pct: 10,
      payment_terms: 'Net 30',
      billing_schedule: 'Monthly — 25th',
    },
    financials: {
      original_contract_value: 2_310_000,
      approved_change_orders: 0,
      pending_change_orders: 0,
      current_billed: 96_000,
      payments_received: 86_400,
      retainage: 9_600,
      forecast_invoice_value: 2_310_000,
    },
    production: {
      linear_feet_guardrail: 6100,
      stairs: 9,
      balconies: 40,
      awnings: 0,
      miscellaneous_metals: 21,
    },
    schedule: {
      customer: [
        { milestone: 'Structure topped out', date: '2026-09-30', status: 'upcoming' },
        { milestone: 'Metals install start', date: '2026-11-02', status: 'upcoming' },
      ],
      internal: [
        { milestone: 'Required submittal date', date: '2026-08-01', status: 'blocked' },
        { milestone: 'Required FC date', date: '2026-10-01', status: 'blocked' },
      ],
    },
    releases: [
      { release: '610-204', description: 'Tower 3 guardrail package', stage: 'On Hold', hours: 0, start_install: '2026-11-02', pct: 0 },
    ],
    submittals: [
      { rel: 601, title: 'Guardrail design assist', type: 'DRR', status: 'On Hold', ball_in_court: 'PCL', due_date: '2026-08-01' },
    ],
    contacts: [
      { name: 'Doug Whitfield', company: 'MHMW', role: 'Project Manager', phone: '303-555-0142', email: 'doug@mhmw.com' },
      { name: 'Greg Olsen', company: 'PCL', role: 'Senior PM', phone: '720-555-0400', email: 'golsen@pcl.com' },
    ],
    vendors: [],
    documents: [
      { doc_type: 'Contract', name: 'PCL Subcontract — executed.pdf', date: '2026-03-14' },
    ],
    activity: [
      { at: '2026-06-18', who: 'Greg Olsen', text: 'PCL placed metals on hold — owner financing delay' },
      { at: '2026-03-14', who: 'System', text: 'Project created from executed subcontract' },
    ],
    health: [
      { key: 'submittals_overdue', label: 'Submittals Overdue', value: 'Paused', tone: 'neutral' },
      { key: 'pending_change_orders', label: 'Pending COs', value: 'None', tone: 'good' },
      { key: 'billing_available', label: 'Billing Available', value: '$0', tone: 'neutral' },
      { key: 'materials_at_risk', label: 'Materials at Risk', value: 'None', tone: 'good' },
      { key: 'fabrication_delay', label: 'Fab Delay', value: 'On hold', tone: 'neutral' },
      { key: 'installation_risk', label: 'Install Risk', value: 'Unknown', tone: 'neutral' },
      { key: 'cashflow_forecast', label: 'Cashflow Forecast', value: 'Paused', tone: 'neutral' },
      { key: 'forecast_accuracy', label: 'Forecast Accuracy', value: '—', tone: 'neutral' },
    ],
    brief: {
      risk_level: 'On Hold',
      generated_at: '2026-07-07 06:00',
      status_line: 'Project is on hold at PCL’s direction (owner financing delay since Jun 18). No production or submittal activity is scheduled until released.',
      upcoming: ['No active deadlines while on hold'],
      risks: [
        'Schedule risk if the hold extends past September — the guardrail package needs ~10 weeks lead before the Nov 2 install.',
      ],
      approvals: [],
      forecast: 'Forecast completion Feb 2027, contingent on release date. Contract value $2.31M unchanged.',
      next_actions: [
        'Check in with PCL monthly on hold status',
        'Keep the estimate warm — re-price steel if hold exceeds 90 days',
      ],
    },
  },

  {
    id: 4,
    job_number: '445',
    project_name: 'Cherry Creek Medical Pavilion',
    customer_project_number: 'GHP-44521',
    contract_number: 'C-445088',
    status: 'active',
    percent_complete: 81,
    created_date: '2025-09-22',
    estimated_start_date: '2025-11-10',
    estimated_completion_date: '2026-08-15',
    actual_completion_date: null,

    customer: {
      general_contractor: 'GH Phipps Construction',
      owner: 'Cherry Creek Health Partners',
      architect: 'Davis Partnership',
      structural_engineer: 'Monroe & Newell',
    },
    team: {
      project_manager: 'Doug Whitfield',
      estimator: 'Ray Sandoval',
      field_superintendent: 'Marcus Lee',
      drafting_lead: 'Katie Brennan',
      account_manager: 'Bill Hargrove',
      executive_owner: 'Bill Hargrove',
    },
    contract: {
      uploaded: true,
      review_complete: true,
      contract_type: 'Lump Sum Subcontract',
      retainage_pct: 7.5,
      payment_terms: 'Net 30',
      billing_schedule: 'Monthly — 25th',
    },
    financials: {
      original_contract_value: 1_120_000,
      approved_change_orders: 96_400,
      pending_change_orders: 12_000,
      current_billed: 984_600,
      payments_received: 911_000,
      retainage: 73_845,
      forecast_invoice_value: 1_228_400,
    },
    production: {
      linear_feet_guardrail: 980,
      stairs: 2,
      balconies: 14,
      awnings: 5,
      miscellaneous_metals: 18,
    },
    schedule: {
      customer: [
        { milestone: 'Envelope complete', date: '2026-05-30', status: 'complete' },
        { milestone: 'Awning install', date: '2026-07-21', status: 'upcoming' },
        { milestone: 'Substantial completion', date: '2026-08-15', status: 'upcoming' },
      ],
      internal: [
        { milestone: 'Required submittal date', date: '2025-12-15', status: 'complete' },
        { milestone: 'Required FC date', date: '2026-03-20', status: 'complete' },
        { milestone: 'Fabrication start', date: '2026-04-01', status: 'complete' },
        { milestone: 'Required install date', date: '2026-07-21', status: 'active' },
      ],
    },
    releases: [
      { release: '445-088', description: 'Balcony rails & guards', stage: 'Install Complete', hours: 220, start_install: '2026-06-02', pct: 100 },
      { release: '445-092', description: 'Entry awnings (5 ea)', stage: 'Ship', hours: 164, start_install: '2026-07-21', pct: 85 },
      { release: '445-095', description: 'Misc embeds & ladders', stage: 'Fabrication', hours: 96, start_install: '2026-07-28', pct: 60 },
    ],
    submittals: [
      { rel: 441, title: 'Awning shop drawings', type: 'For Construction', status: 'Approved', ball_in_court: 'MHMW', due_date: '2025-12-15' },
      { rel: 447, title: 'Closeout O&M package', type: 'For Record', status: 'In Review', ball_in_court: 'GH Phipps', due_date: '2026-08-01' },
    ],
    contacts: [
      { name: 'Doug Whitfield', company: 'MHMW', role: 'Project Manager', phone: '303-555-0142', email: 'doug@mhmw.com' },
      { name: 'Lauren Diaz', company: 'GH Phipps', role: 'Project Engineer', phone: '303-555-0522', email: 'ldiaz@ghphipps.com' },
    ],
    vendors: [
      { vendor: 'Rocky Mountain Powder Coat', notified: true, material_ordered: true, expected_delivery: '2026-07-15' },
    ],
    documents: [
      { doc_type: 'Contract', name: 'GH Phipps Subcontract.pdf', date: '2025-09-24' },
      { doc_type: 'FC Drawings', name: '445-088 FC Set Rev B.pdf', date: '2026-03-20' },
      { doc_type: 'Change Order', name: 'CO-02 Added canopy.pdf', date: '2026-05-12' },
    ],
    activity: [
      { at: '2026-07-06', who: 'Marcus Lee', text: 'Awnings staged for powder coat pickup' },
      { at: '2026-06-02', who: 'System', text: 'Release 445-088 marked install complete' },
      { at: '2026-05-12', who: 'System', text: 'CO-02 approved (+$96.4k)' },
    ],
    health: [
      { key: 'submittals_overdue', label: 'Submittals Overdue', value: 'None', tone: 'good' },
      { key: 'pending_change_orders', label: 'Pending COs', value: '$12k', tone: 'good' },
      { key: 'billing_available', label: 'Billing Available', value: '$88k', tone: 'good' },
      { key: 'materials_at_risk', label: 'Materials at Risk', value: 'None', tone: 'good' },
      { key: 'fabrication_delay', label: 'Fab Delay', value: 'On track', tone: 'good' },
      { key: 'installation_risk', label: 'Install Risk', value: 'Low', tone: 'good' },
      { key: 'cashflow_forecast', label: 'Cashflow Forecast', value: '+$108k', tone: 'good' },
      { key: 'forecast_accuracy', label: 'Forecast Accuracy', value: '96%', tone: 'good' },
    ],
    brief: {
      risk_level: 'Low',
      generated_at: '2026-07-07 06:00',
      status_line: 'Nearing completion at 81%. Balcony scope is installed; awnings ship this week for the Jul 21 install. Closeout package is the last open item.',
      upcoming: [
        'Awning install Jul 21',
        'Misc embeds ship Jul 28',
        'Closeout O&M package due Aug 1',
      ],
      risks: [],
      approvals: ['Closeout O&M package (Rel 447) in review with GH Phipps'],
      forecast: 'Forecast completion Aug 15. Forecast invoice value $1.23M, +$96.4k from approved CO-02.',
      next_actions: [
        'Confirm powder coat pickup Jul 15 to protect awning install',
        'Submit final billing and start retainage release ($73.8k held)',
        'Complete closeout package with GH Phipps',
      ],
    },
  },

  {
    id: 5,
    job_number: '720',
    project_name: 'DIA Concourse B Expansion',
    customer_project_number: 'HP-DEN-7203',
    contract_number: 'C-720311',
    status: 'active',
    percent_complete: 24,
    created_date: '2026-04-28',
    estimated_start_date: '2026-07-01',
    estimated_completion_date: '2027-06-30',
    actual_completion_date: null,

    customer: {
      general_contractor: 'Hensel Phelps',
      owner: 'Denver International Airport',
      architect: 'Gensler',
      structural_engineer: 'Martin/Martin',
    },
    team: {
      project_manager: 'Doug Whitfield',
      estimator: 'Ray Sandoval',
      field_superintendent: 'Anthony Cruz',
      drafting_lead: 'Katie Brennan',
      account_manager: 'Bill Hargrove',
      executive_owner: 'Bill Hargrove',
    },
    contract: {
      uploaded: true,
      review_complete: false,
      contract_type: 'Design-Assist Subcontract',
      retainage_pct: 5,
      payment_terms: 'Net 45',
      billing_schedule: 'Monthly — 20th',
    },
    financials: {
      original_contract_value: 4_680_000,
      approved_change_orders: 0,
      pending_change_orders: 118_000,
      current_billed: 512_000,
      payments_received: 486_400,
      retainage: 25_600,
      forecast_invoice_value: 4_798_000,
    },
    production: {
      linear_feet_guardrail: 9400,
      stairs: 14,
      balconies: 0,
      awnings: 0,
      miscellaneous_metals: 32,
    },
    schedule: {
      customer: [
        { milestone: 'Design-assist GMP set', date: '2026-08-15', status: 'upcoming' },
        { milestone: 'First metals install', date: '2026-12-01', status: 'upcoming' },
      ],
      internal: [
        { milestone: 'Required submittal date', date: '2026-07-30', status: 'active' },
        { milestone: 'Required FC date', date: '2026-10-15', status: 'upcoming' },
      ],
    },
    releases: [
      { release: '720-311', description: 'Concourse guardrail — Phase 1', stage: 'Submittal', hours: 340, start_install: '2026-12-01', pct: 15 },
      { release: '720-318', description: 'Monumental stair (Level 2)', stage: 'Design Assist', hours: 410, start_install: '2027-01-20', pct: 10 },
    ],
    submittals: [
      { rel: 721, title: 'Design-assist guardrail concept', type: 'DRR', status: 'In Review', ball_in_court: 'Hensel Phelps', due_date: '2026-07-30' },
      { rel: 726, title: 'Monumental stair structural coordination', type: 'DRR', status: 'Draft', ball_in_court: 'MHMW', due_date: '2026-08-15' },
    ],
    contacts: [
      { name: 'Doug Whitfield', company: 'MHMW', role: 'Project Manager', phone: '303-555-0142', email: 'doug@mhmw.com' },
      { name: 'Rachel Ford', company: 'Hensel Phelps', role: 'Design-Assist Lead', phone: '303-555-0700', email: 'rford@henselphelps.com' },
    ],
    vendors: [],
    documents: [
      { doc_type: 'Contract', name: 'Hensel Phelps Design-Assist Agreement.pdf', date: '2026-04-30' },
      { doc_type: 'Customer Schedule', name: 'DIA Concourse B Master Schedule.pdf', date: '2026-05-20' },
    ],
    activity: [
      { at: '2026-07-03', who: 'Katie Brennan', text: 'Guardrail concept package in review with HP' },
      { at: '2026-07-01', who: 'System', text: 'Pending CO logged: $118k (added Level 3 scope)' },
    ],
    health: [
      { key: 'submittals_overdue', label: 'Submittals Overdue', value: 'None', tone: 'good' },
      { key: 'pending_change_orders', label: 'Pending COs', value: '$118k', tone: 'warn' },
      { key: 'billing_available', label: 'Billing Available', value: '$96k', tone: 'good' },
      { key: 'materials_at_risk', label: 'Materials at Risk', value: 'None', tone: 'good' },
      { key: 'fabrication_delay', label: 'Fab Delay', value: 'Not started', tone: 'neutral' },
      { key: 'installation_risk', label: 'Install Risk', value: 'Low', tone: 'good' },
      { key: 'cashflow_forecast', label: 'Cashflow Forecast', value: '+$118k', tone: 'good' },
      { key: 'forecast_accuracy', label: 'Forecast Accuracy', value: '82%', tone: 'warn' },
    ],
    brief: {
      risk_level: 'Medium',
      generated_at: '2026-07-07 06:00',
      status_line: 'Large design-assist project in early coordination. Guardrail concept is in review; the monumental stair is the long-lead structural risk.',
      upcoming: [
        'Design-assist submittal due Jul 30',
        'GMP set due to owner Aug 15',
        'FC set required by Oct 15',
      ],
      risks: [
        'Contract review incomplete — design-assist scope boundaries and CO terms not yet confirmed by BB01.',
        'Monumental stair requires early structural coordination with Martin/Martin to hold the Jan 2027 install.',
      ],
      approvals: ['Guardrail concept (Rel 721) in review with Hensel Phelps'],
      forecast: 'Forecast completion Jun 2027. Forecast invoice value $4.80M pending the $118k Level 3 CO.',
      next_actions: [
        'Finish BB01 contract review on the design-assist agreement',
        'Lock structural coordination meeting for the monumental stair',
        'Return guardrail concept revisions to Hensel Phelps',
      ],
    },
  },

  {
    id: 6,
    job_number: '355',
    project_name: 'Union Station Retail Buildout',
    customer_project_number: 'SWIN-3390',
    contract_number: 'C-355020',
    status: 'complete',
    percent_complete: 100,
    created_date: '2025-05-06',
    estimated_start_date: '2025-06-15',
    estimated_completion_date: '2026-02-28',
    actual_completion_date: '2026-03-05',

    customer: {
      general_contractor: 'Swinerton Builders',
      owner: 'Union Station Alliance',
      architect: 'Semple Brown Design',
      structural_engineer: 'S.A. Miro',
    },
    team: {
      project_manager: 'Doug Whitfield',
      estimator: 'Ray Sandoval',
      field_superintendent: 'Marcus Lee',
      drafting_lead: 'Katie Brennan',
      account_manager: 'Bill Hargrove',
      executive_owner: 'Bill Hargrove',
    },
    contract: {
      uploaded: true,
      review_complete: true,
      contract_type: 'Lump Sum Subcontract',
      retainage_pct: 10,
      payment_terms: 'Net 30',
      billing_schedule: 'Monthly — 25th',
    },
    financials: {
      original_contract_value: 486_000,
      approved_change_orders: 22_300,
      pending_change_orders: 0,
      current_billed: 508_300,
      payments_received: 508_300,
      retainage: 0,
      forecast_invoice_value: 508_300,
    },
    production: {
      linear_feet_guardrail: 620,
      stairs: 1,
      balconies: 0,
      awnings: 3,
      miscellaneous_metals: 11,
    },
    schedule: {
      customer: [
        { milestone: 'Substantial completion', date: '2026-02-28', status: 'complete' },
        { milestone: 'Final acceptance', date: '2026-03-05', status: 'complete' },
      ],
      internal: [
        { milestone: 'Required install date', date: '2026-02-10', status: 'complete' },
        { milestone: 'Closeout complete', date: '2026-03-05', status: 'complete' },
      ],
    },
    releases: [
      { release: '355-020', description: 'Storefront guardrail & feature stair', stage: 'Install Complete', hours: 186, start_install: '2026-01-20', pct: 100 },
    ],
    submittals: [
      { rel: 351, title: 'Guardrail & stair shop drawings', type: 'GC Approval', status: 'Approved', ball_in_court: 'MHMW', due_date: '2025-08-01' },
    ],
    contacts: [
      { name: 'Doug Whitfield', company: 'MHMW', role: 'Project Manager', phone: '303-555-0142', email: 'doug@mhmw.com' },
      { name: 'Mike Alvarez', company: 'Swinerton', role: 'Project Manager', phone: '303-555-0910', email: 'malvarez@swinerton.com' },
    ],
    vendors: [],
    documents: [
      { doc_type: 'Contract', name: 'Swinerton Subcontract.pdf', date: '2025-05-08' },
      { doc_type: 'Closeout Package', name: '355-020 Closeout Final.pdf', date: '2026-03-05' },
    ],
    activity: [
      { at: '2026-03-05', who: 'System', text: 'Project closed — final acceptance received' },
      { at: '2026-03-05', who: 'Doug Whitfield', text: 'Retainage released in full' },
      { at: '2026-01-20', who: 'Marcus Lee', text: 'Install complete' },
    ],
    health: [
      { key: 'submittals_overdue', label: 'Submittals Overdue', value: 'None', tone: 'good' },
      { key: 'pending_change_orders', label: 'Pending COs', value: 'None', tone: 'good' },
      { key: 'billing_available', label: 'Billing Available', value: '$0', tone: 'neutral' },
      { key: 'materials_at_risk', label: 'Materials at Risk', value: 'None', tone: 'good' },
      { key: 'fabrication_delay', label: 'Fab Delay', value: 'Complete', tone: 'good' },
      { key: 'installation_risk', label: 'Install Risk', value: 'Complete', tone: 'good' },
      { key: 'cashflow_forecast', label: 'Cashflow Forecast', value: 'Closed', tone: 'neutral' },
      { key: 'forecast_accuracy', label: 'Forecast Accuracy', value: '99%', tone: 'good' },
    ],
    brief: {
      risk_level: 'Complete',
      generated_at: '2026-07-07 06:00',
      status_line: 'Closed out and paid in full. Final acceptance received Mar 5; retainage released. Repeat opportunity with Swinerton noted.',
      upcoming: ['No open items — project closed'],
      risks: [],
      approvals: [],
      forecast: 'Final invoice value $508.3k, +$22.3k over base. Delivered 5 days past baseline (weather).',
      next_actions: [
        'Request client review / testimonial from Swinerton',
        'Archive closeout package to company records',
      ],
    },
  },
];

export const DEMO_PROJECTS = projects;

export function getDemoProject(id) {
  const key = String(id);
  return projects.find(p => String(p.id) === key || p.job_number === key) || null;
}
