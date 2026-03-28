"""
One-time migration to renumber fab_orders for the unified ordering scheme.

Usage:
    python -c "from app import create_app; app = create_app(); \
    from app.brain.job_log.features.fab_order.migrate_unified import renumber_fab_orders; \
    with app.app_context(): renumber_fab_orders()"

Or call renumber_fab_orders() from a Flask shell.

Ordering:
    fab_order = 1  : Complete / Shipping Complete (shared)
    fab_order = 2  : Paint complete, Store, Shipping planning (shared)
    fab_order = 3+ : Dynamic stages in order:
                     Welded QC -> Welded -> Fit Up Complete. -> Material Ordered -> Cut start -> Released
"""

from app.models import Releases, db
from app.api.helpers import DYNAMIC_STAGE_ORDER, FIXED_TIER_STAGES, _get_all_variants_for_stages
from app.logging_config import get_logger

logger = get_logger(__name__)


def renumber_fab_orders(dry_run=False):
    """Renumber all fab_orders to the unified ordering scheme.

    Args:
        dry_run: If True, log changes but don't commit.

    Returns:
        dict with counts of changes made.
    """
    stats = {'fixed_tier_1': 0, 'fixed_tier_2': 0, 'dynamic': 0, 'total': 0}

    # Step 1: Set fixed tier 1 (Complete stages)
    tier_1_stages = FIXED_TIER_STAGES[1]
    tier_1_variants = _get_all_variants_for_stages(tier_1_stages)
    tier_1_releases = Releases.query.filter(Releases.stage.in_(tier_1_variants)).all()
    for r in tier_1_releases:
        if r.fab_order != 1:
            logger.info(f"Tier 1: {r.job}-{r.release} ({r.stage}) fab_order {r.fab_order} -> 1")
            r.fab_order = 1
            stats['fixed_tier_1'] += 1

    # Step 2: Set fixed tier 2 (Paint complete, Store, Shipping planning)
    tier_2_stages = FIXED_TIER_STAGES[2]
    tier_2_variants = _get_all_variants_for_stages(tier_2_stages)
    tier_2_releases = Releases.query.filter(Releases.stage.in_(tier_2_variants)).all()
    for r in tier_2_releases:
        if r.fab_order != 2:
            logger.info(f"Tier 2: {r.job}-{r.release} ({r.stage}) fab_order {r.fab_order} -> 2")
            r.fab_order = 2
            stats['fixed_tier_2'] += 1

    # Step 3: Renumber dynamic stages sequentially, preserving relative order within each stage
    next_fab_order = 3
    for stage_name in DYNAMIC_STAGE_ORDER:
        variants = _get_all_variants_for_stages([stage_name])
        # Get releases in this stage, sorted by current fab_order (preserving relative order)
        stage_releases = Releases.query.filter(
            Releases.stage.in_(variants)
        ).order_by(Releases.fab_order.asc().nullslast()).all()

        for r in stage_releases:
            if r.fab_order != next_fab_order:
                logger.info(
                    f"Dynamic: {r.job}-{r.release} ({r.stage}) "
                    f"fab_order {r.fab_order} -> {next_fab_order}"
                )
                r.fab_order = next_fab_order
                stats['dynamic'] += 1
            next_fab_order += 1

    stats['total'] = stats['fixed_tier_1'] + stats['fixed_tier_2'] + stats['dynamic']

    if dry_run:
        logger.info(f"DRY RUN — rolling back. Stats: {stats}")
        db.session.rollback()
    else:
        db.session.commit()
        logger.info(f"Migration complete. Stats: {stats}")

    return stats
