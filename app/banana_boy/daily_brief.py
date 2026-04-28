"""Daily brief — 6:30 AM Mountain Time morning summary for opted-in users.

Gathers facts deterministically (unread notifications, my open submittals
where I'm ball-in-court, today's installs), then asks Haiku to write a
friendly 4-sentence morning brief from those facts. Result lands in the
user's Banana Boy chat thread as an assistant ChatMessage.

Empty-signal users are skipped silently — no spam.

Mountain Time is enforced by APScheduler's CronTrigger; this module computes
"today" using America/Denver so the date matches the trigger's notion of
"today" regardless of the server's wall clock timezone.
"""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from app.banana_boy.client import HAIKU_MODEL, get_client
from app.banana_boy.tools import (
    _release_to_compact,
    _submittal_to_compact,
    query_open_submittals,
)
from app.logging_config import get_logger
from app.models import (
    ChatMessage,
    Notification,
    ROLE_ASSISTANT,
    Releases,
    User,
    db,
)

logger = get_logger(__name__)

MOUNTAIN_TZ = ZoneInfo("America/Denver")
BRIEF_MAX_TOKENS = 600

BRIEF_SYSTEM = (
    "You are Banana Boy writing a brief, friendly 6:30 AM morning summary "
    "for a single user. Write in second person ('you'). Lead with the most "
    "time-sensitive item. Cap at ~6 short lines. Use markdown bullets for "
    "lists. Don't speculate — only mention things that are in the facts. "
    "If a section is empty, skip it silently. End with one upbeat sentence."
)


def _today_in_mountain():
    return datetime.now(MOUNTAIN_TZ).date()


def _my_open_submittals(user: User) -> list[dict]:
    name_substrings = [s for s in (user.first_name, user.last_name) if s]
    if not name_substrings:
        return []
    rows = query_open_submittals(
        ball_in_court_substrings=name_substrings,
        exclude_closed=True,
        limit=20,
    )
    return [_submittal_to_compact(s) for s in rows]


def _gather_facts(user: User) -> dict:
    today = _today_in_mountain()

    notif_rows = (
        Notification.query.filter_by(user_id=user.id, is_read=False)
        .order_by(Notification.created_at.desc())
        .limit(10)
        .all()
    )
    unread_notifications = [
        {
            "type": n.type,
            "message": n.message,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notif_rows
    ]

    install_rows = (
        Releases.query.filter(Releases.start_install == today)
        .order_by(Releases.job.asc(), Releases.release.asc())
        .limit(20)
        .all()
    )
    todays_installs = [_release_to_compact(r) for r in install_rows]

    return {
        "user_first_name": user.first_name or user.username,
        "today": today.isoformat(),
        "unread_notifications": unread_notifications,
        "my_open_submittals": _my_open_submittals(user),
        "todays_installs": todays_installs,
    }


def _has_any_signal(facts: dict) -> bool:
    return any([
        facts.get("unread_notifications"),
        facts.get("my_open_submittals"),
        facts.get("todays_installs"),
    ])


def _format_brief(facts: dict) -> str:
    client = get_client()
    response = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=BRIEF_MAX_TOKENS,
        system=BRIEF_SYSTEM,
        messages=[{"role": "user", "content": json.dumps(facts, default=str)}],
    )
    text = "".join(
        b.text for b in response.content if getattr(b, "type", None) == "text"
    ).strip()
    return text or "Good morning! Nothing pressing on your plate today."


def _send_brief_for_user(user: User) -> bool:
    """Generate + persist a brief for one user. Returns True if a message was written."""
    facts = _gather_facts(user)
    if not _has_any_signal(facts):
        logger.info("daily_brief_skipped_no_signal", user_id=user.id)
        return False

    text = _format_brief(facts)
    msg = ChatMessage(user_id=user.id, role=ROLE_ASSISTANT, content=text)
    db.session.add(msg)
    db.session.commit()
    logger.info(
        "daily_brief_sent",
        user_id=user.id,
        notif_count=len(facts["unread_notifications"]),
        bic_submittal_count=len(facts["my_open_submittals"]),
        install_count=len(facts["todays_installs"]),
    )
    return True


def send_daily_briefs(app) -> None:
    """Top-level scheduler entry. Iterates opted-in users; never raises."""
    with app.app_context():
        users = (
            User.query
            .filter_by(is_active=True, wants_daily_brief=True)
            .all()
        )
        logger.info("daily_brief_run_start", user_count=len(users))
        sent = 0
        for user in users:
            try:
                if _send_brief_for_user(user):
                    sent += 1
            except Exception as exc:  # noqa: BLE001 — never let one user kill the loop
                logger.error("daily_brief_failed", user_id=user.id, error=str(exc))
                db.session.rollback()
        logger.info("daily_brief_run_complete", sent=sent, total=len(users))
