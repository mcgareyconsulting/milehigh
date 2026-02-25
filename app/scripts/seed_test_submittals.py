"""
Seed 3 fake ProcoreSubmittal rows for project_number 000 (for testing DWL location filter).

Usage:
  python -m app.scripts.seed_test_submittals

Submittal IDs are test-loc-000-1, test-loc-000-2, test-loc-000-3. Safe to run multiple times
(skips if any already exist).
"""

from datetime import datetime

from app import create_app
from app.models import ProcoreSubmittal, db


def seed_test_submittals(project_number: str = "000") -> int:
    added = 0
    records = [
        {
            "submittal_id": f"test-loc-{project_number}-1",
            "title": "Test Submittal 1 – Location Filter",
            "status": "Open",
            "order_number": 1.0,
        },
        {
            "submittal_id": f"test-loc-{project_number}-2",
            "title": "Test Submittal 2 – Location Filter",
            "status": "Open",
            "order_number": 2.0,
        },
        {
            "submittal_id": f"test-loc-{project_number}-3",
            "title": "Test Submittal 3 – Location Filter",
            "status": "Draft",
            "order_number": 3.0,
        },
    ]
    for r in records:
        if ProcoreSubmittal.query.filter_by(submittal_id=r["submittal_id"]).first():
            print(f"Already exists: {r['submittal_id']}")
            continue
        sub = ProcoreSubmittal(
            submittal_id=r["submittal_id"],
            procore_project_id=None,
            project_number=project_number,
            project_name="Test Project (Location)",
            title=r["title"],
            status=r["status"],
            type="Test",
            ball_in_court=None,
            submittal_manager=None,
            order_number=r["order_number"],
            notes=None,
            submittal_drafting_status="",
            due_date=None,
            was_multiple_assignees=False,
        )
        db.session.add(sub)
        added += 1
        print(f"Added: {r['submittal_id']} ({r['status']})")
    if added:
        db.session.commit()
    return added


def main():
    app = create_app()
    with app.app_context():
        n = seed_test_submittals()
        print(f"Done. Inserted {n} test submittal(s) for project_number 000.")
    return 0


if __name__ == "__main__":
    exit(main())
