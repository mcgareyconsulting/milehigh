from app.brain import brain_bp
from flask import jsonify, request
from app.brain.drafting_work_load.service import (
    SubmittalOrderingService,
    SubmittalOrderUpdate,
    DraftingWorkLoadService,
    UrgencyService,
    LocationService,
)
from app.logging_config import get_logger
from app.models import Submittals, ProcoreOutbox, db
from app.auth.utils import login_required, admin_required, get_current_user
from app.procore.api import SUBMITTAL_STATUSES, VALID_SUBMITTAL_STATUS_IDS, SUBMITTAL_STATUS_ID_TO_NAME
from app.procore.client import get_procore_client
from app.procore.helpers import create_submittal_event
from datetime import datetime

logger = get_logger(__name__)


@brain_bp.route('/drafting-work-load')
@login_required
def drafting_work_load():
    """Return Drafting Work Load data from the db.
    Query param tab: 'open' (default) = submittals with status Open; 'draft' = submittals with status not Open or Closed.
    Optional query params lat, lng: when both provided, only submittals for job_sites that contain or are near
    the point (active job_sites; PostGIS: within 25m, else point-in-polygon)."""
    try:
        tab = request.args.get('tab', 'open')
        if tab not in ('open', 'draft'):
            tab = 'open'
        lat_raw = request.args.get('lat')
        lng_raw = request.args.get('lng')
        job_numbers_filter = None
        if lat_raw is not None and lng_raw is not None:
            try:
                lat = float(lat_raw)
                lng = float(lng_raw)
            except (TypeError, ValueError):
                pass
            else:
                job_numbers_filter = LocationService.get_job_numbers_for_location(lat, lng)
                if not job_numbers_filter:
                    return jsonify({"submittals": []}), 200

        submittals = DraftingWorkLoadService.get_dwl_submittals(job_numbers_filter, tab=tab)
        return jsonify({
            "submittals": [submittal.to_dict() for submittal in submittals]
        }), 200
    except Exception as exc:
        logger.error("Error getting drafting work load data", error=str(exc))
        return jsonify({
            "error": "Failed to get drafting work load data",
            "details": str(exc)
        }), 500

@brain_bp.route("/drafting-work-load/order", methods=["PUT"])
@admin_required
def update_submittal_order():
    """Update the order_number for a submittal (simple update, no cascading)"""
    try:
        data = request.json
        submittal_id = str(data.get('submittal_id', ''))
        order_number = data.get('order_number')

        if not submittal_id:
            return jsonify({"error": "submittal_id is required"}), 400
        
        # Validate order number
        is_valid, error_msg = SubmittalOrderingService.validate_order_number(order_number)
        if not is_valid:
            return jsonify({"error": error_msg}), 400

        # Convert to float if not None, and round urgency slots to tenth place
        if order_number is not None:
            order_number = float(order_number)
            # If it's an urgency slot (0 < order < 1), round to nearest tenth
            if 0 < order_number < 1:
                order_number = round(order_number, 1)

        # Get the submittal
        submittal = Submittals.query.filter_by(submittal_id=submittal_id).first()
        if not submittal:
            return jsonify({"error": "Submittal not found"}), 404

        old_order = SubmittalOrderingService.safe_float_order(submittal.order_number)

        # Get all submittals in the same group
        all_group_submittals = []
        if submittal.ball_in_court:
            all_group_submittals = Submittals.query.filter_by(
                ball_in_court=submittal.ball_in_court
            ).all()

        if all_group_submittals:
            # Calculate updates
            update_request = SubmittalOrderUpdate(
                submittal_id=submittal_id,
                new_order=order_number,
                old_order=old_order,
                ball_in_court=submittal.ball_in_court
            )
            
            updates = SubmittalOrderingService.calculate_updates(
                update_request, 
                all_group_submittals
            )
            
            # Apply updates
            for subm, new_order_val in updates:
                subm.order_number = new_order_val
                subm.last_updated = datetime.utcnow()
        else:
            # No group, just update this one
            submittal.order_number = order_number
            submittal.last_updated = datetime.utcnow()
        
        db.session.commit()

        user = get_current_user()
        try:
            create_submittal_event(
                submittal_id, "updated",
                {"order_number": {"old": old_order, "new": order_number}},
                webhook_payload=None, source="Brain",
                internal_user_id=user.id if user else None,
            )
        except Exception as event_err:
            logger.warning("Failed to create SubmittalEvent for order update: %s", event_err)

        return jsonify({
            "success": True,
            "submittal_id": submittal_id,
            "order_number": order_number
        }), 200

    except Exception as exc:
        logger.error("Error updating submittal order", error=str(exc))
        db.session.rollback()
        return jsonify({
            "error": "Failed to update order",
            "details": str(exc)
        }), 500

