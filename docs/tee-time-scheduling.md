# "Tee Time" Capacity Scheduling — Starter Concept

**Branch:** `feature/tee-time-install-schedule`
**Status:** Concept / idea-shaping. No implementation yet.
**Date:** July 11, 2026

> Client ask (paraphrased from Daniel's note): PMs can stack unlimited releases on
> the same install dates, which overruns fabrication with unrealistic dates. Build a
> "tee time" system — define available **fab and install hours per week by product
> type**, and when a PM schedules a release they must **pick an open capacity slot,
> not just a date**. Once the slot is locked, the system **works backward to a hard
> drafting deadline** that feeds the drafting workload (DWL). Weekly GC look-aheads
> drive the **"required on site"** date that kicks the whole chain off.
> First build: get the tee-time system in place so we stop overrunning fabrication.
> **Open question from the client: capacity at the shop level, product-type level, or both?**

---

## 1. The core idea: invert the schedule

Today the install date is an **output**. Two ways a release gets one:

- **Derived** by the serial-flow engine in `app/brain/job_log/scheduling/calculator.py`:
  fab work is one global queue ordered by `fab_order`; we sum the remaining fab hours
  *in front* of a release, divide by a single daily fab capacity
  (`FAB_HOURS_PER_DAY = 104`, i.e. 13 fabricators × 8h — `scheduling/config.py:60`),
  add an install buffer (`INSTALL_BUFFER_DAYS = 3`), and land a projected install
  start → `comp_eta`.
- **Hard-typed** by a PM (`start_install` with `start_install_formulaTF = False`
  marking it a hard date). Hard-date releases are *excluded* from the hours-in-front
  sums (`calculator.py:91`).

The failure mode the client is describing: **nothing enforces a ceiling.** A PM can
hard-set ten releases to the same week and the model happily accepts it — the hours
simply don't fit in the shop, but no code says so. Install has *no* capacity ceiling
at all today; fab has only an implicit serial one. The *only* existing throttle on
scheduling demand is the "at most 2 ASAPs per PM" soft cap (`routes.py:1631`,
overridable) — a small conceptual precursor to real capacity limiting.

The tee-time model **inverts the dependency**:

```
   TODAY (push):   fab queue  ─derive→  install date  ─derive→  comp_eta
                   (drafting deadline is set independently, may or may not be realistic)

   TEE TIME (pull): required-on-site (GC)  →  PICK an open install slot  ─lock→
                    ─work backward→  hard fab window  ─work backward→  hard drafting deadline → DWL
```

The install slot becomes an **input the PM reserves against finite weekly capacity**,
and the drafting + fab deadlines fall out of it. A slot can only be booked if the
week has hours left.

---

## 2. What we already have (reuse, don't rebuild)

The good news: most of the *arithmetic* exists. The missing piece is the **capacity
ledger** — the thing that says "this week is full."

| Primitive | Where | Reuse for tee time |
|---|---|---|
| Per-release **install hours** | `Releases.install_hrs` (`models.py:453`) | the "size" of a slot booking |
| Per-release **fab hours** | `Releases.fab_hrs` (`models.py:452`) | the size of the fab-capacity draw |
| **Crew size** | `Releases.num_guys` (`models.py:476`) | already scales install duration |
| **Install start date** | `Releases.start_install` (`models.py:461`) | *becomes* the reserved tee-time slot |
| **comp_eta** forward math | `calculate_install_complete_date()` (`calculator.py:189`): `start + ceil(install_hrs / (num_guys×8)) biz days` | unchanged — tells us which weeks a booking spans |
| **Backward drafting deadline** | DWL sets submittal `due_date` = `start_install − 15 business days` (the "Design Drawings Due" / DDD date), `drafting_work_load/service.py`; a second path backs `due_date` off `gc_jobsite_schedule_date` by 60 business days | **this IS the "work backward to a hard drafting deadline"** the client wants — already wired to feed the DWL |
| **GC-provided "required on site"** | `Submittals.gc_jobsite_schedule_date` (`models.py:123`) — a GC-supplied jobsite install date, entered by hand | the demand-date primitive; the tee-time slot must land at/before it (§4/§7) |
| **Slot → job-log handoff** | `PendingStartInstall` keyed by Rel (`models.py:218`); date set on a submittal transfers to the release when pasted | the plumbing that carries a locked slot into the job log |
| Business-day arithmetic | `app/trello/utils.add_business_days` / `calculate_business_days_before` | all date math |
| Stage → remaining-% map | `scheduling/config.py:38` | fab-load draw-down as work progresses |

So a backward *link* for piece #3 of the client's ask exists (DDD = start_install −
15 business days) — **but it is not a viable chain, because the 15-day lead is
fab-blind** (see gap C9): between "drawings due" and "crews on site" the real world
must fit GC approval → FC → release → material procurement → fabrication → paint →
ship, which cannot happen in 15 business days. The only constant shaped like a true
full-pipeline lead is the 60-business-day GC-schedule backdate. The tee-time backward
chain must insert a **fab window** (sized from `fab_hrs` + shop load) and an approval
lead between the install slot and the drafting deadline — the 15-day rule is a
drafting-side nudge to reuse, not the chain itself.

