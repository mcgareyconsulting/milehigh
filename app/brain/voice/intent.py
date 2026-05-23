"""
@milehigh-header
schema_version: 1
purpose: Parse a wake-word-gated voice command into a structured, deterministic Intent for the DWL dispatcher.
exports:
  WAKE_WORD_RE: Regex matching the "Banana Boy" wake word in a transcript.
  strip_wake_word: Return the command portion after the wake word, or None if absent.
  Intent: Dataclass describing a parsed action (action, submittal_id, position, drafter, value).
  parse_intent: Turn a raw transcript into an Intent (or None when nothing matches).
imports_from: [dataclasses, re, typing, app.brain.voice.normalizers]
imported_by: [app/brain/voice/dispatcher.py, tests/voice/test_intent.py]
invariants:
  - Pure: no Flask/DB/IO. parse_intent never raises on bad input; it returns None.
  - parse_intent only fires on text that contains the wake word.
  - Intent.confidence is 'high' for an exact template match, 'low' when a slot was guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from app.brain.voice.normalizers import (
    extract_position,
    extract_submittal_id,
    normalize_text,
)

# "banana boy", "hey banana boy", "ok banana boy" — tolerate a leading address.
WAKE_WORD_RE = re.compile(r"\b(?:hey\s+|ok\s+|okay\s+)?banana\s+boy\b", re.IGNORECASE)

# Valid drafting-status phrases -> stored value.
_STATUS_PHRASES = {
    "started": "STARTED",
    "start": "STARTED",
    "need vif": "NEED VIF",
    "needs vif": "NEED VIF",
    "vif": "NEED VIF",
    "hold": "HOLD",
    "on hold": "HOLD",
    "clear status": "",
    "clear": "",
}


@dataclass
class Intent:
    """A parsed, deterministic command ready for the dispatcher.

    `action` is one of: set_order, bump, step, resort, set_status, set_due_date,
    add_note. Unused slots stay None. `raw_*` fields hold the spoken fragment so
    the dispatcher can resolve them against the live DWL context.
    """
    action: str
    raw_submittal: Optional[str] = None
    raw_drafter: Optional[str] = None
    position: Optional[int] = None
    direction: Optional[str] = None
    value: Optional[str] = None
    confidence: str = "high"
    transcript: str = ""
    unknown_slots: List[str] = field(default_factory=list)


def strip_wake_word(transcript: str) -> Optional[str]:
    """Return the text following the wake word, or None if the wake word is absent.

    Everything up to and including the wake word is dropped, so a meeting
    sentence like "...anyway, hey Banana Boy, bump 234-433" yields "bump 234-433".
    """
    if not transcript:
        return None
    m = WAKE_WORD_RE.search(transcript)
    if not m:
        return None
    return transcript[m.end():].strip(" ,.-")


def _find_drafter_fragment(command: str) -> Optional[str]:
    """Pull the spoken drafter name out of "... in Colton's list" / "for Colton".

    Returns the bare first name fragment (e.g. "colton") or None. Resolution to a
    real ball_in_court value happens in the dispatcher against live data.
    """
    norm = normalize_text(command)
    # "colton's list", "resort colton's queue" (possessive directly before list noun)
    m = re.search(r"\b([a-z]+)'s\s+(?:list|queue|pile|stack)\b", norm)
    if m:
        return m.group(1)
    # "in colton's list", "to colton list", "on colton's queue"
    m = re.search(r"\b(?:in|to|on)\s+([a-z]+)(?:'s)?\s+(?:list|queue|pile|stack)\b", norm)
    if m:
        return m.group(1)
    # "for colton"
    m = re.search(r"\bfor\s+([a-z]+)\b", norm)
    if m:
        return m.group(1)
    return None


def parse_intent(transcript: str) -> Optional[Intent]:
    """Parse a transcript into an Intent, or None if it isn't an actionable command.

    Requires the wake word. Tries each command template in priority order and
    returns the first match. Designed to be cheap and deterministic — the hot
    path for in-meeting use.
    """
    command = strip_wake_word(transcript)
    if command is None:
        return None
    norm = normalize_text(command)
    if not norm:
        return None

    submittal = extract_submittal_id(command)
    drafter = _find_drafter_fragment(command)

    # --- resort: "resort colton's list" / "resort colton" (no submittal needed) ---
    if re.search(r"\b(re-?sort|re-?order|clean up|compress)\b", norm):
        if drafter:
            return Intent(action="resort", raw_drafter=drafter, transcript=transcript)
        return Intent(action="resort", raw_drafter=None, confidence="low",
                      unknown_slots=["drafter"], transcript=transcript)

    # --- bump: "bump 234-433", "make 234-433 urgent" ---
    if re.search(r"\b(bump|urgent|urgently|escalate|rush)\b", norm):
        return Intent(action="bump", raw_submittal=submittal,
                      confidence="high" if submittal else "low",
                      unknown_slots=[] if submittal else ["submittal"],
                      transcript=transcript)

    # --- step: "step 234-433 up", "move 234-433 up one" ---
    # A bare up/down with no explicit list position; "to 5"/"number 5" routes to set_order.
    step_m = re.search(r"\b(up|down)\b", norm)
    if step_m and re.search(r"\b(step|nudge|move|bump)\b", norm) and "list" not in norm \
            and extract_position(command) is None:
        return Intent(action="step", raw_submittal=submittal,
                      direction=step_m.group(1),
                      confidence="high" if submittal else "low",
                      unknown_slots=[] if submittal else ["submittal"],
                      transcript=transcript)

    # --- set_status: "mark 234-433 started / on hold / need vif" ---
    for phrase, value in sorted(_STATUS_PHRASES.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"\b{re.escape(phrase)}\b", norm):
            return Intent(action="set_status", raw_submittal=submittal, value=value,
                          confidence="high" if submittal else "low",
                          unknown_slots=[] if submittal else ["submittal"],
                          transcript=transcript)

    # --- set_due_date: "set due date on 234-433 to next friday" ---
    if re.search(r"\bdue\b", norm):
        m = re.search(r"\bto\s+(.+)$", command.strip(), re.IGNORECASE)
        value = m.group(1).strip() if m else None
        return Intent(action="set_due_date", raw_submittal=submittal, value=value,
                      confidence="high" if (submittal and value) else "low",
                      unknown_slots=[s for s, ok in (("submittal", submittal), ("value", value)) if not ok],
                      transcript=transcript)

    # --- add_note: "note on 234-433: waiting on shop drawings" ---
    note_m = re.search(r"\bnote\b\s*(?:on\s+\S+)?\s*[:\-]?\s*(.*)$", command.strip(), re.IGNORECASE)
    if note_m and re.search(r"\bnote\b", norm):
        text = note_m.group(1).strip()
        # Drop a leading submittal id echoed inside the note phrase.
        if submittal:
            text = re.sub(r"^\s*on\s+[\d\s\-]+", "", text).strip(" :,-")
        return Intent(action="add_note", raw_submittal=submittal, value=text or None,
                      confidence="high" if (submittal and text) else "low",
                      unknown_slots=[s for s, ok in (("submittal", submittal), ("value", text)) if not ok],
                      transcript=transcript)

    # --- set_order: "move 234-433 to number 5 in colton's list" ---
    if re.search(r"\b(move|put|set|place|order|reorder)\b", norm):
        position = extract_position(command)
        unknown = []
        if not submittal:
            unknown.append("submittal")
        if position is None:
            unknown.append("position")
        return Intent(action="set_order", raw_submittal=submittal, position=position,
                      raw_drafter=drafter,
                      confidence="high" if (submittal and position is not None) else "low",
                      unknown_slots=unknown, transcript=transcript)

    return None
