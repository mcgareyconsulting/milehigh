"""T&M ticket ingestion — the first document type through the Brain's ingestion path.

v1 is the legacy-paper pipeline: upload a scan/photo/PDF of a handwritten T&M
ticket, Claude vision extracts structured fields with per-field confidence, a
human reviews/corrects in a modal, then confirms (optionally linking a release)
or rejects. Everything defaults to AI vision — tickets are 1-2 pages, so no
text-layer routing is needed at this volume.
"""
