import pandas as pd
from app.models import db, Job
import logging
import gc  # For garbage collection
from sqlalchemy.exc import SQLAlchemyError


def to_date(val):
    """Convert a value to a date, returning None if conversion fails or value is null."""
    if pd.isnull(val):
        return None
    dt = pd.to_datetime(val)
    return dt.date() if not pd.isnull(dt) else None

def safe_truncate_string(value, max_length):
    """Safely truncate a string to fit within the specified length."""
    if value is None or pd.isna(value):
        return None

    string_value = str(value)
    if len(string_value) <= max_length:
        return string_value

    # Truncate and add indicator that it was truncated
    truncated = string_value[:max_length-3] + "..."
    print(f"Truncated string from {len(string_value)} to {len(truncated)} characters")
    return truncated


def seed_from_combined_data(combined_data, batch_size=50):
    """
    Safely seed the database from combined Trello/Excel data.
    Uses batched commits with cleanup to prevent memory overflow and isolate errors.
    """

    total_created = 0
    total_items = len([item for item in combined_data if item.get("excel")])
    batch_count = 0

    print(f"Starting batch seeding for {total_items} items with batch size {batch_size}...")

    for i in range(0, len(combined_data), batch_size):
        batch_items = combined_data[i:i + batch_size]
        batch_count += 1
        jobs_to_add = []
        batch_created = 0

        print(f"Processing batch {batch_count} (items {i+1}-{min(i+batch_size, len(combined_data))})...")

        for item in batch_items:
            try:
                excel_data = item.get("excel")
                if not excel_data:
                    continue

                # Clean and convert Excel values safely
                def safe_float(val):
                    try:
                        return float(val)
                    except (TypeError, ValueError):
                        return None

                jr = Job(
                    job=excel_data.get("Job #"),
                    release=excel_data.get("Release #"),
                    job_name=safe_truncate_string(excel_data.get("Job"), 128),
                    description=safe_truncate_string(excel_data.get("Description"), 512),
                    fab_hrs=safe_float(excel_data.get("Fab Hrs")),
                    install_hrs=safe_float(excel_data.get("Install HRS")),
                    paint_color=safe_truncate_string(excel_data.get("Paint color"), 128),
                    pm=safe_truncate_string(excel_data.get("PM"), 128),
                    by=safe_truncate_string(excel_data.get("BY"), 128),
                    released=to_date(excel_data.get("Released")),
                    fab_order=safe_truncate_string(excel_data.get("Fab Order"), 128),
                    cut_start=safe_truncate_string(excel_data.get("Cut start"), 128),
                    fitup_comp=safe_truncate_string(excel_data.get("Fitup comp"), 128),
                    welded=safe_truncate_string(excel_data.get("Welded"), 128),
                    paint_comp=safe_truncate_string(excel_data.get("Paint Comp"), 128),
                    ship=safe_truncate_string(excel_data.get("Ship"), 128),
                    start_install=to_date(excel_data.get("Start install")),
                    start_install_formula=excel_data.get("start_install_formula"),
                    start_install_formulaTF=excel_data.get("start_install_formulaTF"),
                    comp_eta=to_date(excel_data.get("Comp. ETA")),
                    job_comp=safe_truncate_string(excel_data.get("Job Comp"), 128),
                    invoiced=safe_truncate_string(excel_data.get("Invoiced"), 128),
                    notes=safe_truncate_string(excel_data.get("Notes"), 512),
                    last_updated_at=pd.Timestamp.now(),
                    source_of_update="System",
                )

                # Add Trello data if available
                if item.get("trello"):
                    trello_data = item["trello"]
                    jr.trello_card_id = trello_data.get("id")
                    jr.trello_card_name = safe_truncate_string(trello_data.get("name"), 128)
                    jr.trello_list_id = trello_data.get("list_id")
                    jr.trello_list_name = safe_truncate_string(trello_data.get("list_name"), 128)
                    jr.trello_card_description = safe_truncate_string(trello_data.get("desc"), 512)

                    if trello_data.get("due"):
                        jr.trello_card_date = to_date(trello_data["due"])

                jobs_to_add.append(jr)
                batch_created += 1

            except Exception as e:
                identifier = item.get("identifier")
                logging.error(f"⚠️ Skipping record {identifier}: {e}")
                continue

        # Commit this batch safely
        if not jobs_to_add:
            print(f"  No valid jobs to commit in batch {batch_count}")
            continue

        try:
            print(f"  Committing batch {batch_count} with {len(jobs_to_add)} records...")
            db.session.bulk_save_objects(jobs_to_add)
            db.session.commit()
            total_created += len(jobs_to_add)
            print(f"  ✓ Batch {batch_count} committed successfully. Total created: {total_created}")

        except SQLAlchemyError as e:
            db.session.rollback()
            logging.error(f"✗ Batch {batch_count} failed: {e}")
        finally:
            # Memory cleanup
            db.session.expunge_all()
            gc.collect()

    print(f"\n🎉 Seeding completed! Successfully created {total_created} jobs in {batch_count} batches.")
