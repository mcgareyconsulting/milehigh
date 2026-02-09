"""
Analyze fabrication stage timelines using SyncOperation + SyncLog data.

Why this exists
---------------
Production DB may not have `job_events`, so we reconstruct stage transitions from
the Trello sync audit trail:
- `sync_logs` contains timestamped messages + JSON `data` blobs
- Trello list moves log fields like `job`, `release`, `to_stage`, `payload_to`, etc.

Outputs
-------
- Console summary
- CSV exports (timelines + aggregated stats)
- JSON summary (for downstream tooling)

Usage
-----
python app/scripts/analyze_stage_durations_from_sync_logs.py \
  --out-dir /tmp/stage_analysis
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

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


STAGE_LOG_MESSAGES = {
    # Primary signals (these contain job/release + stage info in SyncLog.data)
    "JobEvent created for stage update",
    "Duplicate stage update event detected, skipping",
    "Creating stage update event for list move",
}


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    # Accept ISO-ish strings: "2026-02-06", "2026-02-06T12:34:56", etc.
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _ensure_out_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def _normalize_stage(stage: Optional[str]) -> Optional[str]:
    if stage is None:
        return None
    s = str(stage).strip()
    if not s:
        return None
    # Keep canonical strings as-is; only normalize obvious whitespace.
    return " ".join(s.split())


@dataclass(frozen=True)
class StageTransition:
    job: int
    release: str
    ts: datetime
    from_stage: Optional[str]
    to_stage: Optional[str]
    operation_id: Optional[str]
    log_id: int
    message: str


def _extract_job_release(d: Dict[str, Any]) -> Optional[Tuple[int, str]]:
    job = d.get("job")
    release = d.get("release")
    if job is None or release is None:
        return None
    try:
        return int(job), str(release)
    except Exception:
        return None


def _extract_from_to_stage(message: str, d: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """
    Try several known keys written by Trello sync logging.
    We intentionally accept multiple variants since prod data may span versions.
    """
    # Most reliable in "Duplicate..." path
    from_stage = d.get("payload_from") or d.get("from_list") or d.get("old_stage")
    to_stage = d.get("payload_to") or d.get("to_stage") or d.get("to_list") or d.get("new_stage")

    # In "Creating stage update event for list move", the script logs `new_stage`
    # but that is equal to the Trello list name (stage) in current implementation.
    return _normalize_stage(from_stage), _normalize_stage(to_stage)


def _iter_stage_transitions(
    min_ts: Optional[datetime] = None,
    max_ts: Optional[datetime] = None,
) -> Iterable[StageTransition]:
    # Filter to only Trello/OneDrive sync operations (exclude Procore)
    query = (
        SyncLog.query
        .join(SyncOperation, SyncLog.operation_id == SyncOperation.operation_id)
        .filter(SyncLog.message.in_(list(STAGE_LOG_MESSAGES)))
        .filter(SyncOperation.source_system.in_(['trello', 'onedrive']))
    )

    if min_ts:
        query = query.filter(SyncLog.timestamp >= min_ts)
    if max_ts:
        query = query.filter(SyncLog.timestamp <= max_ts)

    query = query.order_by(SyncLog.timestamp.asc())

    for log in query.yield_per(2000):
        d = log.data or {}
        jr = _extract_job_release(d)
        if not jr:
            continue
        from_stage, to_stage = _extract_from_to_stage(log.message, d)
        if to_stage is None:
            continue
        yield StageTransition(
            job=jr[0],
            release=jr[1],
            ts=log.timestamp,
            from_stage=from_stage,
            to_stage=to_stage,
            operation_id=log.operation_id,
            log_id=log.id,
            message=log.message,
        )


def _build_jobs_lookup() -> Dict[Tuple[int, str], Dict[str, Any]]:
    """
    Build a small lookup for enrichment (job_name, pm, etc.).
    Only accesses fields that exist in the Job model.
    """
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
    rows: List[Dict[str, Any]] = []
    for t in transitions:
        extra = jobs_lookup.get((t.job, t.release), {})
        rows.append(
            {
                "job": t.job,
                "release": t.release,
                "pm": extra.get("pm"),
                "job_name": extra.get("job_name"),
                "released_date": extra.get("released_date"),
                "timestamp": t.ts,
                "from_stage": t.from_stage,
                "to_stage": t.to_stage,
                "operation_id": t.operation_id,
                "sync_log_id": t.log_id,
                "message": t.message,
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=[
                "job",
                "release",
                "pm",
                "job_name",
                "released_date",
                "timestamp",
                "from_stage",
                "to_stage",
                "operation_id",
                "sync_log_id",
                "message",
            ]
        )
    df = pd.DataFrame(rows)
    df = df.sort_values(["job", "release", "timestamp", "sync_log_id"], ascending=True)
    return df


def _dedupe_consecutive_stages(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove consecutive duplicate `to_stage` within a job-release timeline.
    """
    if df.empty:
        return df
    df = df.copy()
    df["to_stage_prev"] = df.groupby(["job", "release"])["to_stage"].shift(1)
    df = df[df["to_stage"] != df["to_stage_prev"]].drop(columns=["to_stage_prev"])
    return df


