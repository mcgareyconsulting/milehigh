# Submittal Events — Pattern Analysis

**Source:** prod `submittal_events` + `submittals` + `users` tables
**Window:** 2026-03-13 → 2026-04-26 (44 days of event history)
**Volume:** 2,002 events · 1,312 submittals · 41 projects

> Caveat — event tracking only goes back ~44 days. Submittals created before 2026-03-13 only show partial histories, so the global Open→Closed cohort is small (n=129). Per-drafter "turn duration" cohorts are larger (n=194 closed solo segments) and more reliable.

---

## TL;DR

1. **The "Dalton ~2 weeks vs Colton ~1 week" gut feel is not supported by the data.** Median solo-turn duration is *lower* for Dalton (0.07d) than Colton (1.09d). Mean is similar (3.14d vs 3.62d). Dalton carries roughly **2× Colton's volume** — that's the more interesting asymmetry.
2. **Submittal type dwarfs every other variable.** "For Construction" has 0.05 handoffs and ~0 day lifespan (effectively pass-through). "Drafting Release Review" averages 2.76 handoffs and 10.6-day lifespan. Reporting them in one bucket masks everything.
3. **Project-level thrash is real and concentrated.** A handful of projects average 3+ BIC handoffs per submittal, with one submittal hitting 15 handoffs. Likely scope/spec quality issue, not drafter speed.
4. **Submittal manager matters for queue cleanliness.** Rich Losasso runs the cleanest queue at 1.15 avg handoffs; Danny Riddell's queue averages 2.60.
5. **Colton × Danny Riddell is the slowest drafter–manager pair** (5.24d mean turn vs 1–3d for everything else). Worth a one-on-one.

---

## 1. Drafter Cycle Time

A "solo turn" = a continuous period where exactly one drafter's name is in `ball_in_court`. Duration = time until the next BIC change. Mean is skewed by long-tail stalls; **median is the better summary**.

### Solo turns, completed segments

| Drafter | n | mean | **median** | p25 | p75 | max |
|---|---:|---:|---:|---:|---:|---:|
| Dalton Rauer    | 123 | 3.14d | **0.07d** | 0.01 | 4.28 | 31.14 |
| Colton Arendt   |  56 | 3.62d | **1.09d** | 0.10 | 5.85 | 22.15 |
| Rourke Alvarado |  15 | 1.41d | **0.20d** | 0.04 | 1.46 | 6.79 |

**Reading:** Dalton fires off many quick turnarounds (median 1.7 hours) but has a fat tail of multi-week stalls. Colton's median is 15× higher — he's more consistently slow per item, but his tail is shorter. Their *means* converge.

### By submittal type (most signal is in Drafting Release Review)

| Type | Drafter | n | mean | median |
|---|---|---:|---:|---:|
| Drafting Release Review | Dalton          | 100 | 3.35 | 0.07 |
| Drafting Release Review | Colton          |  36 | 3.82 | 1.12 |
| Drafting Release Review | Rourke          |   6 | 1.46 | 0.52 |
| Submittal for GC Approval | Dalton        |  19 | 2.68 | 1.26 |
| Submittal for GC Approval | Colton        |  20 | 3.25 | 0.31 |
| Submittal for GC Approval | Rourke        |   7 | 1.78 | 0.25 |
| For Construction (any drafter)             |   3 | ~0   | ~0   |

`For Construction` is essentially auto-close — drafters are listed but nothing meaningful happens before close. Exclude from drafter performance.

### Drafter × Submittal Manager

| Drafter | Sub Mgr | n | mean d |
|---|---|---:|---:|
| Colton Arendt    | **Danny Riddell** | 15 | **5.24** ⬅ slowest pairing |
| Dalton Rauer     | Gary Almeida      | 35 | 3.70 |
| Colton Arendt    | Gary Almeida      | 22 | 3.18 |
| Dalton Rauer     | Rich Losasso      | 61 | 3.02 |
| Colton Arendt    | Rich Losasso      | 19 | 2.85 |
| Dalton Rauer     | Danny Riddell     | 27 | 2.68 |
| Rourke Alvarado  | Gary Almeida      | 11 | 1.53 |
| Rourke Alvarado  | Rich Losasso      |  4 | 1.08 |

> Action: ask Colton/Danny what's behind the 5.24-day average. Most other pairings are 1–4 days.

### Volume / load

| Drafter | total appearances | solo turns | currently open (BIC) |
|---|---:|---:|---:|
| Dalton Rauer    | 336 | 234 | **83** |
| Colton Arendt   | 167 | 142 | 64 |
| Rourke Alvarado |  41 |  22 | 5 |

Dalton handles ~2× Colton's flow over the window and currently sits on more open work. That's the more actionable inequality than turn-time.

---

## 2. BIC Handoffs Per Submittal

507 submittals had ≥1 BIC change tracked.

- **mean = 1.73**, median = 0, max = **15**
- 279 submittals (55%) had **0 handoffs** (mostly `For Construction`)
- 48 submittals (9%) had **≥7 handoffs** — the rework tail

### Top "thrash" projects (≥5 submittals)

| Project | n | mean | max |
|---|---:|---:|---:|
| Flats at Sand Creek | 8 | **4.25** | 8 |
| Alta Metro Center | 26 | **3.31** | **15** |
| Marshall Pointe | 14 | **3.29** | 11 |
| 4th St. North | 27 | 3.19 | 8 |
| Misc. Project MHMW | 7 | 3.14 | 9 |
| East Oak Townhomes | 8 | 2.62 | 6 |
| Heritage on Hover | 18 | 2.61 | 7 |
| Banyan High Point | 92 | 0.76 | 8 |
| Aspendale Littleton (Headwaters) | 39 | 0.54 | 7 |
| **Hines – Retreat at Longmont** | 18 | **0.00** | 0 |

