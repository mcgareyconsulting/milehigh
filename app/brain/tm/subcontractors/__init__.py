"""Admin-facing subcontractor roster management: invite, resend, deactivate/
reactivate, and assign-to-ticket. All routes are @admin_required and live on
brain_bp. The subcontractor's OWN session/login lives in app/subcontractor_auth/;
their ticket-facing view lives in app/brain/tm/subcontractor_view/ — this
package is the admin side only.
"""
