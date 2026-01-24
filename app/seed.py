import pandas as pd
from app.models import db, Job, SyncOperation, SyncStatus
from app.combine import combine_trello_excel_data
from app.trello.operations import create_sync_operation, update_sync_operation
from app.trello.logging import safe_log_sync_event
import logging
import gc  # For garbage collection
from sqlalchemy.exc import SQLAlchemyError
import os
from pathlib import Path


def to_date(val):
    """Convert a value to a date, returning None if conversion fails or value is null."""
    if pd.isnull(val) or val is None:
        return None
    
    # Convert to string and strip whitespace
    val_str = str(val).strip()
    if not val_str or val_str == '':
        return None
    
    # Handle dates in M/D format (without year) - add year based on month
    # Months 4-12 → 2025, Months 1-3 → 2026
    import re
    m_d_match = re.match(r'^(\d{1,2})/(\d{1,2})$', val_str)
    if m_d_match:
        month = int(m_d_match.group(1))
        day = int(m_d_match.group(2))
        
        # Determine year based on month
        if 4 <= month <= 12:
            year = 2025
        elif 1 <= month <= 3:
            year = 2026
        else:
            # Invalid month, return None
            return None
        
        # Reconstruct date string with year
        val_str = f"{month}/{day}/{year}"
    
    try:
        # Try parsing with pandas
        # Use errors='coerce' to return NaT instead of raising
        dt = pd.to_datetime(val_str, errors='coerce')
        
        if pd.isnull(dt):
            return None
        
        # Check for out-of-bounds dates (pandas can sometimes create invalid dates)
        try:
            return dt.date()
        except (ValueError, OverflowError):
            # Date is out of bounds, return None
            return None
            
    except (ValueError, TypeError, OverflowError) as e:
        # If parsing fails, return None
        return None

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

def safe_float(val):
    """Safely convert a value to float, returning None if conversion fails."""
    if val is None or pd.isna(val):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


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


