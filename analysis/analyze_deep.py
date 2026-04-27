"""Deep analysis on expanded dataset (sync_logs + submittal_events merged).

Covers:
  A. Baseline metrics on expanded 5-month dataset
  B. First-touch latency (queue dwell)
  C. Re-opens / rework loops
  D. Stale-now report
  E. Day-of-week / time-of-day activity
  F. Manager -> drafter routing
  G. Throughput trend over 5 months
  H. HOLD / NEED VIF / STARTED dwell
  I. Late-stage scope changes (title / manager mid-flight)
  J. Bimodality of drafter distributions
  K. Multi-assignee analysis
"""
import pandas as pd
import numpy as np
from collections import Counter, defaultdict
from datetime import timedelta

events = pd.read_pickle("analysis/events.pkl").sort_values("created_at").reset_index(drop=True)
sync_log = pd.read_pickle("analysis/sync_log_events.pkl").sort_values("ts").reset_index(drop=True)
sync_creates = pd.read_pickle("analysis/sync_log_creates.pkl").sort_values("created_ts").reset_index(drop=True)
subs = pd.read_pickle("analysis/submittals.pkl")
users = pd.read_pickle("analysis/users.pkl")

DRAFTERS = {"Dalton Rauer", "Colton Arendt", "Rourke Alvarado"}
QA_REVIEWERS = {"David Servold", "Luis Solano"}
SUBMITTAL_MANAGERS = {"Rich Losasso", "Gary Almeida", "Danny Riddell"}

sub_meta = subs.set_index(subs["submittal_id"].astype(str)).to_dict("index")


def parse_bic_set(bic):
    if not bic or pd.isna(bic):
        return frozenset()
    return frozenset(p.strip() for p in str(bic).split(",") if p.strip())


# ---------- BUILD UNIFIED EVENT STREAM ----------
# For each submittal, an ordered list of unified events. Source: 'sync_log' or 'submittal_event'.
# We keep the union of:
#   - sync_logs (Procore webhook changes — 5 months)
#   - submittal_events (Procore + Brain — 6 weeks; provides Brain-side status changes
#     and ALSO duplicates the Procore webhooks for last 6 weeks)
# Dedupe: a (submittal_id, change_type, ts_rounded, old, new) tuple.

unified = []  # list of dicts

# From sync_logs
for _, r in sync_log.iterrows():
    sid = str(r["submittal_id"])
    op = r["op_type"]
    if op == "procore_ball_in_court":
        unified.append({
            "ts": r["ts"], "sid": sid, "kind": "bic",
            "old": r["old_value"], "new": r["new_value"],
            "source": "Procore", "origin": "sync_log",
        })
    elif op == "procore_submittal_status":
        unified.append({
            "ts": r["ts"], "sid": sid, "kind": "status",
            "old": r["old_value"], "new": r["new_value"],
            "source": "Procore", "origin": "sync_log",
        })
    elif op == "procore_submittal_title":
        unified.append({
            "ts": r["ts"], "sid": sid, "kind": "title",
            "old": r["old_value"], "new": r["new_value"],
            "source": "Procore", "origin": "sync_log",
        })
    elif op == "procore_submittal_manager":
        unified.append({
            "ts": r["ts"], "sid": sid, "kind": "manager",
            "old": r["old_value"], "new": r["new_value"],
            "source": "Procore", "origin": "sync_log",
        })

# From submittal_events
for _, r in events.iterrows():
    sid = str(r["submittal_id"])
    p = r["payload"] if isinstance(r["payload"], dict) else {}
    if r["action"] == "created":
        unified.append({
            "ts": r["created_at"], "sid": sid, "kind": "created",
            "old": None, "new": p.get("status"),
            "bic_at_create": p.get("ball_in_court"),
            "source": r["source"], "origin": "submittal_event",
        })
    else:
        for key in ("ball_in_court", "status", "title", "submittal_manager", "submittal_drafting_status",
                    "due_date", "notes"):
            v = p.get(key)
            if isinstance(v, dict) and ("old" in v or "new" in v):
                kind = {"ball_in_court": "bic", "status": "status", "title": "title",
                        "submittal_manager": "manager", "submittal_drafting_status": "draft_status",
                        "due_date": "due_date", "notes": "notes"}[key]
                unified.append({
                    "ts": r["created_at"], "sid": sid, "kind": kind,
                    "old": v.get("old"), "new": v.get("new"),
                    "source": r["source"], "origin": "submittal_event",
                })