@brain_bp.route("/drafting-work-load/notes", methods=["PUT"])
@admin_required
def update_submittal_notes():
    """Update the notes for a submittal"""
    try:
        data = request.json
        submittal_id = data.get('submittal_id')
        notes = data.get('notes')
        
        if submittal_id is None:
            return jsonify({
                "error": "submittal_id is required"
            }), 400
        
        # Ensure submittal_id is a string for proper database comparison
        submittal_id = str(submittal_id)
        
        submittal = Submittals.query.filter_by(submittal_id=submittal_id).first()
        if not submittal:
            return jsonify({
                "error": "Submittal not found"
            }), 404
        
        old_notes = submittal.notes
        # Update via service layer
        DraftingWorkLoadService.update_notes(submittal, notes)
        
        db.session.commit()

        user = get_current_user()
        try:
            create_submittal_event(
                submittal_id, "updated",
                {"notes": {"old": old_notes, "new": notes}},
                webhook_payload=None, source="Brain",
                internal_user_id=user.id if user else None,
            )
        except Exception as event_err:
            logger.warning("Failed to create SubmittalEvent for notes update: %s", event_err)
        
        return jsonify({
            "success": True,
            "submittal_id": submittal_id,
            "notes": notes
        }), 200
    except Exception as exc:
        logger.error("Error updating submittal notes", error=str(exc))
        db.session.rollback()
        return jsonify({
            "error": "Failed to update notes",
            "details": str(exc)
        }), 500

@brain_bp.route("/drafting-work-load/submittal-drafting-status", methods=["PUT"])
@admin_required
def update_submittal_drafting_status():
    """Update the submittal_drafting_status for a submittal"""
    try:
        data = request.json
        submittal_id = data.get('submittal_id')
        submittal_drafting_status = data.get('submittal_drafting_status')
        
        if submittal_id is None:
            return jsonify({
                "error": "submittal_id is required"
            }), 400
        
        # Allow None or empty string for blank status
        if submittal_drafting_status is None:
            submittal_drafting_status = ''
        
        # Validate status value (empty string is allowed for blank/placeholder)
        valid_statuses = ['', 'STARTED', 'NEED VIF', 'HOLD']
        if submittal_drafting_status not in valid_statuses:
            return jsonify({
                "error": f"submittal_drafting_status must be one of: (blank), {', '.join([s for s in valid_statuses if s])}"
            }), 400
        
        # Ensure submittal_id is a string for proper database comparison
        submittal_id = str(submittal_id)
        
        submittal = Submittals.query.filter_by(submittal_id=submittal_id).first()
        if not submittal:
            return jsonify({
                "error": "Submittal not found"
            }), 404
        
        old_status = submittal.submittal_drafting_status or ""
        # Update via service layer
        success, error_msg = DraftingWorkLoadService.update_drafting_status(
            submittal, 
            submittal_drafting_status
        )
        
        if not success:
            return jsonify({"error": error_msg}), 400
        
        db.session.commit()

        user = get_current_user()
        try:
            create_submittal_event(
                submittal_id, "updated",
                {"submittal_drafting_status": {"old": old_status, "new": submittal_drafting_status or ""}},
                webhook_payload=None, source="Brain",
                internal_user_id=user.id if user else None,
            )
        except Exception as event_err:
            logger.warning("Failed to create SubmittalEvent for drafting status update: %s", event_err)
        
        return jsonify({
            "success": True,
            "submittal_id": submittal_id,
            "submittal_drafting_status": submittal_drafting_status
        }), 200
    except Exception as exc:
        logger.error("Error updating submittal drafting status", error=str(exc))
        db.session.rollback()
        return jsonify({
            "error": "Failed to update submittal_drafting_status",
            "details": str(exc)
        }), 500

