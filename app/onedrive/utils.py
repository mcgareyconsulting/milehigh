import pandas as pd
from app.onedrive.api import get_excel_dataframe
from app.config import Config as cfg


def find_excel_row(df, identifier):
    """
    Finds and returns the row in the DataFrame where 'Job # - Release #' matches the identifier.
    Returns the row as a pandas Series with only the relevant columns if found, otherwise returns None.
    """
    combined = df["Job #"].astype(str) + "-" + df["Release #"].astype(str)
    match = df[combined == identifier]
    if not match.empty:
        return match.iloc[0][relevant_columns]
    return None


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


def build_unique_identifiers(df):
    """
    Combines 'Job #' and 'Release #' columns into unique identifiers in the format 'Job #-Release #'.
    Returns a list of these identifiers.
    """
    # Drop rows where either value is missing
    filtered = df.dropna(subset=["Job #", "Release #"])
    # Convert to string and combine
    identifiers = (
        filtered["Job #"].astype(str) + "-" + filtered["Release #"].astype(str)
    )
    return identifiers.tolist()
