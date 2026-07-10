# BB PDF Review — Hardening & Roadmap

**Status:** planning · **Owner:** Daniel · **Written:** 2026-07-10
**Feature:** Banana Boy (BB) code-compliance review of For-Construction drawing sets
**Code:** `app/brain/pdf_review/` (`service.py`, `worker.py`, `routes.py`, `rules.py`, `report.py`) · `frontend/src/components/BBReviewPanel.jsx`

---

## Why this doc exists

BB review is a proof-of-concept that works — it caught the real terminal-rise code
violation on job **590-674** — but it was built to *prove the concept*, not to be
*lived in daily*. Three of its most important pieces are stubbed:

- the **latency budget** (single 10-minute call that times out),
- the **error surface** (a timeout reports itself as "no API key"),
- the **feedback loop** (PM accept/reject is captured but nothing consumes it).

This is the plan to take it from "impressive demo" to "vital tool people run every day."

## The incident that triggered this (2026-07-10)

Review of 590-674 (internal release PK **839**, drawing version 44, ~728 KB / 25–40
pages) failed in production with the banner **"Review failed: review call failed (no
API key or request error) — see logs."**

Root cause from the prod logs:

```
event: bb_pdf_review_failed
error: HTTPSConnectionPool(host='api.anthropic.com', port=443): Read timed out. (read timeout=600)
```

Requested 12:22:42 → failed 12:32:43 = **exactly the 600s `REQUEST_TIMEOUT`**. Not the
API key. The same set completes fine in sandbox because that run finished under 10
minutes; prod tipped over the ceiling on a deeper adaptive-thinking run.

**Two misleading things surfaced during triage, both fixable below:**
1. The banner text is a catch-all (`worker.py:59`) — a timeout, an HTTP error, and a
   missing key all produce the same "no API key or request error" string.
2. "590-674" appears **nowhere in the logs** — the failure path only logs the integer
   `release_id` (839), and `job_release` is logged *only on the success path*
   (`service.py:100`). A failed review is ungreppable by its real number.

### Why it's slow (the mental model, so we don't chase the wrong lever)

Latency on an LLM call is driven by **output tokens generated serially**, not by input
page count. Prefill (reading the PDF) is massively parallel and cheap — hundreds of
pages ingest in seconds. What costs time here:

- `"thinking": {"type": "adaptive"}` with a **32k `max_tokens`** ceiling → the model
  spends a giant *serial* thinking budget (code comment records ~25k output observed).
- **opus-4-8** → the slowest token-generation tier.
- **one monolithic call** → all ~25k tokens emitted in a single sequential stream.

~25k tokens ÷ ~50 tok/s ≈ ~8 min of pure generation, which is why it sits right at the
600s edge. A short-output, parallelized, Sonnet pipeline over *hundreds* of pages beats
a deep-thinking single-shot opus call over 30 pages — output length and fan-out, not
page count, are the levers.

---

## Current architecture (as-built)

```
POST /releases/<id>/drawing/versions/<vid>/bb-review   → BBDrawingReview(status=pending)
   → worker.start_review()  (ThreadPoolExecutor, 2 workers)
      → read PDF → service.review()
         → single non-streaming Anthropic call
            model=opus-4-8, thinking=adaptive, max_tokens=32000, timeout=600s
         → parse strict-JSON findings
      → write findings | error onto the row
GET  /releases/<id>/drawing/versions/<vid>/bb-review    → status + findings (frontend polls every 5s while pending)
GET  /releases/<id>/bb-review/report                    → PM-facing ranked report (report.py)
POST /releases/<id>/bb-review/<rid>/feedback            → BBReviewFeedback (accept/reject + notes + finding snapshot)  ← WRITE-ONLY today
```

- **Rules** (`rules.py`) are a hardcoded `RULES` list (13 rules: stairs, rails, guards,
  structural steel, welding, material/finish — Division 05). The system prompt is
  assembled from them. The rule library is the reliability layer: without it the model
  trusts an on-sheet schedule and clears borderline defects.
- **Report** (`report.py`) is pure (no DB/Flask): maps each finding (verdict, severity)
  → urgency bucket, tallies, writes the headline and bell message. `hold_recommended =
  any violation`.
- **Notification**: PM gets a bell notification on actionable findings.

---

## Roadmap

### Phase 0 — Kill the clunk *(small; one branch; `service.py` + `worker.py` + `BBReviewPanel.jsx`)*