uni = pd.DataFrame(unified)
print(f"unified events before dedup: {len(uni)}")

# Dedupe: round ts to second + same (sid, kind, old, new) is duplicate
uni["ts_round"] = uni["ts"].dt.floor("S")
dedup_keys = ["sid", "kind", "old", "new", "ts_round"]
uni_d = uni.sort_values(["ts", "origin"]).drop_duplicates(subset=dedup_keys, keep="first").reset_index(drop=True)
print(f"unified events after dedup:  {len(uni_d)}")
print(f"date range: {uni_d['ts'].min()} -> {uni_d['ts'].max()}")
print(f"unique submittals with events: {uni_d['sid'].nunique()}")

# Per-submittal sub-streams
streams = {sid: g.sort_values("ts").reset_index(drop=True) for sid, g in uni_d.groupby("sid")}

# Submittal create timestamps (from sync_creates and submittal_events.created)
create_ts = {}
for _, r in sync_creates.iterrows():
    create_ts[str(r["submittal_id"])] = r["created_ts"]
for _, r in events[events["action"] == "created"].iterrows():
    sid = str(r["submittal_id"])
    if sid not in create_ts or r["created_at"] < create_ts[sid]:
        create_ts[sid] = r["created_at"]

print(f"submittals with known create timestamp: {len(create_ts)}")


# ---------- SECTION A: re-run baseline metrics on expanded set ----------
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
        "max": s.max(),
    }


# Build drafter solo segments using BIC events
drafter_segments = []
for sid, st in streams.items():
    bic_rows = st[st["kind"] == "bic"]
    if len(bic_rows) == 0:
        continue
    transitions = []
    # Bootstrap: if first event is BIC change with old=X, then X was BIC at start (ts unknown)
    if not bic_rows.empty:
        first_old = bic_rows.iloc[0]["old"]
        if first_old:
            # Use create_ts if available
            ct = create_ts.get(sid)
            if ct:
                transitions.append((ct, parse_bic_set(first_old)))
        for _, r in bic_rows.iterrows():
            transitions.append((r["ts"], parse_bic_set(r["new"])))

    meta = sub_meta.get(sid, {})
    proj = meta.get("project_name")
    mgr = meta.get("submittal_manager")
    stype = meta.get("type")

    for i, (ts, bic_set) in enumerate(transitions):
        end_ts = transitions[i + 1][0] if i + 1 < len(transitions) else None
        for drafter in DRAFTERS:
            if drafter in bic_set:
                solo = (bic_set == {drafter})
                duration = (end_ts - ts).total_seconds() / 86400.0 if end_ts else None
                drafter_segments.append({
                    "drafter": drafter, "sid": sid, "start": ts, "end": end_ts,
                    "duration_days": duration, "solo": solo,
                    "project": proj, "mgr": mgr, "type": stype,
                })

ds = pd.DataFrame(drafter_segments)
ds_solo_closed = ds[ds["solo"] & ds["duration_days"].notna()]

print("\n" + "=" * 78)
print("A. EXPANDED COHORT — DRAFTER SOLO TURN DURATION (5 months)")
print("=" * 78)
print(f"{'Drafter':<22}{'n':>6}{'mean':>10}{'median':>10}{'p25':>8}{'p75':>8}{'max':>8}")
for d in DRAFTERS:
    s = stats(ds_solo_closed[ds_solo_closed["drafter"] == d]["duration_days"])
    if s["n"] == 0:
        continue
    print(f"{d:<22}{s['n']:>6}{s['mean']:>10.2f}{s['median']:>10.2f}{s['p25']:>8.2f}{s['p75']:>8.2f}{s['max']:>8.2f}")

