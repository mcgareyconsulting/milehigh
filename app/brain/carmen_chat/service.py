"""Persistence + orchestration for Carmen chat.

Each turn: load the signed-in user (for the current-user block + user-scoped tools), run the
read-only tool agent over the thread's text history, and persist the turn with its spend
metrics. Only plain text is persisted; the agent re-queries via tools as needed each turn.
"""
from app.logging_config import get_logger
from app.models import CarmenChatConversation, CarmenChatMessage, User, db

from . import agent

logger = get_logger(__name__)


def list_conversations(user_id: int):
    convos = (CarmenChatConversation.query.filter_by(user_id=user_id)
              .order_by(CarmenChatConversation.updated_at.desc()).all())
    return [c.to_dict() for c in convos]


def get_conversation(user_id: int, conversation_id: int):
    convo = db.session.get(CarmenChatConversation, conversation_id)
    if not convo or convo.user_id != user_id:
        return None
    return convo


def _history_pairs(convo: CarmenChatConversation):
    return [{"role": m.role, "content": m.content} for m in convo.messages]


def _title_from(text: str) -> str:
    text = (text or "").strip().replace("\n", " ")
    return (text[:60] + "…") if len(text) > 60 else (text or "New chat")


def send_message(user_id: int, conversation_id, user_text: str) -> dict:
    """Run one chat turn. Returns {conversation_id, user_message, assistant_message}."""
    user_text = (user_text or "").strip()
    if not user_text:
        raise ValueError("message is required")

    convo = None
    if conversation_id:
        convo = get_conversation(user_id, conversation_id)
        if convo is None:
            raise PermissionError("conversation not found")
    if convo is None:
        convo = CarmenChatConversation(user_id=user_id, title=_title_from(user_text))
        db.session.add(convo)
        db.session.flush()

    history = _history_pairs(convo)
    user = db.session.get(User, user_id)

    user_msg = CarmenChatMessage(conversation_id=convo.id, role="user", content=user_text)
    db.session.add(user_msg)

    result = agent.run_chat(history, user_text, user=user, user_id=user_id)
    m = result["metrics"]

    assistant_msg = CarmenChatMessage(
        conversation_id=convo.id,
        role="assistant",
        content=result["answer"],
        anthropic_request_id=(m.get("request_ids") or [None])[-1],
        model=m.get("model"),
        input_tokens=m.get("input_tokens"),
        output_tokens=m.get("output_tokens"),
        cache_read_tokens=m.get("cache_read_tokens"),
        cache_write_tokens=m.get("cache_write_tokens"),
        cost_usd=m.get("cost_usd"),
        duration_ms=m.get("duration_ms"),
        tool_calls=m.get("tool_calls"),
    )
    db.session.add(assistant_msg)
    db.session.commit()

    # Ledger the spend (own transaction, post-commit — never breaks the chat turn).
    from app.services import ai_usage
    ai_usage.record(
        "bb_chat",
        model=m.get("model"),
        input_tokens=m.get("input_tokens") or 0,
        output_tokens=m.get("output_tokens") or 0,
        cache_read_tokens=m.get("cache_read_tokens") or 0,
        cache_write_tokens=m.get("cache_write_tokens") or 0,
        cost_usd=m.get("cost_usd"),
        duration_ms=m.get("duration_ms"),
        user_id=user_id,
        request_id=(m.get("request_ids") or [None])[-1],
        entity_type="bb_chat_message",
        entity_id=assistant_msg.id,
    )

    assistant = assistant_msg.to_dict()
    # Structured artifacts (e.g. look-ahead PDF) for the chat UI card — not persisted on
    # the message row; the client also recovers download_path from message text if needed.
    artifacts = result.get("artifacts") or []
    if artifacts:
        assistant["artifacts"] = artifacts

    return {
        "conversation_id": convo.id,
        "user_message": user_msg.to_dict(),
        "assistant_message": assistant,
    }
