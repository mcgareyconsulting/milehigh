"""Deep analysis on the job-log / release / shop-flow side.

Mirrors the submittal deep analysis but adapted to:
  - Stage transitions (instead of BIC handoffs)
  - Per-release drafter (`by`) and PM (`pm`) — fixed assignments
  - Released → Complete lifespan (instead of Open → Closed)
  - Stage dwell (per kanban stage)

Data sources (5 months):
  - releases (snapshot)
  - release_events (44 days, modern audit)
  - sync_logs list_move events linked via trello_card_id (5 months)
  - job_change_logs (5 months, but noisy — Excel oscillations)
"""
import pandas as pd
import numpy as np
from collections import Counter, defaultdict
from datetime import timedelta

releases = pd.read_pickle("analysis/releases.pkl")
revents = pd.read_pickle("analysis/release_events.pkl")
list_moves = pd.read_pickle("analysis/list_moves.pkl")
jcl = pd.read_pickle("analysis/job_change_logs.pkl")

# Drafter / PM code map
DRAFTER_CODE = {
    "DCR": "Dalton Rauer",
    "CBA": "Colton Arendt",
    "RJA": "Rourke Alvarado",
    "DEP": "Dustin Pauley",
    "DTS": "David Servold",
    "RL":  "Rich Losasso (drafter? legacy)",
    "GA":  "Gary Almeida (drafter? legacy)",
    "DR":  "DR (ambiguous: Dalton or Danny)",
    "FMW": "FMW (?)",
    "WDO": "Bill O'Neill (?)",
    "WO":  "Bill O'Neill (?)",
    "SDO": "SDO (?)",
}
PM_CODE = {
    "RL": "Rich Losasso",
    "GA": "Gary Almeida",
    "DR": "Danny Riddell",
    "WO": "Bill O'Neill",
    "WDO": "Bill O'Neill",
}

DRAFTERS = {"DCR", "CBA", "RJA"}  # primary drafters

# Build unified stage transition stream
# Source 1: list_moves (Trello-side) — needs release lookup via card_id
card_to_jr = {}
for _, r in releases.iterrows():
    if pd.notna(r["trello_card_id"]):
        card_to_jr[r["trello_card_id"]] = (r["job"], r["release"])

list_moves["from"] = list_moves["data"].apply(lambda d: d.get("from_list") if isinstance(d, dict) else None)
list_moves["to"] = list_moves["data"].apply(lambda d: d.get("to_list") if isinstance(d, dict) else None)
list_moves["jr"] = list_moves["card_id"].map(card_to_jr)

# Source 2: release_events update_stage
stage_re = revents[revents["action"] == "update_stage"].copy()
stage_re["from"] = stage_re["payload"].apply(lambda p: p.get("from") if isinstance(p, dict) else None)
stage_re["to"] = stage_re["payload"].apply(lambda p: p.get("to") if isinstance(p, dict) else None)

# Build unified
unified = []
for _, r in list_moves.iterrows():
    jr = r["jr"]
    if not jr or pd.isna(r["from"]) or pd.isna(r["to"]):
        continue
    unified.append({
        "ts": r["ts"], "job": jr[0], "release": jr[1],
        "from": r["from"], "to": r["to"],
        "kind": "stage", "source": "Trello", "origin": "sync_log",
    })

for _, r in stage_re.iterrows():
    unified.append({
        "ts": r["created_at"], "job": int(r["job"]), "release": str(r["release"]),
        "from": r["from"], "to": r["to"],
        "kind": "stage",
        "source": r["source"].split(":")[0] if r["source"] else "Brain",
        "origin": "release_event",
    })

uni = pd.DataFrame(unified)
uni = uni[uni["from"].notna() & uni["to"].notna() & (uni["from"] != uni["to"])]
uni["ts_round"] = uni["ts"].dt.floor("min")
uni = uni.sort_values(["ts", "origin"]).drop_duplicates(
    subset=["job", "release", "from", "to", "ts_round"], keep="first"
).reset_index(drop=True)
print(f"unified stage transitions: {len(uni)}  ({uni['ts'].min()} -> {uni['ts'].max()})")

