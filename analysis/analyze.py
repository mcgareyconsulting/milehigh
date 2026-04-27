"""Analyze SubmittalEvents for patterns: drafter cycle time, BIC handoffs, project lifespan."""
import pandas as pd
import numpy as np
from collections import Counter, defaultdict

events = pd.read_pickle("analysis/events.pkl").sort_values("created_at").reset_index(drop=True)
subs = pd.read_pickle("analysis/submittals.pkl")
users = pd.read_pickle("analysis/users.pkl")

# Lookup: submittal -> dict of metadata
sub_meta = subs.set_index(subs["submittal_id"].astype(str)).to_dict("index")

# Drafters of interest (per ball_in_court frequency)
DRAFTERS = {"Dalton Rauer", "Colton Arendt", "Rourke Alvarado"}
# Note: David Servold appears in BIC but is admin/QA, not a drafter
# Also include Servold for completeness on the QA leg
QA_REVIEWERS = {"David Servold", "Luis Solano"}
SUBMITTAL_MANAGERS = {"Rich Losasso", "Gary Almeida", "Danny Riddell"}

DATA_START = events["created_at"].min()
DATA_END = events["created_at"].max()


def parse_bic_set(bic):
    if not bic or pd.isna(bic):
        return frozenset()
    return frozenset(p.strip() for p in str(bic).split(",") if p.strip())


# ----- Build timeline per submittal -----
# For each submittal, walk events in order, capture (ts, bic, status) state
# Initial state from creation event payload (if present) or fall back to current submittals row

timelines = defaultdict(list)  # sid -> list of dicts (ts, bic, status, source, kind)

for _, row in events.iterrows():
    sid = str(row["submittal_id"])
    p = row["payload"] if isinstance(row["payload"], dict) else {}
    if row["action"] == "created":
        timelines[sid].append({
            "ts": row["created_at"],
            "bic": p.get("ball_in_court"),
            "status": p.get("status"),
            "source": row["source"],
            "kind": "created",
            "payload": p,
        })
    else:  # updated
        # Capture BIC and/or status transitions
        bic_change = p.get("ball_in_court") if isinstance(p.get("ball_in_court"), dict) else None
        status_change = p.get("status") if isinstance(p.get("status"), dict) else None
        if bic_change or status_change:
            timelines[sid].append({
                "ts": row["created_at"],
                "bic_old": bic_change.get("old") if bic_change else None,
                "bic_new": bic_change.get("new") if bic_change else None,
                "status_old": status_change.get("old") if status_change else None,
                "status_new": status_change.get("new") if status_change else None,
                "source": row["source"],
                "kind": "updated",
                "payload": p,
            })

# ----- BIC HANDOFFS PER SUBMITTAL -----
handoffs_per_sub = {}
for sid, tl in timelines.items():
    n = sum(1 for e in tl if e["kind"] == "updated" and e.get("bic_new") is not None)
    handoffs_per_sub[sid] = n

# ----- DRAFTER SEGMENTS -----
# A "drafter segment" = period where a known drafter's name appears in BIC.
# We start counting when bic_new contains the drafter; stop at next BIC change.
# Filter: only "solo" segments (drafter name alone) for cleanest measure;
# also report "any inclusion" as a secondary metric.

drafter_segments = []  # list of dicts: drafter, sid, start, end, duration_days, solo, project_name, sub_manager

for sid, tl in timelines.items():
    # Build a sequence of (ts, bic_set) transitions
    transitions = []
    for e in tl:
        if e["kind"] == "created" and e.get("bic"):
            transitions.append((e["ts"], parse_bic_set(e["bic"])))
        elif e["kind"] == "updated" and e.get("bic_new") is not None:
            transitions.append((e["ts"], parse_bic_set(e["bic_new"])))

    if not transitions:
        continue

    meta = sub_meta.get(sid, {})
    proj = meta.get("project_name")
    mgr = meta.get("submittal_manager")
    stype = meta.get("type")

    for i, (ts, bic_set) in enumerate(transitions):
        end_ts = transitions[i + 1][0] if i + 1 < len(transitions) else None
        # If terminal, only count if it ended (status closed in submittals)
        for drafter in DRAFTERS:
            if drafter in bic_set:
                # solo = drafter alone
                solo = (bic_set == {drafter})
                duration = None
                if end_ts:
                    duration = (end_ts - ts).total_seconds() / 86400.0
                drafter_segments.append({
                    "drafter": drafter,
                    "sid": sid,
                    "start": ts,
                    "end": end_ts,
                    "duration_days": duration,
                    "solo": solo,
                    "project_name": proj,
                    "sub_manager": mgr,
                    "type": stype,
                })