def incremental_seed_missing_jobs(batch_size=50):
    """
    Incremental seeding function that checks the database for existing jobs
    and only adds missing ones from Excel rows with job-release that don't have X or T in Ship column.
    
    This function:
    1. Gets all Excel rows with job-release (has Job # and Release #)
    2. Filters out rows where Ship column contains 'X' or 'T'
    3. Cross-references with Trello cards (but seeds even without Trello cards)
    4. Checks which jobs already exist in the database
    5. Only creates new Job records for missing ones
    6. Tracks the operation with sync logging
    
    Returns:
        dict: Summary of the operation including counts and operation_id
    """
    
    # Create sync operation for tracking
    sync_op = create_sync_operation(
        operation_type="incremental_seed",
        source_system="system"
    )
    operation_id = sync_op.operation_id
    
    try:
        print("🔄 Starting incremental seeding process...")
        safe_log_sync_event(operation_id, "INFO", "Starting incremental seeding process")
        
        # Get Trello cards for cross-reference (optional - jobs will be created even without Trello)
        print("📊 Fetching Trello cards from 5 target lists for cross-reference...")
        from app.trello.api import get_trello_cards_from_subset
        from app.trello.utils import extract_identifier
        # NOTE: Excel/OneDrive functionality removed - get_excel_dataframe no longer available
        
        # Get unique cards from the 5 Trello lists
        trello_cards = get_trello_cards_from_subset()
        unique_trello_identifiers = set()
        trello_identifier_to_card = {}  # Map identifier -> card
        
        for card in trello_cards:
            name = (card.get("name") or "").strip()
            if name:
                identifier = extract_identifier(name)
                if identifier:
                    unique_trello_identifiers.add(identifier)
                    # Store first card for each identifier
                    if identifier not in trello_identifier_to_card:
                        trello_identifier_to_card[identifier] = card
        
        print(f"🎯 Found {len(unique_trello_identifiers)} unique job identifiers in Trello lists")
        
        # NOTE: Excel functionality removed - this function no longer works without Excel data
        print("⚠️  WARNING: Excel functionality removed - incremental_seed_missing_jobs requires Excel data")
        raise NotImplementedError("Excel/OneDrive functionality has been removed. This function requires Excel data.")
        
        # Get all Excel rows (already filtered to job-release: has Job # and Release #)
        print("📊 Loading all Excel rows with job-release...")
        # df = get_excel_dataframe()  # REMOVED: Excel functionality no longer available
        
        # Create identifier column for Excel rows
        df["identifier"] = df["Job #"].astype(str) + "-" + df["Release #"].astype(str)
        
        # Filter Excel rows: job-release without X or T in Ship column
        print("🔍 Filtering Excel rows: Ship column must NOT contain 'X' or 'T'...")
        
        # Helper function to check if Ship contains X or T
        def ship_has_x_or_t(ship_value):
            """Check if Ship column contains 'X' or 'T' (case-sensitive)."""
            if pd.isna(ship_value) or ship_value is None:
                return False
            ship_str = str(ship_value).strip()
            return 'X' in ship_str or 'T' in ship_str
        
        # Filter rows: must have job-release AND Ship must NOT have X or T
        filtered_df = df[~df["Ship"].apply(ship_has_x_or_t)].copy()
        
        total_excel_job_release = len(df)
        total_filtered_rows = len(filtered_df)
        rows_with_x_or_t = total_excel_job_release - total_filtered_rows
        
        print(f"📊 Total Excel rows with job-release: {total_excel_job_release}")
        print(f"✂️  Rows excluded (Ship has X or T): {rows_with_x_or_t}")
        print(f"✅ Rows eligible for seeding (Ship does NOT have X or T): {total_filtered_rows}")
        
        # Convert filtered DataFrame to combined_data format for compatibility
        # Compute predicted list for each row and only process those that would go to "Released"
        valid_items = []
        trello_only_count = 0  # Not applicable in new approach, but kept for logging
        excel_with_trello_count = 0
        excel_without_trello_count = 0
        predicted_released_count = 0
        
        for _, row in filtered_df.iterrows():
            identifier = row["identifier"]
            trello_card = trello_identifier_to_card.get(identifier)
            
            # Convert row to dict format compatible with existing code
            excel_data = row.to_dict()

            # Determine predicted list using staging flags
            fitup_comp = str(excel_data.get("Fitup comp", "") or "").strip()
            welded = str(excel_data.get("Welded", "") or "").strip()
            paint_comp = str(excel_data.get("Paint Comp", "") or "").strip()
            ship_val = str(excel_data.get("Ship", "") or "").strip()

            predicted_list = None
            if (
                fitup_comp == "X"
                and welded == "X"
                and paint_comp == "X"
                and (ship_val == "O" or ship_val == "T")
            ):
                predicted_list = "Paint complete"
            elif (
                fitup_comp == "X"
                and welded == "O"
                and paint_comp == ""
                and (ship_val == "T" or ship_val == "O" or ship_val == "")
            ):
                predicted_list = "Fit Up Complete."
            elif (
                fitup_comp == "X"
                and welded == "X"
                and paint_comp == "X"
                and (ship_val == "X")
            ):
                predicted_list = "Shipping completed"
            else:
                predicted_list = "Released"

            if predicted_list == "Released":
                predicted_released_count += 1
            else:
                # Skip items that would not go to Released per requirement
                continue
            
            item = {
                "identifier": identifier,
                "trello": trello_card,
                "excel": excel_data,
                "predicted_list": predicted_list
            }
            valid_items.append(item)
            
            if trello_card:
                excel_with_trello_count += 1
            else:
                excel_without_trello_count += 1
        
        total_items = len(valid_items)
        print(f"✅ Found {total_items} eligible Excel rows that would go to 'Released'")
        print(f"🔗 Rows WITH Trello cards: {excel_with_trello_count}")
        print(f"⚠️  Rows WITHOUT Trello cards: {excel_without_trello_count}")
        
        safe_log_sync_event(
            operation_id, 
            "INFO", 
            "Excel filtering and Trello cross-check completed",
            total_excel_job_release=total_excel_job_release,
            rows_excluded_ship_has_x_or_t=rows_with_x_or_t,
            eligible_rows=total_items,
            eligible_with_trello=excel_with_trello_count,
            eligible_without_trello=excel_without_trello_count,
            unique_trello_identifiers=len(unique_trello_identifiers)
        )
        
        # Use the filtered items for processing
        combined_data = valid_items
        
        # Check which jobs already exist in database
        existing_jobs = set()
        new_jobs_data = []
        
        print("🔍 Checking for existing jobs in database...")
        print("   (Only processing rows predicted for 'Released' list)")
        
        for item in combined_data:
            excel_data = item.get("excel")
            trello_data = item.get("trello")
            identifier = item.get("identifier")
            
            # Only require Excel data (Trello is optional)
            if not excel_data:
                print(f"⚠️  Skipping {identifier} - missing Excel data")
                continue
                
            job_num = excel_data.get("Job #")
            release_str = str(excel_data.get("Release #", "")).strip()
            
            if not job_num or not release_str:
                print(f"⚠️  Skipping {identifier} - invalid job/release numbers")
                continue
            
            # Validate job number is an integer
            try:
                job_num = int(job_num)
            except (ValueError, TypeError):
                print(f"⚠️  Skipping {identifier} - Job # is not a valid integer: {job_num}")
                continue
                
            # Check if job already exists in database
            existing_job = Job.query.filter_by(job=job_num, release=release_str).first()
            
            if existing_job:
                existing_jobs.add(f"{job_num}-{release_str}")
            else:
                # This job has Excel data (and possibly Trello), is predicted 'Released', and is not in the database
                new_jobs_data.append(item)
        
        existing_count = len(existing_jobs)
        new_count = len(new_jobs_data)
        
        print(f"✅ Found {existing_count} existing jobs in database")
        print(f"🆕 Found {new_count} new jobs to create")
        
        safe_log_sync_event(
            operation_id,
            "INFO", 
            "Database check completed",
            existing_jobs=existing_count,
            new_jobs=new_count
        )
        
        if new_count == 0:
            print("✨ No new jobs to create - database is up to date!")
            update_sync_operation(operation_id, status=SyncStatus.COMPLETED, records_processed=total_items)
            return {
                "operation_id": operation_id,
                "total_items": total_items,
                "existing_jobs": existing_count,
                "new_jobs_created": 0,
                "status": "up_to_date"
            }
        
        # Split items by whether they already have a Trello card
        jobs_with_trello = [it for it in new_jobs_data if it.get("trello")]
        jobs_without_trello = [it for it in new_jobs_data if not it.get("trello")]

        print(f"🧭 New jobs with Trello: {len(jobs_with_trello)} | without Trello: {len(jobs_without_trello)}")

        total_created = 0

        # First, create Trello cards for items without Trello, which also creates DB records
        if jobs_without_trello:
            print(f"🃏 Creating Trello cards for {len(jobs_without_trello)} jobs without Trello...")
            from app.trello.api import create_trello_card_from_excel_data
            created_cards = 0
            for item in jobs_without_trello:
                try:
                    excel_data = item.get("excel")
                    if not excel_data:
                        continue
                    # We already filtered to 'Released', so target list is 'Released'
                    result = create_trello_card_from_excel_data(excel_data, list_name="Released")
                    if result and result.get("success"):
                        created_cards += 1
                        total_created += 1
                    else:
                        logging.warning(
                            "Failed to create Trello card for job",
                            extra={"identifier": item.get("identifier"), "error": result.get("error") if result else None}
                        )
                        safe_log_sync_event(
                            operation_id,
                            "WARNING",
                            "Failed to create Trello card for job",
                            identifier=item.get("identifier"),
                            error=(result.get("error") if result else None)
                        )
                except Exception as e:
                    logging.error(f"Error creating Trello card: {e}")
                    safe_log_sync_event(
                        operation_id,
                        "ERROR",
                        "Exception while creating Trello card",
                        identifier=item.get("identifier"),
                        error=str(e)
                    )

            print(f"🃏 Trello card creation complete. Created: {created_cards}")
            safe_log_sync_event(
                operation_id,
                "INFO",
                "Trello card creation completed for items without Trello",
                created_cards=created_cards
            )

        # Next, batch-insert remaining jobs that already have Trello cards
        if jobs_with_trello:
            print(f"🚀 Creating {len(jobs_with_trello)} new jobs (with Trello) in batches of {batch_size}...")
            batch_count = 0
            for i in range(0, len(jobs_with_trello), batch_size):
                batch_items = jobs_with_trello[i:i + batch_size]
                batch_count += 1
                jobs_to_add = []
                
                print(f"Processing batch {batch_count} (items {i+1}-{min(i+batch_size, len(jobs_with_trello))})...")
                
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
                    
                    except Exception as e:
                        identifier = item.get("identifier")
                        logging.error(f"⚠️ Skipping record {identifier}: {e}")
                        safe_log_sync_event(
                            operation_id,
                            "ERROR",
                            f"Failed to process record {identifier}",
                            error=str(e),
                            identifier=identifier
                        )
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
                    
                    safe_log_sync_event(
                        operation_id,
                        "INFO",
                        f"Batch {batch_count} committed successfully",
                        batch_size=len(jobs_to_add),
                        total_created=total_created
                    )
                    
                except SQLAlchemyError as e:
                    db.session.rollback()
                    logging.error(f"✗ Batch {batch_count} failed: {e}")
                    safe_log_sync_event(
                        operation_id,
                        "ERROR",
                        f"Batch {batch_count} failed",
                        error=str(e),
                        batch_number=batch_count
                    )
                finally:
                    # Memory cleanup
                    db.session.expunge_all()
                    gc.collect()
        
        # Update sync operation with final results
        update_sync_operation(
            operation_id,
            status=SyncStatus.COMPLETED,
            records_processed=total_items,
            records_created=total_created
        )
        
        print(f"\n🎉 Incremental seeding completed!")
        print(f"📊 Total items processed: {total_items}")
        print(f"✅ Existing jobs found: {existing_count}")
        print(f"🆕 New jobs created: {total_created}")
        
        safe_log_sync_event(
            operation_id,
            "INFO",
            "Incremental seeding completed successfully",
            total_processed=total_items,
            existing_jobs=existing_count,
            new_jobs_created=total_created
        )
        
        return {
            "operation_id": operation_id,
            "total_items": total_items,
            "existing_jobs": existing_count,
            "new_jobs_created": total_created,
            "status": "completed"
        }
        
    except Exception as e:
        logging.error(f"Incremental seeding failed: {e}")
        safe_log_sync_event(
            operation_id,
            "ERROR",
            "Incremental seeding failed",
            error=str(e),
            error_type=type(e).__name__
        )
        
        update_sync_operation(
            operation_id,
            status=SyncStatus.FAILED,
            error_type=type(e).__name__,
            error_message=str(e)
        )
        
        raise


