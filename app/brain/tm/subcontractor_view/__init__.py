"""The subcontractor-facing T&M surface: list/view/edit/submit tickets
assigned to the logged-in subcontractor. Deliberately a separate route module
from app/brain/tm/routes.py (admin, sees everything) rather than a branch
inside it — scoping-by-assignment is a fundamentally different authorization
query than admin's "see everything," and a dedicated file makes an inverted
`if` far less likely to leak another subcontractor's ticket.
"""
