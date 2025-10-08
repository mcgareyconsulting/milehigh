import pandas as pd
from app.models import db, Job
import logging

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
    Seed database from combined Trello/Excel data - creates new jobs for all items.
    Uses batched commits to avoid exceeding database memory limits.
    
    Args:
        combined_data: List of combined Excel/Trello data items
        batch_size: Number of records to process per batch (default: 50)
    """
    total_created = 0
    total_items = len([item for item in combined_data if item["excel"]])
    batch_count = 0
    
    print(f"Starting batch seeding for {total_items} items with batch size {batch_size}...")
    
    # Process items in batches
    for i in range(0, len(combined_data), batch_size):
        batch_items = combined_data[i:i + batch_size]
        batch_created = 0
        batch_count += 1
        
        print(f"Processing batch {batch_count} (items {i+1}-{min(i+batch_size, len(combined_data))})...")
        
        try:
            for item in batch_items:
                if item["excel"]:  # Only process if Excel data exists
                    excel_data = item["excel"]
                    identifier = item["identifier"]

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

                    db.session.add(jr)
                    batch_created += 1
            
            # Commit this batch
            if batch_created > 0:
                print(f"  Committing batch {batch_count} with {batch_created} new jobs...")
                db.session.commit()
                total_created += batch_created
                print(f"  ✓ Batch {batch_count} committed successfully. Total created so far: {total_created}")
            else:
                print(f"  No jobs to commit in batch {batch_count}")
                
        except Exception as e:
            print(f"  ✗ Error in batch {batch_count}: {str(e)}")
            db.session.rollback()
            print(f"  Rolled back batch {batch_count}")
            raise e

    print(f"\n🎉 Seeding completed! Successfully created {total_created} jobs in {batch_count} batches.")