def _compute_stage_durations(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each job-release, compute duration in each stage as the delta until next transition.
    """
    if df.empty:
        return pd.DataFrame(
            columns=[
                "job",
                "release",
                "pm",
                "job_name",
                "stage",
                "stage_start",
                "stage_end",
                "duration_hours",
                "duration_days",
                "operation_id",
            ]
        )

    df = df.copy()
    df["next_ts"] = df.groupby(["job", "release"])["timestamp"].shift(-1)
    df["stage"] = df["to_stage"]
    df["stage_start"] = df["timestamp"]
    df["stage_end"] = df["next_ts"]
    df["duration_seconds"] = (df["stage_end"] - df["stage_start"]).dt.total_seconds()
    df["duration_hours"] = df["duration_seconds"] / 3600.0
    df["duration_days"] = df["duration_hours"] / 24.0

    # Last stage has unknown end time; keep it, but duration will be NaN
    out_cols = [
        "job",
        "release",
        "pm",
        "job_name",
        "stage",
        "stage_start",
        "stage_end",
        "duration_hours",
        "duration_days",
        "operation_id",
    ]
    return df[out_cols]


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


def _compute_stuck_jobs(
    durations: pd.DataFrame,
    now_ts: datetime,
    min_age_days: float = 7.0,
) -> pd.DataFrame:
    """
    Mark items whose current stage has been active longer than `min_age_days`.
    We compute "current stage age" using the last transition timestamp.
    """
    if durations.empty:
        return pd.DataFrame()
    last = durations[durations["stage_end"].isna()].copy()
    if last.empty:
        return pd.DataFrame()
    last["current_stage_age_days"] = (now_ts - last["stage_start"]).dt.total_seconds() / 86400.0
    last = last[last["current_stage_age_days"] >= min_age_days]
    return last.sort_values("current_stage_age_days", ascending=False)


def _sync_operation_stats(min_ts: Optional[datetime], max_ts: Optional[datetime]) -> pd.DataFrame:
    # Filter to only Trello/OneDrive sync operations (exclude Procore)
    query = SyncOperation.query.filter(SyncOperation.source_system.in_(['trello', 'onedrive']))
    if min_ts:
        query = query.filter(SyncOperation.started_at >= min_ts)
    if max_ts:
        query = query.filter(SyncOperation.started_at <= max_ts)

    rows: List[Dict[str, Any]] = []
    for op in query.yield_per(5000):
        rows.append(
            {
                "operation_id": op.operation_id,
                "operation_type": op.operation_type,
                "status": str(op.status),
                "source_system": op.source_system,
                "source_id": op.source_id,
                "started_at": op.started_at,
                "completed_at": op.completed_at,
                "duration_seconds": op.duration_seconds,
                "records_processed": op.records_processed,
                "records_updated": op.records_updated,
                "records_created": op.records_created,
                "records_failed": op.records_failed,
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # Helpful rolled up view
    df["duration_hours"] = df["duration_seconds"] / 3600.0
    return df


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze stage durations from SyncLog/SyncOperation.")
    parser.add_argument("--out-dir", required=True, help="Directory to write CSV/JSON outputs")
    parser.add_argument("--min-ts", default=None, help="Filter: ISO timestamp lower bound (inclusive)")
    parser.add_argument("--max-ts", default=None, help="Filter: ISO timestamp upper bound (inclusive)")
    parser.add_argument("--stuck-min-days", type=float, default=7.0, help="Flag jobs stuck in current stage >= N days")
    args = parser.parse_args()

    out_dir = _ensure_out_dir(args.out_dir)
    min_ts = _parse_dt(args.min_ts)
    max_ts = _parse_dt(args.max_ts)

    app = create_app()
    with app.app_context():
        jobs_lookup = _build_jobs_lookup()

        transitions = list(_iter_stage_transitions(min_ts=min_ts, max_ts=max_ts))
        timeline = _transitions_to_timeline_df(transitions, jobs_lookup)
        timeline = _dedupe_consecutive_stages(timeline)

        durations = _compute_stage_durations(timeline)

        # Aggregate stats
        overall_stage_stats = _agg_duration_stats(durations, ["stage"])
        pm_stage_stats = _agg_duration_stats(durations, ["pm", "stage"])

        # Stuck items
        now_ts = datetime.utcnow()
        stuck = _compute_stuck_jobs(durations, now_ts=now_ts, min_age_days=args.stuck_min_days)

        # Sync operation stats
        ops = _sync_operation_stats(min_ts=min_ts, max_ts=max_ts)

        # Write outputs
        timeline_csv = os.path.join(out_dir, "stage_transitions_timeline.csv")
        durations_csv = os.path.join(out_dir, "stage_durations.csv")
        stage_stats_csv = os.path.join(out_dir, "stage_duration_stats_overall.csv")
        pm_stage_stats_csv = os.path.join(out_dir, "stage_duration_stats_by_pm.csv")
        stuck_csv = os.path.join(out_dir, "stuck_jobs_current_stage.csv")
        ops_csv = os.path.join(out_dir, "sync_operations.csv")

        timeline.to_csv(timeline_csv, index=False)
        durations.to_csv(durations_csv, index=False)
        overall_stage_stats.to_csv(stage_stats_csv, index=False)
        pm_stage_stats.to_csv(pm_stage_stats_csv, index=False)
        stuck.to_csv(stuck_csv, index=False)
        ops.to_csv(ops_csv, index=False)

        summary = {
            "filters": {
                "min_ts": args.min_ts,
                "max_ts": args.max_ts,
                "stuck_min_days": args.stuck_min_days,
            },
            "counts": {
                "transitions_raw": len(transitions),
                "transitions_deduped": int(len(timeline)),
                "stage_segments": int(len(durations)),
                "stuck_jobs": int(len(stuck)) if isinstance(stuck, pd.DataFrame) else 0,
                "sync_operations": int(len(ops)),
            },
            "output_files": {
                "timeline_csv": timeline_csv,
                "durations_csv": durations_csv,
                "stage_stats_csv": stage_stats_csv,
                "pm_stage_stats_csv": pm_stage_stats_csv,
                "stuck_csv": stuck_csv,
                "ops_csv": ops_csv,
            },
        }
        summary_path = os.path.join(out_dir, "summary.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, default=str)

        # Console summary
        print("\nStage analysis complete.\n")
        print(f"Transitions (raw): {len(transitions)}")
        print(f"Transitions (deduped): {len(timeline)}")
        print(f"Stage segments w/ durations: {durations['duration_hours'].notna().sum() if not durations.empty else 0}")
        print(f"Stuck jobs (>= {args.stuck_min_days} days in current stage): {len(stuck) if isinstance(stuck, pd.DataFrame) else 0}")
        print(f"Sync operations: {len(ops)}")
        print(f"\nOutputs written to: {out_dir}")
        print(f"- {os.path.basename(timeline_csv)}")
        print(f"- {os.path.basename(durations_csv)}")
        print(f"- {os.path.basename(stage_stats_csv)}")
        print(f"- {os.path.basename(pm_stage_stats_csv)}")
        print(f"- {os.path.basename(stuck_csv)}")
        print(f"- {os.path.basename(ops_csv)}")
        print(f"- {os.path.basename(summary_path)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