def process_single_identifier(identifier: str, dry_run: bool = True):
    """
    Process a single job-release identifier of the form "<job>-<release>".
    - Predicts the Trello list based on staging flags
    - If dry_run=False and job not in DB:
      - If no Trello card: create Trello card in predicted list (also creates DB)
      - If Trello card exists: create DB record with Excel data
    Returns a dict with details.
    """
    # NOTE: Excel/OneDrive functionality removed - this function requires Excel data
    raise NotImplementedError("Excel/OneDrive functionality has been removed. process_single_identifier requires Excel data.")
    
    from app.trello.api import get_trello_cards_from_subset, create_trello_card_from_excel_data
    from app.trello.utils import extract_identifier

    # Load Excel - REMOVED
    # df = get_excel_dataframe()
    df["identifier"] = df["Job #"].astype(str) + "-" + df["Release #"].astype(str)

    # Find the row
    row = df[df["identifier"] == identifier]
    if row.empty:
        return {"success": False, "error": f"Identifier not found in Excel: {identifier}", "identifier": identifier}

    row = row.iloc[0]

    # Predict list based on staging
    fitup_comp = str(row.get("Fitup comp", "") or "").strip()
    welded = str(row.get("Welded", "") or "").strip()
    paint_comp = str(row.get("Paint Comp", "") or "").strip()
    ship_val = str(row.get("Ship", "") or "").strip()

    predicted_list = None
    if (
        fitup_comp == "X"
        and welded == "X"
        and paint_comp == "X"
        and (ship_val == "O" or ship_val == "T")
    ):
        predicted_list = "Paint complete"
    elif (
        fitup_comp == "X"
        and welded == "O"
        and paint_comp == ""
        and (ship_val == "T" or ship_val == "O" or ship_val == "")
    ):
        predicted_list = "Fit Up Complete."
    elif (
        fitup_comp == "X"
        and welded == "X"
        and paint_comp == "X"
        and (ship_val == "X")
    ):
        predicted_list = "Shipping completed"
    else:
        predicted_list = "Released"

    # Check DB existence
    job_num = row.get("Job #")
    release_str = str(row.get("Release #", "")).strip()
    existing_job = None
    if job_num and release_str:
        # Validate job number is an integer
        try:
            job_num = int(job_num)
            existing_job = Job.query.filter_by(job=job_num, release=release_str).first()
        except (ValueError, TypeError):
            # Skip rows with invalid job numbers
            pass

    # Check Trello existence for this identifier
    cards = get_trello_cards_from_subset()
    has_trello = False
    trello_card_found = None
    for c in cards:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        ident = extract_identifier(name)
        if ident == identifier:
            has_trello = True
            trello_card_found = c
            break

    result = {
        "success": True,
        "identifier": identifier,
        "job": job_num,
        "release": release_str,
        "ship": ship_val,
        "predicted_list": predicted_list,
        "exists_in_db": existing_job is not None,
        "has_trello_card": has_trello,
        "dry_run": dry_run,
        "action": "none"
    }

    if dry_run:
        # Just report what would happen
        if existing_job:
            result["action"] = "skip_existing_db"
        else:
            result["action"] = "create_trello_and_db" if not has_trello else "create_db_only"
        return result

    # Execute if not dry run
    if existing_job:
        result["action"] = "skip_existing_db"
        return result

    excel_data = row.to_dict()

    if not has_trello:
        # Create Trello card in predicted list (also creates DB)
        create_res = create_trello_card_from_excel_data(excel_data, list_name=predicted_list)
        result["action"] = "created_trello_and_db"
        result["create_result"] = create_res
        return result

    # Has Trello already; create DB record from Excel
    try:
        # Mirror batch path: create Job object directly
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

        # Set Trello details if we found the card
        if trello_card_found:
            jr.trello_card_id = trello_card_found.get("id")
            jr.trello_card_name = safe_truncate_string(trello_card_found.get("name"), 128)
            jr.trello_list_id = trello_card_found.get("list_id")
            jr.trello_list_name = safe_truncate_string(trello_card_found.get("list_name"), 128)
            jr.trello_card_description = safe_truncate_string(trello_card_found.get("desc"), 512)
            if trello_card_found.get("due"):
                jr.trello_card_date = to_date(trello_card_found["due"])

        db.session.add(jr)
        db.session.commit()

        result["action"] = "created_db_only"
        result["job_id"] = jr.id
        return result

    except Exception as e:
        db.session.rollback()
        return {"success": False, "identifier": identifier, "error": str(e)}


