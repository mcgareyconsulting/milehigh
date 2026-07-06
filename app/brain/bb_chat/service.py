"""Persistence + orchestration for BB lifecycle chat.

Each turn: resolve any release/submittal reference in the message (re-anchoring the thread if
one is found), assemble the current lifecycle bundle for the thread's anchor, call the agent,
and persist the turn. Only plain text is persisted; the bundle is re-assembled fresh each
turn so follow-ups always reflect current data.
"""
from app.logging_config import get_logger
from app.models import BBChatConversation, BBChatMessage, db

from . import agent, assembler, resolver

logger = get_logger(__name__)


def list_conversations(user_id: int):
    convos = (
        BBChatConversation.query.filter_by(user_id=user_id)
        .order_by(BBChatConversation.updated_at.desc())
        .all()
    )
    return [c.to_dict() for c in convos]


def get_conversation(user_id: int, conversation_id: int):
    convo = db.session.get(BBChatConversation, conversation_id)
    if not convo or convo.user_id != user_id:
        return None
    return convo


def _history_pairs(convo: BBChatConversation):
    return [{"role": m.role, "content": m.content} for m in convo.messages]


def _title_from(text: str) -> str:
    text = (text or "").strip().replace("\n", " ")
    return (text[:60] + "…") if len(text) > 60 else (text or "New chat")


def _apply_anchor(convo: BBChatConversation, anchor: dict):
    convo.anchor_kind = anchor["kind"]
    convo.anchor_job = anchor.get("job")
    convo.anchor_release = anchor.get("release")
    convo.anchor_submittal_id = anchor.get("submittal_id")


def _current_anchor(convo: BBChatConversation):
    if not convo.anchor_kind:
        return None
    return {"kind": convo.anchor_kind, "job": convo.anchor_job,
            "release": convo.anchor_release, "submittal_id": convo.anchor_submittal_id,
            "label": (f"release {convo.anchor_job}-{convo.anchor_release}" if convo.anchor_release
                      else f"submittal {convo.anchor_submittal_id}" if convo.anchor_submittal_id
                      else f"job {convo.anchor_job}")}


def send_message(user_id: int, conversation_id, user_text: str) -> dict:
    """Run one lifecycle chat turn. Returns {conversation_id, user_message, assistant_message}."""
    user_text = (user_text or "").strip()
    if not user_text:
        raise ValueError("message is required")

    convo = None
    if conversation_id:
        convo = get_conversation(user_id, conversation_id)
        if convo is None:
            raise PermissionError("conversation not found")
    if convo is None:
        convo = BBChatConversation(user_id=user_id, title=_title_from(user_text))
        db.session.add(convo)
        db.session.flush()

    history = _history_pairs(convo)

    # Re-anchor the thread if this message names a (resolvable) release/submittal.
    new_anchor = resolver.resolve(user_text)
    if new_anchor:
        _apply_anchor(convo, new_anchor)
        if not history:  # first turn — title the thread after the entity
            convo.title = new_anchor["label"]

    anchor = _current_anchor(convo)
    bundle = assembler.assemble(anchor) if anchor else None

    user_msg = BBChatMessage(conversation_id=convo.id, role="user", content=user_text)
    db.session.add(user_msg)

    result = agent.run_chat(history, user_text, bundle=bundle, user_id=user_id)
    m = result["metrics"]

    assistant_msg = BBChatMessage(
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
    )
    db.session.add(assistant_msg)
    db.session.commit()

    return {
        "conversation_id": convo.id,
        "user_message": user_msg.to_dict(),
        "assistant_message": assistant_msg.to_dict(),
    }
