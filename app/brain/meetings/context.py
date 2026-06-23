"""Assemble the two context streams a meeting feeds — one per output.

A meeting produces two outputs, each grounded by a different context:

  to-do EXTRACTION  ← assemble_extraction_context(meeting)
      agenda / notes the user dropped in (authored "before" view), plus a LIGHT job-state
      line per likely-discussed entity (canonical names/tokens, NO event history) and any
      LEARNED GUIDANCE from past meetings. Purpose: match the to-dos better.

  meeting SUMMARY   ← build_runtime_events(meeting)
      the release/submittal event updates that landed DURING the meeting window
      [occurred_at, ended_at|now] — "what changed in the systems while we met". Purpose:
      ground the summary in real activity, not just what was said.

Entity scoping is shared and hybrid: when the meeting is pinned to a project_number we use
that project's releases/submittals; otherwise we scan the transcript + agenda for job tokens
and fuzzy-match active jobs (reusing owner_match's candidate builder). Active `alias` signals
normalize garbled names BEFORE matching so grounding improves up front.
"""
import re
from datetime import datetime, timedelta

from app.models import (
    db, Releases, Submittals, ReleaseEvents, SubmittalEvents, ExtractionSignal,
)
from app.brain.meetings import owner_match
from app.brain.meetings.extract import MAX_CONTEXT_CHARS
from app.logging_config import get_logger

logger = get_logger(__name__)

# Bounds that keep context from crowding out the transcript or ballooning cost.
MAX_ENTITIES = 15          # cap submittals brought into context
# A multi-job production standup touches many jobs and drift detection needs the SPECIFIC
# release the room named in context, so releases get a larger budget than submittals and a
# per-job cap keeps one big job (480 has 40+ releases) from flooding the set.
MAX_RELEASES = 25
PER_JOB_RELEASES = 6       # releases per name-only-mentioned job (explicit tokens bypass this)
EVENTS_PER_ENTITY = 8      # most recent in-window events shown per entity (summary)
MAX_GUIDANCE = 6           # top learned patterns injected as extraction guidance

_JOB_TOKEN = re.compile(r"\b(\d{2,4})-(\w+)\b")  # '480-146' — same shape used in extract


# --- alias normalization (learnings feedback) -------------------------------- #

def _active_aliases():
    """Active garbled→canonical name aliases learned from past meetings."""
    return ExtractionSignal.query.filter_by(signal_type="alias", active=True).all()


def apply_aliases(text):
    """Replace learned garbled names with their canonical job name (case-insensitive),
    so fuzzy matching sees the real name. No-op when nothing has been learned yet."""
    if not text:
        return text or ""
    for sig in _active_aliases():
        if sig.key and sig.value:
            text = re.sub(re.escape(sig.key), sig.value, text, flags=re.IGNORECASE)
    return text


# --- entity scoping (shared by both context streams) ------------------------- #

def _int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _releases_for_job(job_number):
    jn = _int(job_number)
    if jn is None:
        return []
    return (Releases.query
            .filter(Releases.job == jn, Releases.is_archived.is_(False))
            .all())


def _rank_releases_for_job(releases, text_tokens):
    """Order a job's releases by how well their scope description overlaps the meeting text
    (so 'P3 canopies' surfaces 480-625 ahead of its 40+ siblings), then by release token."""
    def score(r):
        desc_tokens = set(owner_match._tokens(f"{r.description or ''} {r.job_name or ''}"))
        return (-len(desc_tokens & text_tokens), str(r.release))
    return sorted(releases, key=score)