@brain_bp.route("/drafting-work-load/step", methods=["POST"])
@admin_required
def step_submittal_order():
    """Step a submittal order up or down within its zone (simple 2-item swap)"""
    try:
        data = request.json
        submittal_id = str(data.get('submittal_id', ''))
        direction = data.get('direction', '')

        if not submittal_id:
            return jsonify({"error": "submittal_id is required"}), 400

        if direction not in ('up', 'down'):
            return jsonify({"error": "direction must be 'up' or 'down'"}), 400

        submittal = Submittals.query.filter_by(submittal_id=submittal_id).first()
        if not submittal:
            return jsonify({"error": "Submittal not found"}), 404

        if not submittal.ball_in_court:
            return jsonify({"error": "Submittal must have a ball_in_court value"}), 400

        all_group_submittals = Submittals.query.filter_by(
            ball_in_court=submittal.ball_in_court
        ).all()

        old_order = submittal.order_number

        try:
            updates = SubmittalOrderingService.step_order(submittal, direction, all_group_submittals)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        # Capture swap partner info before applying updates
        neighbor = next((subm for subm, _ in updates if subm.submittal_id != submittal_id), None)
        neighbor_old_order = neighbor.order_number if neighbor else None

        for subm, new_order_val in updates:
            subm.order_number = new_order_val
            subm.last_updated = datetime.utcnow()

        db.session.commit()

        user = get_current_user()
        try:
            event_payload = {
                "order_step": direction,
                "order_number": {"old": old_order, "new": submittal.order_number},
            }
            if neighbor:
                event_payload["swapped_with"] = {
                    "submittal_id": neighbor.submittal_id,
                    "order_number": {"old": neighbor_old_order, "new": neighbor.order_number},
                }
            create_submittal_event(
                submittal_id, "updated",
                event_payload,
                webhook_payload=None, source="Brain",
                internal_user_id=user.id if user else None,
            )
        except Exception as event_err:
            logger.warning("Failed to create SubmittalEvent for step: %s", event_err)

        return jsonify({
            "success": True,
            "submittal_id": submittal_id,
            "direction": direction,
            "updates": [{"submittal_id": subm.submittal_id, "order_number": new_order_val}
                        for subm, new_order_val in updates]
        }), 200

    except Exception as exc:
        logger.error("Error stepping submittal order", error=str(exc))
        db.session.rollback()
        return jsonify({
            "error": "Failed to step submittal order",
            "details": str(exc)
        }), 500


@brain_bp.route("/drafting-work-load/resort", methods=["POST"])
@admin_required
def resort_drafter_order():
    """Compress ordered (>= 1) submittals for a drafter to sequential integers starting at 1."""
    try:
        data = request.json
        ball_in_court = str(data.get('ball_in_court', '')).strip()

        if not ball_in_court:
            return jsonify({"error": "ball_in_court is required"}), 400

        all_group_submittals = Submittals.query.filter_by(ball_in_court=ball_in_court).all()

        updates = SubmittalOrderingService.resort_ordered_submittals(all_group_submittals)

        for subm, new_order_val in updates:
            subm.order_number = new_order_val
            subm.last_updated = datetime.utcnow()

        db.session.commit()

        user = get_current_user()
        for subm, new_order_val in updates:
            try:
                create_submittal_event(
                    subm.submittal_id, "updated",
                    {"resort": True, "order_number": {"new": new_order_val}},
                    webhook_payload=None, source="Brain",
                    internal_user_id=user.id if user else None,
                )
            except Exception as event_err:
                logger.warning("Failed to create SubmittalEvent for resort: %s", event_err)

        return jsonify({
            "success": True,
            "ball_in_court": ball_in_court,
            "updates": [{"submittal_id": subm.submittal_id, "order_number": new_order_val}
                        for subm, new_order_val in updates]
        }), 200

    except Exception as exc:
        logger.error("Error resorting submittal order", error=str(exc))
        db.session.rollback()
        return jsonify({
            "error": "Failed to resort submittal order",
            "details": str(exc)
        }), 500


