import pandas as pd

relevant_columns = [
    "Job",
    "Description",
    "Fab Hrs",
    "Install HRS",
    "Paint color",
    "PM",
    "BY",
    "Released",
    "Fab Order",
    "Cut start",
    "Fitup comp",
    "Welded",
    "Paint Comp",
    "Ship",
    "Start install",
    "Comp. ETA",
    "Job Comp",
    "Notes",
]


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


def save_excel_snapshot(
    df, filename="excel_snapshot.xlsx", rows=None, columns=relevant_columns
):
    """
    Save a slice of the DataFrame to a local Excel file for later comparison.
    - rows: list of row indices to save (optional)
    - columns: list of column names to save (optional)
    """
    snapshot = df
    if rows is not None:
        snapshot = snapshot.loc[rows]
    if columns is not None:
        snapshot = snapshot[columns]
    snapshot.to_excel(filename, index=False)
    print(f"Snapshot saved to {filename}")