def get_trello_excel_cross_check_summary():
    """
    Get a detailed summary of the Trello/Excel cross-check without making database changes.
    Useful for understanding what jobs would be processed by incremental seeding.
    
    Includes all Excel rows with job-release (no filtering by Ship column).
    
    Returns:
        dict: Detailed summary of the cross-check analysis
    """
    try:
        # NOTE: Excel/OneDrive functionality removed
        raise NotImplementedError("Excel/OneDrive functionality has been removed. get_trello_excel_cross_check_summary requires Excel data.")
        
        from app.trello.api import get_trello_cards_from_subset
        from app.trello.utils import extract_identifier
        
        # Get unique cards from the 5 Trello lists
        print("🎯 Analyzing Trello cards from 5 target lists...")
        trello_cards = get_trello_cards_from_subset()
        unique_trello_identifiers = set()
        trello_cards_by_list = {}
        trello_identifier_to_card = {}  # Map identifier -> card for cross-checking
        
        for card in trello_cards:
            name = (card.get("name") or "").strip()
            list_name = card.get("list_name", "Unknown")
            
            if list_name not in trello_cards_by_list:
                trello_cards_by_list[list_name] = 0
            trello_cards_by_list[list_name] += 1
            
            if name:
                identifier = extract_identifier(name)
                if identifier:
                    unique_trello_identifiers.add(identifier)
                    # Store first card for each identifier
                    if identifier not in trello_identifier_to_card:
                        trello_identifier_to_card[identifier] = card
        
        # Get all Excel rows (already filtered to job-release: has Job # and Release #) - REMOVED
        print("📊 Loading all Excel rows with job-release...")
        # df = get_excel_dataframe()  # REMOVED: Excel functionality no longer available
        
        # Create identifier column for Excel rows
        df["identifier"] = df["Job #"].astype(str) + "-" + df["Release #"].astype(str)
        
        # Use all rows (no filtering by Ship column)
        filtered_df = df.copy()
        total_excel_job_release = len(df)
        
        print(f"📊 Total Excel rows with job-release: {total_excel_job_release}")
        print(f"✅ Processing all rows (no Ship column filtering)")
        
        # Cross-check: Which Excel rows have Trello cards?
        excel_with_trello = []
        excel_without_trello = []
        # Predicted target lists for would-be-created cards
        predicted_by_list_counts = {}
        predicted_identifiers_by_list = {}
        
        for _, row in filtered_df.iterrows():
            identifier = row["identifier"]
            has_trello = identifier in trello_identifier_to_card
            
            row_dict = row.to_dict()
            if has_trello:
                excel_with_trello.append({
                    "identifier": identifier,
                    "job": row.get("Job #"),
                    "release": row.get("Release #"),
                    "ship": row.get("Ship"),
                    "trello_card": trello_identifier_to_card[identifier].get("name", ""),
                    "trello_list": trello_identifier_to_card[identifier].get("list_name", "")
                })
            else:
                # Determine predicted list using the same staging rules used during seeding
                fitup_comp = str(row.get("Fitup comp", "") or "").strip()
                welded = str(row.get("Welded", "") or "").strip()
                paint_comp = str(row.get("Paint Comp", "") or "").strip()
                ship_val = str(row.get("Ship", "") or "").strip()

                predicted_list = None
                if (
                    fitup_comp == "X"
                    and welded == "X"
                    and paint_comp == "X"
                    and (ship_val == "O" or ship_val == "T")
                ):
                    predicted_list = "Paint complete"
                elif (
                    fitup_comp == "X"
                    and welded == "O"
                    and paint_comp == ""
                    and (ship_val == "T" or ship_val == "O" or ship_val == "")
                ):
                    predicted_list = "Fit Up Complete."
                elif (
                    fitup_comp == "X"
                    and welded == "X"
                    and paint_comp == "X"
                    and (ship_val == "X")
                ):
                    predicted_list = "Shipping completed"
                else:
                    predicted_list = "Released"

                # Track counts and identifiers per predicted list
                predicted_by_list_counts[predicted_list] = predicted_by_list_counts.get(predicted_list, 0) + 1
                predicted_identifiers_by_list.setdefault(predicted_list, []).append(identifier)

                excel_without_trello.append({
                    "identifier": identifier,
                    "job": row.get("Job #"),
                    "release": row.get("Release #"),
                    "ship": row.get("Ship"),
                    "job_name": row.get("Job", ""),
                    "predicted_list": predicted_list
                })
        
        print(f"🔗 Excel rows WITH Trello cards: {len(excel_with_trello)}")
        print(f"⚠️  Excel rows WITHOUT Trello cards: {len(excel_without_trello)}")
        
        # Check database status for all Excel rows
        existing_in_db = 0
        missing_from_db = 0
        would_be_created_identifiers = []  # Clean list of identifiers that would be created
        
        for _, row in filtered_df.iterrows():
            job_num = row.get("Job #")
            release_str = str(row.get("Release #", "")).strip()
            identifier = row["identifier"]
            
            if job_num and release_str:
                # Validate job number is an integer
                try:
                    job_num = int(job_num)
                    existing_job = Job.query.filter_by(job=job_num, release=release_str).first()
                except (ValueError, TypeError):
                    # Skip rows with invalid job numbers
                    existing_job = None
                if existing_job:
                    existing_in_db += 1
                else:
                    missing_from_db += 1
                    # Only include identifiers that don't have Trello cards (these would get cards created)
                    if identifier not in trello_identifier_to_card:
                        would_be_created_identifiers.append(identifier)
        
        # Sort identifiers for cleaner output
        would_be_created_identifiers.sort()
        
        print(f"📝 Jobs that would be created (with Trello cards): {len(would_be_created_identifiers)}")
        if would_be_created_identifiers:
            print(f"   Identifiers: {', '.join(would_be_created_identifiers)}")
        
        summary = {
            "trello_analysis": {
                "total_cards": len(trello_cards),
                "unique_identifiers": len(unique_trello_identifiers),
                "cards_by_list": trello_cards_by_list
            },
            "excel_analysis": {
                "total_excel_job_release": total_excel_job_release,
                "rows_with_trello": len(excel_with_trello),
                "rows_without_trello": len(excel_without_trello),
                "rows_examples_without_trello": excel_without_trello[:10],  # Show first 10 examples
                "predicted_target_lists": {
                    "counts_by_list": predicted_by_list_counts,
                    "identifiers_by_list": predicted_identifiers_by_list
                }
            },
            "database_status": {
                "jobs_already_in_db": existing_in_db,
                "jobs_missing_from_db": missing_from_db,
                "would_be_created": missing_from_db,
                "rows_in_db": existing_in_db,
                "rows_missing_from_db": missing_from_db
            },
            "would_be_created_identifiers": {
                "count": len(would_be_created_identifiers),
                "identifiers": would_be_created_identifiers
            },
            "target_lists": [
                "Fit Up Complete.",
                "Paint complete", 
                "Shipping completed",
                "Store at MHMW for shipping",
                "Shipping planning",
                "Released"
            ]
        }
        
        return summary
        
    except Exception as e:
        return {"error": str(e)}