> The top 5 projects by avg handoffs deserve a look. Is it spec quality, GC behavior, scope churn? At 15 handoffs on a single submittal, *something* is broken.

### By submittal manager

| Manager | n | mean handoffs | max |
|---|---:|---:|---:|
| Danny Riddell | 86 | **2.60** | 9 |
| Gary Almeida | 153 | 2.26 | 15 |
| Rich Losasso | 266 | **1.15** | 11 |

Rich runs his queue notably cleaner. Either his projects are better-scoped or he's resolving questions before passing the ball.

### By type

| Type | n | mean handoffs |
|---|---:|---:|
| Drafting Release Review | 211 | **2.76** |
| Submittal for GC Approval | 135 | 2.04 |
| For Construction | 158 | 0.05 |

---

## 3. Open → Closed Lifespan (observed transitions only)

n=129 — only submittals where both the Open and Closed transitions fell inside the 44-day window.

- Global: **mean 5.22d, median 0.02d** (median pulled to ~0 by For Construction)

### By type — the only cut that matters

| Type | n | mean d | median d | max d |
|---|---:|---:|---:|---:|
| Submittal for GC Approval | 9 | **11.50** | 9.14 | 26.20 |
| **Drafting Release Review** | 53 | **10.59** | **6.94** | 42.15 |
| For Construction | 66 | 0.11 | 0.00 | 6.98 |

**Real drafting cycle time is ~7 days median, ~10–11 days mean.** Anything that quotes "average submittal time" without splitting by type is misleading.

### By project (≥3 closed in window)

| Project | n | mean | median | max |
|---|---:|---:|---:|---:|
| Martin Residence | 4 | 9.54 | 4.44 | 29.29 |
| Marshall Pointe | 6 | 9.16 | 4.08 | 26.94 |
| Banyan High Point | 14 | 9.05 | 3.58 | 27.07 |
| Sandstone Ranch | 5 | 7.94 | 0.03 | 22.72 |
| Stack at Wheat Ridge | 4 | 7.51 | 0.00 | 30.05 |
| Metro Center | 7 | 7.30 | 1.02 | 24.06 |
| Alta Metro Center | 6 | 7.24 | 5.05 | 20.30 |
| Novel Flatiron Crossing | 8 | 7.04 | 0.06 | 42.15 |
| Alta Flatirons | 18 | 4.30 | 1.84 | 17.79 |
| Outlook Green Valley Ranch | 13 | 2.00 | 0.01 | 20.03 |

### By submittal manager

| Manager | n | mean d | median d |
|---|---:|---:|---:|
| Gary Almeida | 51 | 6.37 | 1.79 |
| Rich Losasso | 53 | 4.73 | 0.01 |
| Danny Riddell | 25 | 3.89 | 0.00 |

---

## 4. Handoff Sequence Patterns

Top "from → to" BIC pairs (filtered to a representative name when BIC has multiple people):

| count | from → to |
|---:|---|
| 125 | David Servold → David Servold *(self — multi-name BIC churn)* |
| 43 | Dalton Rauer → Dalton Rauer *(self)* |
| **41** | **Rich Losasso → Dalton Rauer** |
| **31** | **Dalton Rauer → David Servold** *(drafter → QA)* |
| 29 | David Servold → Danny Riddell |
| 27 | David Servold → Colton Arendt |
| 25 | David Servold → Luis Solano |
| 23 | Dalton Rauer → Rich Losasso *(bounce back to manager)* |
| 23 | David Servold → Dalton Rauer |
| 21 | David Servold → Gary Almeida |
| 21 | Colton Arendt → David Servold |
| 13 | Gary Almeida → Dalton Rauer |
| 11 | Danny Riddell → Colton Arendt |

The dominant "happy path" is **Manager → Drafter → David Servold (QA) → next stop**. The 23 instances of `Dalton → Rich Losasso` and 11 of `Danny → Colton` suggest drafters bouncing items *back* to managers — worth a quick look at whether those are missing-info bounces (process gap) vs legitimate scope changes.

The 125 `David Servold → David Servold` self-edges are him modifying multi-name BIC composition (e.g. adding/removing a co-assignee). Not real handoffs.

---

## Recommended next moves

1. **Reframe internal performance reporting around submittal type.** "Drafting Release Review" is the unit of work; everything else is noise.
2. **Investigate Colton/Danny pairing** (5.24d avg vs 1–3d everywhere else) — is it project mix, communication cadence, or specific submittal complexity?
3. **Audit the 5 thrash projects** (Flats at Sand Creek, Alta Metro Center, Marshall Pointe, 4th St. North, Misc. MHMW) for spec/scope quality. The 15-handoff submittal on Alta Metro Center is a case study.
4. **Consider Dalton's queue depth** (83 open vs Colton's 64). If you want predictable turn time, balancing the queue may matter more than coaching speed.
5. **Look into "drafter → manager" bounces** (Dalton→Rich, Colton→Gary, etc.) — if these are info-request bounces, a structured intake checklist could eliminate one round trip on ~50+ submittals.
6. **Re-run this in 60–90 days** when the event history covers a fuller cohort of Open→Closed cycles. The current n=129 lifespan cohort is enough to spot patterns but not to set hard SLA targets.

---

*Raw data dumped to `analysis/{events,submittals,users}.pkl`. Per-segment, per-handoff, and per-lifespan CSVs in `analysis/*.csv`.*
