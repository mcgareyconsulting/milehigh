import pandas as pd
from app.models import db, Job


def to_date(val):
    if pd.isnull(val):
        return None
    dt = pd.to_datetime(val)
    return dt.date() if not pd.isnull(dt) else None


def seed_job_releases_from_df(df):
    for _, row in df.iterrows():
        jr = Job(
            job=row["Job #"],
            release=row["Release #"],
            job_name=row["Job"],
            description=row.get("Description"),
            fab_hrs=row.get("Fab Hrs"),
            install_hrs=row.get("Install HRS"),
            paint_color=row.get("Paint color"),
            pm=row.get("PM"),
            by=row.get("BY"),
            released=to_date(row.get("Released")),
            fab_order=row.get("Fab Order"),
            cut_start=row.get("Cut start"),
            fitup_comp=row.get("Fitup comp"),
            welded=row.get("Welded"),
            paint_comp=row.get("Paint Comp"),
            ship_start=row.get("Ship Start"),
            install=row.get("install"),
            comp_eta=to_date(row.get("Comp. ETA")),
            job_comp=row.get("Job Comp"),
            invoiced=row.get("Invoiced"),
            notes=row.get("Notes"),
        )
        db.session.add(jr)
    db.session.commit()
