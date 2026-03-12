"""
Fix submittal_events schema mismatch.
Rename user_id → internal_user_id and add missing columns.
"""

from app import create_app
from app.models import db

app = create_app()

def upgrade():
    with app.app_context():
        with db.engine.connect() as conn:
            # Check what columns exist
            inspector = db.inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('submittal_events')]

            # Rename user_id → internal_user_id if it exists
            if 'user_id' in columns and 'internal_user_id' not in columns:
                conn.execute(db.text("""
                    ALTER TABLE submittal_events
                    RENAME COLUMN user_id TO internal_user_id
                """))
                print("✓ Renamed user_id → internal_user_id")
                conn.commit()

            # Add external_user_id if missing
            if 'external_user_id' not in columns:
                conn.execute(db.text("""
                    ALTER TABLE submittal_events
                    ADD COLUMN external_user_id VARCHAR(255) DEFAULT NULL
                """))
                print("✓ Added external_user_id")
                conn.commit()

            # Add is_system_echo if missing
            if 'is_system_echo' not in columns:
                conn.execute(db.text("""
                    ALTER TABLE submittal_events
                    ADD COLUMN is_system_echo BOOLEAN DEFAULT FALSE NOT NULL
                """))
                print("✓ Added is_system_echo")
                conn.commit()

        print("✓ submittal_events schema fixed")

if __name__ == '__main__':
    upgrade()
