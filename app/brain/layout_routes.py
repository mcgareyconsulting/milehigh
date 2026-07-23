"""
@milehigh-header
schema_version: 1
purpose: Persist per-user dashboard layouts for the K2 configurable grid engine. Each grid
  instance ("surface") saves one layout per user — panel order, S/M/L size class, and which
  widgets are hidden — so a PM's arrangement of the Projects page (or their Employee Home)
  follows them across devices. The grid falls back to localStorage when these endpoints are
  unavailable, so persistence is a convenience, never a hard dependency — the server never
  validates ids against a canonical set; the client reconciles unknown/missing ids against
  the panels it actually renders.
exports:
  (routes registered on brain_bp)
    GET /brain/layout/<surface_key>  -> {surface_key, layout: [...], updated_at}
    PUT /brain/layout/<surface_key>  -> same, after upsert
                                        (body: {layout: [{id, span, hidden}, ...]})
imports_from: [flask, app.brain, app.auth.utils, app.models, app.logging_config]
imported_by: [app/brain/__init__.py]
invariants:
  - Login-gated; a layout row belongs to exactly one (user, surface) pair.
  - layout is a bounded list of {id, span, hidden}; over-long lists/ids and bad spans are
    rejected, not truncated. Bare id strings (the pre-size-class format) are still accepted.
"""
from flask import jsonify, request

from app.brain import brain_bp
from app.auth.utils import login_required, get_current_user
from app.models import db, UserPanelLayout
from app.logging_config import get_logger

logger = get_logger(__name__)

# Guardrails so a malformed client can't stuff the JSON column. A grid surface has a
# handful of panels; these caps are far above any real layout.
MAX_PANELS = 100
MAX_ID_LEN = 120
VALID_SPANS = (1, 2, 3)      # width, in grid columns
VALID_ROWS = (1, 2, 3, 4)    # height, in grid row units


def _clean_layout(raw):
    """Coerce the request body's `layout` into a bounded list of {id, span, hidden}.

    Returns (layout, error). Dedupes by id while preserving first-seen order so a buggy
    client that repeats a panel can't inflate the stored list. Accepts bare id strings —
    the format used before size classes existed — and normalizes them to full entries.
    """
    if raw is None:
        return None, "Missing 'layout'."
    if not isinstance(raw, list):
        return None, "'layout' must be a list of panel entries."
    if len(raw) > MAX_PANELS:
        return None, f"Too many panels (max {MAX_PANELS})."

    layout, seen = [], set()
    for item in raw:
        if isinstance(item, str):
            item = {"id": item}
        if not isinstance(item, dict):
            return None, "Each layout entry must be an object or a panel id string."

        panel_id = item.get("id")
        if not isinstance(panel_id, str):
            return None, "Panel ids must be strings."
        panel_id = panel_id.strip()
        if not panel_id:
            continue
        if len(panel_id) > MAX_ID_LEN:
            return None, f"Panel id too long (max {MAX_ID_LEN})."
        if panel_id in seen:
            continue

        span = item.get("span", 1)
        if span is None:
            span = 1
        # bool is an int subclass in Python, so True would sneak past `in VALID_SPANS`.
        if isinstance(span, bool) or span not in VALID_SPANS:
            return None, f"span must be one of {VALID_SPANS}."

        rows = item.get("rows", 2)
        if rows is None:
            rows = 2
        if isinstance(rows, bool) or rows not in VALID_ROWS:
            return None, f"rows must be one of {VALID_ROWS}."

        seen.add(panel_id)
        layout.append({
            "id": panel_id,
            "span": span,
            "rows": rows,
            "hidden": item.get("hidden") is True,
        })
    return layout, None


@brain_bp.route("/layout/<surface_key>", methods=["GET"])
@login_required
def get_layout(surface_key):
    """This user's saved layout for one grid surface (empty list if none saved)."""
    user = get_current_user()
    row = UserPanelLayout.query.filter_by(
        user_id=user.id, surface_key=surface_key
    ).first()
    if row is None:
        return jsonify({"surface_key": surface_key, "layout": [], "updated_at": None}), 200
    return jsonify(row.to_dict()), 200


@brain_bp.route("/layout/<surface_key>", methods=["PUT"])
@login_required
def put_layout(surface_key):
    """Upsert this user's layout for one grid surface."""
    user = get_current_user()
    if len(surface_key) > 120:
        return jsonify({"error": "surface_key too long."}), 400

    layout, err = _clean_layout((request.get_json(silent=True) or {}).get("layout"))
    if err:
        return jsonify({"error": err}), 400

    try:
        row = UserPanelLayout.query.filter_by(
            user_id=user.id, surface_key=surface_key
        ).first()
        if row is None:
            row = UserPanelLayout(user_id=user.id, surface_key=surface_key, layout=layout)
            db.session.add(row)
        else:
            row.layout = layout
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error(
            "layout_save_failed",
            user_id=user.id,
            surface_key=surface_key,
            error=str(exc),
            error_type=type(exc).__name__,
            exc_info=True,
        )
        return jsonify({"error": "Failed to save layout."}), 500

    logger.info(
        "layout_saved",
        user_id=user.id,
        surface_key=surface_key,
        panel_count=len(layout),
        hidden_count=sum(1 for entry in layout if entry["hidden"]),
    )
    return jsonify(row.to_dict()), 200
