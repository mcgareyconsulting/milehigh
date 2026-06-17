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
    # threaded=True so the dev server handles concurrent requests. The frontend fires
    # bursts of parallel calls (e.g. the timeline release-detail modal loads checklist +
    # photos + drawings at once, and the drawing hub adds more); a single-threaded server
    # resets the colliding connections, surfacing as intermittent "HTTP 0" in the browser.
    # Production runs under gunicorn (multi-worker) and is unaffected by this.
    app.run(debug=False, port=8000, threaded=True)
