# Fab Capacity Calibration — Findings

**Branch:** `feature/tee-time-sim`
**Date:** July 22, 2026
**Status:** Analysis complete; stage-weight change proposed to client (emailed 7/22), **not yet applied — awaiting approval.** Integration approach TBD (see §7).
**Method:** Read-only queries against production. No schema or data changes.

> Prompt from the shop: releases are stacking up "released through Welded QC" and we
> need a defensible timeline. Working assumption was **~400 hrs/week of fab work
> (Cut Start → Welded QC)**. Can the data confirm or refute that, and can we lay out
> the current fab queue against that capacity without overloading the shop?

---

## 1. Headline findings

1. **The 400 hrs/week estimate is correct.** Measured fab throughput over the last
   12 weeks: **mean 398 hrs/wk, median ~400** — against the code's frozen constant
   of `FAB_HOURS_PER_DAY = 104` → 520/wk (`scheduling/config.py:60`), which is
   **~30% optimistic**.
2. **The shop is effectively a Mon–Thu operation.** Weekday throughput split
   (hours-weighted, ~19 weeks): Mon ~26%, Tue ~32%, Wed ~21%, Thu ~17%, **Fri ~5%**.
   Daily cadence ~80–130 hrs Mon–Thu, Tuesday peak. Monthly ≈ 1,700 hrs.
3. **The current fab queue is ~1.2–1.5 weeks deep, not months.** 24 releases in the
   FABRICATION stage group, 662 raw fab hrs → 474–577 remaining hrs depending on the
   stage-weight map (see §5). At 400/wk everything currently in fab clears Welded QC
   by ~7/29–7/30 (conservatively ~8/4). The binding question is *inflow*, not
   backlog: the week of 8/3 was empty at time of analysis.
4. **The legacy stage-% map materially mis-prices work in progress.** Measured
   phase-effort shares are close to **equal thirds** (cut ~33% / fitup ~34% /
   weld+QC ~33%) vs the map's implied 10/40/40(+10 paint/QC). A release at Cut
   Complete shows 90% remaining but is really ~65% remaining.
5. **Near-term hard install dates were paint-constrained, not fab-constrained.**
   Welded QC → Paint Complete median ≈ 5 business days (p25 = 2). Ship =
   `start_install − 1` biz day (per shop practice). So fab must clear QC ~6 biz days
   before a hard install date under the *unforced* paint flow. Every 7/27–7/28 hard
   date at time of analysis had only 1–2 days of paint window left.

---

## 2. Throughput measurement method

For every `release_events` row with `action='update_stage'`, credit:

```
completed_hours = fab_hrs × (remaining%(from_stage) − remaining%(to_stage))    [if > 0]
```

using the stage-remaining map, then bucket by ISO week of `created_at`. Backward
moves and no-op transitions credit nothing. Multi-stage jumps credit the endpoint
delta, which is **path-independent** — correct for throughput regardless of skipped
intermediate stages.

**Critical implementation detail — legacy Trello label aliases.** ~44% of stage
event sides use pre-rename Trello list names and silently drop out of any
canonical-name join. Alias map required:

| Event label | Canonical stage |
|---|---|
| `Shipping completed` | Ship Complete |
| `Shipping planning` | Ship Planning |
| `Paint complete` | Paint Complete |
| `Fit Up Complete.` | Fitup Complete |
| `Cut start` | Cut Start |
| `Store at MHMW for shipping` | Store at MHMW |
| `Welded` | Welded QC |

Without the aliases the measured throughput is ~35% low and April/May are
unusable. (`Unassigned cards`, installer names, etc. are list-noise — drop.)

**Weekly series (alias-corrected, fab hrs completed):**

