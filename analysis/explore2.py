"""Explore update event payload shapes."""
import pandas as pd
from collections import Counter

events = pd.read_pickle("analysis/events.pkl")

# Look at update payloads from Procore and Brain
for src in ['Procore', 'Brain']:
    sub = events[(events['action'] == 'updated') & (events['source'] == src)]
    print(f"\n=== {src} updated: {len(sub)} ===")
    keys = Counter()
    for p in sub['payload']:
        if isinstance(p, dict):
            keys.update(p.keys())
    print("top payload keys:", keys.most_common(20))

    print("\nfirst 5 sample payloads:")
    for _, row in sub.head(5).iterrows():
        print(f" submittal {row['submittal_id']}: {row['payload']}")

# How many updated events have ball_in_court?
proc_updated = events[(events['action'] == 'updated') & (events['source'] == 'Procore')]
bic_events = proc_updated[proc_updated['payload'].apply(lambda p: isinstance(p, dict) and 'ball_in_court' in p)]
print(f"\nProcore updated WITH ball_in_court change: {len(bic_events)}")
print("sample BIC change payloads:")
for _, r in bic_events.head(8).iterrows():
    print(f"  {r['submittal_id']}: {r['payload'].get('ball_in_court')}")

# Status transitions
stat_events = proc_updated[proc_updated['payload'].apply(lambda p: isinstance(p, dict) and 'status' in p)]
print(f"\nProcore updated WITH status change: {len(stat_events)}")
print("status change payloads (first 10):")
for _, r in stat_events.head(10).iterrows():
    print(f"  {r['submittal_id']}: {r['payload'].get('status')}")