# By type
print("\n  -- by submittal type (Drafting Release Review only, the unit of work) --")
drr = ds_solo_closed[ds_solo_closed["type"] == "Drafting Release Review"]
for d in DRAFTERS:
    s = stats(drr[drr["drafter"] == d]["duration_days"])
    if s["n"] == 0:
        continue
    print(f"{d:<22}{s['n']:>6}{s['mean']:>10.2f}{s['median']:>10.2f}{s['p25']:>8.2f}{s['p75']:>8.2f}{s['max']:>8.2f}")

# Open->Closed lifespan on expanded data
print("\n" + "=" * 78)
print("A2. OPEN → CLOSED LIFESPAN (expanded, observed transitions only)")
print("=" * 78)
lifespans = []
for sid, st in streams.items():
    open_ts = create_ts.get(sid)  # can use create as Open start if present
    closed_ts = None
    for _, r in st.iterrows():
        if r["kind"] == "status":
            if r["new"] == "Open" and open_ts is None:
                open_ts = r["ts"]
            if r["new"] == "Closed":
                closed_ts = r["ts"]
        elif r["kind"] == "created":
            if r["new"] == "Open" and open_ts is None:
                open_ts = r["ts"]
    if open_ts and closed_ts and closed_ts >= open_ts:
        meta = sub_meta.get(sid, {})
        lifespans.append({
            "sid": sid,
            "days": (closed_ts - open_ts).total_seconds() / 86400.0,
            "project": meta.get("project_name"),
            "mgr": meta.get("submittal_manager"),
            "type": meta.get("type"),
        })

ls = pd.DataFrame(lifespans)
print(f"observed Open→Closed cohort size: {len(ls)} (vs 129 in 6-week analysis)")
if len(ls):
    s = stats(ls["days"])
    print(f"global  n={s['n']}  mean={s['mean']:.2f}  median={s['median']:.2f}  "
          f"p25={s['p25']:.2f}  p75={s['p75']:.2f}  max={s['max']:.2f}")

    print("\n  -- by type --")
    for t, g in ls.groupby("type"):
        s = stats(g["days"])
        print(f"  {str(t):<32} n={s['n']:>4}  mean={s['mean']:>6.2f}  median={s['median']:>6.2f}  max={s['max']:>6.2f}")

    print("\n  -- by submittal manager (Drafting Release Review only) --")
    drr_ls = ls[ls["type"] == "Drafting Release Review"]
    for m, g in drr_ls.groupby("mgr"):
        s = stats(g["days"])
        print(f"  {str(m):<22} n={s['n']:>4}  mean={s['mean']:>6.2f}  median={s['median']:>6.2f}  p75={s['p75']:>6.2f}")


# ---------- SECTION B: FIRST-TOUCH LATENCY ----------
print("\n" + "=" * 78)
print("B. FIRST-TOUCH LATENCY (create → first BIC change)")
print("=" * 78)
print("How long the submittal sits in initial BIC before someone moves it.\n")
ftl = []
for sid, st in streams.items():
    ct = create_ts.get(sid)
    if not ct:
        continue
    bics = st[st["kind"] == "bic"]
    if len(bics) == 0:
        continue
    first_bic = bics.iloc[0]
    initial_bic = first_bic["old"]  # Whoever was BIC at create
    days = (first_bic["ts"] - ct).total_seconds() / 86400.0
    if days < 0:
        continue
    meta = sub_meta.get(sid, {})
    ftl.append({
        "sid": sid, "days": days, "initial_bic": initial_bic,
        "mgr": meta.get("submittal_manager"), "type": meta.get("type"),
        "project": meta.get("project_name"),
    })
