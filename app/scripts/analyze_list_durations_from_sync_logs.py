"""
Analyze how long jobs stay in fabrication lists (e.g., Paint Complete) using sync_logs.

Pulls sync_logs where data contains any of: from_list, to, from, id, field, new_value,
old_value, cell, value. Uses operation_id to join with SyncOperation for timestamps and
source (Trello vs OneDrive). Handles both list movements and Excel cell updates (e.g.
ship column P: O/T = Paint Complete, X/RS/ST = Shipping states).

Outputs a client-ready report (HTML + CSVs).

Usage:
    python app/scripts/analyze_list_durations_from_sync_logs.py --out-dir /path/to/report
    python app/scripts/analyze_list_durations_from_sync_logs.py --out-dir /path --min-ts 2025-01-01 --max-ts 2025-12-31
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd
from dotenv import load_dotenv

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT_DIR)

load_dotenv()

try:
    from app import create_app
    from app.models import db, Job, SyncLog, SyncOperation
except ImportError as e:
    print(f"Error importing app modules: {e}")
    sys.exit(1)

# Keys that qualify a sync_log for inclusion (data must contain at least one)
DATA_KEYS_FILTER = {"from_list", "to", "from", "id", "field", "new_value", "old_value", "cell", "value"}

# Excel column to field mapping (M=fitup, N=welded, O=paint_comp, P=ship)
EXCEL_COL_TO_FIELD = {"M": "fitup_comp", "N": "welded", "O": "paint_comp", "P": "ship"}

# List name normalization (canonical name -> variants)
LIST_NORMALIZATION = {
    "Paint complete": ["Paint complete", "Paint Complete"],
    "Fit Up Complete.": ["Fit Up Complete.", "Fit Up Complete"],
    "Shipping completed": ["Shipping completed", "Shipping Completed"],
    "Released": ["Released"],
    "Store at MHMW for shipping": ["Store at MHMW for shipping"],
    "Shipping planning": ["Shipping planning"],
}


def _normalize_list(name: Optional[str]) -> Optional[str]:
    """Normalize list name to canonical form."""
    if not name or not str(name).strip():
        return None
    s = str(name).strip()
    for canonical, variants in LIST_NORMALIZATION.items():
        if s in variants or s == canonical:
            return canonical
    return s  # Unknown list, keep as-is


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _ensure_out_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def _data_has_any_key(data: Optional[Dict], keys: Set[str]) -> bool:
    if not data or not isinstance(data, dict):
        return False
    return bool(keys & set(data.keys()))


@dataclass
class StageTransition:
    job: int
    release: str
    ts: datetime
    from_stage: Optional[str]
    to_stage: Optional[str]
    source: str  # "trello" | "onedrive"
    operation_id: str
    log_id: int
    event_type: str  # "list_move" | "excel_cell"


def _extract_job_release(d: Dict[str, Any], log: SyncLog) -> Optional[Tuple[int, str]]:
    """Extract (job, release) from data or linked columns."""
    job = d.get("job")
    release = d.get("release")
    if job is not None and release is not None:
        try:
            return int(job), str(release)
        except (ValueError, TypeError):
            pass
    if log.excel_identifier:
        parts = str(log.excel_identifier).split("-", 1)
        if len(parts) == 2:
            try:
                return int(parts[0]), parts[1]
            except ValueError:
                pass
    if log.job_id:
        job_rec = Job.query.get(log.job_id)
        if job_rec:
            return job_rec.job, job_rec.release
    return None


def _extract_from_to_stage(d: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Extract from_stage and to_stage from data."""
    from_stage = (
        d.get("payload_from")
        or d.get("from_list")
        or d.get("from")
        or d.get("current_list_name")
    )
    to_stage = (
        d.get("payload_to")
        or d.get("to_stage")
        or d.get("to")
        or d.get("to_list")
        or d.get("new_list_name")
        or d.get("new_list")  # Trello card update started
        or d.get("new_stage")
    )
    return _normalize_list(from_stage), _normalize_list(to_stage)


def _cell_to_stage(cell: str, value: Any) -> Optional[str]:
    """
    Map Excel cell update to stage change.
    Column P (ship): O/T = Paint Complete, ST = Store at MHMW, RS = Shipping planning, X = Shipping completed.
    Column O (paint_comp): X = can enter Paint Complete (if fitup, welded also X).
    """
    if not cell or not isinstance(cell, str):
        return None
    col = cell[0].upper() if cell else None
    val = str(value).strip().upper() if value is not None else ""
    field_name = EXCEL_COL_TO_FIELD.get(col)
    if field_name == "ship":
        if val in ("X",):
            return "Shipping completed"
        if val in ("ST",):
            return "Store at MHMW for shipping"
        if val in ("RS",):
            return "Shipping planning"
        if val in ("O", "T", ""):
            return "Paint complete"  # Still in Paint Complete
    if field_name == "paint_comp" and val == "X":
        return "Paint complete"
    return None