| Week of | Hrs | | Week of | Hrs |
|---|---|---|---|---|
| 2026-05-04 | 457 | | 2026-06-15 | 596 |
| 2026-05-11 | 308 | | 2026-06-22 | 472 |
| 2026-05-18 | 414 | | 2026-06-29 | 212 *(July 4)* |
| 2026-05-25 | 211 *(Memorial)* | | 2026-07-06 | 335 |
| 2026-06-01 | 434 | | 2026-07-13 | 360 |
| 2026-06-08 | 405 | | | |

Range ~210 (holiday) – ~600 (best). March–April excluded from steady-state: the
system was in adoption ramp and April (~2,490 hrs/mo) is backfill catch-up, not
real throughput.

**Known biases:** hours are credited *at estimate value* when stages move, so
batch card updates spike single weeks; events for releases no longer in `releases`
(archived) drop out of the join → measured 400 is, if anything, a slight
undercount of true capacity.

---

## 3. Paint / ship gap (reverse-engineered)

Per-release first-arrival timestamps:

| Gap | n | median | p25 | p75 | Note |
|---|---|---|---|---|---|
| Welded QC → Paint Complete | 151 | **7 cal days (~5 biz)** | 2 | 28 | p75 tail = storage/wait, not paint time |
| Welded QC → Ship Complete | 21 | 16 cal days | 8 | 43 | inflated by Store-at-MHMW waiting on install dates |

Client's stated paint time (~3–4 days) sits between p25 and median — real when
paint is prioritized. **Planning rule adopted: Welded QC due `start_install − 6`
business days (5 paint + 1 ship) unless paint expedites.**

---

## 4. Queue layout at 400 hrs/wk (snapshot 2026-07-22)

Scope: FABRICATION stage group only. Hours basis: stage-weighted remaining.
Sequencing: hard dates first (earliest deadline), then `fab_order`.