def relevant_entities(meeting):
    """(releases, submittals) most likely discussed — ADDITIVE, release-aware scoping.

    project_number SEEDS the set (its rows are always included) but never EXCLUDES: we
    always also scan transcript + agenda for explicit job-release tokens and fuzzy-match
    active jobs (after learned aliases), then union. This fixes the v2 bug where a
    multi-job production standup pinned to one project_number dropped every other job that
    was actually discussed (and so could never be drift-checked).

    Release-aware: a specifically-named release (e.g. '480-625') is always pulled in, while
    a job mentioned only by name contributes its most scope-relevant releases — not all of
    them — so one big job can't flood the budget.
    """
    text = apply_aliases(f"{meeting.transcript or ''}\n{meeting.agenda_text or ''}")
    text_tokens = set(owner_match._tokens(text))

    # Explicit 'JOB-REL' tokens — capture both the job AND the specific release the room
    # named, and count job mentions to rank when we exceed the cap.
    explicit = {(m.group(1), m.group(2)) for m in _JOB_TOKEN.finditer(text)}
    explicit_by_job, job_mentions = {}, {}
    for job, rel in explicit:
        explicit_by_job.setdefault(job, set()).add(rel)
        job_mentions[job] = job_mentions.get(job, 0) + 1
    job_numbers = set(job_mentions)

    # Fuzzy name matches against active jobs / open submittals.
    matched_submittal_ids = set()
    for c in owner_match.build_candidates():
        inter = text_tokens & c["tokens"]
        if not inter or not any(len(t) >= 4 for t in inter):
            continue
        if len(inter) / len(c["tokens"]) < owner_match.FUZZY_ACCEPT:
            continue
        if c["job_number"]:
            jn = str(c["job_number"])
            job_numbers.add(jn)
            job_mentions[jn] = max(job_mentions.get(jn, 0), len(inter))
        if c.get("submittal_id"):
            matched_submittal_ids.add(c["submittal_id"])

    # project_number SEEDS: always present, even with no mention (and even pre-transcript,
    # e.g. the snapshot captured at meeting creation before any transcript exists).
    seed = str(meeting.project_number).strip() if meeting.project_number else None
    if seed:
        job_numbers.add(seed)

    # Rank jobs: the project seed first, then by mention frequency, then numerically.
    ordered_jobs = sorted(
        job_numbers, key=lambda jn: (jn != seed, -job_mentions.get(jn, 0), jn))

    releases, seen = [], set()
    for jn in ordered_jobs:
        job_rels = _releases_for_job(jn)
        wanted = explicit_by_job.get(jn, set())
        named = [r for r in job_rels if str(r.release) in wanted]          # always include
        others = _rank_releases_for_job(
            [r for r in job_rels if str(r.release) not in wanted], text_tokens)
        for r in named + others[:PER_JOB_RELEASES]:
            if r.id not in seen:
                seen.add(r.id)
                releases.append(r)
        if len(releases) >= MAX_RELEASES:
            break

    submittals, seen_sub = [], set()
    sub_rows = []
    if seed:
        sub_rows += Submittals.query.filter(Submittals.project_number == seed).all()
    if matched_submittal_ids:
        sub_rows += (Submittals.query
                     .filter(Submittals.submittal_id.in_(matched_submittal_ids)).all())
    for s in sub_rows:
        if s.submittal_id not in seen_sub:
            seen_sub.add(s.submittal_id)
            submittals.append(s)

    return releases[:MAX_RELEASES], submittals[:MAX_ENTITIES]


# --- state-line rendering (shared) ------------------------------------------- #

def _d(value):
    return value.isoformat() if value else "—"


def _release_state_line(r):
    # description is the scope phrase the shop actually says aloud ("the canopy steel",
    # "east stair") — job_name is the GC-prefixed formal title nobody speaks. Showing
    # both lets the model match a spoken item to the right release.
    desc = (r.description or "").strip()
    desc = f' "{desc}"' if desc else ""
    # job_comp / invoiced are the completion-zone fields the shop reports on aloud
    # ("that's at 25%", "did we invoice it") — show them so the model can spot a spoken
    # value that contradicts the record (drift detection), not just stage/dates.
    return (f"- {r.job}-{r.release} {r.job_name or ''}{desc} — stage={r.stage or '—'}, "
            f"PM={r.pm or '—'}, start_install={_d(r.start_install)}, "
            f"comp_eta={_d(r.comp_eta)}, job_comp={r.job_comp or '—'}, "
            f"invoiced={r.invoiced or '—'}")


def _submittal_state_line(s):
    name = s.project_name or s.title or ""
    return (f"- submittal {s.submittal_id} {name} — status={s.status or '—'}, "
            f"BIC={s.ball_in_court or '—'}, due={_d(s.due_date)}")


# --- EXTRACTION context: agenda + light job state + guidance ----------------- #

def _light_state_lines(meeting):
    """One current-state line per likely-discussed entity (NO event history) — grounds
    to-do extraction so the model uses canonical job names/tokens. '' when none."""
    releases, submittals = relevant_entities(meeting)
    if not releases and not submittals:
        return ""
    lines = [_release_state_line(r) for r in releases]
    lines += [_submittal_state_line(s) for s in submittals]
    return "\n".join(lines)


def learned_guidance():
    """Top reinforced 'pattern' signals, as short guidance lines. '' when none yet."""
    sigs = (ExtractionSignal.query
            .filter_by(signal_type="pattern", active=True)
            .order_by(ExtractionSignal.count.desc())
            .limit(MAX_GUIDANCE)
            .all())
    return "\n".join(f"- {s.value}" for s in sigs if s.value)