# Normalize stage names (some have trailing periods etc.)
NORMALIZE = {
    "Fit Up Complete.": "Fit Up Complete",
    "Fit Up Complete": "Fit Up Complete",
    "Fitup Complete": "Fit Up Complete",
    "Cut Complete": "Cut Complete",
    "Cut start": "Cut Start",
    "Paint complete": "Paint Complete",
    "Paint Start": "Paint Start",
    "Welded QC": "Welded QC",
    "Welded": "Welded",
    "Weld Complete": "Welded",
    "Released": "Released",
    "Material Ordered": "Material Ordered",
    "Hold": "Hold",
    "Store at MHMW for shipping": "Store at MHMW",
    "Shipping planning": "Shipping Planning",
    "Shipping completed": "Shipping Completed",
    "Complete": "Complete",
    "Created": "Created",
    "Shipped": "Shipped",
    "Fitup Start": "Fitup Start",
}
def norm(s):
    if not s or pd.isna(s):
        return None
    return NORMALIZE.get(str(s).strip(), str(s).strip())

uni["from_n"] = uni["from"].apply(norm)
uni["to_n"] = uni["to"].apply(norm)

# Forward stage order
STAGE_ORDER = [
    "Material Ordered", "Released", "Cut Start", "Cut Complete",
    "Fitup Start", "Fit Up Complete", "Welded", "Welded QC",
    "Paint Start", "Paint Complete", "Store at MHMW",
    "Shipping Planning", "Shipping Completed", "Complete",
]
STAGE_IDX = {s: i for i, s in enumerate(STAGE_ORDER)}

def is_backward(a, b):
    ia, ib = STAGE_IDX.get(a), STAGE_IDX.get(b)
    if ia is None or ib is None:
        return None
    return ib < ia


# Per-release timeline
streams = {}
for (j, rel), g in uni.groupby(["job", "release"]):
    streams[(j, int(str(rel).strip())) if str(rel).strip().isdigit() else (j, rel)] = g.sort_values("ts").reset_index(drop=True)
# Recompute streams without the awkward int conversion
streams = {jr: g.sort_values("ts").reset_index(drop=True) for jr, g in uni.groupby(["job", "release"])}


def stats(s):
    s = pd.Series(s).dropna()
    if len(s) == 0:
        return {"n": 0}
    return {
        "n": len(s), "mean": s.mean(), "median": s.median(),
        "p25": s.quantile(0.25), "p75": s.quantile(0.75), "max": s.max(),
    }


# ===================================================================
print("=" * 78)
print("COHORT SUMMARY")
print("=" * 78)
print(f"releases: {len(releases)}  active: {(releases['is_active']==True).sum()}  archived: {releases['is_archived'].sum()}")
rel_dt = pd.to_datetime(releases["released"], errors="coerce")
print(f"release dates: {rel_dt.min()} -> {rel_dt.max()}")
print(f"stage_group: {dict(releases['stage_group'].value_counts())}")
print(f"unique projects (parsed from job_name): see section L")
print(f"unique drafters in `by`: {releases['by'].nunique()}")
print(f"unique PMs in `pm`: {releases['pm'].nunique()}")
print(f"\nunified stage events: {len(uni)}  unique releases with events: {len(streams)}")

# ===================================================================
print("\n" + "=" * 78)
print("A. PER-DRAFTER (`by`) THROUGHPUT AND CURRENT LOAD")
print("=" * 78)
by_drafter = releases.groupby("by", dropna=False).agg(
    total=("id", "count"),
    completed=("stage_group", lambda s: (s == "COMPLETE").sum()),
    in_fab=("stage_group", lambda s: (s == "FABRICATION").sum()),
    ready_to_ship=("stage_group", lambda s: (s == "READY_TO_SHIP").sum()),
    avg_fab_hrs=("fab_hrs", "mean"),
    sum_fab_hrs=("fab_hrs", "sum"),
).sort_values("total", ascending=False)
print(f"{'code':<5}{'name':<32}{'total':>7}{'compl':>7}{'fab':>5}{'ship':>5}{'avg fab h':>12}{'tot fab h':>12}")
for code, row in by_drafter.iterrows():
    name = DRAFTER_CODE.get(str(code), str(code))[:30]
    afh = f"{row['avg_fab_hrs']:.1f}" if pd.notna(row['avg_fab_hrs']) else "-"
    sfh = f"{row['sum_fab_hrs']:.0f}" if pd.notna(row['sum_fab_hrs']) else "-"
    print(f"{str(code):<5}{name:<32}{int(row['total']):>7}{int(row['completed']):>7}{int(row['in_fab']):>5}{int(row['ready_to_ship']):>5}{afh:>12}{sfh:>12}")

