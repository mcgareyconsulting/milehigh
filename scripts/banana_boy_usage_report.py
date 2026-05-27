"""Quick CLI report on Banana Boy API usage.

Pulls from the same DB the app would use (ENVIRONMENT=sandbox/production/local).

    python scripts/banana_boy_usage_report.py
    ENVIRONMENT=sandbox python scripts/banana_boy_usage_report.py --days 30
"""
import argparse
import os
import sys
from datetime import datetime, timedelta

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import config as _app_config  # noqa: F401, E402  (loads .env)
from app.db_config import get_database_config  # noqa: E402

from sqlalchemy import create_engine, text  # noqa: E402


def _money(x):
    if x is None:
        return "$0.0000"
    return f"${x:,.4f}"


def _row(label, value, width=40):
    return f"  {label:<{width}}{value}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=30, help="Window in days (default 30).")
    p.add_argument("--limit", type=int, default=10, help="Top-N rows in detail sections.")
    args = p.parse_args()

    environment = os.environ.get("FLASK_ENV") or os.environ.get("ENVIRONMENT", "local")
    db_url, _ = get_database_config(environment.lower())
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    safe = db_url
    if "@" in safe:
        prefix, rest = safe.split("://", 1)
        creds, host = rest.split("@", 1)
        safe = f"{prefix}://***@{host}"

    print(f"\nBanana Boy usage — environment={environment}  db={safe}\n")
    cutoff = datetime.utcnow() - timedelta(days=args.days)

    engine = create_engine(db_url)
    with engine.connect() as conn:
        # Does the table exist?
        try:
            conn.execute(text("SELECT 1 FROM banana_boy_usage LIMIT 1"))
        except Exception as exc:
            print(f"  banana_boy_usage table not found in this DB.")
            print(f"  ({type(exc).__name__}: {exc})")
            print(f"\n  Run the migration first:")
            print(f"    ENVIRONMENT={environment} python migrations/create_banana_boy_usage_table.py\n")
            return 1

        # Totals (all time)
        total = conn.execute(text("""
            SELECT
                COUNT(*)                AS calls,
                COALESCE(SUM(cost_usd), 0)   AS cost,
                COUNT(DISTINCT user_id) AS users,
                COUNT(DISTINCT chat_message_id) AS messages,
                MIN(created_at)         AS first_seen,
                MAX(created_at)         AS last_seen
            FROM banana_boy_usage
        """)).mappings().one()

        print("All-time totals")
        print(_row("API calls", f"{total['calls']:,}"))
        print(_row("Cost (USD)", _money(total["cost"])))
        print(_row("Distinct users", total["users"]))
        print(_row("Assistant messages w/ usage", total["messages"]))
        print(_row("First call", total["first_seen"] or "—"))
        print(_row("Last call", total["last_seen"] or "—"))
        if not total["calls"]:
            print("\n  (no rows yet — nothing else to show)\n")
            return 0

        # Window totals
        win = conn.execute(text("""
            SELECT COUNT(*) AS calls,
                   COALESCE(SUM(cost_usd), 0) AS cost
            FROM banana_boy_usage WHERE created_at >= :cutoff
        """), {"cutoff": cutoff}).mappings().one()
        print(f"\nLast {args.days} days")
        print(_row("API calls", f"{win['calls']:,}"))
        print(_row("Cost (USD)", _money(win["cost"])))

        # By provider/operation/model
        print(f"\nBy provider / operation / model (last {args.days} days)")
        rows = conn.execute(text("""
            SELECT provider, operation, model,
                   COUNT(*) AS calls,
                   COALESCE(SUM(cost_usd), 0)            AS cost,
                   COALESCE(SUM(input_tokens), 0)        AS input_tok,
                   COALESCE(SUM(output_tokens), 0)       AS output_tok,
                   COALESCE(SUM(input_chars), 0)         AS input_chars,
                   COALESCE(SUM(audio_seconds), 0)       AS audio_sec,
                   COALESCE(AVG(duration_ms), 0)         AS avg_ms
            FROM banana_boy_usage
            WHERE created_at >= :cutoff
            GROUP BY provider, operation, model
            ORDER BY cost DESC
        """), {"cutoff": cutoff}).mappings().all()
        if rows:
            print(f"  {'provider':<10} {'operation':<14} {'model':<32} {'calls':>6}  {'cost':>10}  {'avg_ms':>7}  detail")
            for r in rows:
                detail = []
                if r["input_tok"] or r["output_tok"]:
                    detail.append(f"in={r['input_tok']:,}tok out={r['output_tok']:,}tok")
                if r["input_chars"]:
                    detail.append(f"chars={r['input_chars']:,}")
                if r["audio_sec"]:
                    detail.append(f"audio={r['audio_sec']:.1f}s")
                print(f"  {r['provider']:<10} {r['operation']:<14} {r['model']:<32} {r['calls']:>6}  {_money(r['cost']):>10}  {int(r['avg_ms']):>7}  {' '.join(detail)}")

        # By user
        print(f"\nTop users by cost (last {args.days} days)")
        try:
            rows = conn.execute(text("""
                SELECT u.username, bu.user_id,
                       COUNT(*) AS calls,
                       COALESCE(SUM(bu.cost_usd), 0) AS cost
                FROM banana_boy_usage bu
                LEFT JOIN users u ON u.id = bu.user_id
                WHERE bu.created_at >= :cutoff
                GROUP BY u.username, bu.user_id
                ORDER BY cost DESC
                LIMIT :limit
            """), {"cutoff": cutoff, "limit": args.limit}).mappings().all()
            for r in rows:
                who = r["username"] or f"user#{r['user_id']}"
                print(f"  {who:<35} {r['calls']:>6} calls   {_money(r['cost'])}")
        except Exception as exc:
            print(f"  (could not join users table: {exc})")

        # By day
        print(f"\nDaily cost (last {args.days} days)")
        rows = conn.execute(text("""
            SELECT DATE(created_at) AS day,
                   COUNT(*) AS calls,
                   COALESCE(SUM(cost_usd), 0) AS cost
            FROM banana_boy_usage
            WHERE created_at >= :cutoff
            GROUP BY DATE(created_at)
            ORDER BY day DESC
        """), {"cutoff": cutoff}).mappings().all()
        for r in rows:
            print(f"  {str(r['day']):<12} {r['calls']:>6} calls   {_money(r['cost'])}")

        # Most expensive single calls
        print(f"\nMost expensive individual calls (last {args.days} days)")
        rows = conn.execute(text("""
            SELECT id, created_at, user_id, provider, operation, model, cost_usd, duration_ms,
                   input_tokens, output_tokens, input_chars, audio_seconds
            FROM banana_boy_usage
            WHERE created_at >= :cutoff
            ORDER BY cost_usd DESC NULLS LAST
            LIMIT :limit
        """), {"cutoff": cutoff, "limit": args.limit}).mappings().all()
        for r in rows:
            extras = []
            if r["input_tokens"]:
                extras.append(f"{r['input_tokens']}→{r['output_tokens']} tok")
            if r["input_chars"]:
                extras.append(f"{r['input_chars']} chars")
            if r["audio_seconds"]:
                extras.append(f"{r['audio_seconds']:.1f}s audio")
            print(f"  #{r['id']:<6} {str(r['created_at'])[:19]}  user#{r['user_id']:<4} "
                  f"{r['provider']:<10}/{r['operation']:<14} {_money(r['cost_usd']):>10}  "
                  f"{r['duration_ms']:>5}ms  {' '.join(extras)}")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
