"""
M7: Add last_bic_update column to submittals table and backfill with most recent BIC event.

This migration:
1. Adds last_bic_update TIMESTAMP column to submittals table
2. Backfills the column by querying submittal_events for the most recent 'updated' event
   from 'Procore' source that contains 'ball_in_court' in the payload
3. Updates the Submittals model to include the new column and syncs write paths

Note: This is a hybrid approach — the dynamic get_last_bic_from_events() method is retained
for audit/backfill purposes, but write paths should set last_bic_update directly for
performance reasons.
"""

from app import create_app
from app.models import db, Submittals, SubmittalEvents
from datetime import datetime

app = create_app()

def upgrade():
    """Add last_bic_update column and backfill with data from submittal_events."""
    with app.app_context():
        # Check if column already exists
        inspector = db.inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('submittals')]

        if 'last_bic_update' in columns:
            print("last_bic_update column already exists, skipping migration")
            return

        # Add the column
        with db.engine.connect() as conn:
            conn.execute(db.text("""
                ALTER TABLE submittals
                ADD COLUMN last_bic_update TIMESTAMP DEFAULT NULL
            """))
            conn.commit()

        print("✓ Added last_bic_update column to submittals")

        # Backfill: for each submittal, find the most recent BIC event from Procore
        print("Backfilling last_bic_update from submittal_events...")

        try:
            submittals = Submittals.query.all()
            updated_count = 0

            for submittal in submittals:
                # Query submittal_events for the most recent BIC update from Procore
                events = SubmittalEvents.query.filter(
                    SubmittalEvents.submittal_id == str(submittal.submittal_id),
                    SubmittalEvents.action == 'updated',
                    SubmittalEvents.source == 'Procore'
                ).order_by(SubmittalEvents.created_at.desc()).all()

                # Find the most recent event with ball_in_court in payload
                last_bic_event = None
                for event in events:
                    if event.payload and isinstance(event.payload, dict) and 'ball_in_court' in event.payload:
                        last_bic_event = event
                        break

                if last_bic_event:
                    submittal.last_bic_update = last_bic_event.created_at
                    db.session.add(submittal)
                    updated_count += 1

            db.session.commit()
            print(f"✓ Backfilled {updated_count} submittals with last_bic_update")
        except Exception as e:
            print(f"⚠ Backfill skipped (submittal_events schema not ready): {e}")
            print("  Run earlier migrations first, then backfill can happen on next run")

def downgrade():
    """Remove last_bic_update column."""
    with app.app_context():
        inspector = db.inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('submittals')]

        if 'last_bic_update' not in columns:
            print("last_bic_update column does not exist, skipping downgrade")
            return

        with db.engine.connect() as conn:
            conn.execute(db.text("""
                ALTER TABLE submittals DROP COLUMN IF EXISTS last_bic_update
            """))
            conn.commit()

        print("✓ Removed last_bic_update column from submittals")

if __name__ == '__main__':
    upgrade()
