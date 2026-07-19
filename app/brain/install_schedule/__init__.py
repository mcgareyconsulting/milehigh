"""
@milehigh-header
schema_version: 1
purpose: Next-week installation schedule — assembles active releases whose start_install falls in the coming 7 days, grouped by crew, hard dates first, with overload/overlap flags.
exports:
  (routes register on brain_bp at /brain/install-schedule; service.build_next_week_schedule assembles the payload)
imports_from: [app.brain.install_schedule.service, app.brain.install_schedule.routes]
imported_by: [app/brain/__init__.py]
invariants:
  - Read-only. No writes, no external calls; deterministic assembly over the releases table.
  - Hard dates (start_install_formulaTF is False, not ASAP/neutral) are the scheduling anchors and always sort first.
"""
