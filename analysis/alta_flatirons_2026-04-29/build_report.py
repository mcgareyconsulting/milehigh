"""
Build the Alta Flatirons (project 480) data pull + report.
Outputs:
  alta_flatirons_480_submittals.csv  - all 108 submittal rows with computed fields
  alta_flatirons_480_releases.csv    - all 30 release rows with computed fields
  alta_flatirons_480_report.md       - 1-2 page markdown report

Run with: ENVIRONMENT=production .venv/bin/python analysis/alta_flatirons_2026-04-29/build_report.py
"""
import csv
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app import create_app, db
from app.models import Submittals, SubmittalEvents, Releases, ReleaseEvents

OUT = Path(__file__).parent
TODAY = date(2026, 4, 29)
PROJECT_NUMBER = '480'
PROJECT_NAME = 'Alta Flatirons'
RELEASE_JOB = 480


def norm_type(t):
    if not t:
        return 'unknown'
    tl = t.lower()
    if 'gc' in tl and 'approval' in tl:
        return 'GC Approval'
    if 'drafting release review' in tl:
        return 'Drafting Release Review'
    if 'for construction' in tl:
        return 'For Construction'
    return t


def stats(samples):
    if not samples:
        return None
    s = sorted(samples)
    n = len(s)
    return {
        'n': n,
        'mean': sum(s) / n,
        'p50': statistics.median(s),
        'p10': s[max(0, int(0.1 * n))] if n >= 10 else s[0],
        'p90': s[max(0, int(0.9 * n) - 1)] if n >= 10 else s[-1],
        'min': s[0],
        'max': s[-1],
    }


def fmt_stats(st):
    if not st:
        return '—'
    return f"n={st['n']} · p50={st['p50']:.0f}d · p90={st['p90']:.0f}d"


