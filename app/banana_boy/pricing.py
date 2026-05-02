"""Pricing tables and cost computation for Banana Boy API usage.

Prices are USD and reflect public list prices as of 2026-04. Verify against
provider pricing pages before using these for billing or invoicing.
"""

# Per 1M tokens.
ANTHROPIC_PRICING = {
    "claude-haiku-4-5-20251001": {
        "input": 1.00,
        "output": 5.00,
        "cache_read": 0.10,
        "cache_creation": 1.25,
    },
}

# OpenAI Whisper: per minute of audio.
# OpenAI TTS: per 1M characters of input.
OPENAI_PRICING = {
    "whisper-1": {"per_minute": 0.006},
    "gpt-4o-mini-tts": {"per_million_chars": 0.60},
    "tts-1": {"per_million_chars": 15.00},
    "tts-1-hd": {"per_million_chars": 30.00},
}


def anthropic_cost(model: str, input_tokens: int = 0, output_tokens: int = 0,
                   cache_read_tokens: int = 0, cache_creation_tokens: int = 0) -> float | None:
    p = ANTHROPIC_PRICING.get(model)
    if not p:
        return None
    return (
        (input_tokens or 0) * p["input"] / 1_000_000
        + (output_tokens or 0) * p["output"] / 1_000_000
        + (cache_read_tokens or 0) * p["cache_read"] / 1_000_000
        + (cache_creation_tokens or 0) * p["cache_creation"] / 1_000_000
    )


def whisper_cost(model: str, audio_seconds: float | None) -> float | None:
    p = OPENAI_PRICING.get(model)
    if not p or audio_seconds is None:
        return None
    return audio_seconds / 60.0 * p["per_minute"]


def tts_cost(model: str, input_chars: int) -> float | None:
    p = OPENAI_PRICING.get(model)
    if not p:
        return None
    return (input_chars or 0) * p["per_million_chars"] / 1_000_000
