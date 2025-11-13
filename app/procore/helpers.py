import pandas as pd
# Helper function to convert pandas NaT/NaN to None
def clean_value(value):
    if pd.isna(value):
        return None
    # If it's a pandas Timestamp, convert to Python datetime
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime() if not pd.isna(value) else None
    return value