| # | Change | Where | Why |
|---|--------|-------|-----|
| 1 | Cap thinking: `adaptive` → `{"type":"enabled","budget_tokens":~10k}` | `service.py:63` | Biggest single latency lever; bounds the serial token stream. |
| 2 | Stream the call (SSE accumulate) | `service.py:53` | Non-streaming = the 600s guillotine; streaming keeps the socket alive. |
| 3 | Honest error taxonomy — distinguish timeout / no-key / HTTP-4xx / HTTP-5xx / bad-JSON; log `job_release`, `duration_ms`, tokens on the failure path | `service.py:98`, `worker.py:59` | Stop the timeout masquerading as "no API key"; make failed reviews greppable by job-release. |
| 4 | One retry with backoff on transient (timeout / 5xx) | `service.py` | A single flaky call shouldn't need a human to hit "Re-run." |
| 5 | Frontend poll backoff (5s→30s) + "BB is reviewing (~N min)…" affordance | `BBReviewPanel.jsx:39` | Kills the every-5s access-log spam and sets the wait expectation. |

**Outcome:** "10-minute coin-flip that lies about why it failed" → "3–4 minute call that
streams and reports honestly."

### Phase 1 — Make it trustworthy

- **Adversarial verify pass.** Before a `violation` sets `hold_recommended`, run a cheap
  second call: "here's the finding + the exact sheets it cites — refute or confirm." One
  false hold-fab kills adoption faster than a missed defect. Highest trust-per-dollar.
- **Parallelize by rule-group.** Split the 13 rules into groups (stairs / rails+guards /
  structural+welding+material), fan out concurrent calls, merge. Wall-clock = slowest
  group, each group's output is smaller — *also* the structural latency fix.
- **Confidence score per finding** → sort/threshold so borderline
  `needs_field_verification` doesn't crowd out a hard violation.
- **Dedup findings across re-runs/versions** so drawing v2 doesn't re-surface v1's
  findings as new.

### Phase 2 — Make it self-improving *(the moat; built-but-disconnected today)*

`BBReviewFeedback` (PM accept/reject + notes + `finding_snapshot`) is captured on every
finding and **nothing consumes it.** Closing this loop is the whole "learns from our
mistakes" thesis.

- **Move `RULES` to a DB table** (the `rules.py:14` TODO) — add/edit rules from the UI
  without a deploy. Today every new rule needs a code change + deploy.
- **Close the feedback loop** (mirror `app/brain/meetings/learn.py`): periodically
  distill accept/reject feedback into *proposed* rule edits — a repeatedly-rejected rule
  gets tightened, a repeatedly-confirmed near-miss gets promoted. Human approves before
  live.
- **Version the rule set per review** (store which rule ids/version ran) so historical
  feedback stays meaningful as rules evolve.
- **Rule-effectiveness metrics** — per rule: hit rate, PM accept rate, false-positive
  rate. Tells us which rules to trust and which to retire.

### Phase 3 — Integration & scale

- **Auto-trigger review on FC drawing upload** — no manual per-version button.
- **`hold_recommended` actually gates fab** — today it's computed and thrown away; wire
  it to a soft flag on the release/card.
- **Findings drop pins on the sheet** via the existing PDF mentions/markup system
  instead of living only in a side panel.
- **Large-set handling** — sheet-index prefilter so only relevant sheets go to each
  rule-group, staying under the 32 MB / token ceiling as sets grow.

---

## Sequencing recommendation

1. **Phase 0 now** — small, self-contained, removes the daily pain.
2. **Phase 1 parallelize + verify** next — takes it from "impressive demo" to "PM trusts
   the hold."
3. **Phase 2** once 0–1 make it a tool people run daily — the feedback loop only pays off
   with real daily usage feeding it.

## Open questions

- Model choice per phase: keep opus for the main pass, or move to Sonnet + verify-with-opus?
- Where should the rule-authoring UI live — the "submit markup to BB" surface, or admin?
- Does `hold_recommended` gate fab *hard* (blocks) or *soft* (flags)? Likely soft first.

---

# Track B — Continuous compliance via Procore ingestion (shift-left)

> Added 2026-07-10 after the Bill conversation. Everything above (Phases 0–3) is about
> making *one review* fast and trustworthy. This track changes *when and where* review
> happens: BB stops being a button on an FC and becomes a check that rides the submittal
> from **DRR → GC → FC**, with drawings pulled from Procore automatically and findings
> surfaced on the **DWL**. Long-term, "FC passed BB" becomes the **DWL→JL handoff gate**.

## The thesis (Bill + Daniel, text 2026-07-10)

- **Reviewing at FC is too late** — by then the drawing is expensive to change. Findings
  must surface during DRR/GC.
- **Pull FCs (and earlier drawings) from Procore into the Job Log / DWL** — makes it fast
  to feed findings back to BB for training on what we catch in the shop.
