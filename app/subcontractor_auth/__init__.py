"""Session-based auth for external Subcontractor accounts — deliberately
parallel to, and fully isolated from, app/auth/ (internal staff). Session
identity lives at session['subcontractor_id'], never session['user_id']; the
two identity spaces never resolve into each other. See utils.py / routes.py.
"""
