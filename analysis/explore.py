"""Quick exploration to understand the data shape."""
import pandas as pd

events = pd.read_pickle("analysis/events.pkl")
subs = pd.read_pickle("analysis/submittals.pkl")
users = pd.read_pickle("analysis/users.pkl")

print("=" * 70)
print("EVENTS")
print("=" * 70)
print(f"rows: {len(events)}")
print(f"cols: {list(events.columns)}")
print(f"\nactions:\n{events['action'].value_counts()}")
print(f"\nsources:\n{events['source'].value_counts()}")
print(f"\nis_system_echo:\n{events['is_system_echo'].value_counts()}")
print(f"\ninternal_user_id non-null: {events['internal_user_id'].notna().sum()}")
print(f"external_user_id non-null: {events['external_user_id'].notna().sum()}")
print(f"\ndate range: {events['created_at'].min()} -> {events['created_at'].max()}")

print("\n" + "=" * 70)
print("SAMPLE EVENT PAYLOADS (5 each action)")
print("=" * 70)
for action in events['action'].unique():
    print(f"\n--- {action} ---")
    sample = events[events['action'] == action].head(2)
    for _, row in sample.iterrows():
        print(f"src={row['source']} payload_keys={list(row['payload'].keys()) if isinstance(row['payload'], dict) else type(row['payload'])}")
        if isinstance(row['payload'], dict):
            for k, v in list(row['payload'].items())[:8]:
                vstr = str(v)[:120]
                print(f"   {k}: {vstr}")

print("\n" + "=" * 70)
print("SUBMITTALS")
print("=" * 70)
print(f"rows: {len(subs)}")
print(f"cols: {list(subs.columns)}")
print(f"\nstatus:\n{subs['status'].value_counts(dropna=False)}")
print(f"\ndrafting_status:\n{subs['submittal_drafting_status'].value_counts(dropna=False)}")
print(f"\ntype:\n{subs['type'].value_counts(dropna=False).head(15)}")
print(f"\nproject count: {subs['project_name'].nunique()}")
print(f"submittal_manager top:\n{subs['submittal_manager'].value_counts(dropna=False).head(15)}")
print(f"\nball_in_court top:\n{subs['ball_in_court'].value_counts(dropna=False).head(15)}")

print("\n" + "=" * 70)
print("USERS")
print("=" * 70)
print(users[['id', 'username', 'first_name', 'last_name', 'is_drafter', 'is_admin']].to_string())
