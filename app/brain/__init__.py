"""
@milehigh-header
schema_version: 1
purpose: Central blueprint that aggregates all Brain sub-modules (job log, DWL, map, board, notifications) under a single /brain URL prefix.
exports:
  brain_bp: Flask Blueprint registered at /brain, used by all sub-module route files.
imports_from: [flask, app.logging_config, app.brain.job_log.routes, app.brain.drafting_work_load.routes, app.brain.map.routes, app.brain.board.routes, app.brain.notification_routes]
imported_by: [app/__init__.py, app/brain/job_log/routes.py, app/brain/drafting_work_load/routes.py, app/brain/board/routes.py, app/brain/notification_routes.py, app/brain/map/routes.py]
invariants:
  - Sub-module route files import brain_bp from here; circular import is intentional and resolved by bottom-of-file imports.
  - All sub-blueprint routes are registered on brain_bp, not on separate blueprints.
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)

MHMW Brain Module
Flask Blueprint for all services and routes related to MHMW Operations.

This module provides routes for data collection and display of information related to
the Job Log, Job History Changelog, as well as other operations related to the
combination and distillation of MHMW Ops data.
"""
from flask import Blueprint
from app.logging_config import get_logger


# Logging
# logger = get_logger()

brain_bp = Blueprint("brain", __name__)

from app.brain.job_log import routes as job_log_routes
from app.brain.job_log import pdf_markup_routes  # noqa: F401  (registers /releases/<id>/drawing endpoints)
from app.brain.drafting_work_load import routes as dwl_routes
from app.brain.map import routes as map_routes
from app.brain.board import routes as board_routes
from app.brain import notification_routes
