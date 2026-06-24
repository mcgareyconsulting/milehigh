"""Route a RawSourceRecord to the extractor that fits its shape.

Deterministic extractors are tried in order (cheap, exact, no tokens); the first
that matches AND yields line items wins. Anything unmatched or empty falls through
to the Claude LLM extractor, which reads the PDF natively. Returns the normalized
order dict, or None when nothing — not even the LLM — can recover line items.
"""
from app.brain.material_orders.extractors import (
    dencol_confirm,
    dencol_drawing,
    drexel_inline,
    llm,
)
from app.logging_config import get_logger

logger = get_logger(__name__)

# Order matters: inline body lines, then the priced confirm table, then the
# drawing callouts. (The shapes don't overlap, but a stable order keeps routing
# predictable and lets the cheapest match win.)
DETERMINISTIC = [drexel_inline, dencol_confirm, dencol_drawing]


def extract_order(record):
    """RawSourceRecord -> normalized order dict, or None."""
    for extractor in DETERMINISTIC:
        try:
            if not extractor.matches(record):
                continue
            result = extractor.extract(record)
        except Exception:  # noqa: BLE001 — a broken extractor must not block the others/LLM
            logger.warning("material_order_extractor_error", extractor=extractor.NAME,
                           source_record_id=getattr(record, "id", None), exc_info=True)
            continue
        if result and result.get("lines"):
            logger.info("material_order_extracted", extractor=extractor.NAME,
                        source_record_id=getattr(record, "id", None),
                        lines=len(result["lines"]))
            return result

    result = llm.extract(record)
    if result and result.get("lines"):
        logger.info("material_order_extracted", extractor=llm.NAME,
                    source_record_id=getattr(record, "id", None),
                    lines=len(result["lines"]))
        return result
    return None
