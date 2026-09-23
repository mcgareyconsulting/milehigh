"""
@milehigh-header
schema_version: 1
purpose: The subcontractor-facing read surface (T3). Serves a subcontractor session
  the releases assigned to THEIR installer crew, through an allowlist serializer that
  can only ever emit approved fields.
exports: (none — routes register on brain_bp via side-effect import)
imports_from: []
imported_by: [app/brain/__init__.py]
invariants:
  - Every route here is @subcontractor_login_required, never @login_required.
  - Scope is the crew: Releases.installer == Subcontractor.installer_team. A NULL
    crew returns [], never everything — the query fails closed.
  - The payload is an ALLOWLIST, not the internal row minus some fields. A column
    added to Releases can never reach a subcontractor without editing SUB_FIELDS.
  - Separate from app/brain/tm/subcontractor_view/, which serves T&M tickets. That
    module may eventually move under here; releases and tickets are different data.
"""