def _iter_eligible_logs(
    min_ts: Optional[datetime] = None,
    max_ts: Optional[datetime] = None,
) -> Iterable[Tuple[SyncLog, SyncOperation]]:
    """Yield (SyncLog, SyncOperation) for logs with relevant data keys, excluding Procore."""
    query = (
        db.session.query(SyncLog, SyncOperation)
        .join(SyncOperation, SyncLog.operation_id == SyncOperation.operation_id)
        .filter(SyncOperation.source_system.in_(["trello", "onedrive"]))
        .filter(SyncLog.data.isnot(None))
    )
    if min_ts:
        query = query.filter(SyncLog.timestamp >= min_ts)
    if max_ts:
        query = query.filter(SyncLog.timestamp <= max_ts)
    query = query.order_by(SyncLog.timestamp.asc())

    for log, op in query.yield_per(2000):
        d = log.data or {}
        if not _data_has_any_key(d, DATA_KEYS_FILTER):
            continue
        yield log, op


def _iter_transitions(
    min_ts: Optional[datetime] = None,
    max_ts: Optional[datetime] = None,
) -> Iterable[StageTransition]:
    """Extract stage transitions from eligible logs."""
    seen_in_op: Dict[Tuple[str, int, str], Set[str]] = {}  # (op_id, job, release) -> set of transition keys

    for log, op in _iter_eligible_logs(min_ts, max_ts):
        d = log.data or {}
        jr = _extract_job_release(d, log)
        if not jr:
            continue
        job, release = jr
        source = (op.source_system or "unknown").lower()
        if source not in ("trello", "onedrive"):
            continue

        # List move events
        from_stage, to_stage = _extract_from_to_stage(d)
        if to_stage is not None:
            key = f"{from_stage}|{to_stage}"
            op_key = (log.operation_id, job, release)
            if op_key not in seen_in_op:
                seen_in_op[op_key] = set()
            if key in seen_in_op[op_key]:
                continue
            seen_in_op[op_key].add(key)
            yield StageTransition(
                job=job,
                release=release,
                ts=log.timestamp,
                from_stage=from_stage,
                to_stage=to_stage,
                source=source,
                operation_id=log.operation_id,
                log_id=log.id,
                event_type="list_move",
            )
            continue

        # Excel cell updates (P = ship drives exit from Paint Complete)
        cell = d.get("cell")
        value = d.get("value")
        if cell and value is not None:
            stage = _cell_to_stage(cell, value)
            if stage:
                # Infer from_stage: if we're moving to shipping, we came from Paint complete
                if stage in ("Shipping completed", "Store at MHMW for shipping", "Shipping planning"):
                    from_stage = "Paint complete"
                else:
                    from_stage = None
                key = f"cell_{cell}_{value}"
                op_key = (log.operation_id, job, release)
                if op_key not in seen_in_op:
                    seen_in_op[op_key] = set()
                if key in seen_in_op[op_key]:
                    continue
                seen_in_op[op_key].add(key)
                yield StageTransition(
                    job=job,
                    release=release,
                    ts=log.timestamp,
                    from_stage=from_stage,
                    to_stage=stage,
                    source=source,
                    operation_id=log.operation_id,
                    log_id=log.id,
                    event_type="excel_cell",
                )

        # updated_cells array (Excel update completed - uses "address" or "cell")
        for item in d.get("updated_cells") or []:
            addr = (item.get("address") or item.get("cell")) if isinstance(item, dict) else None
            val = item.get("value") if isinstance(item, dict) else None
            if addr and val is not None:
                stage = _cell_to_stage(addr, val)
                if stage and stage in ("Shipping completed", "Store at MHMW for shipping", "Shipping planning"):
                    from_stage = "Paint complete"
                    key = f"uc_{addr}_{val}"
                    op_key = (log.operation_id, job, release)
                    if op_key not in seen_in_op:
                        seen_in_op[op_key] = set()
                    if key in seen_in_op[op_key]:
                        continue
                    seen_in_op[op_key].add(key)
                    yield StageTransition(
                        job=job,
                        release=release,
                        ts=log.timestamp,
                        from_stage=from_stage,
                        to_stage=stage,
                        source=source,
                        operation_id=log.operation_id,
                        log_id=log.id,
                        event_type="excel_cell",
                    )


def _build_jobs_lookup() -> Dict[Tuple[int, str], Dict[str, Any]]:
    out: Dict[Tuple[int, str], Dict[str, Any]] = {}
    for j in Job.query.yield_per(5000):
        out[(j.job, j.release)] = {
            "job_name": j.job_name,
            "pm": j.pm,
            "released_date": j.released.isoformat() if j.released else None,
        }
    return out


