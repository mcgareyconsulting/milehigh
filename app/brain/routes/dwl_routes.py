from app.brain import brain_bp
from flask import jsonify, request
from app.brain.services.dwl_service import SubmittalOrderingService, SubmittalOrderUpdate, DraftingWorkLoadService
from app.logging_config import get_logger
from app.models import ProcoreSubmittal, db
from datetime import datetime

logger = get_logger(__name__)

@brain_bp.route('/drafting-work-load')
def drafting_work_load():
    """Return Drafting Work Load data from the db, including all submittals (filtered by frontend tabs)"""
    try:
        # Get all submittals - frontend will filter by tab (Open vs Draft)
        submittals = ProcoreSubmittal.query.all()
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

@brain_bp.route("/drafting-work-load/reorder-group", methods=["POST"])
def reorder_group():
    """Reorder all items in a ball_in_court group so the lowest order >= 1 becomes 1"""
    try:
        data = request.json
        ball_in_court = data.get('ball_in_court')
        
        if not ball_in_court:
            return jsonify({
                "error": "ball_in_court is required"
            }), 400
        
        # Get all submittals in this group
        all_group_submittals = ProcoreSubmittal.query.filter_by(
            ball_in_court=ball_in_court
        ).all()
        
        if not all_group_submittals:
            return jsonify({
                "error": f"No submittals found for ball_in_court: {ball_in_court}"
            }), 404
        
        # Calculate updates - finds lowest order >= 1 and makes it 1, renumbers rest sequentially
        updates = SubmittalOrderingService.reorder_group_to_start_from_one(all_group_submittals)
        
        if not updates:
            return jsonify({
                "success": True,
                "message": "No items to reorder (no items with order_number >= 1)",
                "ball_in_court": ball_in_court,
                "items_updated": 0
            }), 200
        
        # Apply updates to database records
        # This updates the order_number field and last_updated timestamp for each submittal
        for submittal, new_order_val in updates:
            submittal.order_number = new_order_val
            submittal.last_updated = datetime.utcnow()
        
        # Commit all changes to the database
        db.session.commit()
        
        logger.info(f"Reordered {len(updates)} items for ball_in_court '{ball_in_court}'")
        
        return jsonify({
            "success": True,
            "ball_in_court": ball_in_court,
            "items_updated": len(updates)
        }), 200
        
    except Exception as exc:
        logger.error("Error reordering group", error=str(exc))
        db.session.rollback()
        return jsonify({
            "error": "Failed to reorder group",
            "details": str(exc)
        }), 500