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
    version: 'v2.0.338',
    date: 'August 9, 2026',
    summary:
      'The release hub grows an Attachments tab with a built-in drawing viewer and a plain-language change log, every new release gets a billing tag, fab estimates learn the shop\'s four-day week, Carmen can read out the EOS scorecard, and production now has proven offsite backups.',
    changes: [
      {
        type: 'improved',
        title: 'The release hub, round two',
        detail:
          'The hub modal is bigger and now has three tabs — Details, Attachments, and Change Log. Details leads with the date flow, lays the metadata out in three clean columns, and shows stage progress the only correct way: in bananas. The notes rail became a full activity feed, grouping notes together with stage, fab, and date updates by day, and + Note updates the Job Log row the moment you save.',
      },
      {
        type: 'new',
        title: 'Drawings without leaving the hub',
        detail:
          'The new Attachments tab puts documents and photos in a rail on the left and opens PDFs in a read-only viewer right beside them — fit, width, zoom, page nav, no new window. Carmen\'s drawing review lives here too, now open to drafters as well as admins, and when a finding cites a page, clicking it jumps the viewer straight there. An amber badge on the tab tells you there are findings worth a look.',
      },
      {
        type: 'improved',
        title: 'A change log that speaks English',
        detail:
          'The hub\'s Change Log tab shows what changed as plain-language field diffs grouped by day — no more update_stage internals — and undo works right from the entry. The Events page keeps its classic table for the people who like it raw.',
      },
      {
        type: 'new',
        title: 'Every release declares how it gets billed',
        detail:
          'Creating a release — pasted or verbal — now requires a billing tag: Contracted, Change Order, or MHMW Cost. The tag shows in the release hub under a new Billing section, where it can be changed later. Existing releases are untagged until someone sets them; the point is that from today forward, nothing enters the log without saying whose dime it\'s on.',
      },
      {
        type: 'improved',
        title: 'Fab estimates respect the four-day week',
        detail:
          'The shop works Monday through Thursday, but projected fab and install dates were counting Fridays as work days. Fab projections now spread hours across the real shop calendar — so a job that spans a weekend lands where it actually will — while install math keeps the Monday–Friday field calendar.',
      },
      {
        type: 'new',
        title: 'Carmen knows the scorecard',
        detail:
          'Ask Carmen for EOS scorecard numbers and she pulls them live from the Brain: hours released to production, fabrication hours, QC completed, fab backlog, yellow dates, T&M hours, and target dates met — each computed Monday–Sunday to match the scorecard columns. She knows whose metric is whose, so "David\'s numbers" or "my metrics" lands on the right ones.',
      },
      {
        type: 'new',
        title: 'Production backups, offsite and proven',
        adminOnly: true,
        detail:
          'The production database is now dumped nightly and shipped to offsite object storage with daily, weekly, and monthly retention tiers. Every dump passes integrity gates before upload, and the whole path was proven with a real recovery drill — a production backup pulled down and restored on a laptop, completely off the hosting platform, all 47 tables intact.',
      },
      {
        type: 'fixed',
        title: 'Supplier-order attachments and lookahead PDFs survive deploys',
        adminOnly: true,
        detail:
          'Two storage locations were silently falling back to a folder inside the deployed code, which gets wiped on every deploy — so supplier-order attachments and ingested lookahead PDFs could vanish while their records lived on. Both now live on the mounted disk with the photos and marked-up PDFs, which were never affected.',
      },
    ],
  },
  {
    version: 'v2.0.334',
    date: 'August 6, 2026',
    summary:
      'The Job Log redesign lands — one release hub modal, a cleaner table, an optional left sidebar — plus smarter dates at the shipping stages and fixes for duplicate release numbers, fab-hour totals, and the drawing link.',
    changes: [
      {
        type: 'new',
        title: 'One release hub for everything about a release',
        detail:
          'Clicking a release\'s description on the Job Log now opens a single hub modal with three tabs — Details, Drawings & Photos, and Change Log — plus a notes rail that stays visible no matter which tab you\'re on, so a note you\'re mid-way through writing survives switching tabs. This replaces the separate details and notes-history popups. The description is now the row\'s one click-through; job and release numbers are plain text.',
      },
      {
        type: 'improved',
        title: 'The Job Log look, rebuilt',
        detail:
          'The Job Log table got its redesign: a uniform grid, IBM Plex type on screen and in the exported PDF, alternating row banding that skips completed rows, tinted stage pills, and whole-cell date flags. The Events, Drafting Work Load, and Archive pages were restyled to match, and the rest of the app picked up the same surface treatment so pages stop feeling like different eras.',
      },
      {
        type: 'new',
        title: 'Left sidebar, if you want it',
        detail:
          'A new Left Sidebar Mode toggle lives in the theme menu next to Dark Mode. Turn it on and, on a wide screen, the top bar is replaced by a collapsible icon rail on the left with the bell, theme, and logout in the footer. It\'s off by default, remembered per browser, and the top bar stays as-is on smaller screens.',
      },
      {
        type: 'improved',
        title: 'Dates behave themselves at the shipping stages',
        detail:
          'When a release reaches Shipping Planning or Ship Complete, estimated install and ship dates are cleared instead of lingering — an estimate that survived to the truck is stale by definition — and you set the real ones by hand. Dates you set by hand are kept but shown in plain white, with no ASAP red or urgency colors. And a release with a firm install date now rolls from Paint Complete straight into Shipping Planning automatically, the way ASAP releases already did.',
      },
      {
        type: 'new',
        title: 'Break or link ship and install dates',
        detail:
          'The install date modal now has an explicit Break / Link button between Ship Date and Start Install. Linked, setting either date fills the other one business day apart; broken, they move independently. No more guessing at when the two dates are tied together.',
      },
      {
        type: 'new',
        title: 'Drafters can edit Job Log rows',
        detail:
          'Drafters now get the row menu with Edit row, covering the fields from Job # through Released. Deleting rows stays admin-only.',
      },
      {
        type: 'fixed',
        title: 'Release numbers no longer collide across projects',
        detail:
          'Job numbers wrap around, so an archived release on an old project could block the same number on a new one — 410-108 Columbine blocking 410-108 Alta Metro. Uniqueness now includes the project name, and everywhere the app looks up a release by number it now resolves to the active row a human means, never an archived twin.',
      },
      {
        type: 'fixed',
        title: 'Fab hours now drop as fabrication progresses',
        detail:
          'Total Fab HRS ignored several mid-fabrication stages — Cut Complete, Fitup Start, Weld Start, Weld Complete — so the number barely moved while the shop worked. The remaining-hours discounts now cover every stage, consistently in the table, the totals, and the scheduling math.',
      },
      {
        type: 'fixed',
        title: 'The drawing button stops going grey for no reason',
        detail:
          'The Job Log\'s drawing link now survives Procore\'s quirks: it pages through large submittal lists instead of silently truncating, refetches when Procore hands back stale approver data after a re-distribute, looks back 30 days instead of 7, and refuses to ever link a photo or markup in place of the actual drawing PDF.',
      },
      {
        type: 'fixed',
        title: 'Order # 0 clears the slot in Drafting Work Load',
        detail:
          'Typing 0 in the ORDER # cell now clears the release out of the drafting order like blank or dash, instead of silently doing nothing.',
      },
      {
        type: 'improved',
        title: 'The Bug Tracker embraces its destiny',
        adminOnly: true,
        detail:
          'The admin board is now Ongoing Complaints. You don\'t create an item, you File a Complaint, and an empty column has nothing to complain about.',
      },
    ],
  },
  {
    version: 'v2.0.322',
    date: 'July 26, 2026',
    summary:
      'Banana Boy is now Carmen, the paper T&M ticket goes digital with its own subcontractor portal, and Carmen can hand you a GC-ready look-ahead schedule as a PDF.',
    changes: [
      {
        type: 'new',
        title: 'Digital T&M tickets, with a subcontractor portal',
        adminOnly: true,
        detail:
          'The paper T&M form now has a digital counterpart under the new T&M tab. Open a ticket against a job or release, key the date, location, and description of work, add labor, material, and equipment line items, and attach photos straight from a phone or iPad in the field. Tickets carry a real lifecycle — a discarded draft is voided, never deleted — so the record survives. Subcontractors get their own invite-by-email login and a stripped-down portal showing only the tickets assigned to them, with no rates, pricing, or financial data visible anywhere. Costs, O&P, and automatic change-order generation land in a later phase.',
      },
      {
        type: 'improved',
        title: 'Subcontractor work lives under one Subs tab',
        adminOnly: true,
        detail:
          'Subcontractors and the installer invoice tracker were two separate items in the top nav; they are now two tabs under a single Subs tab — Subcontractors for inviting and managing the roster, Invoice Paid for marking which installer invoices have been paid. Old links to /subcontractors still work and land on the right tab. Customer billing stays where it was, under its own Invoicing tab.',
      },
      {
        type: 'improved',
        title: 'Banana Boy is now Carmen',
        detail:
          'BB has been renamed Carmen across the app — the chat assistant, the drawing reviewer, and the mailbox that ingests forwarded email, which now lives at carmen_ai@mhmw.com. Nothing about how she works changed, and the banana stays.',
      },
      {
        type: 'new',
        title: 'GC look-ahead schedule PDF from Carmen',
        adminOnly: true,
        detail:
          'Ask Carmen for a look-ahead on a job and she builds a multi-phase production schedule — drafting, fabrication, paint, shipping, installation — from that job\'s live releases, open DRRs, and GC approvals, then renders it as a print-ready landscape Gantt PDF with a phase color legend, downloadable right from the chat. She draws only dates that actually exist on the records: hard dates, projected dates, and clearly marked estimates, never invented ones.',
      },
      {
        type: 'improved',
        title: 'Better accept/reject flow on drawing-review findings',
        adminOnly: true,
        detail:
          'Accepting or rejecting a finding from the drawing reviewer now lets you attach a note explaining the call, in a roomier form that saves cleanly and keeps your decision visible on the finding.',
      },
      {
        type: 'fixed',
        title: 'Carmen\'s mailbox rides out Microsoft hiccups',
        adminOnly: true,
        detail:
          'Forwarded email polling now retries with backoff when Microsoft returns a throttle or temporary server error, instead of failing the whole poll and leaving messages waiting for the next cycle.',
      },
    ],
  },
  {
    version: 'v2.0.311',
    date: 'July 23, 2026',
    summary:
      'A Subs page for tracking installer invoice payments, and Procore markups now land where they belong on reviewed drawings.',
    changes: [
      {
        type: 'new',
        title: 'Subs page for installer invoices',
        adminOnly: true,
        detail:
          'A new admin Subs page lists every active release that has an installer assigned, grouped by installer, with a Yes/No toggle for whether that installer has been paid. Filter by paid, unpaid, or installer to see what is still outstanding. This is separate from the Job Log\'s Invoiced column, which still tracks customer billing.',
      },
      {
        type: 'fixed',
        title: 'Procore markups no longer rotated on reviewed drawings',
        detail:
          'On rotated sheets, the page-number stamp added for drawing review was throwing every Procore markup 90 degrees off and out of place. The stamp now rotates itself to match the sheet instead of rewriting the page, so markups sit exactly where Procore put them and the stamp still reads upright.',
      },
      {
        type: 'fixed',
        title: 'Admin pages load on a direct link or refresh',
        adminOnly: true,
        detail:
          'The metrics and submittal-matching admin pages returned a 404 when opened by URL or refreshed. Both now load correctly.',
      },
    ],
  },
  {
    version: 'v2.0.306',
    date: 'July 23, 2026',
    summary:
      'Optional Chrome desktop alerts for mentions and to-dos while Brain stays open in a tab.',
    changes: [
      {
        type: 'new',
        title: 'Desktop notifications (opt-in)',
        detail:
          'Open the notification bell and click Enable to allow Chrome desktop alerts. Mentions, to-dos, and other bell notifications will pop on your desktop when Brain is open but in the background — even if you\'re in another window. Turn them off anytime from the same menu. Alerts pause if you close the Brain tab.',
      },
    ],
  },
  {
    version: 'v2.0.305',
    date: 'July 21, 2026',
    summary:
      'Project health now measures itself against the GC\'s weekly lookahead, and Banana Boy has learned how MHMW actually drafts.',
    changes: [
      {
        type: 'new',
        title: 'GC lookahead cross-check on Project health',
        adminOnly: true,
        detail:
          'A project\'s health score can now be checked against the general contractor\'s 3-week lookahead: each dated GC need is lined up against our releases and submittals, and the score is docked for real slips and gaps using the GC\'s own dates instead of a generic staleness signal. Running as a pilot on one live job while GC lookahead ingestion is built out.',
      },
      {
        type: 'improved',
        title: 'Banana Boy knows MHMW\'s conventions',
        adminOnly: true,
        detail:
          'BB chat and the drawing reviewer now draw on a curated MHMW knowledge base — code conventions, abbreviations and lumber, fasteners and parts, weld symbols, and the DRR and submittal-for-GC workflows — so answers and reviews are grounded in how MHMW actually drafts.',
      },
      {
        type: 'fixed',
        title: 'Install-window cockpit hidden on shipping-lane Timeline cards',
        detail:
          'The install-window cockpit no longer shows on Timeline cards in the shipping lanes, where it doesn\'t apply — it now appears only where an install window is meaningful.',
      },
    ],
  },
  {
    version: 'v2.0.301',
    date: 'July 19, 2026',
    summary:
      'A new Ship Date on the Job Log that fills itself in from the install date, and the Timeline now mirrors each assigned release into its installer\'s lane.',
    changes: [
      {
        type: 'new',
        title: 'Ship Date on the Job Log',
        detail:
          'Releases now carry a Ship Date, shown as its own column on the Job Log and editable in the Start Install modal. Enter one date and the other auto-fills — ship defaults to one business day before install, and either can be set independently. The Ship Date cell is colored to match the Start install cell exactly (green upcoming, yellow past, red for ASAP), so the paired columns always agree.',
      },
      {
        type: 'improved',
        title: 'Timeline mirrors releases into installer lanes',
        detail:
          'When a release is assigned to an installer, the Timeline now mirrors it into that installer\'s lane as a range bar spanning Start install through its completion estimate. The installer lanes read as a true Gantt of who is on what and when, while the shipping lanes stay day-bucketed.',
      },
    ],
  },
  {
    version: 'v2.0.296',
    date: 'July 18, 2026',
    summary:
      'A next-week install schedule view, a Materials Ordered column on the Job Log, live data flowing into the Projects tab, and a cleaner top navigation.',
    changes: [
      {
        type: 'new',
        title: 'Next-week install schedule',
        detail:
          'A new Install Schedule view lays out the coming week\'s installs grouped by crew, hard-scheduled dates first, and flags overlaps and overloaded days. Install hours come from what\'s entered on the release today, so anything still unassigned shows up in its own bucket to make the gap obvious.',
      },
      {
        type: 'improved',
        title: 'Materials Ordered has its own Job Log column',
        detail:
          'Ordered-but-not-received material now shows as its own column on the Job Log, so you can scan which releases are still waiting on parts without opening each one. BB can also read a release\'s material-order status when you ask about it in chat.',
      },
      {
        type: 'new',
        title: 'Live data on the Projects tab',
        adminOnly: true,
        detail:
          'The Projects tab now overlays real sandbox data onto the demo scaffold — releases, submittals, a merged activity feed, health tiles, and percent-complete all render from live records, with a banner and per-tab dots marking which sections are live versus still demo. Financials and Contract stay on demo data until T&M and change-order ingestion lands.',
      },
      {
        type: 'improved',
        title: 'Cleaner top navigation',
        detail:
          'Reworked the top navigation bar\'s structure so it lays out and scales more cleanly across screen sizes.',
      },
      {
        type: 'improved',
        title: 'Push delivery for the Banana Boy mailbox',
        adminOnly: true,
        detail:
          'Email forwarded to the Banana Boy mailbox can now arrive by Microsoft Graph push notification instead of waiting for the next poll, so supplier orders and forwards land closer to real time. Off by default until the subscription is switched on.',
      },
    ],
  },
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