def _transitions_to_timeline_df(
    transitions: List[StageTransition],
    jobs_lookup: Dict[Tuple[int, str], Dict[str, Any]],
) -> pd.DataFrame:
    rows = []
    for t in transitions:
        extra = jobs_lookup.get((t.job, t.release), {})
        rows.append({
            "job": t.job,
            "release": t.release,
            "identifier": f"{t.job}-{t.release}",
            "pm": extra.get("pm"),
            "job_name": extra.get("job_name"),
            "released_date": extra.get("released_date"),
            "timestamp": t.ts,
            "from_stage": t.from_stage,
            "to_stage": t.to_stage,
            "source": t.source,
            "event_type": t.event_type,
            "operation_id": t.operation_id,
            "sync_log_id": t.log_id,
        })
    if not rows:
        return pd.DataFrame(columns=[
            "job", "release", "identifier", "pm", "job_name", "released_date",
            "timestamp", "from_stage", "to_stage", "source", "event_type",
            "operation_id", "sync_log_id",
        ])
    df = pd.DataFrame(rows)
    return df.sort_values(["job", "release", "timestamp", "sync_log_id"], ascending=True)


def _dedupe_consecutive_stages(df: pd.DataFrame) -> pd.DataFrame:
    """Remove consecutive duplicate to_stage within a job-release timeline."""
    if df.empty or len(df) < 2:
        return df
    df = df.copy()
    df["to_stage_prev"] = df.groupby(["job", "release"])["to_stage"].shift(1)
    df = df[df["to_stage"] != df["to_stage_prev"]].drop(columns=["to_stage_prev"], errors="ignore")
    return df


def _compute_stage_durations(df: pd.DataFrame) -> pd.DataFrame:
    """Compute duration in each stage per job-release."""
    if df.empty:
        return pd.DataFrame(columns=[
            "job", "release", "identifier", "pm", "job_name", "stage",
            "stage_start", "stage_end", "duration_hours", "duration_days",
            "source", "operation_id",
        ])
    df = df.copy()
    df["next_ts"] = df.groupby(["job", "release"])["timestamp"].shift(-1)
    df["stage"] = df["to_stage"]
    df["stage_start"] = df["timestamp"]
    df["stage_end"] = df["next_ts"]
    df["duration_seconds"] = (df["stage_end"] - df["stage_start"]).dt.total_seconds()
    df["duration_hours"] = df["duration_seconds"] / 3600.0
    df["duration_days"] = df["duration_hours"] / 24.0
    return df[[
        "job", "release", "identifier", "pm", "job_name", "stage",
        "stage_start", "stage_end", "duration_hours", "duration_days",
        "source", "operation_id",
    ]]


def _agg_duration_stats(durations: pd.DataFrame, group_cols: List[str]) -> pd.DataFrame:
    if durations.empty:
        return pd.DataFrame()
    d = durations.dropna(subset=["duration_hours"]).copy()
    if d.empty:
        return pd.DataFrame()

    def p90(x: pd.Series) -> float:
        return float(x.quantile(0.90))

    g = d.groupby(group_cols, dropna=False)["duration_hours"]
    stats = g.agg(["count", "mean", "median", "min", "max", p90]).reset_index()
    stats = stats.rename(columns={"p90": "p90_hours"})
    stats["mean_days"] = stats["mean"] / 24.0
    stats["median_days"] = stats["median"] / 24.0
    stats["p90_days"] = stats["p90_hours"] / 24.0
    return stats.sort_values(group_cols)