ds = pd.DataFrame(drafter_segments)
# Closed segments only (those with an end ts)
ds_closed = ds[ds["duration_days"].notna()].copy()
ds_solo_closed = ds_closed[ds_closed["solo"]].copy()


def fmt_days(x):
    if pd.isna(x):
        return "-"
    return f"{x:.2f}"


def stats(s):
    s = s.dropna()
    if len(s) == 0:
        return {"n": 0}
    return {
        "n": len(s),
        "mean": s.mean(),
        "median": s.median(),
        "p25": s.quantile(0.25),
        "p75": s.quantile(0.75),
        "min": s.min(),
        "max": s.max(),
    }


print("=" * 78)
print("DATA WINDOW")
print("=" * 78)
print(f"{DATA_START}  →  {DATA_END}  ({(DATA_END - DATA_START).days} days)")
print(f"events: {len(events)}   submittals: {len(subs)}   projects: {subs['project_name'].nunique()}")

# 1) Drafter cycle time (solo segments, closed)
print("\n" + "=" * 78)
print("1. DRAFTER 'TURN' DURATION (solo BIC, completed segments)")
print("=" * 78)
print("How long the submittal sat with this drafter alone before being handed off.\n")
print(f"{'Drafter':<22}{'n':>6}{'mean d':>10}{'median':>10}{'p25':>8}{'p75':>8}{'max':>8}")
for d in DRAFTERS:
    s = stats(ds_solo_closed[ds_solo_closed["drafter"] == d]["duration_days"])
    if s["n"] == 0:
        continue
    print(f"{d:<22}{s['n']:>6}{s['mean']:>10.2f}{s['median']:>10.2f}{s['p25']:>8.2f}{s['p75']:>8.2f}{s['max']:>8.2f}")

print("\n--- Including segments where drafter is one of multiple BICs ---")
for d in DRAFTERS:
    s = stats(ds_closed[ds_closed["drafter"] == d]["duration_days"])
    if s["n"] == 0:
        continue
    print(f"{d:<22}{s['n']:>6}{s['mean']:>10.2f}{s['median']:>10.2f}{s['p25']:>8.2f}{s['p75']:>8.2f}{s['max']:>8.2f}")

# 1b) Drafter turns by submittal type
print("\n--- Drafter solo turns by submittal type ---")
for stype, group in ds_solo_closed.groupby("type"):
    print(f"\nType: {stype}")
    print(f"{'Drafter':<22}{'n':>6}{'mean d':>10}{'median':>10}")
    for d in DRAFTERS:
        s = stats(group[group["drafter"] == d]["duration_days"])
        if s["n"] == 0:
            continue
        print(f"{d:<22}{s['n']:>6}{s['mean']:>10.2f}{s['median']:>10.2f}")

# 2) BIC handoffs per submittal
print("\n" + "=" * 78)
print("2. BIC HANDOFFS PER SUBMITTAL")
print("=" * 78)
hp = pd.Series(handoffs_per_sub, name="handoffs")
print(f"Submittals with ≥1 tracked event: {len(hp)}")
print(f"Mean handoffs: {hp.mean():.2f}   median: {hp.median()}   max: {hp.max()}")

# distribution
dist = hp.value_counts().sort_index()
print("\nDistribution:")
for k, v in dist.head(15).items():
    bar = "█" * int(v / max(dist) * 40)
    print(f"  {k:>3} handoffs: {v:>4}  {bar}")

# Per project
print("\n--- Avg handoffs per project (≥5 submittals) ---")
hp_df = hp.reset_index()
hp_df.columns = ["sid", "handoffs"]
hp_df["project"] = hp_df["sid"].map(lambda s: sub_meta.get(s, {}).get("project_name"))
hp_df["mgr"] = hp_df["sid"].map(lambda s: sub_meta.get(s, {}).get("submittal_manager"))
hp_df["type"] = hp_df["sid"].map(lambda s: sub_meta.get(s, {}).get("type"))
hp_df["status"] = hp_df["sid"].map(lambda s: sub_meta.get(s, {}).get("status"))

