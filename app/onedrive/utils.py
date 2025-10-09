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

    logger.info("OneDrive poll starting with sync lock acquired")
    event_info = parse_polling_data()
    sync_from_onedrive(event_info)
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
               Returns (None, None) if not found.
    """
    df = get_excel_dataframe()
    # Ensure job is int, but keep release as string to preserve format like "v862"
    job = int(job)
    # Convert release to string to handle cases like "v862"
    release = str(release)

    # Debug: Log what we're looking for and what's available
    logger.info(f"Looking for Job # {job} (type: {type(job)}) and Release # {release} (type: {type(release)})")
    
    # Check if the columns exist
    if "Job #" not in df.columns or "Release #" not in df.columns:
        logger.error(f"Required columns not found. Available columns: {list(df.columns)}")
        return None, None
    
    # Debug: Show some sample values
    if not df.empty:
        logger.info(f"Sample Job # values: {df['Job #'].head().tolist()}")
        logger.info(f"Sample Release # values: {df['Release #'].head().tolist()}")
        logger.info(f"Job # column dtype: {df['Job #'].dtype}")
        logger.info(f"Release # column dtype: {df['Release #'].dtype}")

    match = df[(df["Job #"] == job) & (df["Release #"] == release)]
    if not match.empty:
        idx = match.index[0] + cfg.EXCEL_INDEX_ADJ
        row = match.iloc[0]
        logger.info(f"Found match at DataFrame index {match.index[0]}, Excel row {idx}")
        return idx, row
    else:
        logger.warning(f"No row found for Job # {job} and Release # {release}.")
        # Additional debugging: check if any rows match just the job number
        job_matches = df[df["Job #"] == job]
        if not job_matches.empty:
            logger.info(f"Found {len(job_matches)} rows with Job # {job}, but different Release # values: {job_matches['Release #'].tolist()}")
        else:
            logger.info(f"No rows found with Job # {job} at all")
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
