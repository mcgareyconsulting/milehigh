"""
@milehigh-header
schema_version: 1
purpose: Normalize raw speech-to-text fragments into clean tokens (submittal IDs, list positions, drafter names) before intent parsing.
exports:
  normalize_text: Lowercase, collapse whitespace, strip filler, spell out punctuation words.
  words_to_number: Convert a spelled-out number phrase ("two thirty four") to an int.
  extract_submittal_id: Pull a job/submittal id like "234-433" out of a fragment, tolerating spoken digits and "dash"/"to".
  extract_position: Pull a 1-based list position ("number five", "to the top") out of a fragment.
  match_submittal_id: Resolve a spoken id against a set of known ids, exact then fuzzy (edit distance <= 1).
  match_drafter: Resolve a spoken first name against a set of known ball_in_court values.
imports_from: [re, difflib]
imported_by: [app/brain/voice/intent.py, tests/voice/test_normalizers.py]
invariants:
  - Pure functions only; no Flask, DB, or IO. Safe to unit test in isolation.
  - All matchers return None on no/ambiguous match rather than guessing.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Iterable, List, Optional, Tuple

# Filler words an STT engine emits that never carry command meaning.
_FILLER = {"uh", "um", "er", "ah", "like", "please", "okay", "ok", "just"}

# Spoken digit/number vocabulary for words_to_number.
_UNITS = {
    "zero": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}
_ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}

# Words that act as the "-" between two number runs in a submittal id.
_DASH_WORDS = {"dash", "hyphen", "to", "through"}


def normalize_text(text: str) -> str:
    """Lowercase, strip filler words, and normalize whitespace/punctuation.

    Keeps digits, letters, hyphens, and apostrophes; turns everything else into
    spaces so downstream regexes see clean token boundaries.
    """
    if not text:
        return ""
    text = text.lower()
    # Spoken punctuation -> symbol so "dash" survives as a word boundary token.
    text = re.sub(r"[^\w'\-]+", " ", text)
    tokens = [t for t in text.split() if t and t not in _FILLER]
    return " ".join(tokens)


def words_to_number(phrase: str) -> Optional[int]:
    """Convert a short spelled-out number phrase to an int.

    Speakers read multi-digit IDs as concatenated groups, not sums: "two thirty
    four" means 2|34 -> 234, "four thirty three" -> 433. We therefore split the
    phrase into number "chunks" (a tens word optionally followed by a unit, a
    teen, or a lone digit/unit) and concatenate their digit strings. "thirty
    four" stays one chunk -> 34; "five" -> 5; digit strings pass through.
    Returns None if no numeric content is found. "X hundred" multiplies the
    preceding chunk by 100 (e.g. "one hundred" -> 100).
    """
    phrase = phrase.strip().lower()
    if not phrase:
        return None

    words = phrase.split()
    chunks: List[str] = []
    i = 0
    while i < len(words):
        w = words[i]
        if w.isdigit():
            chunks.append(w)
            i += 1
        elif w in _TENS:
            val = _TENS[w]
            if i + 1 < len(words) and words[i + 1] in _UNITS and 1 <= _UNITS[words[i + 1]] <= 9:
                val += _UNITS[words[i + 1]]
                i += 2
            else:
                i += 1
            chunks.append(str(val))
        elif w in _UNITS:
            chunks.append(str(_UNITS[w]))
            i += 1
        elif w in _ORDINALS:
            chunks.append(str(_ORDINALS[w]))
            i += 1
        elif w == "hundred" and chunks:
            chunks[-1] = str(int(chunks[-1]) * 100)
            i += 1
        elif w == "thousand" and chunks:
            chunks[-1] = str(int(chunks[-1]) * 1000)
            i += 1
        else:
            i += 1

    if not chunks:
        return None
    return int("".join(chunks))


def _spoken_run_to_digits(run: str) -> Optional[str]:
    """Convert one spoken run (between dash words) to a digit string.

    "two thirty four" -> "234"; "234" -> "234"; "four thirty three" -> "433".
    """
    run = run.strip()
    if not run:
        return None
    if re.fullmatch(r"\d+", run):
        return run
    n = words_to_number(run)
    if n is None:
        return None
    return str(n)


def extract_submittal_id(text: str) -> Optional[str]:
    """Extract a submittal id of the form "<digits>-<digits>" from a fragment.

    Tolerates spoken forms: "234 dash 433", "two thirty four to four thirty
    three", "234-433", "234 433". Returns the canonical "234-433" string or None.
    """
    norm = normalize_text(text)
    if not norm:
        return None

    # Fast path: already-formatted "234-433" or "234 - 433".
    m = re.search(r"\b(\d{1,4})\s*-\s*(\d{1,4})\b", norm)
    if m:
        return f"{m.group(1)}-{m.group(2)}"

    # Split on dash words and try to read two adjacent numeric runs.
    tokens = norm.split()
    dash_idxs = [i for i, t in enumerate(tokens) if t in _DASH_WORDS]
    for di in dash_idxs:
        left = _spoken_run_to_digits(" ".join(tokens[max(0, di - 4):di]))
        right = _spoken_run_to_digits(" ".join(tokens[di + 1:di + 5]))
        if left and right:
            return f"{left}-{right}"

    # Two bare digit groups separated only by space: "234 433".
    m = re.search(r"\b(\d{2,4})\s+(\d{2,4})\b", norm)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return None


# Cue words that introduce a list position, plus filler we skip between cue and number.
_POSITION_CUES = {"number", "position", "slot", "spot", "at", "to"}
_POSITION_SKIP = {"number", "position", "slot", "spot", "the"}


def extract_position(text: str) -> Optional[int]:
    """Extract a 1-based list position from a fragment.

    Understands "number five", "position 5", "slot 5", "to 5", "to the top"
    (=> 1), and bare ordinals ("fifth"). Submittal-id digits are stripped first
    so "move 234-433 to 5" reads as position 5, not 234. Returns None if no
    position is found.
    """
    norm = normalize_text(text)
    if not norm:
        return None
    # Drop submittal-id-shaped tokens so their digits aren't read as a position.
    norm = re.sub(r"\b\d{1,4}\s*-\s*\d{1,4}\b", " ", norm)
    tokens = norm.split()

    if "top" in tokens:
        return 1
    for word, val in _ORDINALS.items():
        if word in tokens:
            return val

    for idx, tok in enumerate(tokens):
        if tok not in _POSITION_CUES:
            continue
        num_tokens: List[str] = []
        for nxt in tokens[idx + 1:]:
            if nxt.isdigit() or nxt in _UNITS or nxt in _TENS or nxt in _ORDINALS:
                num_tokens.append(nxt)
            elif nxt in _POSITION_SKIP:
                continue
            else:
                break
        if num_tokens:
            n = words_to_number(" ".join(num_tokens))
            if n and n >= 1:
                return n
    return None


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def match_submittal_id(spoken: Optional[str], known_ids: Iterable[str]) -> Tuple[Optional[str], List[str]]:
    """Resolve a spoken submittal id against the set of known ids.

    Returns (resolved_id, candidates). resolved_id is set only on an
    unambiguous match (exact, or a single close fuzzy match). When several ids
    are equally close, resolved_id is None and candidates lists them so the
    caller can ask the user to disambiguate.
    """
    if not spoken:
        return None, []
    known = list(known_ids)
    if spoken in known:
        return spoken, [spoken]

    # Fuzzy: rank by similarity, keep those within a tight band of the best.
    scored = sorted(((_similarity(spoken, k), k) for k in known), reverse=True)
    if not scored:
        return None, []
    best_score = scored[0][0]
    if best_score < 0.8:
        return None, []
    close = [k for s, k in scored if best_score - s <= 0.05]
    if len(close) == 1:
        return close[0], close
    return None, close


def match_drafter(spoken: Optional[str], known_names: Iterable[str]) -> Tuple[Optional[str], List[str]]:
    """Resolve a spoken first name against known ball_in_court values.

    ball_in_court may be a full name ("Colton Reed") or comma-separated; match
    case-insensitively on any first name. Returns (resolved_name, candidates)
    using the same disambiguation contract as match_submittal_id.
    """
    if not spoken:
        return None, []
    spoken = spoken.strip().lower()
    if not spoken:
        return None, []

    matches = []
    for name in known_names:
        if not name:
            continue
        first_names = [p.strip().split()[0].lower() for p in name.split(",") if p.strip()]
        if spoken in first_names or any(_similarity(spoken, fn) >= 0.85 for fn in first_names):
            matches.append(name)
    matches = list(dict.fromkeys(matches))  # de-dup, preserve order
    if len(matches) == 1:
        return matches[0], matches
    return None, matches
