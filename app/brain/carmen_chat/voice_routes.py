"""Carmen voice-to-voice routes. Registered on brain_bp.

One round trip per turn: the browser posts a mic recording, we transcribe it with xAI,
run the *existing* read-only Carmen agent over the transcript (so the answer still comes
from her database tools and still lands in her conversation history), and hand back both
the written answer and a spoken one.

Live mode (`live.py`) is the other half: an open conversation over a WebSocket the
browser holds directly with xAI. Flask only brokers it — mints a token, runs tool calls,
and files the transcript afterwards.

Endpoints:
  GET   /brain/carmen-chat/voice/config     should the client show a mic? which voice?
  POST  /brain/carmen-chat/voice            multipart audio -> transcript + answer + audio
  POST  /brain/carmen-chat/voice/speak      {text} -> audio (replay a written answer aloud)
  GET   /brain/carmen-chat/voice/voices     (admin) live xAI voice roster
  POST  /brain/carmen-chat/voice/live/token mint a client secret + the session config
  POST  /brain/carmen-chat/voice/live/tool  run one read-only tool for the live session
  POST  /brain/carmen-chat/voice/live/turn  file a spoken exchange into chat history
  POST  /brain/carmen-chat/voice/live/apply (admin) execute a confirmed change proposal

Access is the same `is_carmen_chat` gate as the text chat, and the turn is just as
read-only — speaking to Carmen can't mutate anything the typed chat couldn't.
"""
import base64
import time

from flask import jsonify, request

from app.auth.utils import admin_required, carmen_chat_required, get_current_user
from app.brain import brain_bp
from app.brain.carmen_chat import edits, live, service, voice
from app.brain.carmen_chat.agent import _artifact_from_tool
from app.models import CarmenChatConversation, CarmenChatMessage, db
from app.logging_config import get_logger

logger = get_logger(__name__)


def _audio_envelope(spoken: dict) -> dict:
    """Base64 the synthesized clip for inline delivery alongside the answer text."""
    return {
        "data_base64": base64.b64encode(spoken["audio"]).decode("ascii"),
        "mime": spoken["mime"],
        "duration_seconds": spoken.get("duration_seconds"),
        "voice_id": spoken.get("voice_id"),
        "chars": spoken.get("chars"),
        "truncated": bool(spoken.get("truncated")),
    }


@brain_bp.route('/carmen-chat/voice/config', methods=['GET'])
@carmen_chat_required
def carmen_voice_config():
    """Whether voice is live on this server, and which voice Carmen speaks in."""
    return jsonify({**voice.config_summary(), 'live': live.config_summary(get_current_user())}), 200


@brain_bp.route('/carmen-chat/voice', methods=['POST'])
@carmen_chat_required
def carmen_voice_turn():
    """One spoken turn. Multipart: `audio` file + optional `conversation_id`."""
    user = get_current_user()
    clip = request.files.get('audio') or request.files.get('file')
    if clip is None:
        return jsonify({'error': 'audio file is required'}), 400

    conversation_id = request.form.get('conversation_id') or None
    if conversation_id:
        try:
            conversation_id = int(conversation_id)
        except (TypeError, ValueError):
            return jsonify({'error': 'conversation_id must be an integer'}), 400

    payload = clip.read()
    started = time.monotonic()
    try:
        heard = voice.transcribe(payload, mimetype=clip.mimetype or '',
                                 filename=(clip.filename or 'clip').rsplit('.', 1)[0])
    except voice.VoiceNotConfigured as exc:
        return jsonify({'error': str(exc)}), 503
    except voice.VoiceError as exc:
        return jsonify({'error': str(exc)}), 502
    stt_ms = int((time.monotonic() - started) * 1000)

    transcript = (heard.get('text') or '').strip()
    if not transcript:
        logger.info('carmen_voice_empty_transcript', user_id=user.id,
                    bytes=len(payload), duration_ms=stt_ms)
        return jsonify({'error': "Carmen didn't catch that — try again.",
                        'transcript': ''}), 422

    agent_started = time.monotonic()
    try:
        result = service.send_message(user.id, conversation_id, transcript)
    except PermissionError:
        return jsonify({'error': 'conversation not found'}), 404
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        logger.error('carmen_voice_agent_failed', user_id=user.id, error=str(exc),
                     error_type=type(exc).__name__, exc_info=True)
        return jsonify({'error': 'Carmen is temporarily unavailable.'}), 502
    agent_ms = int((time.monotonic() - agent_started) * 1000)

    answer = result['assistant_message']['content']
    tts_started = time.monotonic()
    audio, voice_error = None, None
    try:
        audio = _audio_envelope(voice.synthesize(answer))
    except voice.VoiceError as exc:
        # The answer is already written and persisted — a mute reply beats a lost turn.
        voice_error = str(exc)
    tts_ms = int((time.monotonic() - tts_started) * 1000)

    logger.info('carmen_voice_turn', user_id=user.id,
                conversation_id=result['conversation_id'],
                stt_ms=stt_ms, agent_ms=agent_ms, tts_ms=tts_ms,
                duration_ms=int((time.monotonic() - started) * 1000),
                clip_bytes=len(payload), transcript_chars=len(transcript),
                spoken_chars=(audio or {}).get('chars'),
                voice_id=(audio or {}).get('voice_id'),
                status='spoken' if audio else 'text_only')

    result['transcript'] = transcript
    result['audio'] = audio
    if voice_error:
        result['voice_error'] = voice_error
    result['voice_timings'] = {'stt_ms': stt_ms, 'agent_ms': agent_ms, 'tts_ms': tts_ms}
    return jsonify(result), 200