- **Trigger any time in the sub for GC or DRR phase; by FC all review steps are already
  done.**
- **Long-term:** FC review becomes the handoff between DWL and JL — *FC must pass BB
  before the release is released.* Only once the system is proven.

## How Procore ingestion actually works (research 2026-07-10)

- **Webhooks are notification-only.** Payload = `{id, timestamp, resource_name,
  resource_id, event_type, company_id, project_id, api_version}` — no file, no attachment
  list. You get "Submittals #123 updated" then call back to the API. (procore.github.io/documentation/webhooks-api)
- **No "attachment added" event exists.** Attachments live *inside* a submittal, so a new
  drawing surfaces as a **Submittal `update`** event. On it you GET the submittal, read
  its `attachments` array, and **diff against stored attachments** to find the new file.
- **The file is a second step.** Attachment entries carry a filename + a temporary signed
  URL into Procore's file store; download the bytes from that URL. (developers.procore.com/documentation/attachments)
- *Confidence:* the mechanics are well-established Procore patterns; exact endpoint paths,
  the download-URL field, and URL expiry must be verified against **one live sandbox GET**
  (the JS-rendered docs couldn't be scraped, and our Data Connection App's permissions —
  see below — govern what we can actually fetch).

## What we already have (grounded inventory, cite file:line)

Big head starts — the ingestion half is ~60% built already:

- **Webhook endpoint + subscription:** `POST /procore/webhook` (`app/procore/__init__.py:43`),
  subscribed to the **Submittals** resource for `create` + `update`
  (`app/procore/api.py:292`, `scripts/ensure_webhooks.py:98`). *We already get pinged on
  every submittal update* — the exact trigger this track needs.
- **Full outbound REST client:** `ProcoreAPI` (`app/procore/api.py:53`), base
  `https://api.procore.com` (prod, hardcoded), 3× retry + one forced token refresh on 401.
- **OAuth (client-credentials):** `procore_auth.py` mints/refreshes tokens against
  `login.procore.com/oauth/token`, auto-refresh within 60s of expiry. Single-row
  `ProcoreToken` (`models.py:83`). **No refresh tokens, no scopes in the token request.**
- **We already read the `attachments` structure:** `get_final_pdf_viewers()`
  (`app/procore/procore.py:459`) walks `workflow_data["attachments"]` for the
  "Final PDF Pack" and extracts `viewer_url` — persisted as `Releases.viewer_url` +
  `Releases.procore_submittal_id` (`models.py:492`). *This is the closest existing hook,
  but it reads a **viewer** link, never downloads bytes.*
- **Submittal model + phase:** `Submittals` (`models.py:102`). Phase = the free-text
  **`type`** string (`"Drafting Release Review"` = DRR, `"Submittal for GC Approval"` = GC,
  `"For Construction"` = FC; constants at `procore.py:52,309`). No enum column.
- **Reliability patterns to reuse:** `SubmittalReconcile` coalescing re-fetch ~60s after a
  webhook (`app/procore/reconcile.py`), and the `TrelloOutbox` worker pattern.

## What's net-new / the gaps (this is the real work)

1. **No file download exists — greenfield.** We read attachment *metadata* (viewer_url)
   but never fetch bytes. Need the actual **download URL** in the attachment object (not
   the viewer link) + binary handling + storage.