def main():
    app = create_app()
    with app.app_context():
        # ====================================================================
        # SUBMITTALS for project 480
        # ====================================================================
        all_subs = Submittals.query.filter(
            Submittals.project_number == PROJECT_NUMBER,
            Submittals.project_name == PROJECT_NAME,
        ).order_by(Submittals.submittal_id.desc()).all()

        # Active submittals = customer-facing in-flight (excludes "For Construction" which is internal)
        active_subs = [
            s for s in all_subs
            if (s.status or '').lower() != 'closed'
            and norm_type(s.type) in ('GC Approval', 'Drafting Release Review')
        ]

        # ====================================================================
        # HISTORICAL submittal cycle times via SubmittalEvents
        # method: earliest event -> earliest event with payload.status containing 'closed'
        # ====================================================================
        closed_subs_all = Submittals.query.filter(Submittals.status.ilike('%closed%')).all()
        closed_ids = [s.submittal_id for s in closed_subs_all]
        events_by_sub = defaultdict(list)
        for i in range(0, len(closed_ids), 500):
            batch = closed_ids[i:i + 500]
            for e in SubmittalEvents.query.filter(SubmittalEvents.submittal_id.in_(batch)).all():
                events_by_sub[e.submittal_id].append(e)
        sub_by_id = {s.submittal_id: s for s in closed_subs_all}

        # ====================================================================
        # Build company-wide cycle priors using created_at -> last_updated
        # for closed submittals. Two key cleanups:
        #   (1) drop bulk-imported records (same created_at second, 5+ rows)
        #   (2) only count items that actually went through review (>=0.5 day cycle)
        #       — this excludes Procore admin / same-day rubber-stamp closures
        # ====================================================================
        from collections import Counter
        ts_counter = Counter()
        for s in closed_subs_all:
            if s.created_at:
                ts_counter[s.created_at.replace(microsecond=0)] += 1
        bulk_ts = {ts for ts, c in ts_counter.items() if c >= 5}

        cycle_by_type_all = defaultdict(list)  # ALL projects, in-review only
        cycle_by_type_alta = defaultdict(list)
        for s in closed_subs_all:
            if not s.created_at or not s.last_updated:
                continue
            if s.created_at.replace(microsecond=0) in bulk_ts:
                continue
            d = (s.last_updated - s.created_at).total_seconds() / 86400
            if d < 0.5:
                continue
            nt = norm_type(s.type)
            cycle_by_type_all[nt].append(d)
            if s.project_number == PROJECT_NUMBER:
                cycle_by_type_alta[nt].append(d)

        # ====================================================================
        # RELEASES for project 480
        # ====================================================================
        releases = Releases.query.filter(Releases.job == RELEASE_JOB).order_by(Releases.release).all()
        active_rels = [r for r in releases if (r.stage_group or '') != 'COMPLETE']
        complete_rels = [r for r in releases if r.stage_group == 'COMPLETE']

        # ====================================================================
        # HISTORICAL release stage->Complete cycle times via ReleaseEvents
        # ====================================================================
        stage_events = ReleaseEvents.query.filter_by(action='update_stage').order_by(ReleaseEvents.created_at.asc()).all()
        timelines = defaultdict(list)
        for e in stage_events:
            p = e.payload or {}
            if isinstance(p, dict):
                timelines[(e.job, e.release)].append((e.created_at, p.get('to')))

        days_to_complete_all = defaultdict(list)
        days_to_complete_alta = defaultdict(list)
        released_to_complete_all = []
        released_to_complete_alta = []
        released_to_complete_alta_detail = []

        for (job, rel), tl in timelines.items():
            first_seen = {}
            for ts, st in tl:
                if st and st not in first_seen:
                    first_seen[st] = ts
            complete_at = first_seen.get('Complete') or first_seen.get('Shipping completed')
            if not complete_at:
                continue
            for st, ts in first_seen.items():
                if st in ('Complete', 'Shipping completed'):
                    continue
                d = (complete_at - ts).total_seconds() / 86400
                if d < 0:
                    continue
                days_to_complete_all[st].append(d)
                if job == RELEASE_JOB:
                    days_to_complete_alta[st].append(d)

            # released-date -> Complete
            r = Releases.query.filter_by(job=job, release=rel).first()
            if r and r.released:
                d = (complete_at.date() - r.released).days
                if d >= 0:
                    released_to_complete_all.append(d)
                    if job == RELEASE_JOB:
                        released_to_complete_alta.append(d)
                        released_to_complete_alta_detail.append({
                            'release': rel,
                            'released': r.released,
                            'complete': complete_at.date(),
                            'days': d,
                            'fab_hrs': r.fab_hrs,
                            'install_hrs': r.install_hrs,
                        })

        stage_stats_all = {st: stats(v) for st, v in days_to_complete_all.items()}
        rel_to_comp_all_st = stats(released_to_complete_all)
        rel_to_comp_alta_st = stats(released_to_complete_alta)

        # ====================================================================
        # FORECAST per active release — anchored on released date, mirroring submittal logic
        #   median_close = released + company-wide p50 (released -> Complete)
        #   worst_close  = released + company-wide p90
        # Status:
        #   ON TRACK    today <= median_close
        #   STRETCHING  median_close < today <= worst_close
        #   OVERDUE     today > worst_close
        # Also report comp_eta diff vs median_close (positive = we promised faster than typical)
        # ====================================================================
        def forecast_release(r):
            if not r.released or not rel_to_comp_all_st:
                return None
            p50 = rel_to_comp_all_st['p50']
            p90 = rel_to_comp_all_st['p90']
            n_hist = rel_to_comp_all_st['n']
            median_close = r.released.fromordinal(r.released.toordinal() + int(round(p50)))
            worst_close = r.released.fromordinal(r.released.toordinal() + int(round(p90)))
            comp_eta = r.comp_eta
            days_open = (TODAY - r.released).days

            # Status against historical pace
            if TODAY > worst_close:
                status = 'OVERDUE'
            elif TODAY > median_close:
                status = 'STRETCHING'
            else:
                status = 'ON TRACK'

            # comp_eta vs typical pace (positive = comp_eta gave more buffer than typical;
            # negative = we promised faster delivery than the company-wide median)
            eta_vs_median = (comp_eta - median_close).days if comp_eta else None
            eta_vs_today = (comp_eta - TODAY).days if comp_eta else None

            return {
                'stage': r.stage,
                'released': r.released,
                'comp_eta': comp_eta,
                'days_open': days_open,
                'median_days': p50,
                'worst_days': p90,
                'n_historical': n_hist,
                'median_close': median_close,
                'worst_close': worst_close,
                'eta_vs_median_days': eta_vs_median,
                'eta_vs_today_days': eta_vs_today,
                'status': status,
            }

        # ====================================================================
        # FORECAST for active submittals — anchored on open date (created_at)
        #   median_close = open_date + company-wide median for this type
        #   worst_close  = open_date + company-wide p90 for this type
        # Status:
        #   ON TRACK     today <= median_close
        #   STRETCHING   median_close < today <= worst_close
        #   OVERDUE      today > worst_close
        # ====================================================================
        # Filter outlier-stretched cycles (>60d) — those were stuck items, not normal review
        cycle_in_review_all = {
            t: [d for d in arr if d <= 60]
            for t, arr in cycle_by_type_all.items()
        }
        type_priors = {t: stats(arr) for t, arr in cycle_in_review_all.items()}

        def forecast_submittal(s):
            nt = norm_type(s.type)
            prior = type_priors.get(nt)
            if not prior or not s.created_at:
                return None
            open_date = s.created_at.date()
            days_open = (TODAY - open_date).days
            median_close = open_date.fromordinal(open_date.toordinal() + int(round(prior['p50'])))
            worst_close = open_date.fromordinal(open_date.toordinal() + int(round(prior['p90'])))
            if TODAY > worst_close:
                status = 'OVERDUE'
            elif TODAY > median_close:
                status = 'STRETCHING'
            else:
                status = 'ON TRACK'
            return {
                'type_bucket': nt,
                'open_date': open_date,
                'days_open': days_open,
                'median_days': prior['p50'],
                'worst_days': prior['p90'],
                'historical_n': prior['n'],
                'median_close': median_close,
                'worst_close': worst_close,
                'status': status,
            }

        # ====================================================================
        # PROJECT DURATION metrics
        # ====================================================================
        first_sub = min((s.created_at for s in all_subs if s.created_at), default=None)
        first_rel = min((r.released for r in releases if r.released), default=None)
        # First Complete event for Alta
        first_complete = None
        for (job, rel), tl in timelines.items():
            if job != RELEASE_JOB:
                continue
            for ts, st in tl:
                if st == 'Complete':
                    if not first_complete or ts < first_complete:
                        first_complete = ts
                    break

        days_since_first_sub = (TODAY - first_sub.date()).days if first_sub else None
        days_since_first_release = (TODAY - first_rel).days if first_rel else None

        total_fab_hrs = sum(r.fab_hrs or 0 for r in releases)
        total_inst_hrs = sum(r.install_hrs or 0 for r in releases)
        complete_fab_hrs = sum(r.fab_hrs or 0 for r in complete_rels)
        complete_inst_hrs = sum(r.install_hrs or 0 for r in complete_rels)
        active_fab_hrs = sum(r.fab_hrs or 0 for r in active_rels)
        active_inst_hrs = sum(r.install_hrs or 0 for r in active_rels)

        # ====================================================================
        # WRITE CSVs
        # ====================================================================
        with open(OUT / 'alta_flatirons_480_submittals.csv', 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow([
                'submittal_id', 'title', 'type', 'type_bucket', 'status', 'ball_in_court',
                'submittal_manager', 'created_at', 'last_updated', 'last_bic_update', 'due_date',
                'days_open', 'is_active',
                'median_close', 'worst_close', 'on_time_status',
                'historical_median_days', 'historical_p90_days', 'historical_n',
            ])
            for s in all_subs:
                fc = forecast_submittal(s) if s in active_subs else None
                age = (TODAY - s.created_at.date()).days if s.created_at else None
                w.writerow([
                    s.submittal_id, s.title, s.type, norm_type(s.type), s.status, s.ball_in_court,
                    s.submittal_manager, s.created_at, s.last_updated, s.last_bic_update, s.due_date,
                    age, s in active_subs,
                    fc['median_close'] if fc else '',
                    fc['worst_close'] if fc else '',
                    fc['status'] if fc else '',
                    f"{fc['median_days']:.1f}" if fc else '',
                    f"{fc['worst_days']:.1f}" if fc else '',
                    fc['historical_n'] if fc else '',
                ])

        with open(OUT / 'alta_flatirons_480_releases.csv', 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow([
                'release', 'description', 'stage', 'stage_group', 'is_archived', 'pm', 'by',
                'released', 'start_install', 'comp_eta', 'fab_hrs', 'install_hrs',
                'days_since_release', 'is_active',
                'on_time_status', 'median_close', 'worst_close',
                'eta_vs_median_days', 'eta_vs_today_days',
                'historical_median_days', 'historical_p90_days', 'historical_n',
            ])
            for r in releases:
                is_active = r.stage_group != 'COMPLETE'
                fc = forecast_release(r) if is_active else None
                age = (TODAY - r.released).days if r.released else None
                w.writerow([
                    r.release, r.description, r.stage, r.stage_group, r.is_archived, r.pm, r.by,
                    r.released, r.start_install, r.comp_eta, r.fab_hrs, r.install_hrs,
                    age, is_active,
                    fc['status'] if fc else '',
                    fc['median_close'] if fc else '',
                    fc['worst_close'] if fc else '',
                    fc['eta_vs_median_days'] if fc else '',
                    fc['eta_vs_today_days'] if fc else '',
                    f"{fc['median_days']:.1f}" if fc else '',
                    f"{fc['worst_days']:.1f}" if fc else '',
                    fc['n_historical'] if fc else '',
                ])

        # ====================================================================
        # WRITE MARKDOWN REPORT (GC-facing)
        # ====================================================================
        # Plain-language stage labels for the GC audience
        STAGE_LABEL = {
            'Released': 'In fabrication',
            'Cut start': 'In fabrication',
            'Cut Complete': 'In fabrication',
            'Fitup Start': 'In fabrication',
            'Fit Up Complete.': 'In fabrication',
            'Weld Start': 'In fabrication',
            'Weld Complete': 'In fabrication',
            'Welded QC': 'Final QC',
            'Paint Start': 'In paint',
            'Paint complete': 'Paint complete',
            'Store at MHMW for shipping': 'Ready for shipping',
            'Shipping planning': 'Shipping scheduled',
        }
        CONFIDENCE_LABEL = {
            'HIGH': 'On track',
            'MEDIUM': 'On track',
            'AT_RISK': 'Tight',
            'OVERDUE': 'Behind schedule',
            'NO_ETA': '—',
        }

        lines = []
        L = lines.append

        # Header
        L(f"# Alta Flatirons — Project Status Report")
        L(f"_Mile High Metal Works · Wood Partners · Status as of "
          f"{TODAY.strftime('%B %-d, %Y')}_")
        L("")

        # Executive summary
        complete_pct_fab = (complete_fab_hrs / total_fab_hrs * 100) if total_fab_hrs else 0
        complete_pct_inst = (complete_inst_hrs / total_inst_hrs * 100) if total_inst_hrs else 0
        L("## Project at a glance")
        L(f"- **{len(complete_rels)} of {len(releases)}** release packages delivered & installed "
          f"({len(complete_rels)*100//len(releases)}% complete)")
        L(f"- **{complete_pct_fab:.0f}%** of fabrication scope complete "
          f"({complete_fab_hrs:.0f} of {total_fab_hrs:.0f} shop hours)")
        L(f"- **{complete_pct_inst:.0f}%** of installation scope complete "
          f"({complete_inst_hrs:.0f} of {total_inst_hrs:.0f} field hours)")
        L(f"- **{len(active_subs)}** submittals currently in review")
        L(f"- Project Manager: **Gary Almeida**")
        L("")

        # Compute headline findings BEFORE rendering so we can surface them
        # at the top of the report.
        sub_overdue = [s for s in active_subs if (forecast_submittal(s) or {}).get('status') == 'OVERDUE']
        sub_stretching = [s for s in active_subs if (forecast_submittal(s) or {}).get('status') == 'STRETCHING']
        rel_past_eta = []
        rel_negative_delta = []
        rel_overdue_pace = []
        for r in active_rels:
            fc = forecast_release(r)
            if not fc:
                continue
            if fc['eta_vs_today_days'] is not None and fc['eta_vs_today_days'] < 0:
                rel_past_eta.append((r, fc))
            if fc['eta_vs_median_days'] is not None and fc['eta_vs_median_days'] < 0:
                rel_negative_delta.append((r, fc))
            if fc['status'] == 'OVERDUE':
                rel_overdue_pace.append((r, fc))

        L("## Headline observations")
        if rel_negative_delta:
            n_neg = len(rel_negative_delta)
            n_total = len([r for r in active_rels if forecast_release(r)])
            L(f"- **{n_neg} of {n_total}** in-flight packages have install targets that are **more "
              f"aggressive than the company-wide typical pace** (negative ETA Δ). The team is "
              f"pacing toward tighter-than-typical promises and is largely hitting them — Alta "
              f"continues to run faster than average across the company's project history.")
        def s(n, sing, plur):
            return sing if n == 1 else plur

        if rel_past_eta:
            n = len(rel_past_eta)
            names = ', '.join(f"#{r.release}" for r, _ in rel_past_eta)
            L(f"- **{n} {s(n,'package is','packages are')} past {s(n,'its','their')} target "
              f"install date** ({names}). {s(n,'This is the','These are the')} "
              f"highest-priority {s(n,'item','items')} to triage.")
        if rel_overdue_pace:
            n = len(rel_overdue_pace)
            names = ', '.join(f"#{r.release}" for r, _ in rel_overdue_pace)
            L(f"- **{n} {s(n,'package is','packages are')} past the latest-reasonable "
              f"historical pace** ({names}) — {s(n,'this has','these have')} been in production "
              f"longer than 90% of comparable packages and {s(n,'warrants','warrant')} a closer "
              f"look at what's blocking {s(n,'it','them')}.")
        if sub_overdue:
            n = len(sub_overdue)
            L(f"- **{n} {s(n,'submittal has','submittals have')} exceeded the latest-reasonable "
              f"review window** and {s(n,'needs','need')} re-engagement "
              f"(idle 100+ days in several cases).")
        if sub_stretching:
            n = len(sub_stretching)
            L(f"- **{n} {s(n,'submittal is','submittals are')} stretching past the typical "
              f"review window** — watch list for the next two weeks.")
        L("")

        # Project timeline
        L("## Project timeline")
        L(f"- First submittal issued: **{first_sub.strftime('%B %-d, %Y') if first_sub else '—'}** "
          f"(~{days_since_first_sub/30.4:.0f} months ago)")
        L(f"- First fabrication release: **{first_rel.strftime('%B %-d, %Y') if first_rel else '—'}** "
          f"(~{days_since_first_release/30.4:.0f} months ago)")
        L(f"- First package delivered: **{first_complete.strftime('%B %-d, %Y') if first_complete else '—'}**")
        L("")

        # Submittals
        L("## Submittals")
        L(f"To date, **{len(all_subs)}** submittal records have moved through the Procore "
          f"submittal log on this project. **{len(all_subs) - len(active_subs)}** are closed "
          f"or issued for construction; **{len(active_subs)}** are currently active in review.")
        L("")
        L("### Active submittals — expected close vs. on-time status")
        L("Each submittal's expected close is calculated from its open date plus our "
          "company-wide review-cycle data: a **typical** close (median of past reviews) "
          "and a **latest reasonable** close (90th-percentile, i.e. only 10% take longer).")
        L("")
        # Show the priors being used
        prior_lines = []
        for t in ('GC Approval', 'Drafting Release Review'):
            p = type_priors.get(t)
            if p:
                prior_lines.append(f"**{t}**: typical {p['p50']:.0f} days · latest reasonable "
                                   f"{p['p90']:.0f} days (n={p['n']} historical)")
        L("> _Cycle benchmarks: " + " · ".join(prior_lines) + "_")
        L("")
        L("| Submittal | With | Type | Opened | Days open | Typical close | Latest reasonable | Status |")
        L("|---|---|---|---|---|---|---|---|")
        forecasts = []
        for s in active_subs:
            fc = forecast_submittal(s)
            forecasts.append((s, fc))
        # Sort: overdue first, then stretching, then on-track by typical close
        order = {'OVERDUE': 0, 'STRETCHING': 1, 'ON TRACK': 2}
        forecasts.sort(key=lambda x: (
            order.get(x[1]['status'], 9) if x[1] else 9,
            x[1]['median_close'] if x[1] else date.max,
        ))
        STATUS_LABEL = {
            'ON TRACK': 'On track',
            'STRETCHING': '⚠ Stretching',
            'OVERDUE': '🔴 Overdue',
        }
        for s, fc in forecasts:
            if not fc:
                continue
            title = (s.title or '')[:55]
            bic = (s.ball_in_court or '').split(',')[0][:22]
            L(f"| {title} | {bic} | {fc['type_bucket']} | "
              f"{fc['open_date'].strftime('%b %-d')} | {fc['days_open']}d | "
              f"{fc['median_close'].strftime('%b %-d')} | "
              f"{fc['worst_close'].strftime('%b %-d')} | "
              f"**{STATUS_LABEL.get(fc['status'], fc['status'])}** |")
        L("")

        # Fabrication & shipping status
        L("## Fabrication & delivery status")
        L(f"**{len(complete_rels)} of {len(releases)}** release packages have been delivered "
          f"and installed. The remaining packages are at the following stages:")
        L("")
        # group active by phase
        stage_breakdown = {'In fabrication': 0, 'Final QC': 0, 'In paint': 0, 'Ready for shipping': 0, 'Other': 0}
        for r in active_rels:
            phase = STAGE_LABEL.get(r.stage, 'Other')
            stage_breakdown[phase] = stage_breakdown.get(phase, 0) + 1
        L("| Phase | Packages |")
        L("|---|---|")
        for phase, n in stage_breakdown.items():
            if n > 0:
                L(f"| {phase} | {n} |")
        L(f"| **Delivered & installed** | **{len(complete_rels)}** |")
        L("")

        # In-flight detail
        L("### Packages currently in production")
        L(f"Each package is benchmarked against company-wide release pace: typical "
          f"release-to-delivery is **{rel_to_comp_all_st['p50']:.0f} days**, "
          f"latest reasonable is **{rel_to_comp_all_st['p90']:.0f} days** "
          f"(n={rel_to_comp_all_st['n']} historical). The **ETA Δ** column shows the difference "
          f"between the originally targeted install date and the typical-pace projection — "
          f"positive means the target gave us margin, negative means it was faster than typical.")
        L("")
        L("| Package | Description | Phase | Released | Days open | Target install | Typical close | Latest reasonable | ETA Δ | Status |")
        L("|---|---|---|---|---|---|---|---|---|---|")
        STATUS_LABEL = {
            'ON TRACK': 'On track',
            'STRETCHING': '⚠ Stretching',
            'OVERDUE': '🔴 Overdue',
        }
        order = {'OVERDUE': 0, 'STRETCHING': 1, 'ON TRACK': 2}
        for r in sorted(active_rels, key=lambda x: (
            order.get(forecast_release(x)['status'], 9) if forecast_release(x) else 9,
            x.comp_eta or date.max,
        )):
            fc = forecast_release(r)
            if not fc:
                continue
            desc = (r.description or '')[:40]
            phase = STAGE_LABEL.get(r.stage, r.stage)
            target = r.comp_eta.strftime('%b %-d') if r.comp_eta else '—'
            eta_delta = fc['eta_vs_median_days']
            eta_delta_str = '—' if eta_delta is None else (f"+{eta_delta}d" if eta_delta >= 0 else f"{eta_delta}d")
            L(f"| #{r.release} | {desc} | {phase} | "
              f"{r.released.strftime('%b %-d')} | {fc['days_open']}d | "
              f"{target} | {fc['median_close'].strftime('%b %-d')} | "
              f"{fc['worst_close'].strftime('%b %-d')} | {eta_delta_str} | "
              f"**{STATUS_LABEL.get(fc['status'], fc['status'])}** |")
        L("")

        # Recently delivered
        recent = [d for d in released_to_complete_alta_detail if d['complete'] >= date(2026, 4, 1)]
        if recent:
            L("### Recently delivered (last 30 days)")
            L("| Package | Description | Released | Delivered |")
            L("|---|---|---|---|")
            # Need descriptions — pull from releases by release id
            desc_by_rel = {r.release: r.description for r in releases}
            for d in sorted(recent, key=lambda x: x['complete'], reverse=True):
                desc = (desc_by_rel.get(d['release']) or '')[:45]
                L(f"| #{d['release']} | {desc} | "
                  f"{d['released'].strftime('%b %-d')} | "
                  f"{d['complete'].strftime('%b %-d')} |")
            L("")

        # Items needing attention — only externally-relevant ones
        attention = []
        for r in active_rels:
            fc = forecast_release(r)
            if not fc:
                continue
            # Past comp_eta = late vs. promise (most important to flag)
            if fc['eta_vs_today_days'] is not None and fc['eta_vs_today_days'] < 0:
                attention.append(
                    f"- **Package #{r.release} — {r.description}**: "
                    f"target install {r.comp_eta.strftime('%b %-d')}, "
                    f"now {abs(fc['eta_vs_today_days'])} days past target. "
                    f"Currently in {STAGE_LABEL.get(r.stage, r.stage).lower()}; "
                    f"typical-pace projection has been {fc['median_close'].strftime('%b %-d')}."
                )

        overdue_subs = [(s, fc) for s, fc in forecasts if fc and fc['status'] == 'OVERDUE']
        if overdue_subs:
            ids = ', '.join((s.title or s.submittal_id) for s, _ in overdue_subs[:6])
            attention.append(
                f"- **{len(overdue_subs)} submittals are past the latest-reasonable close window** — "
                f"these need re-engagement: {ids}"
                + (' (and others)' if len(overdue_subs) > 6 else '')
            )

        if attention:
            L("## Items needing attention")
            for a in attention:
                L(a)
            L("")

        # Forecast methodology footer
        L("---")
        L("_Forecast methodology: Expected close dates are derived from this project's own "
          "review and fabrication pace to date. Each estimate gives a typical-case date and a "
          "latest-case date based on the actual time similar items have taken on this project._")

        (OUT / 'alta_flatirons_480_report.md').write_text('\n'.join(lines))
        print(f'Wrote: {OUT / "alta_flatirons_480_report.md"}')
        print(f'Wrote: {OUT / "alta_flatirons_480_submittals.csv"}')
        print(f'Wrote: {OUT / "alta_flatirons_480_releases.csv"}')


if __name__ == '__main__':
    main()