@brain_bp.route('/carmen-chat/voice/speak', methods=['POST'])
@carmen_chat_required
def carmen_voice_speak():
    """Speak arbitrary answer text aloud. Body: {text, voice_id?}."""
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'error': 'text is required'}), 400
    try:
        spoken = voice.synthesize(text, voice_id=data.get('voice_id') or None)
    except voice.VoiceNotConfigured as exc:
        return jsonify({'error': str(exc)}), 503
    except voice.VoiceError as exc:
        return jsonify({'error': str(exc)}), 502
    return jsonify(_audio_envelope(spoken)), 200


@brain_bp.route('/carmen-chat/voice/voices', methods=['GET'])
@admin_required
def carmen_voice_voices():
    """The live xAI voice roster — for picking or confirming Carmen's voice."""
    try:
        voices = voice.list_voices()
    except voice.VoiceNotConfigured as exc:
        return jsonify({'error': str(exc)}), 503
    except voice.VoiceError as exc:
        return jsonify({'error': str(exc)}), 502
    from app.config import Config as cfg
    return jsonify({'voices': voices, 'current': cfg.CARMEN_VOICE_ID}), 200


# --- Live mode: broker only. The browser owns the socket; see live.py. ---------------

@brain_bp.route('/carmen-chat/voice/live/token', methods=['POST'])
@carmen_chat_required
def carmen_live_token():
    """Mint a short-lived xAI client secret plus the session config to open with."""
    user = get_current_user()
    try:
        minted = live.mint_client_secret()
    except live.LiveNotConfigured as exc:
        return jsonify({'error': str(exc)}), 503
    except live.LiveError as exc:
        return jsonify({'error': str(exc)}), 502

    from app.config import Config as cfg
    logger.info('carmen_live_session_brokered', user_id=user.id,
                model=cfg.CARMEN_LIVE_MODEL, voice_id=cfg.CARMEN_VOICE_ID,
                ttl_seconds=minted['ttl_seconds'])
    return jsonify({
        'token': minted['token'],
        'expires_at': minted['expires_at'],
        'ttl_seconds': minted['ttl_seconds'],
        'url': f"wss://api.x.ai/v1/realtime?model={cfg.CARMEN_LIVE_MODEL}",
        'model': cfg.CARMEN_LIVE_MODEL,
        'session': live.session_config(user),
        'max_session_seconds': cfg.CARMEN_LIVE_MAX_SESSION_SECONDS,
    }), 200