proj_h = hp_df.groupby("project")["handoffs"].agg(["count", "mean", "median", "max"]).sort_values("mean", ascending=False)
proj_h = proj_h[proj_h["count"] >= 5]
print(f"{'Project':<45}{'n':>5}{'mean':>8}{'med':>6}{'max':>6}")
for proj, row in proj_h.iterrows():
    name = (proj or "?")[:42]
    print(f"{name:<45}{int(row['count']):>5}{row['mean']:>8.2f}{int(row['median']):>6}{int(row['max']):>6}")

# Per submittal manager
print("\n--- Avg handoffs per submittal manager ---")
mgr_h = hp_df.groupby("mgr")["handoffs"].agg(["count", "mean", "median", "max"]).sort_values("mean", ascending=False)
print(f"{'Submittal Manager':<22}{'n':>5}{'mean':>8}{'med':>6}{'max':>6}")
for mgr, row in mgr_h.iterrows():
    print(f"{str(mgr):<22}{int(row['count']):>5}{row['mean']:>8.2f}{int(row['median']):>6}{int(row['max']):>6}")

# Per type
print("\n--- Avg handoffs per submittal type ---")
type_h = hp_df.groupby("type")["handoffs"].agg(["count", "mean", "median", "max"]).sort_values("mean", ascending=False)
print(f"{'Type':<32}{'n':>5}{'mean':>8}{'med':>6}{'max':>6}")
for t, row in type_h.iterrows():
    print(f"{str(t):<32}{int(row['count']):>5}{row['mean']:>8.2f}{int(row['median']):>6}{int(row['max']):>6}")

# 3) Open → Closed lifespan, only for submittals where we observed BOTH transitions in events
print("\n" + "=" * 78)
print("3. OPEN → CLOSED LIFESPAN (observed transitions only)")
print("=" * 78)

lifespans = []
for sid, tl in timelines.items():
    open_ts = None
    closed_ts = None
    # Created event with status=Open counts as open start
    for e in tl:
        if e["kind"] == "created" and e.get("status") == "Open":
            open_ts = e["ts"]
        elif e["kind"] == "updated":
            if e.get("status_new") == "Open" and open_ts is None:
                open_ts = e["ts"]
            if e.get("status_new") == "Closed":
                closed_ts = e["ts"]
    if open_ts and closed_ts and closed_ts >= open_ts:
        meta = sub_meta.get(sid, {})
        lifespans.append({
            "sid": sid,
            "days": (closed_ts - open_ts).total_seconds() / 86400.0,
            "project": meta.get("project_name"),
            "mgr": meta.get("submittal_manager"),
            "type": meta.get("type"),
        })

ls_df = pd.DataFrame(lifespans)
print(f"Submittals with full Open→Closed observed: {len(ls_df)}")
if len(ls_df):
    s = stats(ls_df["days"])
    print(f"global  n={s['n']}  mean={s['mean']:.2f}  median={s['median']:.2f}  "
          f"p25={s['p25']:.2f}  p75={s['p75']:.2f}  max={s['max']:.2f}")

    print("\n--- by project (≥3 closed) ---")
    pls = ls_df.groupby("project")["days"].agg(["count", "mean", "median", "max"]).sort_values("mean", ascending=False)
    pls = pls[pls["count"] >= 3]
    print(f"{'Project':<45}{'n':>5}{'mean':>8}{'med':>8}{'max':>8}")
    for proj, row in pls.iterrows():
        name = (proj or "?")[:42]
        print(f"{name:<45}{int(row['count']):>5}{row['mean']:>8.2f}{row['median']:>8.2f}{row['max']:>8.2f}")

    print("\n--- by submittal manager ---")
    mls = ls_df.groupby("mgr")["days"].agg(["count", "mean", "median", "max"]).sort_values("mean", ascending=False)
    print(f"{'Manager':<22}{'n':>5}{'mean':>8}{'med':>8}{'max':>8}")
    for mgr, row in mls.iterrows():
        print(f"{str(mgr):<22}{int(row['count']):>5}{row['mean']:>8.2f}{row['median']:>8.2f}{row['max']:>8.2f}")

    print("\n--- by type ---")
    tls = ls_df.groupby("type")["days"].agg(["count", "mean", "median", "max"]).sort_values("mean", ascending=False)
    print(f"{'Type':<32}{'n':>5}{'mean':>8}{'med':>8}{'max':>8}")
    for t, row in tls.iterrows():
        print(f"{str(t):<32}{int(row['count']):>5}{row['mean']:>8.2f}{row['median']:>8.2f}{row['max']:>8.2f}")

