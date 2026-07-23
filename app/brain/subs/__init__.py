"""
@milehigh-header
schema_version: 1
purpose: Admin Subs view — releases assigned to subcontractor installers with
  installer-invoice paid yes/no tracking (Lexi).
exports: (none — routes register on brain_bp via side-effect import)
imports_from: []
imported_by: [app/brain/__init__.py]
invariants:
  - Distinct from Releases.invoiced (MHMW customer billing).
  - Admin-only endpoints.
"""
