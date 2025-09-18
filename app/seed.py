import pandas as pd
from app.models import db, Job


def to_date(val):
    """Convert a value to a date, returning None if conversion fails or value is null."""
    if pd.isnull(val):
        return None
    dt = pd.to_datetime(val)
    return dt.date() if not pd.isnull(dt) else None


def seed_from_combined_data(combined_data):
    """
    Seed database from combined Trello/Excel data - creates new jobs for all items.
    """
    created_count = 0

    for item in combined_data:
        if item["excel"]:  # Only process if Excel data exists
            excel_data = item["excel"]
            identifier = item["identifier"]

            print(f"Creating new job for {identifier}...")

            # Create new job
            jr = Job(
                job=excel_data["Job #"],
                release=excel_data["Release #"],
                job_name=excel_data["Job"],
                description=excel_data.get("Description"),
                fab_hrs=excel_data.get("Fab Hrs"),
                install_hrs=excel_data.get("Install HRS"),
                paint_color=excel_data.get("Paint color"),
                pm=excel_data.get("PM"),
                by=excel_data.get("BY"),
                released=to_date(excel_data.get("Released")),
                fab_order=excel_data.get("Fab Order"),
                cut_start=excel_data.get("Cut start"),
                fitup_comp=excel_data.get("Fitup comp"),
                welded=excel_data.get("Welded"),
                paint_comp=excel_data.get("Paint Comp"),
                ship=excel_data.get("Ship"),
                start_install=to_date(excel_data.get("Start install")),
                start_install_formula=excel_data.get("start_install_formula"),
                start_install_formulaTF=excel_data.get("start_install_formulaTF"),
                comp_eta=to_date(excel_data.get("Comp. ETA")),
                job_comp=excel_data.get("Job Comp"),
                invoiced=excel_data.get("Invoiced"),
                notes=excel_data.get("Notes"),
                last_updated_at=pd.Timestamp.now(),
                source_of_update="System",
            )

            # Add Trello data if available
            if item["trello"]:
                trello_data = item["trello"]
                jr.trello_card_id = trello_data.get("id")
                jr.trello_card_name = trello_data.get("name")
                jr.trello_list_id = trello_data.get("list_id")
                jr.trello_list_name = trello_data.get("list_name")
                jr.trello_card_description = trello_data.get("desc")

                if trello_data.get("due"):
                    jr.trello_card_date = to_date(trello_data["due"])

                print(f"  Added Trello data - Card ID: {jr.trello_card_id}")

            db.session.add(jr)
            created_count += 1

    print(f"Committing {created_count} new jobs...")
    db.session.commit()
    print(f"Success! Created {created_count} jobs in the database.")
