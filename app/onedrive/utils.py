def find_excel_row(df, identifier):
    """
    Finds and returns the row in the DataFrame where 'Job # - Release #' matches the identifier.
    Returns the row as a pandas Series with only the relevant columns if found, otherwise returns None.
    """
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
        "Invoiced",
        "Notes",
    ]
    combined = df["Job #"].astype(str) + "-" + df["Release #"].astype(str)
    match = df[combined == identifier]
    if not match.empty:
        return match.iloc[0][relevant_columns]
    return None