def get_first_identifier_to_seed():
    """
    Returns the first job-release identifier from Excel that:
      - Has Job # and Release #
      - Ship does NOT contain X or T
      - Does not already have a Trello card in target lists
      - Does not already exist in DB
    Returns None if none found.
    """
    # NOTE: Excel/OneDrive functionality removed
    raise NotImplementedError("Excel/OneDrive functionality has been removed. get_first_identifier_to_seed requires Excel data.")
    
    from app.trello.api import get_trello_cards_from_subset
    from app.trello.utils import extract_identifier

    # Build Trello identifier set
    trello_cards = get_trello_cards_from_subset()
    trello_idents = set()
    for card in trello_cards:
        name = (card.get("name") or "").strip()
        if not name:
            continue
        ident = extract_identifier(name)
        if ident:
            trello_idents.add(ident)

    # Load Excel - REMOVED
    # df = get_excel_dataframe()
    df["identifier"] = df["Job #"].astype(str) + "-" + df["Release #"].astype(str)

    def ship_has_x_or_t(ship_value):
        if pd.isna(ship_value) or ship_value is None:
            return False
        s = str(ship_value).strip()
        return "X" in s or "T" in s

    filtered_df = df[~df["Ship"].apply(ship_has_x_or_t)].copy()

    # Iterate in Excel order to get the first eligible
    for _, row in filtered_df.iterrows():
        identifier = row["identifier"]
        if identifier in trello_idents:
            continue
        job_num = row.get("Job #")
        release_str = str(row.get("Release #", "")).strip()
        if not job_num or not release_str:
            continue
        # Validate job number is an integer
        try:
            job_num = int(job_num)
        except (ValueError, TypeError):
            # Skip rows with invalid job numbers
            continue
        existing_job = Job.query.filter_by(job=job_num, release=release_str).first()
        if existing_job:
            continue
        return identifier

    return None

# Example usage and testing functions
def run_incremental_seed_example():
    """
    Example function showing how to use the incremental seeding.
    This can be called from a script or Flask route.
    """
    try:
        print("=" * 60)
        print("🌱 INCREMENTAL SEEDING EXAMPLE")
        print("=" * 60)
        
        result = incremental_seed_missing_jobs(batch_size=25)
        
        print("\n📋 OPERATION SUMMARY:")
        print(f"Operation ID: {result['operation_id']}")
        print(f"Status: {result['status']}")
        print(f"Total items from Trello/Excel: {result['total_items']}")
        print(f"Existing jobs in DB: {result['existing_jobs']}")
        print(f"New jobs created: {result['new_jobs_created']}")
        
        if result['status'] == 'up_to_date':
            print("✨ Database is already up to date!")
        else:
            print(f"🎉 Successfully added {result['new_jobs_created']} new jobs!")
            
        return result
        
    except Exception as e:
        print(f"❌ Incremental seeding failed: {e}")
        raise


def determine_stage_from_staging_columns(row):
    """
    Determine the stage based on staging columns following the priority order.
    
    Args:
        row: DataFrame row or dict with staging columns
        
    Returns:
        str: Stage name
    """
    def normalize_val(val):
        """Normalize value: treat O, empty, null, blank as empty."""
        if pd.isna(val) or val == '' or str(val).strip().upper() == 'O':
            return ''
        return str(val).strip().upper()
    
    # Normalize all staging values
    job_comp = normalize_val(row.get('Job Comp', ''))
    ship = normalize_val(row.get('Ship', ''))
    paint_comp = normalize_val(row.get('Paint Comp', ''))
    welded = normalize_val(row.get('Welded', ''))
    fitup_comp = normalize_val(row.get('Fitup comp', ''))
    cut_start = normalize_val(row.get('Cut start', ''))
    
    # Priority order (highest to lowest):
    # 1. Complete - Job Comp = "X" (overrides everything)
    if job_comp == 'X':
        return 'Complete'
    
    # 2. Shipping completed - Ship = "X" (overrides other stages)
    if ship == 'X':
        return 'Shipping completed'
    
    # 3. Shipping planning - Ship = "RS" (overrides Paint Comp status)
    if ship == 'RS':
        return 'Shipping planning'
    
    # 4. Store at MHMW for shipping - Ship = "ST" (overrides Paint Comp status)
    if ship == 'ST':
        return 'Store at MHMW for shipping'
    
    # 5. Paint complete - Paint Comp = "X" AND Ship is empty/O
    if paint_comp == 'X' and ship == '':
        return 'Paint complete'
    
    # 6. Welded QC - Welded = "X" AND Paint Comp is empty/O
    if welded == 'X' and paint_comp == '':
        return 'Welded QC'
    
    # 7. Fit Up Complete. - Fitup comp = "X" AND Welded is empty/O
    if fitup_comp == 'X' and welded == '':
        return 'Fit Up Complete.'
    
    # 8. Cut start - Cut start = "X" (exactly) AND Fitup comp is empty/O
    if cut_start == 'X' and fitup_comp == '':
        return 'Cut start'
    
    # 9. Released - Default/fallback (includes Cut start with "-", "DENCOL", "HOLD", etc.)
    return 'Released'


