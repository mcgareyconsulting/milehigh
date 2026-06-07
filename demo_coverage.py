"""READ-ONLY coverage probe: of the 41 extracted checklist items, how many pin to an
ACTIVE release in the real job log?

Does NOT call create_app() (which would start the outbox worker). Opens a bare
SELECT-only connection to sandbox for the release catalog, and reads item titles from
the local sqlite. No writes anywhere.
"""
import re
import sqlite3
from difflib import SequenceMatcher
from pathlib import Path

from sqlalchemy import create_engine, text

WT = Path(__file__).resolve().parent
ENV = Path("/Users/danielmcgarey/Desktop/MHMW/milehigh/.env")
LOCAL_DB = WT / "instance" / "jobs.sqlite"

STRONG, WEAK = 85.0, 70.0
_STOP = {"the", "a", "an", "of", "and", "to", "for", "on", "at", "in", "rail", "rails",
         "stair", "building", "install", "ship", "get", "with"}


def sandbox_url():
    for line in ENV.read_text().splitlines():
        if line.startswith("SANDBOX_DATABASE_URL="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("no SANDBOX_DATABASE_URL")


def partial_ratio(short, long):
    """Best fuzzy ratio of `short` against any same-length window of `long` (0-100)."""
    short, long = short.lower().strip(), long.lower()
    if not short or not long:
        return 0.0
    if len(short) > len(long):
        short, long = long, short
    best = 0.0
    for i in range(len(long) - len(short) + 1):
        best = max(best, SequenceMatcher(None, short, long[i:i + len(short)]).ratio())
        if best == 1.0:
            break
    return best * 100.0


def desc_coverage(desc, title):
    toks = {t for t in re.findall(r"[a-z0-9]+", (desc or "").lower()) if t not in _STOP and len(t) > 2}
    if not toks:
        return 0.0
    tl = title.lower()
    return 100.0 * sum(1 for t in toks if t in tl) / len(toks)


def main():
    # 1) active release catalog (READ ONLY)
    eng = create_engine(sandbox_url(), connect_args={"sslmode": "require"})
    with eng.connect() as c:
        rows = c.execute(text("""
            SELECT id, job, release, job_name, description, stage, pm, "by", installer
            FROM releases
            WHERE is_active = true AND is_archived = false
              AND COALESCE(job_comp,'') <> 'X' AND COALESCE(invoiced,'') <> 'X'
        """)).fetchall()
    eng.dispose()
    catalog = [dict(r._mapping) for r in rows]
    active_names = sorted({(r["job_name"] or "").strip() for r in catalog if r["job_name"]})
    print(f"Active releases: {len(catalog)}  |  distinct active job_names: {len(active_names)}")
    print("ACTIVE PROJECTS:", ", ".join(active_names), "\n")

    # drop junk/placeholder names that fuzzy-match everything (e.g. 'Test')
    catalog = [r for r in catalog
               if len((r["job_name"] or "").strip()) >= 5 and (r["job_name"] or "").strip().lower() != "test"]

    # 2) the 41 extracted item titles (local sqlite, read only)
    con = sqlite3.connect(f"file:{LOCAL_DB}?mode=ro", uri=True)
    items = [r[0] for r in con.execute("SELECT title FROM checklist_items ORDER BY id").fetchall()]
    con.close()
    print(f"Extracted items: {len(items)}\n" + "=" * 78)

    def short_name(jn):  # drop GC prefix before the first ' - '
        parts = re.split(r"\s*-\s*", jn or "", maxsplit=1)
        return parts[1] if len(parts) == 2 and len(parts[1]) >= 3 else (jn or "")

    def name_score(jn, title):  # is the project NAMED in the title? (any distinctive token present)
        toks = [t for t in re.findall(r"[a-z]+", short_name(jn).lower())
                if t not in _STOP and len(t) >= 5]
        if not toks:
            return 0.0
        tt = re.findall(r"[a-z]+", title.lower())
        best = 0.0
        for t in toks:
            if any(SequenceMatcher(None, t, x).ratio() >= 0.82 for x in tt):
                best = max(best, 100.0 if len(t) >= 6 else 75.0)
        return best

    buckets = {"strong": 0, "weak": 0, "none": 0}
    misses = []
    for title in items:
        best = max(catalog, key=lambda r: name_score(r["job_name"], title), default=None)
        ns = name_score(best["job_name"], title) if best else 0.0
        # ambiguity: how many active projects tie at the top name score?
        ties = sum(1 for r in catalog if name_score(r["job_name"], title) >= max(ns, 60)) if ns >= 60 else 0
        tier = "strong" if ns >= STRONG else "weak" if ns >= WEAK else "none"
        buckets[tier] += 1
        tag = {"strong": "✓", "weak": "~", "none": "✗"}[tier]
        if tier == "none":
            misses.append(title)
        else:
            amb = f"  ⚠{ties} candidates" if ties > 1 else ""
            print(f"{tag} [{ns:4.0f}] {title[:46]:46} -> {best['job_name']}{amb}")

    n = len(items)
    print("=" * 78)
    print(f"STRONG (≥{STRONG:.0f} name): {buckets['strong']}/{n}   "
          f"WEAK ({WEAK:.0f}-{STRONG:.0f}): {buckets['weak']}/{n}   "
          f"NONE (<{WEAK:.0f}): {buckets['none']}/{n}")
    print(f"\nUnanchored ({len(misses)}):")
    for m in misses:
        print("   ✗", m[:70])


if __name__ == "__main__":
    main()
