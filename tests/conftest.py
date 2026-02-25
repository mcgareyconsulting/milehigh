"""
Pytest configuration for the test suite.

Ensures TESTING=1 is set before any test runs so create_app() and db_config
always use in-memory SQLite and never connect to sandbox or production.
This prevents tests (e.g. db.drop_all()) from touching real databases.
"""
import os

# Must run before any test module imports create_app
os.environ.setdefault("TESTING", "1")
