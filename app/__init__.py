from flask import Flask, request, make_response, jsonify
from .config import Config as cfg
from app.trello import trello_bp
from app.onedrive import onedrive_bp
from app.onedrive.api import get_excel_dataframe

# database imports
from app.models import db, query_job_releases
from app.seed import seed_job_releases_from_df
import pandas as pd


def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///jobs.sqlite"
    db.init_app(app)

    # Initialize the database
    with app.app_context():
        df = get_excel_dataframe()  # or create DataFrame from your source
        db.create_all()
        seed_job_releases_from_df(df)

    # helpers
    import pandas as pd
    import numpy as np
    from flask import jsonify

    def normalize_percentage_field(value):
        """
        Normalize percentage fields to handle different formats:
        - 0.9 -> 0.9
        - 90% -> 0.9
        - "90%" -> 0.9
        - Empty/None -> None
        """
        if pd.isna(value) or value == "" or value is None:
            return None

        # Convert to string for processing
        str_value = str(value).strip()

        # Handle empty strings
        if not str_value:
            return None

        # If it ends with %, remove % and divide by 100
        if str_value.endswith("%"):
            try:
                return float(str_value[:-1]) / 100
            except ValueError:
                return None

        # Try to convert to float directly
        try:
            return float(str_value)
        except ValueError:
            return None

    def normalize_dataframe_percentages(df, percentage_columns):
        """
        Normalize percentage columns in a dataframe
        """
        df_normalized = df.copy()

        for col in percentage_columns:
            if col in df_normalized.columns:
                df_normalized[col] = df_normalized[col].apply(
                    normalize_percentage_field
                )

        return df_normalized

    # Additional helper function for debugging percentage normalization
    def debug_percentage_comparison(df_db, df_excel, percentage_cols):
        """
        Helper function to debug percentage field comparisons
        """
        debug_info = {}

        for col in percentage_cols:
            if col in df_db.columns and col in df_excel.columns:
                debug_info[col] = {
                    "db_original": df_db[col].tolist(),
                    "excel_original": df_excel[col].tolist(),
                    "db_normalized": [
                        normalize_percentage_field(val) for val in df_db[col]
                    ],
                    "excel_normalized": [
                        normalize_percentage_field(val) for val in df_excel[col]
                    ],
                }

        return debug_info

    # index route
    @app.route("/")
    def index():
        return "Welcome to the Trello OneDrive Sync App!"

    @app.route("/compare", methods=["GET"])
    def compare():
        df_db = query_job_releases()
        df_excel = get_excel_dataframe()

        # Normalize columns/types
        common_cols = [col for col in df_db.columns if col in df_excel.columns]
        df_db = df_db[common_cols].fillna("")
        df_excel = df_excel[common_cols].fillna("")

        # Define percentage columns that need normalization
        percentage_cols = [
            col
            for col in common_cols
            if col.lower() in ["invoiced", "job comp", "jobcomp", "job_comp"]
        ]

        # Normalize percentage fields
        if percentage_cols:
            df_db = normalize_dataframe_percentages(df_db, percentage_cols)
            df_excel = normalize_dataframe_percentages(df_excel, percentage_cols)

            # Fill NaN values in percentage columns with empty string for comparison
            for col in percentage_cols:
                if col in df_db.columns:
                    df_db[col] = df_db[col].fillna("")
                if col in df_excel.columns:
                    df_excel[col] = df_excel[col].fillna("")

        # Handle date columns
        date_cols = [
            col
            for col in common_cols
            if "date" in col.lower() or col.lower() in ["released", "comp. eta"]
        ]
        for col in date_cols:
            if col in df_db.columns:
                df_db[col] = df_db[col].astype(str)
            if col in df_excel.columns:
                df_excel[col] = df_excel[col].astype(str)

        # Add source column for tracking
        df_db["source"] = "db"
        df_excel["source"] = "excel"

        # Concatenate and find differences
        combined = pd.concat([df_db, df_excel], ignore_index=True)

        # Find duplicates based on all columns except 'source'
        subset_cols = [col for col in common_cols if col != "source"]
        diff = combined.drop_duplicates(subset=subset_cols, keep=False)

        # For each differing row, show which columns differ
        differences = []
        for _, row in diff.iterrows():
            identifier = {col: row[col] for col in ["Job #", "Release #"] if col in row}
            source = row["source"]

            # Find matching row in the other source
            other_source = "excel" if source == "db" else "db"
            other_row = combined[
                (combined["source"] == other_source)
                & (combined["Job #"] == row.get("Job #"))
                & (combined["Release #"] == row.get("Release #"))
            ]

            diff_cols = []
            if not other_row.empty:
                for col in subset_cols:
                    current_val = row[col]
                    other_val = other_row.iloc[0][col]

                    # Special handling for percentage columns
                    if col in percentage_cols:
                        # Both values should already be normalized
                        if pd.isna(current_val) and pd.isna(other_val):
                            continue  # Both are NaN, consider equal
                        elif pd.isna(current_val) or pd.isna(other_val):
                            diff_cols.append(col)  # One is NaN, other isn't
                        elif (
                            abs(float(current_val or 0) - float(other_val or 0)) > 0.001
                        ):
                            diff_cols.append(col)  # Different values (with tolerance)
                    else:
                        # Regular comparison for non-percentage columns
                        if current_val != other_val:
                            diff_cols.append(col)
            else:
                diff_cols = subset_cols  # All columns differ if no match found

            differences.append(
                {
                    "identifier": identifier,
                    "source": source,
                    "diff_columns": diff_cols,
                    "row": {col: row[col] for col in subset_cols},
                }
            )

        return jsonify(differences)

    # Register blueprints
    app.register_blueprint(trello_bp, url_prefix="/trello")
    app.register_blueprint(onedrive_bp, url_prefix="/onedrive")

    return app