ftl_df = pd.DataFrame(ftl)
print(f"submittals with measurable first-touch: {len(ftl_df)}")
if len(ftl_df):
    s = stats(ftl_df["days"])
    print(f"global mean={s['mean']:.2f}d  median={s['median']:.2f}d  p75={s['p75']:.2f}d  max={s['max']:.2f}d")

    print("\n  -- by initial BIC (who held it from creation) — top 10 --")
    grp = ftl_df.groupby("initial_bic")["days"].agg(["count", "mean", "median"]).sort_values("count", ascending=False).head(10)
    print(f"  {'Initial BIC':<25}{'n':>5}{'mean':>8}{'med':>8}")
    for bic, row in grp.iterrows():
        print(f"  {str(bic)[:24]:<25}{int(row['count']):>5}{row['mean']:>8.2f}{row['median']:>8.2f}")


# ---------- SECTION C: RE-OPENS / REWORK ----------
print("\n" + "=" * 78)
print("C. RE-OPENS AND REWORK LOOPS")
print("=" * 78)
reopens = []
drafter_seen_twice = []
for sid, st in streams.items():
    statuses = st[st["kind"] == "status"]
    # Count Closed -> Open transitions
    n_reopen = 0
    for _, r in statuses.iterrows():
        if r["old"] == "Closed" and r["new"] == "Open":
            n_reopen += 1
    if n_reopen > 0:
        meta = sub_meta.get(sid, {})
        reopens.append({"sid": sid, "n_reopen": n_reopen, "project": meta.get("project_name"),
                        "title": meta.get("title"), "mgr": meta.get("submittal_manager"), "type": meta.get("type")})

    # Same drafter appearing twice non-consecutively in BIC stream
    bic_seq = []
    for _, r in st[st["kind"] == "bic"].iterrows():
        bic_seq.append(parse_bic_set(r["new"]))
    primary_seq = []
    for s_set in bic_seq:
        d_in = s_set & DRAFTERS
        if d_in:
            primary_seq.append(min(d_in))
        else:
            primary_seq.append(None)
    # Look for a drafter appearing -> someone else -> drafter again
    for d in DRAFTERS:
        positions = [i for i, n in enumerate(primary_seq) if n == d]
        if len(positions) >= 2 and any(positions[i + 1] - positions[i] >= 2 for i in range(len(positions) - 1)):
            meta = sub_meta.get(sid, {})
            drafter_seen_twice.append({"sid": sid, "drafter": d, "n_visits": len(positions),
                                       "project": meta.get("project_name"), "title": meta.get("title")})
            break

print(f"submittals re-opened (Closed→Open at least once): {len(reopens)}")
print(f"  total re-open events: {sum(r['n_reopen'] for r in reopens)}")
print(f"  multi-reopen (≥2): {sum(1 for r in reopens if r['n_reopen'] >= 2)}")
if reopens:
    print("\n  -- top re-opened projects --")
    rop = pd.DataFrame(reopens).groupby("project")["n_reopen"].agg(["count", "sum"]).sort_values("sum", ascending=False).head(10)
    print(f"  {'Project':<45}{'subs':>6}{'reopens':>10}")
    for p, row in rop.iterrows():
        print(f"  {str(p)[:44]:<45}{int(row['count']):>6}{int(row['sum']):>10}")

print(f"\nsubmittals where same drafter handled work twice (rework loop): {len(drafter_seen_twice)}")
if drafter_seen_twice:
    rdf = pd.DataFrame(drafter_seen_twice)
    print("  by drafter:")
    for d, c in rdf["drafter"].value_counts().items():
        print(f"    {d}: {c}")


# ---------- SECTION D: STALE-NOW REPORT ----------
print("\n" + "=" * 78)
print("D. STALE-NOW REPORT (currently open submittals)")
print("=" * 78)
NOW = uni_d["ts"].max()
print(f"as of {NOW}\n")
open_subs = subs[subs["status"].isin(["Open", "Submitted To Client", "Draft"])].copy()

# For each open submittal, find last BIC change
stale_rows = []
for _, sub in open_subs.iterrows():
    sid = str(sub["submittal_id"])
    st = streams.get(sid)
    if st is None:
        last_change_ts = create_ts.get(sid)
    else:
        bic_changes = st[st["kind"] == "bic"]
        last_change_ts = bic_changes["ts"].max() if not bic_changes.empty else create_ts.get(sid)
    if not last_change_ts:
        continue
    days_stale = (NOW - last_change_ts).total_seconds() / 86400.0
    stale_rows.append({
        "sid": sid,
        "title": sub["title"],
        "bic": sub["ball_in_court"],
        "project": sub["project_name"],
        "mgr": sub["submittal_manager"],
        "type": sub["type"],
        "days_stale": days_stale,
    })
