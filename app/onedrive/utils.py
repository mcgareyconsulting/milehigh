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
    # Ensure identifiers are the correct type
    job = int(job)
    release = int(release)

    match = df[(df["Job #"] == job) & (df["Release #"] == release)]
    if not match.empty:
        idx = match.index[0] + cfg.EXCEL_INDEX_ADJ
        row = match.iloc[0]
        return idx, row
    else:
        print(f"No row found for Job # {job} and Release # {release}.")
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
