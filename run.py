"""
@milehigh-header
schema_version: 1
purpose: Application entry point — creates the Flask app and runs it on port 8000.
exports:
  app: The Flask application instance (used by WSGI servers)
imports_from: [app]
imported_by: []
invariants:
  - Application entry point — invoked directly (`python run.py`), not imported by other modules.
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
"""
import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=False, port=8000)