stale_df = pd.DataFrame(stale_rows).sort_values("days_stale", ascending=False)

for thresh in [7, 14, 30, 60, 90]:
    n = (stale_df["days_stale"] > thresh).sum()
    print(f"  open submittals with no BIC movement in >{thresh}d: {n}")

print("\n  -- top 15 stalest open submittals --")
print(f"  {'days':>6}  {'BIC':<26}  {'project':<28}  title")
for _, r in stale_df.head(15).iterrows():
    print(f"  {r['days_stale']:>6.1f}  {str(r['bic'])[:25]:<26}  {str(r['project'])[:27]:<28}  {str(r['title'])[:55]}")

print("\n  -- stale (>30d) by current BIC holder --")
gst = stale_df[stale_df["days_stale"] > 30].groupby("bic").size().sort_values(ascending=False).head(15)
for bic, n in gst.items():
    print(f"    {n:>3}   {bic}")


# ---------- SECTION E: TIME-OF-DAY / DAY-OF-WEEK ----------
print("\n" + "=" * 78)
print("E. WHEN DOES WORK HAPPEN? (BIC changes only)")
print("=" * 78)
bic_only = uni_d[uni_d["kind"] == "bic"].copy()
# All times are in UTC stored. Mountain Time = UTC-6 or -7. Convert to MT (DST-aware: -6 in summer).
# Approximation: subtract 6h for simple display.
bic_only["mt"] = bic_only["ts"] - timedelta(hours=6)
bic_only["dow"] = bic_only["mt"].dt.day_name()
bic_only["hour"] = bic_only["mt"].dt.hour

dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
print("BIC changes by day of week (Mountain time approx):")
dow_counts = bic_only["dow"].value_counts().reindex(dow_order)
mx = dow_counts.max()
for d, c in dow_counts.items():
    bar = "█" * int((c / mx) * 40) if c else ""
    print(f"  {d:<10} {int(c):>5}  {bar}")

print("\nBIC changes by hour of day:")
hour_counts = bic_only["hour"].value_counts().sort_index()
mx = hour_counts.max()
for h, c in hour_counts.items():
    bar = "█" * int((c / mx) * 40) if c else ""
    print(f"  {h:>2}:00  {int(c):>5}  {bar}")


# ---------- SECTION F: MANAGER -> DRAFTER ROUTING ----------
print("\n" + "=" * 78)
print("F. MANAGER → DRAFTER ROUTING PREFERENCES")
print("=" * 78)
routing = Counter()  # (mgr, drafter) -> count
# A "routing" event = a BIC change from manager-name to a drafter-set containing exactly one drafter
for sid, st in streams.items():
    for _, r in st[st["kind"] == "bic"].iterrows():
        old_set = parse_bic_set(r["old"])
        new_set = parse_bic_set(r["new"])
        # who handed off from
        from_mgr = old_set & SUBMITTAL_MANAGERS
        # who was assigned to
        to_drafter = new_set & DRAFTERS
        if from_mgr and to_drafter and len(to_drafter) >= 1:
            for m in from_mgr:
                for d in to_drafter:
                    routing[(m, d)] += 1

print("Manager → Drafter assignments (BIC transition mgr→drafter):")
print(f"{'Manager':<18}{'Dalton':>10}{'Colton':>10}{'Rourke':>10}{'total':>10}")
for m in sorted(SUBMITTAL_MANAGERS):
    row = [routing.get((m, d), 0) for d in ["Dalton Rauer", "Colton Arendt", "Rourke Alvarado"]]
    total = sum(row)
    if total == 0:
        continue
    pct = [f"{x} ({100 * x / total:.0f}%)" for x in row]
    print(f"{m:<18}{pct[0]:>10}{pct[1]:>10}{pct[2]:>10}{total:>10}")


