"""Quick check on list_moves and the Excel field updates."""
import pandas as pd

list_moves = pd.read_pickle("analysis/list_moves.pkl")
db_updates = pd.read_pickle("analysis/db_updates.pkl")
releases = pd.read_pickle("analysis/releases.pkl")

list_moves["from"] = list_moves["data"].apply(lambda d: d.get("from_list") if isinstance(d, dict) else None)
list_moves["to"] = list_moves["data"].apply(lambda d: d.get("to_list") if isinstance(d, dict) else None)

print(f"list_moves date range: {list_moves['ts'].min()} -> {list_moves['ts'].max()}")
print(f"unique card_ids: {list_moves['card_id'].nunique()}")
print(f"\nfrom→to top 25:")
print(list_moves.groupby(["from", "to"]).size().sort_values(ascending=False).head(25))

# Match cards to releases
rel_cards = set(releases["trello_card_id"].dropna())
moves_with_release = list_moves[list_moves["card_id"].isin(rel_cards)]
print(f"\nlist_moves matchable to a release: {len(moves_with_release)} / {len(list_moves)}")

# DB field updates
print(f"\nDB field updates date range: {db_updates['ts'].min()} -> {db_updates['ts'].max()}")
db_updates["field"] = db_updates["data"].apply(lambda d: d.get("field") if isinstance(d, dict) else None)
db_updates["old_v"] = db_updates["data"].apply(lambda d: d.get("old_value") if isinstance(d, dict) else None)
db_updates["new_v"] = db_updates["data"].apply(lambda d: d.get("new_value") if isinstance(d, dict) else None)
db_updates["job"] = db_updates["data"].apply(lambda d: d.get("job") if isinstance(d, dict) else None)
db_updates["release"] = db_updates["data"].apply(lambda d: d.get("release") if isinstance(d, dict) else None)
print(f"\nfield breakdown:")
print(db_updates["field"].value_counts())
print(f"\nunique (job, release): {db_updates[['job','release']].drop_duplicates().shape[0]}")
