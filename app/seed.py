import pandas as pd
from app.models import db, Job, SyncOperation, SyncStatus
from app.combine import combine_trello_excel_data
from app.sync import create_sync_operation, update_sync_operation, safe_log_sync_event
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
        from app.onedrive.api import get_excel_dataframe
        
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
        
        # Get all Excel rows (already filtered to job-release: has Job # and Release #)
        print("📊 Loading all Excel rows with job-release...")
        df = get_excel_dataframe()
        
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
        valid_items = []
        trello_only_count = 0  # Not applicable in new approach, but kept for logging
        excel_with_trello_count = 0
        excel_without_trello_count = 0
        
        for _, row in filtered_df.iterrows():
            identifier = row["identifier"]
            trello_card = trello_identifier_to_card.get(identifier)
            
            # Convert row to dict format compatible with existing code
            excel_data = row.to_dict()
            
            item = {
                "identifier": identifier,
                "trello": trello_card,
                "excel": excel_data
            }
            valid_items.append(item)
            
            if trello_card:
                excel_with_trello_count += 1
            else:
                excel_without_trello_count += 1
        
        total_items = len(valid_items)
        print(f"✅ Found {total_items} eligible Excel rows (job-release, Ship without X/T)")
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
        print("   (Processing eligible Excel rows: job-release without X/T in Ship)")
        
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
                
            # Check if job already exists in database
            existing_job = Job.query.filter_by(job=job_num, release=release_str).first()
            
            if existing_job:
                existing_jobs.add(f"{job_num}-{release_str}")
            else:
                # This job has Excel data (and possibly Trello), Ship without X/T, but is not in the database
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
                    # Determine target list based on staging flags (mirrors determine_trello_list_from_db)
                    fitup_comp = str(excel_data.get("Fitup comp", "") or "").strip()
                    welded = str(excel_data.get("Welded", "") or "").strip()
                    paint_comp = str(excel_data.get("Paint Comp", "") or "").strip()
                    ship = str(excel_data.get("Ship", "") or "").strip()

                    list_name = None
                    if (
                        fitup_comp == "X"
                        and welded == "X"
                        and paint_comp == "X"
                        and (ship == "O" or ship == "T")
                    ):
                        list_name = "Paint complete"
                    elif (
                        fitup_comp == "X"
                        and welded == "O"
                        and paint_comp == ""
                        and (ship == "T" or ship == "O" or ship == "")
                    ):
                        list_name = "Fit Up Complete."
                    elif (
                        fitup_comp == "X"
                        and welded == "X"
                        and paint_comp == "X"
                        and (ship == "X")
                    ):
                        list_name = "Shipping completed"
                    # Fallback to "Released" if no staging rule matched
                    if not list_name:
                        list_name = "Released"

                    result = create_trello_card_from_excel_data(excel_data, list_name=list_name)
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


def get_trello_excel_cross_check_summary():
    """
    Get a detailed summary of the Trello/Excel cross-check without making database changes.
    Useful for understanding what jobs would be processed by incremental seeding.
    
    Now includes analysis of Excel rows with job-release that don't have X or T in Ship column.
    
    Returns:
        dict: Detailed summary of the cross-check analysis
    """
    try:
        from app.trello.api import get_trello_cards_from_subset
        from app.trello.utils import extract_identifier
        from app.onedrive.api import get_excel_dataframe
        
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
        
        # Get all Excel rows (already filtered to job-release: has Job # and Release #)
        print("📊 Loading all Excel rows with job-release...")
        df = get_excel_dataframe()
        
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
        print(f"✅ Rows eligible (Ship does NOT have X or T): {total_filtered_rows}")
        
        # Cross-check: Which filtered Excel rows have Trello cards?
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
        
        print(f"🔗 Excel rows (eligible) WITH Trello cards: {len(excel_with_trello)}")
        print(f"⚠️  Excel rows (eligible) WITHOUT Trello cards: {len(excel_without_trello)}")
        
        # Check database status for eligible Excel rows
        existing_in_db = 0
        missing_from_db = 0
        would_be_created_identifiers = []  # Clean list of identifiers that would be created
        
        for _, row in filtered_df.iterrows():
            job_num = row.get("Job #")
            release_str = str(row.get("Release #", "")).strip()
            identifier = row["identifier"]
            
            if job_num and release_str:
                existing_job = Job.query.filter_by(job=job_num, release=release_str).first()
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
            "excel_filtered_analysis": {
                "total_excel_job_release": total_excel_job_release,
                "rows_excluded_ship_has_x_or_t": rows_with_x_or_t,
                "rows_eligible_ship_no_x_or_t": total_filtered_rows,
                "eligible_rows_with_trello": len(excel_with_trello),
                "eligible_rows_without_trello": len(excel_without_trello),
                "eligible_rows_examples_without_trello": excel_without_trello[:10],  # Show first 10 examples
                "predicted_target_lists": {
                    "counts_by_list": predicted_by_list_counts,
                    "identifiers_by_list": predicted_identifiers_by_list
                }
            },
            "database_status": {
                "jobs_already_in_db": existing_in_db,
                "jobs_missing_from_db": missing_from_db,
                "would_be_created": missing_from_db,
                "eligible_rows_in_db": existing_in_db,
                "eligible_rows_missing_from_db": missing_from_db
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


if __name__ == "__main__":
    # This allows you to run the seeding directly from command line
    # python -m app.seed
    print("Running incremental seeding example...")
    run_incremental_seed_example()