# ---------- SECTION G: THROUGHPUT TREND ----------
print("\n" + "=" * 78)
print("G. THROUGHPUT TREND (closes per week, Drafting Release Review)")
print("=" * 78)
closes = uni_d[(uni_d["kind"] == "status") & (uni_d["new"] == "Closed")].copy()
# join with submittals to get type
closes["type"] = closes["sid"].map(lambda s: sub_meta.get(s, {}).get("type"))
drr_closes = closes[closes["type"] == "Drafting Release Review"].copy()
drr_closes["week"] = drr_closes["ts"].dt.to_period("W")
weekly = drr_closes.groupby("week").size()
mx = weekly.max() if len(weekly) else 1
print(f"{'week':<25}{'closes':>8}")
for wk, n in weekly.items():
    bar = "█" * int(n / mx * 40)
    print(f"  {str(wk):<23}{int(n):>5}  {bar}")

# All-types weekly (background)
print(f"\nAll-type closes per week (for context):")
all_w = closes.groupby(closes["ts"].dt.to_period("W")).size()
mx = all_w.max() if len(all_w) else 1
for wk, n in all_w.items():
    bar = "█" * int(n / mx * 40)
    print(f"  {str(wk):<23}{int(n):>5}  {bar}")


# ---------- SECTION H: DRAFTING STATUS DWELL ----------
print("\n" + "=" * 78)
print("H. DRAFTING STATUS DWELL (HOLD / NEED VIF / STARTED)")
print("=" * 78)
ds_changes = uni_d[uni_d["kind"] == "draft_status"].copy()
print(f"draft_status change events: {len(ds_changes)}")
print("\ntransitions:")
print(ds_changes.groupby(["old", "new"]).size().sort_values(ascending=False).head(20))

# Compute time spent in each non-default status
status_dwell = []
for sid, g in ds_changes.groupby("sid"):
    g = g.sort_values("ts").reset_index(drop=True)
    for i in range(len(g)):
        cur = g.iloc[i]
        nxt_ts = g.iloc[i + 1]["ts"] if i + 1 < len(g) else None
        if not nxt_ts:
            continue  # still in this status
        days = (nxt_ts - cur["ts"]).total_seconds() / 86400.0
        status_dwell.append({"sid": sid, "status": cur["new"], "days": days})

if status_dwell:
    sdf = pd.DataFrame(status_dwell)
    print("\ndwell time by status (closed dwell only):")
    for st_name, g in sdf.groupby("status"):
        s = stats(g["days"])
        print(f"  {str(st_name):<15} n={s['n']:>3}  mean={s['mean']:>6.2f}d  median={s['median']:>6.2f}d  max={s['max']:>6.2f}d")


# ---------- SECTION I: LATE-STAGE SCOPE CHANGES ----------
print("\n" + "=" * 78)
print("I. LATE-STAGE SCOPE CHANGES (title or manager change after submittal opened)")
print("=" * 78)
late_changes = []
for sid, st in streams.items():
    title_changes = st[st["kind"] == "title"]
    mgr_changes = st[st["kind"] == "manager"]
    ct = create_ts.get(sid)
    for _, r in title_changes.iterrows():
        if ct and (r["ts"] - ct).total_seconds() / 86400.0 > 1:  # >1 day after create
            meta = sub_meta.get(sid, {})
            late_changes.append({"sid": sid, "kind": "title", "ts": r["ts"],
                                 "days_after_create": (r["ts"] - ct).total_seconds() / 86400.0,
                                 "old": r["old"], "new": r["new"], "project": meta.get("project_name")})
    for _, r in mgr_changes.iterrows():
        if ct and (r["ts"] - ct).total_seconds() / 86400.0 > 1:
            meta = sub_meta.get(sid, {})
            late_changes.append({"sid": sid, "kind": "manager", "ts": r["ts"],
                                 "days_after_create": (r["ts"] - ct).total_seconds() / 86400.0,
                                 "old": r["old"], "new": r["new"], "project": meta.get("project_name")})

