from app.brain import brain_bp
from flask import jsonify, request
from app.brain.drafting_work_load.service import SubmittalOrderingService, SubmittalOrderUpdate, DraftingWorkLoadService, UrgencyService
from app.logging_config import get_logger
from app.models import ProcoreSubmittal, db
from app.auth.utils import login_required
from datetime import datetime

logger = get_logger(__name__)

@brain_bp.route('/drafting-work-load')
@login_required
def drafting_work_load():
    """Return Drafting Work Load data from the db, including submittals with status='Open' or status='Draft'"""
    try:
        # Get submittals with status='Open' or status='Draft'
        submittals = ProcoreSubmittal.query.filter(
            ProcoreSubmittal.status.in_(['Open', 'Draft'])
        ).all()
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
@login_required
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
        submittal = ProcoreSubmittal.query.filter_by(submittal_id=submittal_id).first()
        if not submittal:
            return jsonify({"error": "Submittal not found"}), 404

        # Get all submittals in the same group
        all_group_submittals = []
        if submittal.ball_in_court:
            all_group_submittals = ProcoreSubmittal.query.filter_by(
                ball_in_court=submittal.ball_in_court
            ).all()

        if all_group_submittals:
            # Calculate updates
            update_request = SubmittalOrderUpdate(
                submittal_id=submittal_id,
                new_order=order_number,
                old_order=SubmittalOrderingService.safe_float_order(submittal.order_number),
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
@login_required
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
        
        submittal = ProcoreSubmittal.query.filter_by(submittal_id=submittal_id).first()
        if not submittal:
            return jsonify({
                "error": "Submittal not found"
            }), 404
        
        # Update via service layer
        DraftingWorkLoadService.update_notes(submittal, notes)
        
        db.session.commit()
        
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
@login_required
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
        
        submittal = ProcoreSubmittal.query.filter_by(submittal_id=submittal_id).first()
        if not submittal:
            return jsonify({
                "error": "Submittal not found"
            }), 404
        
        # Update via service layer
        success, error_msg = DraftingWorkLoadService.update_drafting_status(
            submittal, 
            submittal_drafting_status
        )
        
        if not success:
            return jsonify({"error": error_msg}), 400
        
        db.session.commit()
        
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

@brain_bp.route("/drafting-work-load/bump", methods=["POST"])
@login_required
def bump_submittal():
    """Bump a submittal to the 0.9 urgency slot with cascading effects"""
    try:
        data = request.json
        submittal_id = str(data.get('submittal_id', ''))
        
        if not submittal_id:
            return jsonify({"error": "submittal_id is required"}), 400
        
        # Get the submittal
        submittal = ProcoreSubmittal.query.filter_by(submittal_id=submittal_id).first()
        if not submittal:
            return jsonify({"error": "Submittal not found"}), 404
        
        # Check if submittal has ball_in_court (required for bumping)
        if not submittal.ball_in_court:
            return jsonify({"error": "Submittal must have a ball_in_court value to bump"}), 400
        
        # Call the bump function via service
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
        
        # Commit the changes
        db.session.commit()
        
        return jsonify({
            "success": True,
            "submittal_id": submittal_id,
            "order_number": submittal.order_number,
            "message": "Submittal bumped to urgency slot with cascading effects applied"
        }), 200
        
    except Exception as exc:
        logger.error("Error bumping submittal", error=str(exc))
        db.session.rollback()
        return jsonify({
            "error": "Failed to bump submittal",
            "details": str(exc)
        }), 500

@brain_bp.route("/drafting-work-load/due-date", methods=["PUT"])
@login_required
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
        
        submittal = ProcoreSubmittal.query.filter_by(submittal_id=submittal_id).first()
        if not submittal:
            return jsonify({
                "error": "Submittal not found"
            }), 404
        
        # Update via service layer
        success, error_msg = DraftingWorkLoadService.update_due_date(
            submittal, 
            due_date
        )
        
        if not success:
            return jsonify({"error": error_msg}), 400
        
        db.session.commit()
        
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