def preview_csv_jobs_data(csv_file_path=None, max_rows_to_display=50, export_to_csv=None, add_stage_column=True):
    """
    Read CSV file and filter rows with numeric Job # and Release #.
    Display the data in a readable format for eye-checking before DB insertion.
    
    Args:
        csv_file_path: Path to CSV file. If None, looks for JL_Static_Ingestion.csv in project root.
        max_rows_to_display: Maximum number of rows to display in preview (default 50)
        export_to_csv: Optional path to export filtered data as CSV for easier review
    
    Returns:
        dict: Summary with filtered DataFrame and statistics
    """
    # Default to JL_Static_Ingestion.csv in project root if not provided
    if csv_file_path is None:
        # Get project root (parent of app directory)
        project_root = Path(__file__).parent.parent
        csv_file_path = project_root / "JL_Static_Ingestion.csv"
    
    csv_file_path = Path(csv_file_path)
    
    if not csv_file_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_file_path}")
    
    print(f"📄 Reading CSV file: {csv_file_path}")
    print(f"   (Using line 3 as column headers, skipping lines 1-2)\n")
    
    # Read CSV starting from line 3 (0-indexed line 2) as headers
    # Skip first 2 rows (lines 1-2), use row 3 (index 2) as header
    # Use low_memory=False to avoid dtype warnings for mixed types
    df = pd.read_csv(csv_file_path, skiprows=2, header=0, low_memory=False)
    
    print(f"📊 Total rows in CSV (after header): {len(df)}")
    
    # Relevant columns to extract (as specified by user)
    relevant_columns = [
        "Job #", "Release #", "Job", "Description", "Fab Hrs", "Install HRS",
        "Paint color", "PM", "BY", "Released", "Fab Order", "Cut start",
        "Fitup comp", "Welded", "Paint Comp", "Ship", "Start install",
        "Comp. ETA", "Job Comp", "Invoiced", "Notes"
    ]
    
    # Check which columns exist in the CSV
    available_columns = [col for col in relevant_columns if col in df.columns]
    missing_columns = [col for col in relevant_columns if col not in df.columns]
    
    if missing_columns:
        print(f"⚠️  Warning: Some expected columns not found: {missing_columns}\n")
    
    # Filter rows where Job # is numeric and Release # exists (can be alphanumeric like "V123")
    print("🔍 Filtering rows with numeric Job # and valid Release # (alphanumeric allowed)...")
    
    def is_valid_job_release(row):
        """Check if Job # is numeric and Release # exists (can be alphanumeric)."""
        try:
            job_num = row.get("Job #")
            release_num = row.get("Release #")
            
            # Check if both exist and are not null/empty
            if pd.isna(job_num) or pd.isna(release_num):
                return False
            
            # Convert release to string and check it's not empty
            release_str = str(release_num).strip()
            if not release_str:
                return False
            
            # Job # must be numeric
            try:
                float(job_num)
            except (ValueError, TypeError):
                return False
            
            # Release # can be alphanumeric (e.g., "V123", "627", etc.)
            return True
        except (ValueError, TypeError):
            return False
    
    # Apply filter
    mask = df.apply(is_valid_job_release, axis=1)
    filtered_df = df[mask].copy()
    
    total_rows = len(df)
    filtered_rows = len(filtered_df)
    excluded_rows = total_rows - filtered_rows
    
    print(f"   Total rows: {total_rows}")
    print(f"   Rows with numeric Job # and valid Release #: {filtered_rows}")
    print(f"   Rows excluded: {excluded_rows}\n")
    
    if filtered_rows == 0:
        print("❌ No rows found with numeric Job # and valid Release #")
        return {
            "total_rows": total_rows,
            "filtered_rows": 0,
            "excluded_rows": excluded_rows,
            "dataframe": None,
            "summary": "No valid rows found"
        }
    
    # Extract only relevant columns
    filtered_df = filtered_df[available_columns].copy()
    
    # Add Ship date column (null for all, will be set differently)
    filtered_df['Ship date'] = None
    
    # Initialize edge_cases list for later use
    edge_cases = []
    
    # Add Stage column if requested
    if add_stage_column:
        print("🎯 Calculating stage values from staging columns...")
        filtered_df['Stage'] = filtered_df.apply(determine_stage_from_staging_columns, axis=1)
        
        # Check for collisions and edge cases
        print("\n🔍 Checking for edge cases and collisions...")
        edge_cases = []
        collisions = []
        
        for idx, row in filtered_df.iterrows():
            job_comp = str(row.get('Job Comp', '') or '').strip().upper()
            ship = str(row.get('Ship', '') or '').strip().upper()
            paint_comp = str(row.get('Paint Comp', '') or '').strip().upper()
            welded = str(row.get('Welded', '') or '').strip().upper()
            fitup_comp = str(row.get('Fitup comp', '') or '').strip().upper()
            cut_start = str(row.get('Cut start', '') or '').strip().upper()
            
            # Normalize O to empty
            if job_comp == 'O': job_comp = ''
            if ship == 'O': ship = ''
            if paint_comp == 'O': paint_comp = ''
            if welded == 'O': welded = ''
            if fitup_comp == 'O': fitup_comp = ''
            if cut_start == 'O': cut_start = ''
            
            identifier = f"{row['Job #']}-{row['Release #']}"
            stage = row['Stage']
            
            # Note: Ship values (RS, ST, X) now override Paint Comp status, so no edge cases to report
            # This is expected behavior - if Ship has a value, it takes priority
        
        print("✅ Ship values (RS, ST, X) override Paint Comp status - this is expected behavior")
        
        # Check for stage distribution
        stage_counts = filtered_df['Stage'].value_counts()
        print(f"\n📊 Stage distribution:")
        for stage, count in stage_counts.items():
            print(f"   {stage}: {count}")
        
        # Drop staging columns now that we have Stage
        staging_columns_to_drop = ['Cut start', 'Fitup comp', 'Welded', 'Paint Comp', 'Ship', 'Job Comp']
        columns_to_drop = [col for col in staging_columns_to_drop if col in filtered_df.columns]
        if columns_to_drop:
            filtered_df = filtered_df.drop(columns=columns_to_drop)
            print(f"\n🗑️  Dropped staging columns: {', '.join(columns_to_drop)}")
            print(f"   (Stage column contains all staging information)")
        
        # Drop columns with all NaN values (but keep Ship date even if all null)
        all_nan_columns = [col for col in filtered_df.columns 
                          if filtered_df[col].notna().sum() == 0 and col != 'Ship date']
        if all_nan_columns:
            filtered_df = filtered_df.drop(columns=all_nan_columns)
            print(f"🗑️  Dropped columns with all NaN values: {', '.join(all_nan_columns)}")
        
        # Ensure Ship date column exists (null for all)
        if 'Ship date' not in filtered_df.columns:
            filtered_df['Ship date'] = None
            print(f"📅 Added Ship date column (null for all rows)")
    
    # Display summary statistics
    print("=" * 80)
    print("📋 DATA PREVIEW SUMMARY")
    print("=" * 80)
    print(f"Total valid rows: {filtered_rows}")
    print(f"Columns extracted: {len(available_columns)}")
    print(f"\nFirst few rows preview:\n")
    
    # Display first few rows in a readable format
    display_df = filtered_df.head(max_rows_to_display)
    
    # Use pandas display options for better readability
    with pd.option_context('display.max_columns', None, 
                           'display.width', None,
                           'display.max_colwidth', 50):
        print(display_df.to_string(index=False))
    
    if filtered_rows > max_rows_to_display:
        print(f"\n... ({filtered_rows - max_rows_to_display} more rows not shown)")
    
    print("\n" + "=" * 80)
    print("📊 COLUMN STATISTICS")
    print("=" * 80)
    
    # Show some basic stats for key columns
    stats_columns = ["Job #", "Release #", "Fab Hrs", "Install HRS"]
    for col in stats_columns:
        if col in filtered_df.columns:
            non_null = filtered_df[col].notna().sum()
            print(f"{col}: {non_null} non-null values")
    
    # Optionally export to CSV for easier review
    if export_to_csv:
        export_path = Path(export_to_csv)
        filtered_df.to_csv(export_path, index=False)
        print(f"\n💾 Exported filtered data to: {export_path}")
        print(f"   ({filtered_rows} rows, {len(available_columns)} columns)")
    
    print("\n" + "=" * 80)
    print("✅ Preview complete!")
    print("=" * 80)
    
    result = {
        "total_rows": total_rows,
        "filtered_rows": filtered_rows,
        "excluded_rows": excluded_rows,
        "dataframe": filtered_df,
        "columns": available_columns,
        "missing_columns": missing_columns,
        "export_path": str(export_to_csv) if export_to_csv else None,
        "summary": f"Found {filtered_rows} valid rows with numeric Job # and valid Release #"
    }
    
    # Add edge cases info if stage column was added
    if add_stage_column and 'Stage' in filtered_df.columns:
        result['edge_cases'] = edge_cases
        result['stage_distribution'] = filtered_df['Stage'].value_counts().to_dict()
    
    return result