# ===================================================================
print("\n" + "=" * 78)
print("B. PER-PM THROUGHPUT AND LOAD")
print("=" * 78)
by_pm = releases.groupby("pm", dropna=False).agg(
    total=("id", "count"),
    completed=("stage_group", lambda s: (s == "COMPLETE").sum()),
    in_fab=("stage_group", lambda s: (s == "FABRICATION").sum()),
    ready_to_ship=("stage_group", lambda s: (s == "READY_TO_SHIP").sum()),
    sum_fab_hrs=("fab_hrs", "sum"),
).sort_values("total", ascending=False)
print(f"{'code':<5}{'name':<22}{'total':>7}{'compl':>7}{'fab':>5}{'ship':>5}{'tot fab h':>12}")
for code, row in by_pm.iterrows():
    name = PM_CODE.get(str(code), str(code))[:20]
    sfh = f"{row['sum_fab_hrs']:.0f}" if pd.notna(row['sum_fab_hrs']) else "-"
    print(f"{str(code):<5}{name:<22}{int(row['total']):>7}{int(row['completed']):>7}{int(row['in_fab']):>5}{int(row['ready_to_ship']):>5}{sfh:>12}")

# ===================================================================
print("\n" + "=" * 78)
print("C. PM × DRAFTER ROUTING MATRIX (releases assigned)")
print("=" * 78)
ct = pd.crosstab(releases["pm"], releases["by"]).fillna(0).astype(int)
# Print top PMs and drafters
print("                  " + "  ".join(f"{d:>6}" for d in ["DCR", "CBA", "RJA", "DEP", "DTS", "DR", "RL", "GA", "other"]))
for pm_code in ["RL", "GA", "DR", "WO", "WDO"]:
    if pm_code not in ct.index:
        continue
    row_vals = []
    for d in ["DCR", "CBA", "RJA", "DEP", "DTS", "DR", "RL", "GA"]:
        row_vals.append(int(ct.loc[pm_code].get(d, 0)) if d in ct.columns else 0)
    other = int(ct.loc[pm_code].sum() - sum(row_vals))
    pm_name = PM_CODE.get(pm_code, pm_code)
    print(f"  {pm_name:<16} " + "  ".join(f"{v:>6}" for v in row_vals + [other]))

# Percent breakdowns for top 3 PMs
print("\n  Distribution of assignments for top PMs:")
for pm_code in ["RL", "GA", "DR"]:
    if pm_code not in ct.index:
        continue
    row = ct.loc[pm_code]
    total = row.sum()
    print(f"\n  {PM_CODE[pm_code]} (n={total}):")
    for d_code, n in row.sort_values(ascending=False).items():
        if n == 0:
            continue
        pct = 100 * n / total
        print(f"    {d_code:<5} {DRAFTER_CODE.get(d_code, d_code):<30} {n:>4}  ({pct:.0f}%)")

# ===================================================================
print("\n" + "=" * 78)
print("D. RELEASED → COMPLETE LIFESPAN (cycle time per release)")
print("=" * 78)
# For each release: Released date -> first 'Complete' stage transition
complete_ts = {}
for jr, g in streams.items():
    completes = g[g["to_n"] == "Complete"]
    if not completes.empty:
        complete_ts[jr] = completes.iloc[0]["ts"]

# Build lifespan rows
ls_rows = []
today = pd.Timestamp.now()
for _, r in releases.iterrows():
    jr = (r["job"], r["release"])
    rel_date = pd.to_datetime(r["released"], errors="coerce")
    if pd.isna(rel_date) or rel_date > today:
        continue
    ct_ts = complete_ts.get(jr)
    if ct_ts is not None:
        days = (ct_ts - rel_date).total_seconds() / 86400.0
        if 0 <= days <= 365:  # filter implausible
            ls_rows.append({
                "job": r["job"], "release": r["release"], "days": days,
                "drafter": r["by"], "pm": r["pm"], "fab_hrs": r["fab_hrs"],
                "stage_group": r["stage_group"], "job_name": r["job_name"],
            })

