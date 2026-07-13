"""
@milehigh-header
schema_version: 1
purpose: Pure description-matching logic for suggesting job-log releases for DRR submittals.
exports:
  tokenize: Normalize a title/description into a comparable token set
  build_token_frequency: Per-job token frequency Counter used for rarity weighting
  score_candidates: Score all of a job's releases against one submittal title
  suggest: Full suggestion for one submittal -- outcome class + ranked candidates
  OUTCOME_*: Outcome class constants (CONFIDENT / AMBIGUOUS / WEAK / NO_OVERLAP / NO_POOL)
imports_from: []
imported_by: [app/brain/submittal_matching/routes.py]
invariants:
  - Pure functions only: no DB, no Flask, no side effects (unit-testable in isolation).
  - Tokenizer keeps single-character tokens -- building/core numbers ("Bld 8", "Core 5")
    are the discriminating tokens; dropping them collapses sibling releases together.
  - Validated against 59 human-confirmed Rel links on prod (2026-07-12): 36 confident
    agreements, 0 disagreements. Do not loosen CONFIDENT_MIN_SHARED / CONFIDENT_MARGIN
    without re-running that ground-truth check.
updated_by_agent: 2026-07-12T00:00:00Z

Description matcher for the admin Submittal Matching tool.

Matches DRR submittal titles against release descriptions within one job
(project_number == releases.job). Rarity-weighted token overlap: tokens that appear
in few of the job's releases count more than tokens shared by many ("stair" is weak
inside a stair job; "awning" is strong).
"""

import re
from collections import Counter
from typing import Dict, Iterable, List, Optional, Set

# Tokens that carry no scope identity.
STOP_WORDS = {"the", "a", "an", "and", "of", "for", "to", "at", "in", "on", "with", "rev"}

# Vocabulary normalization: submittal titles say "Building 8", release descriptions
# say "Bld 8". install/installation add noise ("Pour Stop Angle Install Bld 15").
NORMALIZE = {"building": "bld", "bldg": "bld", "install": "", "installation": ""}

# Outcome classes for one submittal's suggestion.
OUTCOME_CONFIDENT = "confident"      # clear best candidate -- safe to one-tap confirm
OUTCOME_AMBIGUOUS = "ambiguous"      # close runner-up -- human picks from top candidates
OUTCOME_WEAK = "weak"                # only 1 shared token -- show but don't trust
OUTCOME_NO_OVERLAP = "no_overlap"    # no release shares any token
OUTCOME_NO_POOL = "no_pool"          # job has no releases at all

# Thresholds validated against the Rel-link ground truth (see header invariants).
CONFIDENT_MIN_SHARED = 2   # a confident match needs >= 2 shared tokens
CONFIDENT_MARGIN = 1.5     # ...and a score >= 1.5x the runner-up
TOP_N = 5                  # candidates returned per submittal

_JOB_RELEASE_PREFIX = re.compile(r"\d{3}-\d{3}")
_NUMBER_SIGN = re.compile(r"#0*(\d)")
_WORD = re.compile(r"[a-z0-9]+")


def tokenize(text: Optional[str]) -> Set[str]:
    """Normalize a title or description into a comparable token set.

    Strips job-release prefixes ("340-942 Stair Core C" -> "Stair Core C") so an
    embedded release number can't self-match, expands "#02" -> "2", folds
    building/bldg -> bld, drops stop words, and lightly stems plurals. Single-character
    tokens are KEPT -- they are the building/core discriminators.
    """
    s = _JOB_RELEASE_PREFIX.sub(" ", text or "")
    s = _NUMBER_SIGN.sub(r" \1 ", s)
    out = set()
    for w in _WORD.findall(s.lower()):
        w = NORMALIZE.get(w, w)
        if not w or w in STOP_WORDS:
            continue
        if len(w) > 3 and w.endswith("s"):
            w = w[:-1]
        out.add(w)
    return out


def build_token_frequency(descriptions: Iterable[Optional[str]]) -> Counter:
    """Count, per token, how many of the job's release descriptions contain it.

    Used for rarity weighting: score contribution of a shared token is 1/frequency.
    """
    freq = Counter()
    for d in descriptions:
        freq.update(tokenize(d))
    return freq


def score_candidates(
    title: Optional[str],
    releases: List[Dict],
    token_freq: Counter,
) -> List[Dict]:
    """Score every release of the job against one submittal title.

    Args:
        title: the submittal title
        releases: dicts with at least id/job/release/description (status fields pass through)
        token_freq: the job's token frequency from build_token_frequency

    Returns:
        Candidates that share >= 1 token, sorted best-first. Each carries
        score (rarity-weighted), shared_tokens (sorted list), n_shared.
    """
    title_tokens = tokenize(title)
    scored = []
    for r in releases:
        shared = title_tokens & tokenize(r.get("description"))
        if not shared:
            continue
        score = sum(1.0 / token_freq[t] for t in shared if token_freq[t])
        scored.append({
            **r,
            "score": round(score, 4),
            "shared_tokens": sorted(shared),
            "n_shared": len(shared),
        })
    scored.sort(key=lambda c: -c["score"])
    return scored


def suggest(title: Optional[str], releases: List[Dict], token_freq: Counter) -> Dict:
    """Full suggestion for one submittal: outcome class + top candidates.

    Outcome ladder mirrors the validated probe: NO_POOL (job has no releases),
    NO_OVERLAP, WEAK (<2 shared tokens), AMBIGUOUS (runner-up within margin),
    CONFIDENT (clear winner).
    """
    if not releases:
        return {"outcome": OUTCOME_NO_POOL, "candidates": []}

    scored = score_candidates(title, releases, token_freq)
    if not scored:
        return {"outcome": OUTCOME_NO_OVERLAP, "candidates": []}

    top = scored[0]
    runner = scored[1] if len(scored) > 1 else None

    if top["n_shared"] < CONFIDENT_MIN_SHARED:
        outcome = OUTCOME_WEAK
    elif runner and top["score"] < CONFIDENT_MARGIN * runner["score"]:
        outcome = OUTCOME_AMBIGUOUS
    else:
        outcome = OUTCOME_CONFIDENT

    return {"outcome": outcome, "candidates": scored[:TOP_N]}
