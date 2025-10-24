import pandas as pd
from app.onedrive.api import get_excel_dataframe, get_excel_data_with_timestamp
from app.config import Config as cfg
from app.sync_lock import synchronized_sync
import logging

logger = logging.getLogger(__name__)


@synchronized_sync("OneDrive-Poll")
def run_onedrive_poll():
    """
    Core logic for polling OneDrive and syncing.
    Used by both the manual route and the scheduler.
    Now with automatic locking protection.
    """
    from app.sync import sync_from_onedrive
    from app.onedrive.api import capture_excel_snapshot_with_data

    logger.info("OneDrive poll starting with sync lock acquired")
    event_info = parse_polling_data()
    
    # Run the sync first
    sync_from_onedrive(event_info)
    
    # After sync is complete, check for new rows and save a snapshot
    if event_info and "data" in event_info:
        logger.info("Checking for new rows and saving Excel snapshot after sync completion")
        try:
            # Get the Excel data that was just processed
            current_df = event_info["data"]
            excel_data = {
                "name": "Job Log",  # Default name since we don't have it from parse_polling_data
                "last_modified_time": event_info.get("last_modified_time"),
                "data": current_df
            }
            
            # Check for new rows by comparing with the most recent snapshot
            from app.onedrive.api import get_latest_snapshot, find_new_rows_in_excel
            
            snapshot_date, previous_df, previous_metadata = get_latest_snapshot()
            
            if previous_df is not None:
                logger.info(f"Comparing current data ({len(current_df)} rows) with latest snapshot from {snapshot_date} ({len(previous_df)} rows)")
                
                # Find new rows
                new_rows = find_new_rows_in_excel(current_df, previous_df)
                
                if not new_rows.empty:
                    logger.info(f"🔍 NEW ROWS DETECTED: {len(new_rows)} new rows found!")
                    print(f"🔍 NEW ROWS DETECTED: {len(new_rows)} new rows found!")
                    
                    # Print details of new rows for debugging
                    for idx, row in new_rows.iterrows():
                        job_id = row.get('Job #', 'N/A')
                        release = row.get('Release #', 'N/A')
                        description = row.get('Description', 'N/A')
                        print(f"  - New row: Job #{job_id}, Release {release}: {description}")
                        logger.info(f"New row: Job #{job_id}, Release {release}: {description}")
                else:
                    logger.info("No new rows detected - data unchanged since last snapshot")
                    print("No new rows detected - data unchanged since last snapshot")
            else:
                logger.info("No previous snapshot found - treating all rows as new")
                print("No previous snapshot found - treating all rows as new")
            
            # Save snapshot using the data we already downloaded
            snapshot_result = capture_excel_snapshot_with_data(
                current_df, 
                excel_data
            )
            
            if snapshot_result["success"]:
                logger.info(f"Snapshot saved successfully: {snapshot_result['snapshot_date']} ({snapshot_result['row_count']} rows)")
            else:
                logger.warning(f"Failed to save snapshot: {snapshot_result.get('error', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"Error during diff check and snapshot save: {str(e)}")
            print(f"Error during diff check and snapshot save: {str(e)}")
    else:
        logger.warning("No data available for snapshot - skipping snapshot save")
    
    logger.info("OneDrive poll completed")
    return event_info


def get_excel_row_and_index_by_identifiers(job, release):
    """
    Fetch a row from the Excel file using Job # and Release # as unique identifiers.

    Args:
        job (int or str): The Job # identifier.
        release (int or str): The Release # identifier.

    Returns:
        tuple: (index, pandas.Series) where index is the DataFrame index (int),
               and pandas.Series is the matching row.
               Returns (None, None) if not found or if Excel reading fails.
    """
    try:
        df = get_excel_dataframe()
    except Exception as e:
        logger.error(f"Failed to read Excel file: {str(e)}")
        return None, None

    # Ensure job is int, but keep release as string to preserve format like "v862"
    try:
        job = int(job)
        # Convert release to string to handle cases like "v862"
        release = str(release)
    except (ValueError, TypeError) as e:
        logger.error(f"Invalid job or release identifiers: job={job}, release={release}, error={str(e)}")
        return None, None

    # Debug: Log what we're looking for and what's available
    logger.info(f"Looking for Job # {job} (type: {type(job)}) and Release # {release} (type: {type(release)})")
    
    # Check if the columns exist
    if "Job #" not in df.columns or "Release #" not in df.columns:
        logger.error(f"Required columns not found. Available columns: {list(df.columns)}")
        return None, None

    try:
        match = df[(df["Job #"] == job) & (df["Release #"] == release)]
        if not match.empty:
            idx = match.index[0] + cfg.EXCEL_INDEX_ADJ
            row = match.iloc[0]
            logger.info(f"Found match at DataFrame index {match.index[0]}, Excel row {idx}")
            return idx, row
        else:
            logger.warning(f"No row found for Job # {job} and Release # {release}.")
            return None, None
    except Exception as e:
        logger.error(f"Error searching for Excel row: {str(e)}")
        return None, None


def parse_excel_datetime(dt_str):
    """
    Parse OneDrive/Excel lastModifiedDateTime into naive UTC datetime.
    """
    if not dt_str:
        return None
    dt = pd.to_datetime(dt_str, utc=True)  # ensure UTC
    return dt.tz_convert(None)  # drop tzinfo, make naive


def parse_polling_data():
    """
    Pull excel data from api and process for passing to sync function.
    """
    data = get_excel_data_with_timestamp()

    if data is None:
        print("No data received from OneDrive polling")
        return None

    if "last_modified_time" not in data or "data" not in data:
        print("Invalid OneDrive polling data format")
        return None

    last_modified_time = data["last_modified_time"]
    df = data["data"]
    return {"last_modified_time": last_modified_time, "data": df}