@brain_bp.route("/drafting-work-load/bump", methods=["POST"])
@admin_required
def bump_submittal():
    """Bump a submittal: ordered (>= 1) → urgent slot, or unordered (null) → end of ordered list"""
    try:
        data = request.json
        submittal_id = str(data.get('submittal_id', ''))

        if not submittal_id:
            return jsonify({"error": "submittal_id is required"}), 400

        submittal = Submittals.query.filter_by(submittal_id=submittal_id).first()
        if not submittal:
            return jsonify({"error": "Submittal not found"}), 404

        if not submittal.ball_in_court:
            return jsonify({"error": "Submittal must have a ball_in_court value to bump"}), 400

        if submittal.order_number is None:
            # Unordered → Ordered: append to end of ordered list
            bumped = UrgencyService.bump_unordered_to_ordered(
                submittal,
                submittal_id,
                submittal.ball_in_court
            )
            if not bumped:
                return jsonify({
                    "error": "Submittal could not be bumped.",
                    "details": "Submittal already has an order number."
                }), 400
            message = "Unordered submittal added to end of ordered list"
        else:
            # Ordered → Urgent: existing ladder logic
            bumped = UrgencyService.bump_order_number_to_urgent(
                submittal,
                submittal_id,
                submittal.ball_in_court
            )
            if not bumped:
                return jsonify({
                    "error": "Submittal could not be bumped. Order number must be an integer >= 1.",
                    "details": "The bump function only works on submittals with integer order numbers >= 1"
                }), 400
            message = "Submittal bumped to urgency slot with cascading effects applied"

        db.session.commit()

        user = get_current_user()
        try:
            create_submittal_event(
                submittal_id, "updated",
                {"order_bumped": True, "order_number": submittal.order_number},
                webhook_payload=None, source="Brain",
                internal_user_id=user.id if user else None,
            )
        except Exception as event_err:
            logger.warning("Failed to create SubmittalEvent for bump: %s", event_err)

        return jsonify({
            "success": True,
            "submittal_id": submittal_id,
            "order_number": submittal.order_number,
            "message": message
        }), 200

    except Exception as exc:
        logger.error("Error bumping submittal", error=str(exc))
        db.session.rollback()
        return jsonify({
            "error": "Failed to bump submittal",
            "details": str(exc)
        }), 500

@brain_bp.route("/drafting-work-load/submittal-statuses")
@login_required
def get_submittal_statuses():
    """Return the coded list of submittal statuses for the company (for dropdowns)."""
    return jsonify({"submittal_statuses": SUBMITTAL_STATUSES}), 200


