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
    and only adds missing ones from the Trello/Excel cross-check.
    
    This function:
    1. Gets combined Trello/Excel data from the 5 target lists
    2. Checks which jobs already exist in the database
    3. Only creates new Job records for missing ones
    4. Tracks the operation with sync logging
    
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
        
        # Get combined Trello/Excel data (already cross-checks against 5 target lists)
        print("📊 Fetching Trello cards from 5 target lists...")
        from app.trello.api import get_trello_cards_from_subset
        from app.trello.utils import extract_identifier
        
        # Get unique cards from the 5 Trello lists
        trello_cards = get_trello_cards_from_subset()
        unique_trello_identifiers = set()
        
        for card in trello_cards:
            name = (card.get("name") or "").strip()
            if name:
                identifier = extract_identifier(name)
                if identifier:
                    unique_trello_identifiers.add(identifier)
        
        print(f"🎯 Found {len(unique_trello_identifiers)} unique job identifiers in Trello lists")
        print("📊 Cross-checking with Excel data...")
        
        combined_data = combine_trello_excel_data()
        
        # Filter to only items that have both Trello cards AND Excel data
        valid_items = []
        trello_only_count = 0
        excel_only_count = 0
        
        for item in combined_data:
            has_trello = item.get("trello") is not None
            has_excel = item.get("excel") is not None
            identifier = item.get("identifier")
            
            if has_trello and has_excel:
                valid_items.append(item)
            elif has_trello and not has_excel:
                trello_only_count += 1
            elif has_excel and not has_trello:
                excel_only_count += 1
        
        total_items = len(valid_items)
        print(f"✅ Found {total_items} jobs with both Trello cards and Excel data")
        print(f"📋 Trello-only cards (no Excel match): {trello_only_count}")
        print(f"📊 Excel-only rows (no Trello card): {excel_only_count}")
        
        safe_log_sync_event(
            operation_id, 
            "INFO", 
            "Trello/Excel cross-check completed",
            unique_trello_identifiers=len(unique_trello_identifiers),
            valid_items_with_both=total_items,
            trello_only=trello_only_count,
            excel_only=excel_only_count
        )
        
        # Use the filtered valid items for processing
        combined_data = valid_items
        
        # Check which jobs already exist in database
        existing_jobs = set()
        new_jobs_data = []
        
        print("🔍 Checking for existing jobs in database...")
        print("   (Only considering jobs that have both Trello cards and Excel data)")
        
        for item in combined_data:
            excel_data = item.get("excel")
            trello_data = item.get("trello")
            identifier = item.get("identifier")
            
            # Double-check that we have both (should always be true after filtering above)
            if not excel_data or not trello_data:
                print(f"⚠️  Skipping {identifier} - missing Trello or Excel data")
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
                # This job has a Trello card, Excel data, but is not in the database
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
        
        # Create new jobs using batched approach
        print(f"🚀 Creating {new_count} new jobs in batches of {batch_size}...")
        total_created = 0
        batch_count = 0
        
        for i in range(0, len(new_jobs_data), batch_size):
            batch_items = new_jobs_data[i:i + batch_size]
            batch_count += 1
            jobs_to_add = []
            
            print(f"Processing batch {batch_count} (items {i+1}-{min(i+batch_size, len(new_jobs_data))})...")
            
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
    
    Returns:
        dict: Detailed summary of the cross-check analysis
    """
    try:
        from app.trello.api import get_trello_cards_from_subset
        from app.trello.utils import extract_identifier
        
        # Get unique cards from the 5 Trello lists
        print("🎯 Analyzing Trello cards from 5 target lists...")
        trello_cards = get_trello_cards_from_subset()
        unique_trello_identifiers = set()
        trello_cards_by_list = {}
        
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
        
        # Get combined data
        print("📊 Cross-checking with Excel data...")
        combined_data = combine_trello_excel_data()
        
        # Analyze the cross-check results
        valid_items = []
        trello_only_items = []
        excel_only_items = []
        
        for item in combined_data:
            has_trello = item.get("trello") is not None
            has_excel = item.get("excel") is not None
            identifier = item.get("identifier")
            
            if has_trello and has_excel:
                valid_items.append(item)
            elif has_trello and not has_excel:
                trello_only_items.append(item)
            elif has_excel and not has_trello:
                excel_only_items.append(item)
        
        # Check database status for valid items
        existing_in_db = 0
        missing_from_db = 0
        
        for item in valid_items:
            excel_data = item.get("excel")
            if excel_data:
                job_num = excel_data.get("Job #")
                release_str = str(excel_data.get("Release #", "")).strip()
                
                if job_num and release_str:
                    existing_job = Job.query.filter_by(job=job_num, release=release_str).first()
                    if existing_job:
                        existing_in_db += 1
                    else:
                        missing_from_db += 1
        
        summary = {
            "trello_analysis": {
                "total_cards": len(trello_cards),
                "unique_identifiers": len(unique_trello_identifiers),
                "cards_by_list": trello_cards_by_list
            },
            "cross_check_results": {
                "valid_items_both_trello_excel": len(valid_items),
                "trello_only_no_excel": len(trello_only_items),
                "excel_only_no_trello": len(excel_only_items)
            },
            "database_status": {
                "jobs_already_in_db": existing_in_db,
                "jobs_missing_from_db": missing_from_db,
                "would_be_created": missing_from_db
            },
            "target_lists": [
                "Fit Up Complete.",
                "Paint complete", 
                "Shipping completed",
                "Store at MHMW for shipping",
                "Shipping planning"
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
