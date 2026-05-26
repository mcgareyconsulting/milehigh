"""Inbound intake for vendor part pick-up emails.

The user forwards a vendor pick-up email to an address handled by an inbound-email
provider (CloudMailin), which POSTs the parsed message to /brain/pickup/inbound-email
(app/brain/job_log/routes.py). That route normalizes the payload
(app/pickup_email/cloudmailin.py) and calls ingest_pickup_email() to match the release
and queue the Trello card. No Gmail, no polling, no webhook secret in code — push-based.
"""
from app.pickup_email.ingest import ingest_pickup_email

__all__ = ["ingest_pickup_email"]
