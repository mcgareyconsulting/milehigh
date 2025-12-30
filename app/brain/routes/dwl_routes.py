from app.brain import brain_bp
from flask import jsonify, request
from app.brain.services.dwl_ordering import SubmittalOrderingService, SubmittalOrderUpdate
from app.logging_config import get_logger
from app.models import ProcoreSubmittal, db
from datetime import datetime

logger = get_logger(__name__)

@brain_bp.route('/drafting-work-load')
def drafting_work_load():
    """Return Drafting Work Load data from the db, filtered to only show submittals with status='Open'"""
    # Filter to only show submittals with status == 'Open'
    # Exclude None statuses - only show submittals that are explicitly 'Open'
    submittals = ProcoreSubmittal.query.filter(
        ProcoreSubmittal.status == 'Open'
    ).all()
    return jsonify({
        "submittals": [submittal.to_dict() for submittal in submittals]
    }), 200

@brain_bp.route("/drafting-work-load/order", methods=["PUT"])
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

        # Convert to float if not None
        if order_number is not None:
            order_number = float(order_number)

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
        
        # Allow notes to be None or empty string
        if notes is not None:
            notes = str(notes).strip() or None
        
        submittal.notes = notes
        submittal.last_updated = datetime.utcnow()
        
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