- **Rest of wk 7/20** (~233 hrs left after 167 already logged): the six hard-date
  releases installing 7/27–7/28, in deadline order — 640-957 (ASAP), 380-943,
  590-931, 190-938, **580-659 Stair Core 1 (160.5 hrs — the week's dominant item)**,
  190-103; start 530-921.
- **Wk 7/27** (~344 of 400 hrs): finish 530-921; 530-922 and 560-941 (hard 8/21,
  8/28 — large slack); entire soft queue in fab_order, anchored by **500-665 Stair
  Core 1 Part 2 (104.7 hrs)**.
- **Wk 8/3: empty.** Headroom for inflow.

Flags: all 7/27–7/28 hard dates violate the 6-biz-day paint window (fab finishes
in time; paint has 1–2 days instead of 5–6 → slip risk unless expedited, with
580-659 most at risk). 500-958 and 190-960 carry `fab_hrs = 0` — invisible to all
hours math; need estimates.

---

## 5. Stage-weight recalibration (the durable finding)

### 5.1 What the current map implies vs what the shop does

`STAGE_REMAINING_FAB_PERCENTAGE` implies effort shares **cut 10% / fitup 40% /
weld 40% / paint-QC 10%**, and credits *zero* for Cut Start → Cut Complete (both
0.9).

### 5.2 Measurement — strictly-sequential transitions only

Naive phase timing is contaminated by stage-skipping: **~80% of stage-progress
credit arrives via multi-stage jumps** (only 1,548 of 7,728 credited hours moved
one adjacent step). A jump like Cut Start → Fitup Start means "Cut Complete" never
happened observably; any duration bounded by it is fabricated.

**Validity rule:** a phase duration counts only when the release *entered the
phase-end checkpoint from its adjacent predecessor* (e.g. cut = first `Cut Start`
arrival → an event with `from='Cut Start', to='Cut Complete'`). Phases measured on
the reliably-logged checkpoints only — `Weld Start`/`Weld Complete` appear on
<15% of releases, so **weld+QC is one merged phase** (Fitup Complete → Welded QC).

Hours-weighted wall-time shares (workday-scaled), two independent populations:

| Phase | Per-phase populations (n=151/70/97) | Full clean traversals (n=35) |
|---|---|---|
| Cut (CS→CC) | 34.2% | 32.0% |
| Fitup (FS→FC) | 36.6% | 32.8% |
| Weld+QC (FC→QC) | 29.2% | 35.3% |

Both methods converge on **equal thirds**. The Cut Complete → Fitup Start dwell
(~1.8 wd hours-weighted, ~25% of the window) is handoff *wait*, excluded from
effort. Note: a looser analysis without the sequential filter deflates fitup to
~17–23% — jump-inherited boundaries are the artifact, and the filter is
non-negotiable for any future re-measurement.

### 5.3 Proposed map (v2)

| Stage | Current | **Proposed** |
|---|---|---|
| Released / Material Ordered / Hold | 1.00 | 1.00 |
| Cut Start | 0.90 | **0.85** |
| Cut Complete | 0.90 | **0.65** |
| Fitup Start | 0.90 | **0.65** |
| Fitup Complete | 0.50 | **0.35** |
| Weld Start | 0.50 | **0.35** |
| Weld Complete | 0.10 | 0.10 |
| Welded QC / Paint Start | 0.10 | **0.05** |
| Paint Complete → | 0.00 | 0.00 |

Encodes cut 35% / fitup 30% / weld+QC 30% / paint-residual 5%, and fixes the dead
Cut Start→Cut Complete transition (now worth 20%).

### 5.4 Validation

| Metric | Current map | v2 |
|---|---|---|
| Last-12-wk throughput mean / median | 398 / 410 | 387 / 415 |
| Week-to-week CV | 0.29 | **0.26** |
| Live queue remaining (7/22) | 568 hrs (1.42 wk) | **474 hrs (1.19 wk)** |

Throughput calibration unmoved (~400 either way); signal smoother; queue re-prices
down because Cut Complete stops reading as 90% remaining.

### 5.5 Caveats

Wall-time share is a proxy for labor share (assumes roughly constant crew per
release). Hours-weighting is tonnage-weighted truth — per-release *medians* show
fitup is fast on small work. Only 3 clean traversals above 80 fab-hrs; tails are
thin. Re-measure quarterly as event history deepens.

---

## 6. Status / governance

- Findings + v2 table emailed to Bill (boneill@mhmw.com) 2026-07-22 for approval.
- `scheduling/config.py` invariant: **do not change the map without explicit
  approval** (mirrors the legacy Excel workbook).
- On approval the change must land in **both maps in one commit**:
  `STAGE_REMAINING_FAB_PERCENTAGE` (`scheduling/config.py`) **and**
  `STAGE_HOUR_PERCENTAGES` (`api/helpers.py`, the "Banana Code" matrix) — else the
  queue engine and the hours-summary report diverge (tee-time doc gap C1).

## 7. Integration — open question for the circle-back

This analysis currently lives in ad-hoc read-only scripts. Candidate homes, not
yet decided:

1. **Calibration script** — `scripts/measure_fab_throughput.py`: reproduces §2–§5
   (alias map, sequential filter, weekly series, phase shares) against any DB URL,
   dry-run-style, for the quarterly re-measure. Cheapest; makes the method durable.
2. **Capacity input to the tee-time ledger** — the measured 400/wk (not the 520/wk
   constant) becomes the fab-side `WeeklyCapacity` default; holiday weeks get
   override rows (measured: ~210 hrs). Direct dependency of
   `docs/tee-time-scheduling.md` §5.
3. **Live layout view** — the §4 week-by-week fab layout as a read-only endpoint
   (sibling of `install-schedule`), re-computed from current queue + measured
   capacity. Largest lift; needs the weight change landed first.
4. **Estimate-vs-actual loop** (tee-time doc D3/Path 3) — persist per-release
   measured phase durations so `fab_hrs` quality improves over time.

Recommended order: 1 → land v2 weights (post-approval) → 2, with 3/4 as tee-time
phases. Also worth folding the **alias map** into any code that reads historical
stage events — it is load-bearing for every backward-looking metric.
