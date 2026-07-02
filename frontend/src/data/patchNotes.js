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
    version: 'v2.0.278',
    date: 'July 1, 2026',
    summary:
      'Log a verbal release in seconds, edit any Job Log row inline, schedule Sub-GC drafting from the GC\'s jobsite date, and easier-to-read green dates.',
    changes: [
      {
        type: 'new',
        title: 'Log a verbal release',
        detail:
          'A quick-entry form on the Releases page for releases that come in verbally. It suggests the next release number for you (still editable), and any logged-in user can push one through — no need to wait for a drafter.',
      },
      {
        type: 'new',
        title: 'Edit a whole Job Log row inline',
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
