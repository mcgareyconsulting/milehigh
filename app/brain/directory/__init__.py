"""
@milehigh-header
schema_version: 1
purpose: Admin user directory — first T2 slice. Read-only list of staff (users table)
         and subcontractors (subcontractors table), split for display. No invite,
         permission, password-reset, or block controls yet.
exports:
  (routes register on brain_bp at /brain/directory)
imports_from: [app.brain.directory.routes]
imported_by: [app/brain/__init__.py]
invariants:
  - Admin-only. Read-only; never returns password hashes, invite tokens, or session ids.
  - Employees come from User; subcontractors stay on the Subcontractor table (security
    boundary). Folding them into one role model is a later T2 call.
"""
