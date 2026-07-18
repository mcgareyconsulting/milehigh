/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Static, human-curated changelog feeding the in-app version badge and Patch Notes modal. Newest release first.
 * exports:
 *   PATCH_NOTES: ordered list of release entries
 *   CURRENT_VERSION: convenience accessor for PATCH_NOTES[0].version
 * imports_from: []
 * imported_by: [frontend/src/components/PatchNotesModal.jsx, frontend/src/components/AppShell.jsx]
 * invariants:
 *   - PATCH_NOTES[0] is always the latest release; the version badge renders its `version`.
 *   - Version scheme: v2.0.<pr> where <pr> is the highest merged PR number in the release.
 *   - Each entry's `version` is unique.
 *   - `type` on a change is one of: 'new' | 'improved' | 'fixed'.
 *   - `adminOnly: true` on a change hides it from non-admin users in the modal.
 */

export const PATCH_NOTES = [
  {
    version: 'v2.0.291',
    date: 'July 18, 2026',
    summary:
      'BB drawing review on a submittal is now reliable on large sets, and the Materials Ordered list scrolls when it gets long.',
    changes: [
      {
        type: 'fixed',
        title: 'BB submittal review no longer times out',
        adminOnly: true,
        detail:
          'Reviewing a For-Construction drawing on a submittal now runs in the background instead of blocking the request. The Claude call takes minutes, which was tripping the server\'s request timeout and killing the worker mid-review; the review now moves from pending to complete (or error) on its own and the panel polls for the result, so large or slow reviews finish cleanly and surface a real error message if the call fails.',
      },
      {
        type: 'improved',
        title: 'Materials Ordered list scrolls when long',
        detail:
          'On a release with a lot of ordered material, the Materials Ordered section in Job Details now scrolls within its own area instead of overflowing the modal.',
      },
    ],
  },
  {
    version: 'v2.0.289',
    date: 'July 13, 2026',
    summary:
      'A system-usage dashboard with real AI cost and reliability tracking, and BB drawing review moved onto the submittal itself — pulling For-Construction sets straight from Procore.',
    changes: [
      {
        type: 'new',
        title: 'System-usage & AI dashboard',
        adminOnly: true,
        detail:
          'A new Metrics page shows how the app is actually being used — engagement and adoption, content and activity, release throughput, and system health — over a Day / Week / Month window. Every AI call across the Brain (BB chat, drawing review, supplier-order capture, meeting notes) is now metered, so the dashboard reports real AI spend, reliability, and quality instead of guesswork.',
      },
      {
        type: 'improved',
        title: 'BB drawing review on the submittal, straight from Procore',
        adminOnly: true,
        detail:
          'Banana Boy\'s code-compliance review now lives on the submittal itself: open a submittal and pull its For-Construction drawings directly from Procore, then review each document in place. Every document runs its own review with a verdict tally and an in-line findings list, you can choose a deep (Opus) or lighter, faster (Sonnet) pass, and re-run any document as the set changes.',
      },
    ],
  },
  {
    version: 'v2.0.288',
    date: 'July 12, 2026',
    summary:
      'A redesigned Timeline that reads like the board on its side, incoming material orders you can now open right from it, and a new tool for matching submittals to their releases.',
    changes: [
      {
        type: 'improved',
        title: 'Redesigned Timeline, and a much better tablet view',
        detail:
          'The Timeline is now a day/week bucket board — the Trello board turned on its side — with a Shipping Planning and a Shipping Completed lane on top of the installer-team lanes. Zoom scales the columns from single days out to whole weeks, cards sit on their exact Start-install date, and the whole view was reworked to look and behave far better on an iPad in landscape.',
      },
      {
        type: 'new',
        title: 'Incoming material orders on the Timeline',
        detail:
          'PU / pickup, stock, and galvanizing "ready to ship" orders now appear as chips on the Timeline\'s Shipping Planning lane, positioned by their ready or ordered date so you can see what still has to come in. The chips are now larger and clickable — click one to open that release\'s job details scrolled straight to its Materials Ordered list.',
      },
      {
        type: 'new',
        title: 'Match submittals to releases',
        adminOnly: true,
        detail:
          'A new admin tool suggests which release each drafting submittal belongs to, scoring every suggestion as Confident, Pick-one, or Weak. You confirm, pick between candidates, or mark no match — tightening the submittal-to-release link that the rest of the Brain relies on.',
      },
    ],
  },
  {
    version: 'v2.0.284',
    date: 'July 9, 2026',
    summary:
      'BB can now review a drawing set for code compliance, supplier galvanizing and stock status shows up on job details, and verbal releases are easier and safer to enter.',
    changes: [
      {
        type: 'new',
        title: 'BB code-compliance review for drawings',
        adminOnly: true,
        detail:
          'Banana Boy can now review a release\'s full For-Construction drawing set against a library of fabrication and structural code rules, flagging issues by severity with the sheet citations it used to reach each finding. PMs can accept or deny each flag to help BB improve.',
      },
      {
        type: 'new',
        title: 'Galvanizing & stock order status tracking',
        adminOnly: true,
        detail:
          'Supplier-order capture now also picks up galvanizing "ready to ship" and stock "ready for pickup" notifications forwarded to the mailbox, showing them on the job details panel with their own Planning → Complete status alongside itemized material orders.',
      },
      {
        type: 'improved',
        title: 'Paste-in verbal releases, plus duplicate protection',
        detail:
          'The Verbal Release modal now has a Paste mode — paste one row from a spreadsheet and it fills the form for you. Both verbal and bulk release entry also now catch likely duplicates (same job, name, and description under a different release number) and ask you to confirm before creating them.',
      },
    ],
  },
  {
    version: 'v2.0.281',
    date: 'July 5, 2026',
    summary:
      'Ask BB about any release or submittal, cheaper and more reliable supplier-order capture, and a behind-the-scenes logging and security cleanup.',
    changes: [
      {
        type: 'new',
        title: 'Ask BB about a release or submittal',
        adminOnly: true,
        detail:
          'A new read-only BB chat: type a release or submittal number and BB assembles its full lifecycle — status, submittals, a merged event timeline, and open to-dos — into one grounded summary. Read-only for now; every answer is drawn straight from the Brain.',
      },
      {
        type: 'improved',
        title: 'Cheaper, more reliable supplier-order capture',
        adminOnly: true,
        detail:
          'Supplier-order emails forwarded to the Banana Boy mailbox are now scanned exactly once instead of being re-checked on every poll, and re-scanned only when a late attachment lands. This removes a large silent AI cost and speeds up ingestion.',
      },
      {
        type: 'fixed',
        title: 'Logging and security hardening',
        adminOnly: true,
        detail:
          'A ground-up cleanup of application logs: closed two spots where credentials could reach the logs, cut steady-state log noise, and made every log line consistent and parseable. No change to how the app behaves.',
      },
    ],
  },
  {
    version: 'v2.0.278',
    date: 'July 1, 2026',
    summary:
      'Log a verbal release in seconds, edit any Job Log row inline, schedule Sub-GC drafting from the GC\'s jobsite date, and easier-to-read green dates.',
    changes: [
      {
        type: 'new',
        title: 'Log a verbal release',
        detail:
          'A quick-entry form on the Releases page for releases that come in verbally.',
      },
      {
        type: 'new',
        title: 'Edit a whole Job Log row inline',
        adminOnly: true,
        detail:
          'You can now edit every non-locked field on a Job Log row right inline. Your changes sync straight to the Trello card and its mirror card, so the boards stay in step.',
      },
      {
        type: 'new',
        title: 'Schedule Sub-GC drafting from the GC\'s jobsite date',
        detail:
          'On a Sub-GC submittal you can enter the GC\'s jobsite install schedule date and the drafting due date is set automatically to 60 business days before it. Both dates are kept, so the schedule date can be tracked on its own.',
      },
      {
        type: 'improved',
        title: 'Clearer release numbering on drafting submittals',
        detail:
          'Release numbers and dates on DRR-type drafting submittals are now assigned and displayed more consistently across the Drafting Work Load.',
      },
      {
        type: 'fixed',
        title: 'Readable dates on green backgrounds',
        detail:
          'On-track (green) date pills now use black text on the green highlight, so they\'re easy to read across the Job Log, PM board, and Start Install editor.',
      },
    ],
  },
  {
    version: 'v2.0.268',
    date: 'June 23, 2026',
    summary:
      'Comment threads on PDF drawings, an ordered-materials view on job details, and the next layer of meeting-notes intelligence.',
    changes: [
      {
        type: 'new',
        title: 'Comment threads on PDF drawings',
        detail:
          'Each version of an uploaded drawing now has its own comment thread. @mention a teammate and they get a notification-bell alert that clicks straight through to the drawing.',
      },
      {
        type: 'new',
        title: 'Ordered materials on job details',
        detail:
          'The job details panel now lists materials ordered from suppliers but not yet received, so you can see what\'s still outstanding for a release at a glance.',
      },
      {
        type: 'improved',
        title: 'Automatic supplier-order capture',
        adminOnly: true,
        detail:
          'Supplier order confirmations forwarded to the Banana Boy mailbox are parsed automatically into ordered-material line items and fed into the data lake. Off by default until the mailbox connection is switched on.',
      },
      {
        type: 'new',
        title: 'Meeting "brain drift" detection (BB Meeting v3)',
        adminOnly: true,
        detail:
          'After a meeting, BB now compares what was discussed against the current state of the Brain and flags agreed changes that never landed — read-only for now, surfaced on the meeting view.',
      },
      {
        type: 'new',
        title: 'Auto-schedule the meeting bot from your calendar',
        adminOnly: true,
        detail:
          'Invite bb@mhmw.com to a Teams meeting and the notetaker bot schedules itself to join at the start time. Off by default, pending calendar permissions.',
      },
    ],
  },
  {
    version: 'v2.0.262',
    date: 'June 17, 2026',
    summary:
      'Set Start Install dates right from the Drafting Work Load, a new "Katie" downstream view on the Job Log, a read-only project timeline, and the next round of meeting-notes smarts.',
    changes: [
      {
        type: 'new',
        title: 'Start Install from the Drafting Work Load',
        detail:
          'Drafters can now set a desired Start Install date directly on the Drafting Work Load. The date hands off to the Job Log automatically, so there\'s no need to jump between boards to schedule a release.',
      },
      {
        type: 'new',
        title: 'Project timeline view',
        detail:
          'A read-only, team-laned timeline (Gantt) with week-snap navigation and a jump-to-date picker. Click a release to open a detail panel showing its open to-dos and meeting notes.',
      },
      {
        type: 'improved',
        title: 'Smarter meeting notes (BB Meeting v2)',
        adminOnly: true,
        detail:
          'Meeting to-dos now reconcile against a before/after Brain snapshot, flagging agreed changes that never landed, and you can match an item to a specific release from a dropdown.',
      },
      {
        type: 'improved',
        title: 'Release assignment open to more users',
        detail:
          'Both admins and drafters can now assign release numbers from the Drafting Work Load.',
      },
      {
        type: 'fixed',
        title: 'Cleaner submittal naming on the Drafting Work Load',
        detail:
          'Fixed how submittal type and names are derived so the Drafting Work Load no longer shows missing or doubled-up names.',
      },
    ],
  },
  {
    version: 'v2.0.255',
    date: 'June 14, 2026',
    summary:
      'New Sunbelt rental tracking, cleaner release assignment from the Drafting Work Load, and a batch of search, notification, and styling fixes.',
    changes: [
      {
        type: 'new',
        title: 'In-app patch notes',
        detail:
          'The version number next to "MHMW Brain" in the top-left is now clickable — it opens this What\'s New panel so you can see what shipped in each release.',
      },
      {
        type: 'new',
        title: 'Sunbelt rental reports',
        adminOnly: true,
        detail:
          'A new Rentals page tracks Sunbelt equipment-on-rent. For now the rental list is loaded manually; automatic ingestion is targeted for later this week.',
      },
      {
        type: 'improved',
        title: 'Release assignment from the Drafting Work Load',
        detail:
          'Reworked how release numbers are assigned out of the Drafting Work Load so they stay unique and consistent.',
      },
      {
        type: 'improved',
        title: 'Drafting Work Load & Job Log styling',
        detail:
          'Cleaner column filters, project filter dropdown, table rows, and view toggles across both boards for easier scanning.',
      },
      {
        type: 'improved',
        title: 'Navigation bar refresh',
        detail:
          'Tidied up the top navigation — MHMW Brain pinned at the far left with the menu rolling out to the right.',
      },
      {
        type: 'fixed',
        title: 'Global search closes cleanly',
        detail:
          'The quick/global search no longer gets stuck open; it now closes reliably when you click away or finish a search.',
      },
      {
        type: 'fixed',
        title: 'Repeat to-do notifications',
        detail:
          'Overdue to-dos stop firing duplicate reminder notifications. (Foundational fix — more notification controls to come.)',
      },
    ],
  },
];

export const CURRENT_VERSION = PATCH_NOTES[0].version;