def _write_report_html(out_dir: str, summary: Dict, stage_stats: pd.DataFrame, paint_complete_stats: pd.DataFrame) -> str:
    """Generate client-ready HTML report."""
    path = os.path.join(out_dir, "stage_duration_report.html")
    report_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    stage_table = ""
    if not stage_stats.empty:
        rows = []
        for _, r in stage_stats.iterrows():
            stage = r.get("stage", "N/A")
            count = int(r.get("count", 0))
            mean_d = f"{r.get('mean_days', 0):.1f}"
            median_d = f"{r.get('median_days', 0):.1f}"
            p90_d = f"{r.get('p90_days', 0):.1f}"
            rows.append(f"<tr><td>{stage}</td><td>{count}</td><td>{mean_d}</td><td>{median_d}</td><td>{p90_d}</td></tr>")
        stage_table = "\n".join(rows)

    paint_section = ""
    if not paint_complete_stats.empty:
        rows = []
        for _, r in paint_complete_stats.iterrows():
            stage = r.get("stage", "N/A")
            source = r.get("source", "N/A")
            count = int(r.get("count", 0))
            mean_d = f"{r.get('mean_days', 0):.1f}"
            median_d = f"{r.get('median_days', 0):.1f}"
            rows.append(f"<tr><td>{stage}</td><td>{source}</td><td>{count}</td><td>{mean_d}</td><td>{median_d}</td></tr>")
        paint_section = f"""
        <h2>Paint Complete Duration by Source</h2>
        <table>
            <tr><th>Stage</th><th>Source</th><th>Count</th><th>Mean (days)</th><th>Median (days)</th></tr>
            {"".join(rows)}
        </table>
        """

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Fabrication Stage Duration Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 2rem; }}
        h1 {{ color: #333; }}
        h2 {{ color: #555; margin-top: 1.5rem; }}
        table {{ border-collapse: collapse; margin: 1rem 0; }}
        th, td {{ border: 1px solid #ddd; padding: 0.5rem 1rem; text-align: left; }}
        th {{ background: #f5f5f5; }}
        .meta {{ color: #666; font-size: 0.9rem; margin-bottom: 1rem; }}
    </style>
</head>
<body>
    <h1>Fabrication Stage Duration Report</h1>
    <p class="meta">Generated: {report_date}</p>
    <p class="meta">Filters: {summary.get('filters', {})}</p>

    <h2>Overall Stage Duration Statistics</h2>
    <p>Time jobs spend in each fabrication stage (Paint Complete, Fit Up Complete, etc.) before moving to the next.</p>
    <table>
        <tr><th>Stage</th><th>Count</th><th>Mean (days)</th><th>Median (days)</th><th>P90 (days)</th></tr>
        {stage_table}
    </table>

    {paint_section}

    <h2>Output Files</h2>
    <ul>
        <li>stage_transitions_timeline.csv</li>
        <li>stage_durations.csv</li>
        <li>stage_duration_stats_overall.csv</li>
        <li>stage_duration_stats_by_source.csv</li>
        <li>paint_complete_duration_stats.csv</li>
    </ul>
</body>
</html>
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze stage durations from sync_logs (list moves + Excel updates)."
    )
    parser.add_argument("--out-dir", required=True, help="Directory for report outputs")
    parser.add_argument("--min-ts", default=None, help="Filter: ISO timestamp lower bound (inclusive)")
    parser.add_argument("--max-ts", default=None, help="Filter: ISO timestamp upper bound (inclusive)")
    args = parser.parse_args()

    out_dir = _ensure_out_dir(args.out_dir)
    min_ts = _parse_dt(args.min_ts)
    max_ts = _parse_dt(args.max_ts)

    app = create_app()
    with app.app_context():
        jobs_lookup = _build_jobs_lookup()
        transitions = list(_iter_transitions(min_ts=min_ts, max_ts=max_ts))
        timeline = _transitions_to_timeline_df(transitions, jobs_lookup)
        timeline = _dedupe_consecutive_stages(timeline)
        durations = _compute_stage_durations(timeline)

        # Aggregate stats
        overall_stats = _agg_duration_stats(durations, ["stage"])
        by_source_stats = _agg_duration_stats(durations, ["stage", "source"])
        paint_complete = durations[durations["stage"] == "Paint complete"]
        paint_stats = _agg_duration_stats(paint_complete, ["stage", "source"])

        # Write CSVs
        timeline.to_csv(os.path.join(out_dir, "stage_transitions_timeline.csv"), index=False)
        durations.to_csv(os.path.join(out_dir, "stage_durations.csv"), index=False)
        overall_stats.to_csv(os.path.join(out_dir, "stage_duration_stats_overall.csv"), index=False)
        by_source_stats.to_csv(os.path.join(out_dir, "stage_duration_stats_by_source.csv"), index=False)
        paint_stats.to_csv(os.path.join(out_dir, "paint_complete_duration_stats.csv"), index=False)

        summary = {
            "filters": {
                "min_ts": args.min_ts,
                "max_ts": args.max_ts,
            },
            "counts": {
                "transitions_raw": len(transitions),
                "transitions_deduped": len(timeline),
                "stage_segments": len(durations),
            },
        }
        with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, default=str)

        # HTML report
        html_path = _write_report_html(out_dir, summary, overall_stats, paint_stats)

        print("\nStage duration analysis complete.\n")
        print(f"Transitions (raw): {len(transitions)}")
        print(f"Transitions (deduped): {len(timeline)}")
        print(f"Stage segments: {len(durations)}")
        if not overall_stats.empty:
            print("\nOverall stage duration (days):")
            for _, r in overall_stats.iterrows():
                print(f"  {r['stage']}: count={r['count']}, mean={r['mean_days']:.1f}, median={r['median_days']:.1f}")
        print(f"\nOutputs written to: {out_dir}")
        print(f"  Report: {os.path.basename(html_path)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