@brain_bp.route("/drafting-work-load/procore-status", methods=["PUT"])
@admin_required
def update_submittal_procore_status():
    """Update a submittal's Procore status (Draft/Open/Closed/etc.) via Procore API and sync DB."""
    try:
        data = request.json
        submittal_id = data.get("submittal_id")
        status_id = data.get("status_id")

        if submittal_id is None:
            return jsonify({"error": "submittal_id is required"}), 400
        if status_id is None:
            return jsonify({"error": "status_id is required"}), 400

        try:
            status_id = int(status_id)
        except (TypeError, ValueError):
            return jsonify({"error": "status_id must be an integer"}), 400

        if status_id not in VALID_SUBMITTAL_STATUS_IDS:
            return jsonify({
                "error": f"status_id {status_id} is not allowed for this company",
                "allowed_ids": sorted(VALID_SUBMITTAL_STATUS_IDS),
            }), 400

        submittal_id = str(submittal_id)
        submittal = Submittals.query.filter_by(submittal_id=submittal_id).first()
        if not submittal:
            return jsonify({"error": "Submittal not found"}), 404

        project_id = submittal.procore_project_id
        if not project_id:
            return jsonify({"error": "Submittal has no procore_project_id"}), 400
        try:
            project_id = int(project_id)
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid procore_project_id"}), 400

        old_status = submittal.status
        new_status = SUBMITTAL_STATUS_ID_TO_NAME[status_id]

        # Record outgoing API call in ProcoreOutbox BEFORE calling Procore.
        # The webhook handler checks this table to identify echo webhooks.
        outbox_entry = ProcoreOutbox(
            submittal_id=submittal_id,
            project_id=project_id,
            action='update_status',
            request_payload={'status_id': status_id},
            status='processing',
        )
        db.session.add(outbox_entry)
        db.session.commit()  # commit before API call so webhook handler sees it immediately

        procore_client = get_procore_client()
        try:
            procore_client.update_submittal_status(project_id, int(submittal_id), status_id)
        except Exception as api_exc:
            outbox_entry.status = 'failed'
            outbox_entry.error_message = str(api_exc)[:500]
            db.session.commit()
            raise

        outbox_entry.status = 'completed'
        outbox_entry.completed_at = datetime.utcnow()

        # Create Brain event *before* committing submittal so we always record it;
        # otherwise a fast webhook can create the same payload and our create would be skipped as duplicate.
        user = get_current_user()
        try:
            created = create_submittal_event(
                submittal_id, "updated",
                {"status": {"old": old_status, "new": new_status}},
                webhook_payload=None, source="Brain",
                internal_user_id=user.id if user else None,
            )
            if not created:
                logger.debug(
                    "SubmittalEvent for Procore status update skipped (likely duplicate payload_hash) submittal_id=%s",
                    submittal_id,
                )
        except Exception as event_err:
            logger.error(
                "Failed to create SubmittalEvent for Procore status update: %s",
                event_err,
                exc_info=True,
            )

        submittal.status = new_status
        db.session.commit()

        return jsonify({
            "success": True,
            "submittal_id": submittal_id,
            "status_id": status_id,
            "status": new_status,
        }), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as exc:
        logger.error("Error updating submittal Procore status", error=str(exc))
        db.session.rollback()
        return jsonify({
            "error": "Failed to update Procore status",
            "details": str(exc),
        }), 500


@brain_bp.route("/drafting-work-load/due-date", methods=["PUT"])
@admin_required
def update_submittal_due_date():
    """Update the due_date for a submittal"""
    try:
        data = request.json
        submittal_id = data.get('submittal_id')
        due_date = data.get('due_date')
        
        if submittal_id is None:
            return jsonify({
                "error": "submittal_id is required"
            }), 400
        
        # Allow None or empty string for blank due date
        if due_date is None or due_date == '':
            due_date = None
        
        # Ensure submittal_id is a string for proper database comparison
        submittal_id = str(submittal_id)
        
        submittal = Submittals.query.filter_by(submittal_id=submittal_id).first()
        if not submittal:
            return jsonify({
                "error": "Submittal not found"
            }), 404
        
        old_due_date = submittal.due_date.isoformat() if submittal.due_date else None
        # Update via service layer
        success, error_msg = DraftingWorkLoadService.update_due_date(
            submittal, 
            due_date
        )
        
        if not success:
            return jsonify({"error": error_msg}), 400
        
        db.session.commit()

        new_due_date = submittal.due_date.isoformat() if submittal.due_date else None
        user = get_current_user()
        try:
            create_submittal_event(
                submittal_id, "updated",
                {"due_date": {"old": old_due_date, "new": new_due_date}},
                webhook_payload=None, source="Brain",
                internal_user_id=user.id if user else None,
            )
        except Exception as event_err:
            logger.warning("Failed to create SubmittalEvent for due date update: %s", event_err)
        
        return jsonify({
            "success": True,
            "submittal_id": submittal_id,
            "due_date": submittal.due_date.isoformat() if submittal.due_date else None
        }), 200
    except Exception as exc:
        logger.error("Error updating submittal due date", error=str(exc))
        db.session.rollback()
        return jsonify({
            "error": "Failed to update due_date",
            "details": str(exc)
        }), 500