ls = pd.DataFrame(ls_rows)
print(f"observed Released→Complete cohort: {len(ls)}")
if len(ls):
    s = stats(ls["days"])
    print(f"global  n={s['n']}  mean={s['mean']:.1f}d  median={s['median']:.1f}d  "
          f"p25={s['p25']:.1f}  p75={s['p75']:.1f}  max={s['max']:.1f}")

    print("\n  -- by drafter (Released→Complete days) --")
    print(f"  {'code':<5}{'name':<28}{'n':>5}{'mean':>8}{'median':>8}{'p75':>8}{'max':>8}")
    for code, g in ls.groupby("drafter"):
        s = stats(g["days"])
        if s["n"] < 3:
            continue
        nm = DRAFTER_CODE.get(str(code), str(code))[:26]
        print(f"  {str(code):<5}{nm:<28}{s['n']:>5}{s['mean']:>8.1f}{s['median']:>8.1f}{s['p75']:>8.1f}{s['max']:>8.1f}")

    print("\n  -- by PM (Released→Complete days) --")
    print(f"  {'code':<5}{'name':<22}{'n':>5}{'mean':>8}{'median':>8}{'p75':>8}")
    for code, g in ls.groupby("pm"):
        s = stats(g["days"])
        if s["n"] < 3:
            continue
        nm = PM_CODE.get(str(code), str(code))[:20]
        print(f"  {str(code):<5}{nm:<22}{s['n']:>5}{s['mean']:>8.1f}{s['median']:>8.1f}{s['p75']:>8.1f}")

# ===================================================================
print("\n" + "=" * 78)
print("E. STAGE DWELL TIMES (forward path)")
print("=" * 78)
# For each release, walk transitions in order; for each (from→to with from in pipeline),
# record dwell time = duration spent in the FROM stage prior to the move.
dwell_per_stage = defaultdict(list)
for jr, g in streams.items():
    rows = g.reset_index(drop=True)
    # Bootstrap: time before first transition is unknown, so skip first stage
    for i in range(len(rows)):
        if i == 0:
            continue
        prev = rows.iloc[i - 1]
        cur = rows.iloc[i]
        # The dwell of "from" stage = time between when entered (prev.ts when prev.to == cur.from) and now (cur.ts)
        if prev["to_n"] == cur["from_n"]:
            d = (cur["ts"] - prev["ts"]).total_seconds() / 86400.0
            dwell_per_stage[cur["from_n"]].append(d)

print(f"  {'stage':<22}{'n':>5}{'mean d':>10}{'median':>10}{'p75':>10}")
for stage in STAGE_ORDER:
    vals = dwell_per_stage.get(stage)
    if not vals:
        continue
    s = stats(vals)
    print(f"  {stage:<22}{s['n']:>5}{s['mean']:>10.2f}{s['median']:>10.2f}{s['p75']:>10.2f}")

# ===================================================================
print("\n" + "=" * 78)
print("F. STAGE REGRESSIONS (backward moves)")
print("=" * 78)
backward = uni[uni.apply(lambda r: is_backward(r["from_n"], r["to_n"]) is True, axis=1)]
print(f"backward stage moves: {len(backward)} / {len(uni)} ({100*len(backward)/len(uni):.1f}%)")
print("\ntop backward transitions:")
print(backward.groupby(["from_n", "to_n"]).size().sort_values(ascending=False).head(15))

# Releases with regressions
reg_releases = backward.groupby(["job", "release"]).size().sort_values(ascending=False)
print(f"\nreleases with at least one backward move: {len(reg_releases)} / {len(streams)}")
print(f"top regression-heavy releases:")
for jr, n in reg_releases.head(10).items():
    j, rel = jr
    rel_row = releases[(releases["job"] == j) & (releases["release"] == rel)]
    nm = rel_row["job_name"].iloc[0] if not rel_row.empty else "?"
    print(f"  {j}-{rel:<6} regressions={n:>3}  '{nm[:50]}'")

