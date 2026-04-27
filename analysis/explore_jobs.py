"""Explore job-log data shape before designing analysis."""
import pandas as pd
from collections import Counter

releases = pd.read_pickle("analysis/releases.pkl")
revents = pd.read_pickle("analysis/release_events.pkl")
jcl = pd.read_pickle("analysis/job_change_logs.pkl")
sync_jobs = pd.read_pickle("analysis/sync_jobs.pkl")

print(f"releases: {len(releases)}, archived: {releases['is_archived'].sum()}")
print(f"\nstage distribution (active+archived):")
print(releases["stage"].value_counts())

print(f"\nstage_group:\n{releases['stage_group'].value_counts(dropna=False)}")

print(f"\nfab_order distribution (proxy for queue position):")
print(f"  null: {releases['fab_order'].isna().sum()}")
print(f"  range: {releases['fab_order'].min()} -> {releases['fab_order'].max()}")

print(f"\nreleased date range:")
rels = pd.to_datetime(releases["released"], errors="coerce")
print(f"  min: {rels.min()}  max: {rels.max()}")
print(f"  null: {rels.isna().sum()}")
print(f"\nreleased per month:")
print(rels.dt.to_period("M").value_counts().sort_index())

print(f"\n--- release_events action breakdown ---")
print(revents["action"].value_counts())

# stage-related events
stage_evts = revents[revents["action"] == "update_stage"].copy()
stage_evts["from_stage"] = stage_evts["payload"].apply(lambda p: p.get("from") if isinstance(p, dict) else None)
stage_evts["to_stage"] = stage_evts["payload"].apply(lambda p: p.get("to") if isinstance(p, dict) else None)
print(f"\nstage transitions in release_events ({len(stage_evts)} rows):")
print(stage_evts.groupby(["from_stage", "to_stage"]).size().sort_values(ascending=False).head(25))

print(f"\n--- job_change_logs (5 mo audit) ---")
print(f"date range: {jcl['changed_at'].min()} -> {jcl['changed_at'].max()}")
print(f"unique (job, release): {jcl[['job','release']].drop_duplicates().shape[0]}")
print(f"\ntop transitions in job_change_logs:")
print(jcl.groupby(["from_value", "to_value"]).size().sort_values(ascending=False).head(30))

print(f"\nstate values frequency in to_value:")
print(jcl["to_value"].value_counts().head(20))

print(f"\nsync_jobs message breakdown:")
sync_jobs["msg_prefix"] = sync_jobs["message"].str[:50]
print(sync_jobs["msg_prefix"].value_counts().head(15))

# what's in "List move detected" data?
lm = sync_jobs[sync_jobs["message"].str.contains("List move detected", na=False)].head(5)
print(f"\nList move detected sample data:")
for _, r in lm.iterrows():
    print(f"  {r['timestamp']}  card={r['trello_card_id']}")
    print(f"    {r['data']}")

# DB field update sample
db = sync_jobs[sync_jobs["message"].str.contains("DB field update", na=False)].head(5)
print(f"\nDB field update sample data:")
for _, r in db.iterrows():
    print(f"  {r['timestamp']}  job={r['job_id']} excel={r['excel_identifier']}")
    print(f"    {r['data']}")

# Counts of unique releases / jobs in jcl
print(f"\njob_change_logs unique jobs: {jcl['job'].nunique()}")
print(f"job_change_logs unique (job, release): {jcl[['job','release']].drop_duplicates().shape[0]}")