def seed_jobs_from_csv(csv_file_path=None, batch_size=50, require_confirmation=True):
    """
    Seed the jobs table from CSV file, wiping all existing records first.
    
    This function:
    1. Shows the database connection info
    2. Asks for confirmation (if require_confirmation=True)
    3. Deletes all existing Job records
    4. Seeds the database with data from the CSV file
    
    Args:
        csv_file_path: Path to CSV file. If None, uses default JL_Static_Ingestion.csv
        batch_size: Number of records to insert per batch (default 50)
        require_confirmation: If True, prompts for confirmation before proceeding (default True)
    
    Returns:
        dict: Summary of the operation with counts and status
    """
    from app import create_app
    from datetime import datetime
    
    app = create_app()
    
    with app.app_context():
        # Get database connection info
        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', 'Not configured')
        
        # Mask sensitive parts of the URI for display
        if db_uri != 'Not configured':
            # Mask passwords in connection strings
            if '@' in db_uri:
                parts = db_uri.split('@')
                if len(parts) == 2:
                    user_pass = parts[0].split('://')[-1]
                    if ':' in user_pass:
                        user, _ = user_pass.split(':', 1)
                        masked_uri = db_uri.replace(user_pass, f"{user}:***")
                    else:
                        masked_uri = db_uri
                else:
                    masked_uri = db_uri
            else:
                masked_uri = db_uri
        else:
            masked_uri = db_uri
        
        print("=" * 80)
        print("🗄️  DATABASE SEEDING OPERATION")
        print("=" * 80)
        print(f"\n📊 Database Connection:")
        print(f"   URI: {masked_uri}")
        
        # Count existing records
        existing_count = Job.query.count()
        print(f"   Current records in jobs table: {existing_count}")
        
        if existing_count > 0:
            print(f"\n⚠️  WARNING: This operation will DELETE all {existing_count} existing job records!")
            print(f"   All existing data will be permanently lost.")
        else:
            print(f"\nℹ️  No existing records found. Will proceed with seeding.")
        
        # Get CSV data preview
        print(f"\n📄 Loading CSV data...")
        csv_result = preview_csv_jobs_data(csv_file_path=csv_file_path, max_rows_to_display=0, add_stage_column=True)
        
        if csv_result['filtered_rows'] == 0:
            print("❌ No valid rows found in CSV. Aborting.")
            return {
                "success": False,
                "error": "No valid rows in CSV",
                "existing_count": existing_count,
                "new_count": 0
            }
        
        df = csv_result['dataframe']
        
        # Check for and remove duplicate job-release combinations
        initial_count = len(df)
        duplicates = df[df.duplicated(subset=['Job #', 'Release #'], keep=False)]
        
        if len(duplicates) > 0:
            print(f"\n⚠️  Found {len(duplicates)} duplicate job-release combinations:")
            for idx, row in duplicates.iterrows():
                print(f"   Job {row['Job #']}-{row['Release #']}: {row.get('Job', 'N/A')}")
            
            # Remove duplicates, keeping first occurrence
            df = df.drop_duplicates(subset=['Job #', 'Release #'], keep='first')
            removed_count = initial_count - len(df)
            print(f"\n🗑️  Removed {removed_count} duplicate rows (keeping first occurrence)")
        
        new_count = len(df)
        
        print(f"\n📋 CSV Data Summary:")
        print(f"   Valid rows to insert: {new_count}")
        print(f"   Columns: {len(df.columns)}")
        
        # Confirmation prompt
        if require_confirmation:
            print("\n" + "=" * 80)
            print("⚠️  CONFIRMATION REQUIRED")
            print("=" * 80)
            print(f"\nThis will:")
            print(f"  1. DELETE all {existing_count} existing job records")
            print(f"  2. INSERT {new_count} new job records from CSV")
            print(f"\nDatabase: {masked_uri}")
            
            response = input("\nType 'YES' to proceed, or anything else to cancel: ").strip()
            
            if response != 'YES':
                print("\n❌ Operation cancelled by user.")
                return {
                    "success": False,
                    "cancelled": True,
                    "existing_count": existing_count,
                    "new_count": new_count
                }
        
        print("\n" + "=" * 80)
        print("🚀 STARTING SEEDING OPERATION")
        print("=" * 80)
        
        try:
            # Step 1: Delete all existing records
            if existing_count > 0:
                print(f"\n🗑️  Deleting {existing_count} existing job records...")
                deleted_count = Job.query.delete()
                db.session.commit()
                print(f"   ✓ Deleted {deleted_count} records")
            else:
                print(f"\n✓ No existing records to delete")
            
            # Step 2: Insert new records in batches
            print(f"\n📥 Inserting {new_count} new records in batches of {batch_size}...")
            
            total_created = 0
            batch_count = 0
            errors = []
            
            for i in range(0, len(df), batch_size):
                batch_df = df.iloc[i:i + batch_size]
                batch_count += 1
                jobs_to_add = []
                
                print(f"\n   Processing batch {batch_count} (rows {i+1}-{min(i+batch_size, len(df))})...")
                
                for idx, row in batch_df.iterrows():
                    try:
                        # Map CSV columns to Job model fields
                        stage_value = safe_truncate_string(row.get('Stage'), 128)
                        from app.api.helpers import get_stage_group_from_stage
                        stage_group_value = get_stage_group_from_stage(stage_value) if stage_value else None
                        
                        job_record = Job(
                            job=int(row['Job #']),
                            release=str(row['Release #']).strip(),
                            job_name=safe_truncate_string(row.get('Job'), 128),
                            description=safe_truncate_string(row.get('Description'), 256),
                            fab_hrs=safe_float(row.get('Fab Hrs')),
                            install_hrs=safe_float(row.get('Install HRS')),
                            paint_color=safe_truncate_string(row.get('Paint color'), 64),
                            pm=safe_truncate_string(row.get('PM'), 16),
                            by=safe_truncate_string(row.get('BY'), 16),
                            released=to_date(row.get('Released')),
                            fab_order=safe_float(row.get('Fab Order')),
                            stage=stage_value,
                            stage_group=stage_group_value,
                            start_install=to_date(row.get('Start install')),
                            comp_eta=to_date(row.get('Comp. ETA')),
                            invoiced=safe_truncate_string(row.get('Invoiced'), 8),
                            notes=safe_truncate_string(row.get('Notes'), 256),
                            ship_date=to_date(row.get('Ship date')),  # Will be None for all rows initially
                            last_updated_at=datetime.utcnow(),
                            source_of_update="CSV"
                        )
                        
                        jobs_to_add.append(job_record)
                        
                    except Exception as e:
                        identifier = f"{row.get('Job #', '?')}-{row.get('Release #', '?')}"
                        error_msg = f"Error processing row {identifier}: {str(e)}"
                        errors.append(error_msg)
                        logging.error(error_msg)
                        continue
                
                # Commit this batch
                if not jobs_to_add:
                    print(f"      ⚠️  No valid records in batch {batch_count}")
                    continue
                
                try:
                    db.session.bulk_save_objects(jobs_to_add)
                    db.session.commit()
                    total_created += len(jobs_to_add)
                    print(f"      ✓ Batch {batch_count}: {len(jobs_to_add)} records inserted")
                    
                except SQLAlchemyError as e:
                    db.session.rollback()
                    error_str = str(e)
                    
                    # Check if it's a unique constraint violation (duplicate)
                    if "UNIQUE constraint" in error_str or "duplicate" in error_str.lower():
                        # Try inserting records one by one to identify the duplicate
                        print(f"      ⚠️  Batch {batch_count} has duplicate(s), inserting individually...")
                        batch_created = 0
                        for job_record in jobs_to_add:
                            try:
                                db.session.add(job_record)
                                db.session.commit()
                                batch_created += 1
                            except SQLAlchemyError as dup_error:
                                db.session.rollback()
                                identifier = f"{job_record.job}-{job_record.release}"
                                error_msg = f"Duplicate skipped: {identifier}"
                                errors.append(error_msg)
                                logging.warning(error_msg)
                        
                        total_created += batch_created
                        skipped = len(jobs_to_add) - batch_created
                        if skipped > 0:
                            print(f"      ✓ Batch {batch_count}: {batch_created} inserted, {skipped} duplicates skipped")
                        else:
                            print(f"      ✓ Batch {batch_count}: {batch_created} records inserted")
                    else:
                        # Other database error
                        error_msg = f"Database error in batch {batch_count}: {error_str}"
                        errors.append(error_msg)
                        logging.error(error_msg)
                        print(f"      ✗ Batch {batch_count} failed: {error_str}")
                finally:
                    # Memory cleanup
                    db.session.expunge_all()
                    gc.collect()
            
            # Final summary
            print("\n" + "=" * 80)
            print("✅ SEEDING OPERATION COMPLETE")
            print("=" * 80)
            print(f"\n📊 Summary:")
            print(f"   Records deleted: {existing_count}")
            print(f"   Records inserted: {total_created}")
            print(f"   Errors: {len(errors)}")
            
            if errors:
                print(f"\n⚠️  Errors encountered:")
                for error in errors[:10]:  # Show first 10 errors
                    print(f"   - {error}")
                if len(errors) > 10:
                    print(f"   ... and {len(errors) - 10} more errors")
            
            return {
                "success": True,
                "existing_count": existing_count,
                "new_count": total_created,
                "errors": errors,
                "database_uri": masked_uri
            }
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Fatal error during seeding: {str(e)}"
            logging.error(error_msg, exc_info=True)
            print(f"\n❌ {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "existing_count": existing_count,
                "new_count": 0
            }


if __name__ == "__main__":
    # This allows you to run the seeding directly from command line
    # python -m app.seed
    import sys
    
    # Check if user wants to preview CSV data
    if len(sys.argv) > 1 and sys.argv[1] == "preview":
        print("=" * 80)
        print("📋 CSV JOBS DATA PREVIEW")
        print("=" * 80)
        export_path = sys.argv[2] if len(sys.argv) > 2 else None
        preview_csv_jobs_data(export_to_csv=export_path)
    elif len(sys.argv) > 1 and sys.argv[1] == "seed":
        # Run the seed function
        print("=" * 80)
        print("🌱 CSV TO DATABASE SEEDING")
        print("=" * 80)
        csv_path = sys.argv[2] if len(sys.argv) > 2 else None
        no_confirm = len(sys.argv) > 3 and sys.argv[3] == "--no-confirm"
        result = seed_jobs_from_csv(csv_file_path=csv_path, require_confirmation=not no_confirm)
        if not result.get("success"):
            sys.exit(1)
    else:
        print("Usage:")
        print("  Preview CSV: python -m app.seed preview [output.csv]")
        print("  Seed database: python -m app.seed seed [csv_path] [--no-confirm]")
        print("\nRunning incremental seeding example...")
        run_incremental_seed_example()