def assemble_extraction_context(meeting):
    """Context fed to to-do EXTRACTION (the matching helper, not the summary).

    Agenda (authored) + light job state (canonical names, no event history) + learned
    guidance. Event activity is deliberately NOT here — it powers the summary instead.
    Returns {'agenda', 'state', 'guidance', 'combined'}.
    """
    agenda = (meeting.agenda_text or "").strip()
    state = _light_state_lines(meeting)
    guidance = learned_guidance()

    # State and guidance are small and bounded (MAX_ENTITIES / MAX_GUIDANCE); the agenda
    # is unbounded user input. Budget the agenda against what remains under the
    # extractor's context cap so a long agenda truncates ITSELF — the extractor's own
    # tail-truncation would silently evict the state and guidance sections instead.
    agenda_header = "=== PRE-MEETING CONTEXT (agenda / notes) ===\n"
    state_header = (
        "=== BRAIN SNAPSHOT (current job-log / DWL state for the entities likely "
        "discussed — these are FIELDS, the system of record as it stands now) ===\n"
    )
    reserved = sum(
        len(header) + len(body) + 2  # +2 for the '\n\n' section separator
        for header, body in (
            (state_header, state),
            ("=== LEARNED GUIDANCE (from past meetings) ===\n", guidance),
        ) if body
    )
    agenda_budget = MAX_CONTEXT_CHARS - len(agenda_header) - reserved
    if agenda and len(agenda) > agenda_budget:
        marker = "\n[... agenda truncated ...]"
        agenda = agenda[:max(0, agenda_budget - len(marker))] + marker
        logger.warning("meeting_agenda_truncated", meeting_id=meeting.id,
                       agenda_chars=len(meeting.agenda_text or ""),
                       budget=agenda_budget)

    sections = []
    if agenda:
        sections.append(agenda_header + agenda)
    if state:
        sections.append(state_header + state)
    if guidance:
        sections.append("=== LEARNED GUIDANCE (from past meetings) ===\n" + guidance)

    combined = "\n\n".join(sections)
    logger.info("meeting_extraction_context_assembled", meeting_id=meeting.id,
                has_agenda=bool(agenda), has_state=bool(state),
                has_guidance=bool(guidance), chars=len(combined))
    return {"agenda": agenda, "state": state, "guidance": guidance, "combined": combined}


# --- SUMMARY context: events that landed DURING the meeting ------------------ #

def _meeting_window(meeting):
    """[start, end] of the meeting — bounds the 'during runtime' events for the summary.
    start = meeting time (else creation). end = recorded end (else now, before it's set)."""
    start = meeting.occurred_at or meeting.created_at or datetime.utcnow()
    end = meeting.ended_at or datetime.utcnow()
    if end < start:                      # defensive: never invert the window
        end = start + timedelta(hours=4)
    return start, end


def _release_events_between(job, start, end):
    return (ReleaseEvents.query
            .filter(ReleaseEvents.job == job,
                    ReleaseEvents.is_system_echo.is_(False),
                    ReleaseEvents.created_at >= start,
                    ReleaseEvents.created_at <= end)
            .order_by(ReleaseEvents.created_at.asc())
            .limit(EVENTS_PER_ENTITY)
            .all())


def _submittal_events_between(submittal_id, start, end):
    return (SubmittalEvents.query
            .filter(SubmittalEvents.submittal_id == str(submittal_id),
                    SubmittalEvents.is_system_echo.is_(False),
                    SubmittalEvents.created_at >= start,
                    SubmittalEvents.created_at <= end)
            .order_by(SubmittalEvents.created_at.asc())
            .limit(EVENTS_PER_ENTITY)
            .all())


def build_runtime_events(meeting):
    """Render the release/submittal updates that landed DURING the meeting window
    [occurred_at, ended_at|now] — the events context that feeds the meeting summary.

    Only entities that actually changed in-window are shown (a summary is about what
    moved, not a full roster). Returns '' when nothing changed during the meeting.
    """
    from app.history import (
        _extract_new_value_from_payload, _extract_submittal_new_value_from_payload,
    )
    start, end = _meeting_window(meeting)
    releases, submittals = relevant_entities(meeting)
    if not releases and not submittals:
        return ""

    lines, seen_jobs = [], set()
    for r in releases:
        if r.job in seen_jobs:
            continue  # events are job-scoped — fetch once per job
        seen_jobs.add(r.job)
        evs = _release_events_between(r.job, start, end)
        if not evs:
            continue
        lines.append(_release_state_line(r))
        for ev in evs:
            summ = _extract_new_value_from_payload(ev.action, ev.payload) or ev.action
            # Tag the release token — events are job-scoped, so a multi-release job's
            # events all render here; the token keeps each one self-identifying.
            lines.append(f"    {ev.created_at:%m/%d %H:%M} {ev.job}-{ev.release} "
                         f"{ev.action}: {summ} ({ev.source})")

    for s in submittals:
        evs = _submittal_events_between(s.submittal_id, start, end)
        if not evs:
            continue
        lines.append(_submittal_state_line(s))
        for ev in evs:
            summ = _extract_submittal_new_value_from_payload(ev.action, ev.payload) or ev.action
            lines.append(f"    {ev.created_at:%m/%d %H:%M} {ev.action}: {summ} ({ev.source})")

    return "\n".join(lines)
