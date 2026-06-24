"""Per-shape supplier-order extractors.

Each module owns one email/attachment shape and exposes `NAME`, `matches(record)`
and `extract(record) -> dict | None`, all returning the normalized order dict
shape `extract_header` builds (supplier/po/job/release/orderer + event_type +
supplier_order_no + lines[]). `classify.extract_order` routes a RawSourceRecord to
the right one, falling back to the Claude LLM extractor for anything novel.
"""