---

## 3. What is genuinely new

1. **A weekly capacity definition.** Available fab hours/week and install hours/week.
   Today fab capacity is a single daily constant and install has none. New config,
   ideally overridable per-week (holidays, PTO, a week where a crew is out).

2. **A capacity ledger.** For any week, `booked = Σ hours of releases whose
   fab/install lands in that week`; `remaining = available − booked`. This is a
   *computed rollup*, not stored state — same philosophy as the Projects-tab
   rollups.

3. **A slot picker (the "tee time").** When a PM schedules a release, the UI offers
   **open weeks** (remaining ≥ this release's hours) instead of a free date field,
   and **refuses to overbook** — or books it *yellow/over-capacity* with an explicit
   warning rather than silently. This is the headline feature and the smallest
   first build.

4. **The "required on site" demand signal from GC look-aheads.** The latest
   acceptable install week. The tee-time slot must be booked at or before it. A
   hand-entered version of this already exists (`Submittals.gc_jobsite_schedule_date`);
   what's *new* is auto-ingesting it from the weekly GC look-aheads instead of typing
   it — see §7 Phase 4.

---

## 4. Answering the client's key question: shop, product type, or both?

**Short answer: build the model as "both," but honestly you can only *turn on*
shop-level today — because we don't collect product type on a release yet.**

- We have hours (`fab_hrs`, `install_hrs`) and a crew (`num_guys`) on every release,
  so a **shop-wide weekly ceiling works with zero new data.** That alone kills the
  overbooking problem — the first build.
- We do **not** have a product-type / work-center field on `Releases`. There is a
  `type` column on `Submittals`, but that's the submittal phase (DRR/GC/FC), *not* a
  product category. So "capacity by product type" (e.g. stairs vs. railings vs.
  misc-steel lines that can't share the same welders) needs a **new classification
  dimension added and backfilled** before it can be enforced.

**Recommendation:** design the capacity bucket with a `dimension` key from day one
(`SHOP` now; `PRODUCT_TYPE:<x>` / `INSTALL_TEAM:<x>` later) so switching granularity
is a config change, not a rebuild. Ship shop-level first. This is exactly the
"probably we are not collecting all of this data yet" gap Daniel flagged.

---

## 5. Sketch of the data model (for discussion, not final)

```
WeeklyCapacity                      # the "available hours" definition
  dimension        str   # 'SHOP' | 'PRODUCT_TYPE:stairs' | 'INSTALL_TEAM:red'
  week_start       date  # Monday of the ISO week
  fab_hours        float
  install_hours    float
  # rows are sparse: a base default + per-week overrides for holidays/PTO

CapacitySlot  (a.k.a. the tee time)  # a release's reservation
  release_id       FK Releases
  dimension        str
  week_start       date            # the booked install week
  install_hours    float           # snapshot of install_hrs at booking
  locked           bool            # locked slots drive the hard drafting deadline
  # fab draw is derived from fab_hrs across the fab window ending before this week
```

`remaining(dimension, week)` = `WeeklyCapacity.hours − Σ CapacitySlot.hours`.
The slot picker offers weeks where `remaining ≥ release.install_hrs`. Locking a slot
stamps `start_install`, which the existing DDD math turns into the hard drafting
deadline on the DWL — no new backward-math code required.

Both tables likely live behind computed rollups where possible; only the
**reservation** and the **capacity overrides** are truly persisted.

### 5.1 What it looks like populated — real prod releases, mocked into the model

Using actual releases scheduled in the overbooked 7/13–7/20 window (prod,
2026-07-11). Assumed shop install capacity: 4 crews × 2 guys × 40h = **320 hrs/wk**.

**`weekly_capacity`** — sparse: one default row + overrides only where a week differs.

| id | dimension | week_start | install_hours | note |
|---|---|---|---|---|
| 1 | SHOP | *(default)* | 320 | 4 crews baseline |
| 2 | SHOP | 2026-08-31 | 240 | Labor Day week (4-day) |
| 3 | SHOP | 2026-07-27 | 240 | Saul 1 crew out |

**`capacity_slots`** — one row per booked release. `week_hours` splits a booking
that spans weeks (real example: 580-676 is a 194.7h stair core spanning three weeks).

| id | release | description | week_start | week_hours | total_hrs | locked | booked_by |
|---|---|---|---|---|---|---|---|
| 41 | 500-685 | Stair Core 2 Part 2 | 07-13 | 78.5 | 78.5 | ✅ | GA |
| 42 | 410-669 | RFI 352 Sprinkler Pen. | 07-13 | 180.0 | 180.0 | ✅ | RL |
| 43 | 410-670 | RFI 353 Steel Column | 07-13 | 48.0 | 48.0 | ✅ | RL |
| 44 | 340-641 | Knee Wall Balcony Rail | 07-13 | 39.4 | 39.4 | — | DR |
| 45 | 390-643/4/5 | Bld G Stair Cores ×3 | 07-13 | 55.5 | 55.5 | ✅ | RL |
| 46 | 580-676 | Blue Room Stair Core 2 | 07-20 | 96.0 | 194.7 | ✅ | RL |
| 47 | 580-676 | ″ *(spillover)* | 07-27 | 80.0 | 194.7 | ✅ | RL |
| 48 | 580-676 | ″ *(spillover)* | 08-03 | 18.7 | 194.7 | ✅ | RL |
| 49 | 340-164 | Superior Decks Balconies | 07-20 | 76.0 | 108.0 | — | DR |
| … | *(+18 more rows in these two weeks)* | | | | | | |

**The ledger** (computed view, never stored) — what the system, the picker, and any
dashboard all read:

| week_of | capacity | booked | remaining | util | status | #slots |
|---|---|---|---|---|---|---|
| 07-13 | 320 | 641 | **−321** | 200% | 🔴 OVERBOOKED | 18 |
| 07-20 | 320 | 671 | **−351** | 210% | 🔴 OVERBOOKED | 12 |
| 07-27 | 240 | 262 | −22 | 109% | 🟡 over | 2 |
| 08-03 | 320 | 131 | 189 | 41% | 🟢 open | 1 |
| 08-10 | 320 | 80 | 240 | 25% | 🟢 open | 0 |
| 08-17 | 320 | 86 | 234 | 27% | 🟢 open | 1 |

**What the PM sees** when booking a new 40-hr release (required on site 08-21):

| week | remaining | fits? | |
|---|---|---|---|
| 07-13 | −321 | ❌ full | *(needs admin override)* |
| 07-20 | −351 | ❌ full | |
| 07-27 | −22 | ❌ full | |
| 08-03 | 189 | ✅ **pick** | ← earliest open slot |
| 08-10 | 240 | ✅ pick | |
| 08-17 | 234 | ✅ pick | last week ≤ required-on-site |

Picking 08-03 locks the slot → stamps `start_install = 2026-08-03` (hard). The
existing DDD math would put drawings due 15 business days prior (2026-07-13) — but
per gap C9 that lead leaves zero room for approval + fab, so the real backward chain
must be: slot − ship buffer − **fab window** (`fab_hrs` vs shop load) − approval
lead − drafting time. For a booking made *today* for 08-03, the honest question the
system should answer is "can drawings + approval + fab all still fit?" — not just
"stamp a drafting date."

Today's reality in this same window, for contrast: those 30 releases all landed on
raw dates with no ledger — which is exactly how two consecutive weeks got to
~200% while 08-03 onward sits at 25–40%.

---

## 6. Phased build

- **Phase 1 — Shop-level tee time (the client's "first build").** One weekly install
  ceiling. Slot picker on release scheduling that shows open weeks and blocks (or
  loudly flags) overbooking. Reuses `install_hrs` + the existing DDD backward math.
  No new data collection. *This is the whole "stop overrunning fabrication" win.*
- **Phase 2 — Add fab capacity + make the drafting deadline hard.** Bring `fab_hrs`
  into the ledger so booking an install slot also reserves the upstream fab window;
  promote the DDD date from advisory to an enforced DWL deadline.
- **Phase 3 — Product-type / work-center dimension.** Add + backfill a product-type
  on releases; switch buckets from `SHOP` to per-type. (Prereq: agree the type
  taxonomy with the shop.)
- **Phase 4 — GC look-ahead ingestion → required-on-site.** Feed weekly GC
  look-aheads (from project meetings) into a required-on-site date per scope, so the
  demand date auto-drives the slot search instead of the PM eyeballing it. Ties into
  the existing meeting-ingestion work.

---

## 7. Honest gaps & open questions

- **Product type isn't collected.** Biggest blocker to the "by product type" half of
  the ask. Needs a taxonomy decision + a field + backfill.
- **GC look-aheads aren't ingested** as structured required-on-site dates yet. The
  *field* exists (`Submittals.gc_jobsite_schedule_date`, backs `due_date` off by 60
  business days) but it's hand-entered per submittal — Phase 4 auto-populates it from
  the weekly GC look-aheads via the meeting-ingestion pipeline.
- **Install spanning multiple weeks.** A big release's install crosses week
  boundaries; decide whether it draws from one week (its start) or spreads. Affects
  the ledger math.
- **Overbook policy:** hard block vs. allow-with-warning? The shop may legitimately
  push to overtime — recommend *warn + require override*, not a hard wall.
- **Fab vs. install are different constraints.** A week can be install-full but
  fab-open, or vice-versa. The model handles this (two hour columns) but the picker
  UX needs to show both.
- **Interaction with the existing serial-flow engine.** Once slots are hard, the
  `calculator.py` projection becomes a *check* ("does the fab queue actually clear in
  time for this slot?") rather than the *source* of the install date. Decide the
  relationship deliberately — don't run two schedulers that disagree.

---

*Next step: confirm shop-level-first with the client and whether overbooking should
hard-block or warn-and-override, then prototype the Phase-1 slot picker against the
sandbox job log.*

---

## 8. Data-grounded brainstorm: top 3 improvement paths

Read-only metrics pulled 2026-07-11 from the **production** DB (sandbox run first,
prod confirmed the trends and sharpened them):

| Signal | Prod value | Implication |
|---|---|---|
| Active releases | 257 (31 FABRICATION / 68 READY_TO_SHIP / 158 COMPLETE) | |
| `install_hrs` / `fab_hrs` populated (non-COMPLETE, n=99) | 88% / 91% | **capacity ledger is data-ready today** |
| `num_guys` populated | **1 of 99** | effectively never set — every comp_eta runs on the hardcoded default of 2; per-crew math has no real data |
| `installer` populated | 5/99 (5%); 4 teams ever seen (Eduardo 1, Osbaldo, Oscar, Saul 1) | install-team dimension has almost no data |
| Hard dates vs soft | 30 hard / 69 soft / 2 ASAP | ~30% of the live schedule bypasses the queue engine — the overbooking vector |
| **Booked install hrs, wk of 7/13** | **641 hrs, 18 releases starting** | 4 crews × 2 guys × 40h ≈ **320 hrs/wk real capacity → ~200% booked** |
| **Booked install hrs, wk of 7/20** | **671 hrs, 12 releases** | second consecutive ~2× week — *the client's complaint, quantified* |
| Weeks 3–8 out | 262 → 131 → 80 → 86 → 48 → 32 hrs | demand cliffs after the pile-up: everything crowds into "now" |
| Releases fully past their install dates, still open | **52 releases / ~864 hrs; median 53 days stale, p90 79** | the schedule *decays*: dates slide past and nobody re-books them |
| Remaining fab hours in FABRICATION queue | ~837 hrs ≈ **1.6 shop-weeks** @104/day (19 of 31 still 'Released') | fab is not a months-deep backlog — install capacity and date hygiene are the binding constraints |
| `gc_jobsite_schedule_date` on open submittals | **0 of 280** | the "required on site" field exists and is entirely unused |

**The headline: the next two install weeks are booked at ~200% of realistic crew
capacity (641 and 671 hrs against ~320), with 18 releases stacked on one start week —
while week 5 and beyond sit nearly empty.** That is precisely the failure the
tee-time system exists to prevent, now measured.

### Path 1 — Tee-time install ledger, shop-level (the client's ask; build first)
Weekly install-hours ledger + slot picker, `dimension='SHOP'`, warn-and-override on
overbook (§5–6 Phase 1). The data audit says it's buildable **now** (88% of live
releases carry `install_hrs`) and *needed* now: prod shows back-to-back ~200%-booked
install weeks. Scope it to the *install* side first — the fab queue is ~1.6 weeks
deep, so a fab-hours ledger solves a problem the data doesn't currently show, while
install stacking is unbounded. The empty weeks 5+ mean the picker has real open
slots to offer — spreading the 7/13–7/20 pile-up forward is exactly its job.

### Path 2 — Schedule truth-maintenance (the quiet decay under the pile-up)
52 open releases sit with install dates already past — ~864 hours of phantom
bookings, median **53 days** stale. Any capacity ledger computed over stale dates is
fiction on day one (worse: stale rows inflate "booked" in past weeks while the
pile-up crowds the near future). Build the decay loop *with* the tee time, not after
it: a weekly sweep flags past-due `start_install` rows and forces them through the
slot picker to **re-book** — which is also what organically populates the forward
calendar. This is the difference between a scheduling feature and a scheduling
*system*: staleness gets a workflow, not just a color.

### Path 3 — Calibrate the model from event history (adjust the calculations)
Every constant in the engine is a frozen Excel guess: `FAB_HOURS_PER_DAY=104`, stage
remaining-% map ("do not change without approval"), `INSTALL_BUFFER_DAYS=3` — and
prod shows `num_guys` set on **1 of 99** live releases, so effectively every
comp_eta runs on the hardcoded default crew of 2. Meanwhile `ReleaseEvents` has
months of real stage-transition timestamps. Mine actual stage durations and actual
install-start→complete spans to (a) replace the stage-% guesses with measured
values, (b) learn the real FC→install lead time per job size, and (c) expose
estimate-vs-actual per release so `install_hrs` quality improves over time. This
compounds: better constants make both the queue projection *and* the tee-time
ledger trustworthy — and the ledger's weekly capacity number (≈320 install-hrs/wk
from 4 crews) deserves measurement, not assumption.

**Sequencing:** 1 and 2 ship together as the tee-time MVP (the re-book sweep is the
adoption engine for the picker); 3 runs as an offline analysis first — no product
surface needed to start measuring.

**Deliberately deferred:** per-product-type buckets (no type field, §7), per-crew
buckets (`installer` 2% populated, `num_guys` constant), auto-ingested GC look-aheads
(field unused — adoption problem before ingestion problem).

---

## 9. Gap audit — estimates & calculations (verified in code, 2026-07-11)

### Input-data gaps (what the numbers are made of)

| # | Gap | Evidence | Impact on tee time |
|---|---|---|---|
| D1 | `num_guys` never entered (1/99 in prod) — comp_eta runs on `DEFAULT_NUM_GUYS=2` everywhere; sourced by parsing Trello card *description text* (`"**Number of Guys:** N"`, `trello/api.py:1717`) | prod metrics | slot *duration* (how many weeks a booking spans) is a guess |
| D2 | `install_hrs` missing on 11/99 live releases | prod metrics | those releases are **invisible to the ledger** — 0-hr bookings |
| D3 | No estimate-vs-actual loop: `Install Start`/`Install Complete` stage timestamps exist in `ReleaseEvents`, but actual durations are never compared to `install_hrs` | recon §2/§4 | estimate quality can't improve; ledger inherits estimate error forever |
| D4 | No product-type field; `installer` 5% populated | recon §3 | blocks by-type / by-crew buckets (§4) |
| D5 | `gc_jobsite_schedule_date` 0/280 — no demand-side date captured | prod metrics | "required on site" chain has no fuel |
| D6 | Releases have no creation timestamp (inferred from first event) | projection-findings doc | lead-time analytics (FC→install) stay approximate |

### Calculation-model gaps (how the numbers are combined)

| # | Gap | Evidence | Impact |
|---|---|---|---|
| C1 | **Two unreconciled stage-% maps**: the queue engine uses legacy `STAGE_REMAINING_FAB_PERCENTAGE` (`scheduling/config.py:38`), while `STAGE_HOUR_PERCENTAGES` in `api/helpers.py` (the client's "Banana Code" matrix, declared the future source of truth) is only used by the hours-summary report — the two can disagree on the same release | config.py:34-37 docstring admits it | queue projection and reporting can tell different stories *today* |
| C2 | **Hard-date releases vanish from queue math** — excluded from `hours_in_front` (`calculator.py:91`), but the shop must still fabricate them. With 30/99 hard dates, ~30% of the fab load is invisible to every soft release's projection | recon §2 | soft projected dates are systematically **optimistic** |
| C3 | **No holiday calendar** — `add_business_days` counts Mon–Fri only (`trello/utils.py:257`); zero `holiday` hits in the codebase. July 4th, Thanksgiving, Christmas weeks count as full capacity | verified | dates drift; ledger weeks around holidays overstate capacity (the §5.1 override row handles this — but only in the *new* model) |
| C4 | **Duplicate install-duration formula** — `calculate_installation_duration` (`trello/api.py:1655`) reimplements `calculate_install_complete_date` (`calculator.py:189`); drift risk between Trello card text and DB comp_eta | recon §2 | two sources of truth for the same number |
| C5 | `FAB_HOURS_PER_DAY=104` frozen ("13 fabricators × 8") and `INSTALL_BUFFER_DAYS=3` fixed regardless of paint/galvanizing/size — never measured against actuals | config.py | queue projection accuracy unknown; buffer is folklore |
| C6 | **Stale hard dates never age** — the recalc engine skips hard dates (`service.py:65,216`), so a past hard date sits frozen forever; 52 prod releases prove it | prod metrics | schedule decays silently (Path 2 exists because of this) |
| C7 | Single global fab queue — strict serial FIFO by `fab_order`; no parallelism/work-center modeling; unknown stages count 100% remaining | calculator.py | fine at 1.6-wk depth, misleading if backlog grows |
| C8 | **Drafting side has no feasibility check** — DWL is pure ordering; a "hard drafting deadline" lands on the DWL with no drafting-hours capacity behind it. The tee time can faithfully reproduce the install overbooking problem one level upstream | recon §4 | Phase-2 concern: locked slots could stack un-draftable deadlines |
| C9 | **The 15-day DDD lead is fab-blind** — `due_date = start_install − 15 biz days` (`dwl/service.py:231`) leaves zero room for GC approval → FC → release → material → fab → paint → ship between "drawings done" and "crews on site." It's a drafting nudge, not a schedule. The 60-biz-day GC backdate is the only constant shaped like a full-pipeline lead; neither is derived from `fab_hrs` or shop load | flagged by Daniel 2026-07-12; code verified | the tee-time backward chain must compute a real fab window per release — reusing the 15-day rule as "the chain" would book slots that are physically impossible to hit |

### Reading of the audit

The **biggest single distortion is C2** (hard dates invisible to queue math) — it
compounds: PM hard-sets a date → that release's fab hours vanish from everyone
else's projection → other soft dates look earlier than reality → more pressure to
hard-set → more invisible load. The overbooked 7/13 week is partly this spiral.

The **cheapest wins** are C1 (pick one stage-% map), C4 (delete the duplicate
formula), and C3 (a 10-line holiday list). None need new data.

The **tee-time-critical ones** are D1/D2 (slot sizing), C6 (ledger honesty), and
**C9 (the backward chain needs a real fab window — the 15-day DDD lead cannot carry
approval + fab and would book impossible slots if reused as-is)**. C8 is the
sleeper: make sure Phase 2 checks drafting feasibility before we celebrate hard
drafting deadlines.

---

## 10. The macro pipeline — canonical order, measured durations

**Canonical phase order (per Daniel, 2026-07-12; supersedes the old projection-findings
doc which had DRR first):**

```
Sub GC ──▶ DRR ──▶ FC ──▶ Job Log release ──▶ fab ──▶ install
```

FC releases to the Job Log **same day 99% of the time** (per Daniel; the old ~3-day
figure from the projection findings was measurement noise on a same-day gate).

**Measured from prod** (2026-07-12, read-only; created→closed per submittal,
backfill-clustered rows excluded, 10% trimmed each tail, calendar days):

| Phase | n | median | trimmed mean | p25 | p75 | Daniel's rule of thumb |
|---|---|---|---|---|---|---|
| **Sub GC** (created→closed) | 221 | **32d** | **64d (~9 wks)** | 8d | **111d** | 8 weeks — matches the *mean* |
| **DRR** (created→closed) | 483 | **15d** | 24d | 4d | 37d | 15 days — matches the *median* exactly |
| FC → release | — | same day (99%) | | | | per Daniel |

**The planning insight: Sub GC is not a duration, it's a distribution.** p25=8 days
vs p75=111 days — a 14× spread, driven by how long the GC sits on the approval. DRR
is comparatively tame (4–37d). Any schedule that treats Sub-GC as a fixed 8 weeks
will be badly wrong half the time in each direction. Consequence for the tee time:
**the slot picker should consume a live "where is this scope in the pipeline" state,
not a fixed lead constant** — and the DWL should surface *aging-in-phase* for Sub-GC
submittals so the volatile link is watched, not assumed.

### The macro backward chain (working numbers, v0)

For a scope at each pipeline position, earliest realistic install slot ≈ today +
"remaining pipeline." Using medians for the plan number and p75 for the risk band;
fab window = `fab_hrs / 104` shop-days behind the current queue (~1.6 wks measured)
+ 3-day ship buffer ≈ **~2–3 wks** for a typical release:

| Scope is currently… | Remaining pipeline (median) | Earliest slot ≈ | Risk band (p75) |
|---|---|---|---|
| Not yet submitted | 32d + 15d + fab | **~9–10 wks out** | ~24 wks |
| In **Sub GC** (just opened) | 32d + 15d + fab | ~9–10 wks | ~24 wks |
| In **DRR** | 15d + fab | **~5 wks** | ~9 wks |
| In **FC** / just released | fab only | **~2–3 wks** | ~4 wks |
| In fab queue | queue position | per queue math | |

Sanity check: full-chain median ≈ 32+15 cal days + ~2.5 wks fab ≈ **9–10 weeks**;
conservative (mean Sub GC) ≈ 64+24 days + fab ≈ **~15 weeks**. The existing
`GC_SCHEDULE_LEAD_BUSINESS_DAYS = 60` (12 weeks) sits squarely inside this band —
that constant was empirically encoding the whole pipeline all along.

**v0 slot-picker feasibility rule:** a release can only book an install week ≥
(today + remaining-pipeline median for its current phase); weeks inside the risk
band get a ⚠ "tight — GC approval must run faster than p75" flag rather than a
block. Re-measure these numbers quarterly (the §8 Path-3 mining automates this).

---

## 11. Chain-linkage audit — can we connect Sub GC → DRR → FC → release per scope?

Probed in prod 2026-07-12 (read-only). Two different ambitions, two different answers:

**The macro *measurement* pipeline (what the tee time needs): ✅ works today.**
Phase-duration distributions don't require following one scope across phases — each
phase's own created→closed population measures it (that's §10). FC→release and
release→install staging are traceable. The quarterly MEASURE step can ship now.

**Per-scope traceback ("where is scope X and when does it land"): ❌ blocked in the
middle.** Link-by-link:

| Link | State | Evidence (prod) |
|---|---|---|
| Sub GC → DRR | ❌ no key | 0 type transitions across 696 submittals with typed events — each phase is a separate record in our data; exact-title matching links only 136/1502 scopes (9%, same rate as the May findings), and only **3** scopes trace across all three phases |
| DRR → FC | ❌ no key | same |
| FC → release | 🟡 mostly | 205/257 releases carry `procore_submittal_id` (80%); 166 join a submittals row cleanly (65%). Secondary path: `rel` (76 assigned, 63 join). FC titles also embed the job-release ("340-942 Stair Core C…") — parseable as a third path |
| release → install | ✅ | `ReleaseEvents` stage transitions end-to-end |

**The fix is sitting in the parser: `specification_section` is extracted from every
Procore payload (`app/procore/procore.py:381`) and then dropped — the `Submittals`
model has no column for it.** Spec section is the natural cross-phase constant (one
scope keeps its spec section through GC → DRR → FC). Plan:

1. Add `spec_section` (and Procore's `number`) columns to `Submittals`; persist on
   every sync going forward.
2. One-time read-only Procore API sweep to backfill both fields for all ~1,713
   historical submittals.
3. Measure the real linkage rate (project + spec_section → phase chain). If MHMW's
   Procore discipline populates spec sections consistently, the whole funnel becomes
   traceable retroactively; if it's spotty, fall back to forward-capture (record the
   predecessor at DRR/FC creation, with a match-confirm UI reusing the sub/rel
   matching picker).

Until then, per-scope ETAs use phase-population medians (§10), not per-scope history
— which is all the v0 slot picker needs anyway.