# ===================================================================
print("\n" + "=" * 78)
print("G. STALE-NOW REPORT (currently in pre-Complete stage)")
print("=" * 78)
NOW = uni["ts"].max()
print(f"as of {NOW}\n")
in_progress = releases[(releases["stage_group"].isin(["FABRICATION", "READY_TO_SHIP"])) & releases["is_active"]].copy()
last_move_per_release = uni.groupby(["job", "release"])["ts"].max()

stale_rows = []
for _, r in in_progress.iterrows():
    jr = (r["job"], r["release"])
    last_ts = last_move_per_release.get(jr)
    if last_ts is None:
        continue
    days = (NOW - last_ts).total_seconds() / 86400.0
    stale_rows.append({
        "job": r["job"], "release": r["release"], "stage": r["stage"],
        "drafter": r["by"], "pm": r["pm"],
        "job_name": r["job_name"], "days_stale": days,
        "fab_hrs": r["fab_hrs"], "fab_order": r["fab_order"],
    })
stale_df = pd.DataFrame(stale_rows).sort_values("days_stale", ascending=False)

for thresh in [7, 14, 30, 60, 90]:
    n = (stale_df["days_stale"] > thresh).sum()
    print(f"  in-progress with no stage move in >{thresh}d: {n}")

print(f"\n  -- top 15 stalest in-progress releases --")
print(f"  {'days':>6}  {'stage':<22}  {'drafter':<5}  {'pm':<4}  job-rel  job_name")
for _, r in stale_df.head(15).iterrows():
    print(f"  {r['days_stale']:>6.1f}  {str(r['stage'])[:21]:<22}  {str(r['drafter']):<5}  {str(r['pm']):<4}  "
          f"{int(r['job'])}-{r['release']:<5}  {str(r['job_name'])[:50]}")

print(f"\n  -- stalest by stage --")
for stage, g in stale_df[stale_df["days_stale"] > 30].groupby("stage"):
    print(f"    {stage:<25} count={len(g):>3}  median={g['days_stale'].median():.1f}d  max={g['days_stale'].max():.1f}d")

# ===================================================================
print("\n" + "=" * 78)
print("H. THROUGHPUT TREND (release-completion events per week, 5-month view)")
print("=" * 78)
# Combine: 'Complete' transitions from unified stream + 'Shipped' first-reach from job_change_logs
ct_rows = []
for jr, ts in complete_ts.items():
    ct_rows.append({"jr": jr, "ts": ts, "src": "uni:Complete"})

# job_change_logs: first 'Shipped' per (job, release) — older era equivalent
shipped = jcl[jcl["to_value"] == "Shipped"].copy()
first_shipped = shipped.groupby(["job", "release"])["changed_at"].min()
for (j, rel), ts in first_shipped.items():
    jr = (j, rel)
    if jr in complete_ts:
        continue  # already counted via unified stream
    ct_rows.append({"jr": jr, "ts": ts, "src": "jcl:Shipped"})

ct_df = pd.DataFrame(ct_rows)
print(f"completion events combined: {len(ct_df)} (uni:Complete={len(complete_ts)}, jcl:Shipped added={len(ct_df)-len(complete_ts)})")
ct_df["week"] = ct_df["ts"].dt.to_period("W")
weekly = ct_df.groupby("week").size()
mx = weekly.max() if len(weekly) else 1
print(f"  {'week':<23}  {'n':>3}")
for wk, n in weekly.items():
    bar = "█" * int(n / mx * 40)
    print(f"  {str(wk):<23}  {int(n):>3}  {bar}")

# ===================================================================
print("\n" + "=" * 78)
print("I. WHEN DO STAGE MOVES HAPPEN? (day of week / hour, MT approx)")
print("=" * 78)
uni_dow = uni.copy()
uni_dow["mt"] = uni_dow["ts"] - timedelta(hours=6)
uni_dow["dow"] = uni_dow["mt"].dt.day_name()
uni_dow["hour"] = uni_dow["mt"].dt.hour
print("by day of week:")
dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
counts = uni_dow["dow"].value_counts().reindex(dow_order).fillna(0)
mx = counts.max() or 1
for d, c in counts.items():
    bar = "█" * int(c / mx * 40) if c else ""
    print(f"  {d:<10} {int(c):>4}  {bar}")