2. **FEASIBILITY GATE — SETTLED 2026-07-10 via `scripts/procore_attachment_probe.py`
   (read-only, against real Procore).** Verdict: **feasible — not a permissions wall, an
   endpoint-mapping detail.** Findings:
   - ✅ Our existing client-credentials token reads attachment metadata fine. The drawing
     lives in `workflow_data.attachments` (base `submittal.attachments` was empty for the
     test FC), each with `name`, `id`, a **prostore file id** (in `viewer_url`),
     `download_url`, and `viewer_url`.
   - ❌ The `download_url` points at **app.procore.com** (the web app), which only accepts a
     browser session — it `401`s ("You'll need to login first") for API tokens. **This
     field is unusable for automation; do not build on it.**
   - 🔑 REST file endpoints on **api.procore.com** *accept our token* — probe attempts
     returned `400`/`404` (wrong request/path) but **never `401`/`403`**, i.e. auth and
     permission are fine. We just haven't found the exact endpoint that maps a
     **submittal-approver attachment** (item_type `SubmittalLogApprover`, a niche resource)
     to its bytes. Four guesses (`/prostore/files/{id}`, `/files/{id}`,
     `/projects/{pid}/documents/{id}`) missed.
   - **Correct endpoint identified (user-supplied):**
     `POST /rest/v1.0/document_markup_downloadable_pdfs/find_or_create` with header
     `Procore-Company-Id` and body `{item_id, item_type, attachment_id, project_id}` (the
     same params in the attachment's viewer/download URL). It's **async**: first POST starts
     the render, re-POST the same body until the response carries the download URL (then GET
     it). Probe confirmed the endpoint is **reachable + authorized** — returns `404
     "Item not found"`, **never 401/403**, so auth/permission is NOT the wall.
   - **Still to confirm:** the probe's test submittal (999-946) had **no originating drawing**
     (`attachments_count=0`) — only an *approver* Final-PDF-Pack markup
     (`item_type=SubmittalLogApprover`), which `find_or_create` 404s on. The docs' example
     uses **`item_type=SubmittalLog`** — the *originating/submitter* drawing, which is the
     attachment we actually want for shift-left. Need to re-run the probe against a submittal
     that **has a real submitted drawing** to capture the confirmed working call.
   - Send the **`Procore-Company-Id` header** (our `ProcoreAPI` client omits it today — small add).
3. **Submittal → Release link is value-based only** — typed `rel` integer shared across
   both tables + FC title-substring match. **No FK, no row-level link** (`models.py:128,493`).
   → This is *why* v1 keys findings to the **submittal**, not the release.
4. **`type` is frozen at create.** The update path never re-reads `type`
   (`check_and_update_submittal` writes only ball_in_court/status/title/manager,
   `procore.py:1011+`). To know a submittal's *current* phase for triggering/gating we must
   start refreshing `type` on update (or read it fresh from the API per review).
5. **Review pipeline is release-keyed.** `BBDrawingReview.drawing_version_id →
   ReleaseDrawingVersion` and `release_id`. A submittal-sourced drawing needs a
   submittal-keyed review path (new nullable `submittal_id`, or a submittal drawing that
   maps onto `ReleaseDrawingVersion`-like storage).
6. **`ProcoreOutbox` is not worker-driven** — it's an echo/audit ledger, no retry worker
   (`outbox_service.py` polls `TrelloOutbox` only). Durable download jobs = extend it or
   model on `SubmittalReconcile`.

## Chosen v1 (Daniel's decisions: manual trigger, key to submittal)

Deliberately sidesteps the auto-trigger cost/noise problem *and* the linkage problem:

1. **Feasibility gate — mostly settled (see gap #2).** Auth/permission confirmed; only the
   exact download endpoint for a submittal attachment remains (Procore API reference /
   support). Confirm that endpoint, then wire it + the `Procore-Company-Id` header into the
   Procore client. `scripts/procore_attachment_probe.py` is the reusable probe.
2. **Manual "Pull drawing + Run BB review" action on the DWL submittal popup** (the
   existing rel-assignment popup) — any phase (DRR/GC/FC).
3. **Download → store → review, keyed to `Submittals.id`.** Reuse the PDF storage from the
   markup feature; add a submittal-keyed review path. Reuse everything in `pdf_review/`.
4. **Surface the finding on the DWL submittal row** — compliance badge/count keyed to the
   submittal; details in the popup. Plus Bill's "page or filter for the FCs."

This proves the three unknowns — (a) we can download from Procore, (b) review works on
submittal-sourced drawings, (c) the DWL surface — with zero dependency on rel-assignment or
webhook auto-wiring.

## v2 — Auto-trigger on new drawing (once v1 is proven)

- On the **Submittals `update`** webhook we already receive: GET submittal → diff the
  `attachments` array against stored attachment ids → if a new **drawing** appeared and
  phase ∈ {DRR, GC}, enqueue a review automatically.
- Requires: store prior attachment ids, **unfreeze `type`** (gap #4), a durable job queue
  (gap #6), and cost controls — **hash the PDF and skip unchanged content**, drawing-only
  filter, cheaper model + Track-A parallelize/verify (which becomes load-bearing here).

## v3 — FC handoff gate (proven-system endgame)

- Durable BB review-status on the submittal; "FC passed BB" as the **DWL→JL release
  condition**. **Soft flag first** (warn, don't block); hard gate + override policy later.

## Track B open decisions

- **Feasibility gate:** does our Data Connection App permit downloading submittal/document
  files? (blocking — verify first)
- Which attachment is "the drawing" — content-type + filename heuristic, a specific
  attachment slot, or the "Final PDF Pack" we already locate?
- Do we refresh `type` on every update (unfreeze), or read phase fresh per review?
- DWL surface: badge-per-submittal-row vs a dedicated FC-compliance page/filter (or both).
- Storage: reuse `ReleaseDrawingVersion`/markup storage, or a new store keyed by Procore
  attachment id?
