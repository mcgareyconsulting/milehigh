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

    # index route
    @app.route("/")
    def index():
        return "Welcome to the Trello OneDrive Sync App!"

    # compare route
    @app.route("/compare", methods=["GET"])
    def compare():
        df_db = query_job_releases()
        df_excel = get_excel_dataframe()
        # Normalize columns/types
        common_cols = [col for col in df_db.columns if col in df_excel.columns]
        df_db = df_db[common_cols].fillna("")
        df_excel = df_excel[common_cols].fillna("")

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
                    if row[col] != other_row.iloc[0][col]:
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