@brain_bp.route('/carmen-chat/voice/live/tool', methods=['POST'])
@carmen_chat_required
def carmen_live_tool():
    """Run one read-only tool for the live session. Body: {name, arguments}.

    The acting user comes from the session, not the body — a live caller reaches exactly
    what they could reach by typing, and nothing else.
    """
    user = get_current_user()
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    arguments = data.get('arguments') or {}
    if not name:
        return jsonify({'error': 'name is required'}), 400
    if not isinstance(arguments, dict):
        return jsonify({'error': 'arguments must be an object'}), 400

    if name in (edits.TOOL_PROPOSE_CHANGES, edits.TOOL_PROPOSE_TODO):
        # Second gate: these tools aren't declared to a non-admin's session, but never
        # trust that the client only asks for what it was offered.
        if not live.can_edit(user):
            return jsonify({'result': {'error': 'You can look, but you cannot make changes here.'},
                            'artifact': None}), 200
        try:
            if name == edits.TOOL_PROPOSE_TODO:
                proposal = edits.propose_todo(
                    arguments.get('title'), arguments.get('owner'),
                    due_date=arguments.get('due_date'), release=arguments.get('release'),
                    detail=arguments.get('detail'), user_id=user.id)
            else:
                proposal = edits.propose(arguments.get('identifier'),
                                         arguments.get('changes') or [], user_id=user.id)
        except edits.EditError as exc:
            # A speakable reason, handed back as a tool result so she can relay it.
            return jsonify({'result': {'error': str(exc)}, 'artifact': None}), 200
        except Exception as exc:
            logger.error('carmen_propose_failed', user_id=user.id, tool=name, error=str(exc),
                         error_type=type(exc).__name__, exc_info=True)
            return jsonify({'result': {'error': 'I could not put that together.'},
                            'artifact': None}), 200
        # `proposal` goes back to the model (so she can say what she proposed) and to the
        # UI as a card. The signed token rides along; it is worthless without confirmation.
        return jsonify({'result': proposal, 'proposal': proposal, 'artifact': None}), 200

    started = time.monotonic()
    try:
        result = live.run_tool(name, arguments, user_id=user.id)
    except Exception as exc:
        logger.error('carmen_live_tool_failed', user_id=user.id, tool=name,
                     error=str(exc), error_type=type(exc).__name__, exc_info=True)
        # Hand the model a readable failure instead of dropping the turn on the floor.
        return jsonify({'result': {'error': 'that lookup failed'}, 'artifact': None}), 200
    duration_ms = int((time.monotonic() - started) * 1000)

    # The instruction to write the answer down lives in the session prompt, but a prompt
    # rule competes with everything else in a long conversation and she was dropping it
    # on roughly half of lookups. Restating it in the tool result puts it in front of her
    # at the only moment it matters — right as the data lands — and costs nothing.
    if isinstance(result, dict) and not result.get('error'):
        result = {**result, '_next_step': (
            'Call write_to_chat now with the full written answer — the data above, laid '
            'out with exact numbers, dates and identifiers — and only then speak a one '
            'or two sentence summary of it.'
        )}

    artifact = _artifact_from_tool(name, result if isinstance(result, dict) else {})
    logger.info('carmen_live_tool_call', user_id=user.id, tool=name,
                input=arguments, duration_ms=duration_ms,
                has_artifact=bool(artifact))
    return jsonify({'result': result, 'artifact': artifact}), 200


@brain_bp.route('/carmen-chat/voice/live/turn', methods=['POST'])
@carmen_chat_required
def carmen_live_turn():
    """File a spoken exchange into chat history. Body: {user_text, assistant_text, conversation_id?}.

    A live conversation happens entirely between the browser and xAI, so without this the
    whole thing would evaporate when the tab closes. Persisting the transcript keeps the
    written record and the thread continuous with the typed chat.
    """
    user = get_current_user()
    data = request.get_json(silent=True) or {}
    user_text = (data.get('user_text') or '').strip()
    assistant_text = (data.get('assistant_text') or '').strip()
    if not user_text and not assistant_text:
        return jsonify({'error': 'nothing to record'}), 400

    conversation_id = data.get('conversation_id')
    convo = None
    if conversation_id:
        convo = service.get_conversation(user.id, conversation_id)
        if convo is None:
            return jsonify({'error': 'conversation not found'}), 404
    if convo is None:
        title = (user_text or assistant_text)[:60]
        convo = CarmenChatConversation(user_id=user.id, title=title or 'Live chat')
        db.session.add(convo)
        db.session.flush()

    if user_text:
        db.session.add(CarmenChatMessage(conversation_id=convo.id, role='user', content=user_text))
    if assistant_text:
        db.session.add(CarmenChatMessage(conversation_id=convo.id, role='assistant',
                                         content=assistant_text))
    db.session.commit()

    logger.info('carmen_live_turn_recorded', user_id=user.id, conversation_id=convo.id,
                user_chars=len(user_text), assistant_chars=len(assistant_text))
    return jsonify({'conversation_id': convo.id}), 200


@brain_bp.route('/carmen-chat/voice/live/apply', methods=['POST'])
@admin_required
def carmen_live_apply():
    """Execute a confirmed change proposal. Body: {plan, token, issued_at}.

    This is the only endpoint in Carmen that writes. It runs after a human has confirmed
    the card on screen, and it re-checks everything: the edit capability, the signature,
    the issuing user and the age of the proposal.
    """
    user = get_current_user()
    if not live.can_edit(user):
        return jsonify({'error': 'Spoken edits are turned off.'}), 403

    data = request.get_json(silent=True) or {}
    plan = data.get('plan')
    if not isinstance(plan, dict):
        return jsonify({'error': 'plan is required'}), 400

    try:
        edits.verify(plan, data.get('token'), data.get('issued_at'), user.id)
    except edits.EditError as exc:
        return jsonify({'error': str(exc)}), 400

    try:
        outcome = edits.apply(plan, user_id=user.id)
    except Exception as exc:
        logger.error('carmen_edit_apply_route_failed', user_id=user.id,
                     error=str(exc), error_type=type(exc).__name__, exc_info=True)
        return jsonify({'error': 'That change could not be applied.'}), 502

    return jsonify(outcome), 200
