"""Token → USD pricing for the BB chat, so each turn carries a real cost.

Kept local to bb_chat (rather than importing the meetings pricing table) because
this feature prices Sonnet 5 including cache-read/write tokens, which the meetings
extractor doesn't track. Prefix match keeps dated model ids working.

Rates are USD per million tokens (input, output). Cache reads bill at ~0.1x input;
cache writes (5-minute TTL) at ~1.25x input — see the prompt-caching economics.
"""

# (input, output) $/1M tokens.
MODEL_PRICING = {
    "claude-sonnet-5": (3.0, 15.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-opus-4": (5.0, 25.0),
    "claude-haiku-4": (1.0, 5.0),
}
_DEFAULT_PRICING = (5.0, 25.0)  # assume Opus-tier if unknown — never under-report cost

_CACHE_READ_MULTIPLIER = 0.1
_CACHE_WRITE_MULTIPLIER = 1.25


def _price(model: str):
    for prefix, rates in MODEL_PRICING.items():
        if (model or "").startswith(prefix):
            return rates
    return _DEFAULT_PRICING


def usage_from_body(body: dict, fallback_model: str) -> dict:
    """input/output/cache token counts + computed USD cost from a Messages API response."""
    u = body.get("usage") or {}
    model = body.get("model") or fallback_model
    inp = int(u.get("input_tokens") or 0)
    out = int(u.get("output_tokens") or 0)
    cache_read = int(u.get("cache_read_input_tokens") or 0)
    cache_write = int(u.get("cache_creation_input_tokens") or 0)
    pin, pout = _price(model)
    cost = (
        inp / 1e6 * pin
        + out / 1e6 * pout
        + cache_read / 1e6 * pin * _CACHE_READ_MULTIPLIER
        + cache_write / 1e6 * pin * _CACHE_WRITE_MULTIPLIER
    )
    return {
        "model": model,
        "input_tokens": inp,
        "output_tokens": out,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "cost_usd": round(cost, 6),
    }


def accumulate(totals: dict, turn: dict) -> dict:
    """Sum per-request usage dicts into a running total for the whole chat turn."""
    for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"):
        totals[k] = totals.get(k, 0) + int(turn.get(k) or 0)
    totals["cost_usd"] = round(totals.get("cost_usd", 0.0) + float(turn.get("cost_usd") or 0.0), 6)
    totals["model"] = turn.get("model") or totals.get("model")
    return totals