print("\nby hour:")
hr = uni_dow["hour"].value_counts().sort_index()
mx = hr.max()
for h, c in hr.items():
    bar = "█" * int(c / mx * 40)
    print(f"  {h:>2}:00 {int(c):>4}  {bar}")

print("\nby source:")
print(uni["source"].value_counts())

# ===================================================================
print("\n" + "=" * 78)
print("J. FAB ORDER CHURN (priority changes per release)")
print("=" * 78)
fab_evts = revents[revents["action"] == "update_fab_order"].copy()
fab_per_release = fab_evts.groupby(["job", "release"]).size().sort_values(ascending=False)
print(f"total fab_order changes (44d): {len(fab_evts)}")
print(f"unique releases re-prioritized: {len(fab_per_release)}")
print(f"mean changes per release (where any): {fab_per_release.mean():.1f}")
print(f"median: {fab_per_release.median()}")
print(f"max:    {fab_per_release.max()}")
print(f"\n  top churned releases:")
for (j, rel), n in fab_per_release.head(10).items():
    rel_row = releases[(releases["job"] == j) & (releases["release"] == rel)]
    nm = rel_row["job_name"].iloc[0] if not rel_row.empty else "?"
    print(f"  {j}-{rel:<6} {n:>3} changes  '{nm[:50]}'")

# Reasons for fab_order changes
print("\nfab_order change reasons:")
fab_evts["reason"] = fab_evts["payload"].apply(lambda p: p.get("reason") if isinstance(p, dict) else None)
print(fab_evts["reason"].value_counts())

# ===================================================================
print("\n" + "=" * 78)
print("K. PROJECT-LEVEL PATTERNS")
print("=" * 78)
# Parse project from job_name (everything before " -" or first dash region)
def project_of(name):
    if not name or pd.isna(name):
        return None
    # Many job_names look like "Garrett -Banyan High Point" — strip leading person+dash
    s = str(name)
    if " -" in s:
        s = s.split(" -", 1)[1].strip()
    return s

releases["project"] = releases["job_name"].apply(project_of)
ls_with_proj = ls.copy()
ls_with_proj["project"] = ls_with_proj["job_name"].apply(project_of)

print("Top projects by release count:")
proj_counts = releases["project"].value_counts().head(15)
for p, n in proj_counts.items():
    print(f"  {n:>4}  {p}")

print("\nLifespan by project (≥3 completed):")
proj_ls = ls_with_proj.groupby("project")["days"].agg(["count", "mean", "median", "max"]).sort_values("mean", ascending=False)
proj_ls = proj_ls[proj_ls["count"] >= 3]
print(f"  {'Project':<35}{'n':>5}{'mean':>8}{'median':>9}{'max':>8}")
for p, row in proj_ls.iterrows():
    nm = str(p)[:33]
    print(f"  {nm:<35}{int(row['count']):>5}{row['mean']:>8.1f}{row['median']:>9.1f}{row['max']:>8.1f}")

# ===================================================================
print("\n" + "=" * 78)
print("L. DRAFTER × PM DEEP CYCLE TIME (Released→Complete, by pair)")
print("=" * 78)
if len(ls):
    pair = ls.groupby(["drafter", "pm"])["days"].agg(["count", "mean", "median"]).reset_index()
    pair = pair[pair["count"] >= 3].sort_values("mean", ascending=False)
    print(f"  {'drafter':<8}{'pm':<6}{'n':>5}{'mean':>8}{'median':>9}")
    for _, r in pair.iterrows():
        d_label = f"{r['drafter']}"
        pm_label = f"{r['pm']}"
        print(f"  {d_label:<8}{pm_label:<6}{int(r['count']):>5}{r['mean']:>8.1f}{r['median']:>9.1f}")

# Save
ls.to_csv("analysis/releases_lifespan.csv", index=False)
stale_df.to_csv("analysis/releases_stale.csv", index=False)
uni.to_pickle("analysis/release_stage_events.pkl")
print("\nsaved analysis/{releases_lifespan,releases_stale}.csv + release_stage_events.pkl")