print(f"late title changes: {sum(1 for x in late_changes if x['kind'] == 'title')}")
print(f"late manager changes: {sum(1 for x in late_changes if x['kind'] == 'manager')}")
if late_changes:
    print("\n  -- top 10 late title changes --")
    lc = pd.DataFrame([x for x in late_changes if x["kind"] == "title"]).sort_values("days_after_create", ascending=False).head(10)
    for _, r in lc.iterrows():
        print(f"  {r['days_after_create']:>5.1f}d  {str(r['project'])[:25]:<26}  '{str(r['old'])[:30]}' → '{str(r['new'])[:30]}'")


# ---------- SECTION J: BIMODALITY OF DRAFTER DURATION ----------
print("\n" + "=" * 78)
print("J. BIMODALITY: split drafter durations into 'quick triage' (<1d) vs 'real work' (≥1d)")
print("=" * 78)
print(f"{'Drafter':<22}{'<1d count':>12}{'<1d avg':>12}{'≥1d count':>12}{'≥1d mean':>12}{'≥1d median':>14}")
for d in DRAFTERS:
    g = ds_solo_closed[ds_solo_closed["drafter"] == d]["duration_days"]
    q = g[g < 1]
    r = g[g >= 1]
    print(f"{d:<22}{len(q):>12}{q.mean():>12.3f}{len(r):>12}{r.mean():>12.2f}{r.median():>14.2f}")

print("\n  on Drafting Release Review only:")
drr_solo = ds_solo_closed[ds_solo_closed["type"] == "Drafting Release Review"]
for d in DRAFTERS:
    g = drr_solo[drr_solo["drafter"] == d]["duration_days"]
    q = g[g < 1]
    r = g[g >= 1]
    if len(g) == 0:
        continue
    print(f"  {d:<20} <1d: {len(q):>3} ({q.mean():.2f}d avg)  | ≥1d: {len(r):>3} ({r.mean():.2f}d mean, {r.median():.2f}d median)")


# ---------- SECTION K: MULTI-ASSIGNEE ----------
print("\n" + "=" * 78)
print("K. MULTI-ASSIGNEE (when BIC has 2+ names — review/QA stage)")
print("=" * 78)
multi_segments = []
for sid, st in streams.items():
    bic_rows = st[st["kind"] == "bic"].sort_values("ts").reset_index(drop=True)
    for i in range(len(bic_rows)):
        new_set = parse_bic_set(bic_rows.iloc[i]["new"])
        if len(new_set) >= 2:
            ts = bic_rows.iloc[i]["ts"]
            end_ts = bic_rows.iloc[i + 1]["ts"] if i + 1 < len(bic_rows) else None
            duration = (end_ts - ts).total_seconds() / 86400.0 if end_ts else None
            multi_segments.append({"sid": sid, "n_assignees": len(new_set), "duration_days": duration})

ms = pd.DataFrame(multi_segments)
print(f"multi-assignee BIC segments: {len(ms)}")
ms_closed = ms[ms["duration_days"].notna()]
if len(ms_closed):
    s = stats(ms_closed["duration_days"])
    print(f"  closed segments n={s['n']}  mean={s['mean']:.2f}d  median={s['median']:.2f}d  p75={s['p75']:.2f}d")

print("  by assignee count:")
for n, g in ms.groupby("n_assignees"):
    s = stats(g["duration_days"])
    print(f"    {n} assignees: n={len(g):>4}  closed={s['n']:>4}  mean={s.get('mean', 0):.2f}d  median={s.get('median', 0):.2f}d")

# Save expanded artifacts
ls.to_csv("analysis/lifespans_expanded.csv", index=False)
ds.to_csv("analysis/drafter_segments_expanded.csv", index=False)
stale_df.to_csv("analysis/stale_now.csv", index=False)
uni_d.to_pickle("analysis/unified_events.pkl")
print("\nsaved analysis/{lifespans_expanded,drafter_segments_expanded,stale_now}.csv + unified_events.pkl")