# 4) Handoff sequence patterns - what's the common BIC chain?
print("\n" + "=" * 78)
print("4. HANDOFF SEQUENCE PATTERNS")
print("=" * 78)

# Build (from -> to) pair counts (using primary name, i.e. first in list)
def primary(bic_set):
    if not bic_set:
        return None
    # Return the drafter or the lex-smallest? Use the single name that's a known drafter
    # else the first name alphabetically for stability
    drafters_in = bic_set & DRAFTERS
    if drafters_in:
        return min(drafters_in)
    qa_in = bic_set & QA_REVIEWERS
    if qa_in:
        return min(qa_in)
    mgr_in = bic_set & SUBMITTAL_MANAGERS
    if mgr_in:
        return min(mgr_in)
    return min(bic_set)

pair_counts = Counter()
for sid, tl in timelines.items():
    seq = []
    for e in tl:
        if e["kind"] == "created" and e.get("bic"):
            seq.append(parse_bic_set(e["bic"]))
        elif e["kind"] == "updated" and e.get("bic_new") is not None:
            seq.append(parse_bic_set(e["bic_new"]))
    for a, b in zip(seq, seq[1:]):
        pa, pb = primary(a), primary(b)
        if pa and pb:
            pair_counts[(pa, pb)] += 1

print("Top BIC handoff pairs (from → to):")
for (a, b), c in pair_counts.most_common(20):
    print(f"  {c:>4}  {a}  →  {b}")

# 5) Drafters by sub manager: are some pairings slower?
print("\n" + "=" * 78)
print("5. DRAFTER × SUBMITTAL MANAGER (mean solo turn duration, days)")
print("=" * 78)
piv = ds_solo_closed.groupby(["drafter", "sub_manager"])["duration_days"].agg(["count", "mean"]).reset_index()
print(f"{'Drafter':<20}{'Sub Mgr':<20}{'n':>5}{'mean':>8}")
for _, row in piv.sort_values(["drafter", "mean"], ascending=[True, False]).iterrows():
    if row["count"] < 3:
        continue
    print(f"{row['drafter']:<20}{str(row['sub_manager'])[:19]:<20}{int(row['count']):>5}{row['mean']:>8.2f}")

# 6) Volume by drafter (load)
print("\n" + "=" * 78)
print("6. VOLUME / LOAD")
print("=" * 78)
print("Solo turns picked up per drafter (during data window):")
for d in DRAFTERS:
    n_total = (ds["drafter"] == d).sum()
    n_solo = (ds_solo_closed["drafter"] == d).sum() + ((ds_solo_closed["drafter"] != d) & 0).sum()
    n_solo_completed = ds_solo_closed[ds_solo_closed["drafter"] == d].shape[0]
    n_solo_total = ds[(ds["drafter"] == d) & (ds["solo"])].shape[0]
    print(f"  {d:<22}  total appearances={n_total:>4}  solo turns={n_solo_total:>4}  solo completed={n_solo_completed:>4}")

# Currently in BIC (snapshot)
print("\nCurrent open BIC counts (snapshot from submittals.ball_in_court):")
open_subs = subs[subs["status"].isin(["Open", "Submitted To Client", "Draft"])]
bic_now = Counter()
for v in open_subs["ball_in_court"].dropna():
    for n in str(v).split(","):
        bic_now[n.strip()] += 1
for d in list(DRAFTERS) + list(QA_REVIEWERS) + list(SUBMITTAL_MANAGERS):
    print(f"  {d:<22}: {bic_now.get(d, 0)}")

# Save lifespan and handoffs to CSV for the report
ls_df.to_csv("analysis/lifespans.csv", index=False)
hp_df.to_csv("analysis/handoffs.csv", index=False)
ds.to_csv("analysis/drafter_segments.csv", index=False)
print("\nSaved analysis/{lifespans,handoffs,drafter_segments}.csv")
