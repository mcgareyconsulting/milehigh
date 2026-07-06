"""BB (Banana Boy) chat — a read-only Q&A assistant over the app database.

Phase 1: users with the ``is_bb_chat`` flag ask natural-language questions; the
agent answers by running read-only SQL against the live database. It never mutates
data. Every assistant turn logs a wide ``bb_chat_turn`` event anchored on the
Anthropic ``request-id`` header so spend can be reconciled against the dashboard.

This is the repo's first Anthropic tool-use / agentic loop. It follows the existing
raw-``requests`` idiom (see app/brain/meetings/extract.py) rather than adding an SDK.
"""
