"""
@milehigh-header
schema_version: 1
purpose: The department photo gate — the rule that decides when a stage change needs
  proof, and the check that looks for it. A release changing hands between departments
  (FABRICATION → PAINT → READY_TO_SHIP → COMPLETE, the stage_group axis) must carry a
  photo tagged with the department's entry stage, or a written reason there is none.
  Pure rule + one query; UpdateStageCommand is the only caller and the only enforcer.
exports:
  gate_stage_for: (old_stage, new_stage) → the entry stage whose photo is owed, or None
  gate_photo_exists: Does a live ReleasePhoto tagged with that stage exist on the release
  StagePhotoRequiredError: Raised by the command when the gate is owed and unmet
imports_from: [app.api.helpers, app.models]
imported_by: [app/brain/job_log/features/stage/command.py]
invariants:
  - Only a FORWARD crossing gates (a later group in STAGE_GROUP_ORDER). Moving back is a
    correction, not a handoff, and is never blocked.
  - The photo is tagged with the department's ENTRY stage (GATE_ENTRY_STAGE), not the stage
    asked for — Ship Planning → Complete owes the Ship Complete photo.
  - A multi-department jump owes the destination's gate only; the trail records the jump.
  - Unknown stages never gate: the stage itself is already suspect, and refusing a write
    on a stage we cannot classify would strand the release.
"""
from typing import Optional

from app.api.helpers import (
    GATE_ENTRY_STAGE,
    STAGE_GROUP_ORDER,
    get_stage_group_from_stage,
)


class StagePhotoRequiredError(Exception):
    """Raised when a stage change is blocked because its handoff photo is missing.

    Carries the gated `stage` (the department's entry stage — what the photo must be
    tagged with) and the `requested_stage` the user actually asked for, so the client
    can say both: "moving to Complete needs the Ship Complete photo".
    """

    def __init__(self, stage: str, requested_stage: Optional[str] = None):
        self.stage = stage
        self.requested_stage = requested_stage or stage
        super().__init__(
            f"A photo tagged '{stage}' is required to move to {self.requested_stage}"
        )


def gate_stage_for(old_stage: Optional[str], new_stage: Optional[str]) -> Optional[str]:
    """The entry stage whose photo this transition owes, or None when it owes nothing.

    Owes a photo iff the destination's stage_group sits LATER in STAGE_GROUP_ORDER than
    the origin's. Same group, backward, or unclassifiable on either side → None.
    """
    old_group = get_stage_group_from_stage(old_stage)
    new_group = get_stage_group_from_stage(new_stage)
    if old_group is None or new_group is None or old_group == new_group:
        return None
    try:
        forward = STAGE_GROUP_ORDER.index(new_group) > STAGE_GROUP_ORDER.index(old_group)
    except ValueError:
        return None
    if not forward:
        return None
    return GATE_ENTRY_STAGE.get(new_group)


def gate_photo_exists(release_id: int, gate_stage: str) -> bool:
    """A non-deleted ReleasePhoto tagged with `gate_stage` exists on the release."""
    from app.models import ReleasePhoto, db

    return db.session.query(ReleasePhoto.id).filter(
        ReleasePhoto.release_id == release_id,
        ReleasePhoto.stage == gate_stage,
        ReleasePhoto.is_deleted.is_(False),
    ).first() is not None
