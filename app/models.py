from flask_sqlalchemy import SQLAlchemy
import pandas as pd

db = SQLAlchemy()


class Job(db.Model):
    __tablename__ = "jobs"
    __table_args__ = (db.UniqueConstraint("job", "release", name="_job_release_uc"),)
    id = db.Column(db.Integer, primary_key=True)
    # Job # and Release # for identifiers
    job = db.Column(db.Integer, nullable=False)
    release = db.Column(db.Integer, nullable=False)

    # Excel columns
    job_name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.String(256))
    fab_hrs = db.Column(db.Float)
    install_hrs = db.Column(db.Float)
    paint_color = db.Column(db.String(64))
    pm = db.Column(db.String(16))
    by = db.Column(db.String(16))
    released = db.Column(db.Date)
    fab_order = db.Column(db.Float)
    cut_start = db.Column(db.String(8))
    fitup_comp = db.Column(db.String(8))
    welded = db.Column(db.String(8))
    paint_comp = db.Column(db.String(8))
    ship = db.Column(db.String(8))  # Changed from ship_start to ship
    start_install = db.Column(
        db.Date
    )  # Changed from install to start_install and Date type
    comp_eta = db.Column(db.Date)  # Changed from String to Date
    job_comp = db.Column(db.String(8))
    invoiced = db.Column(db.String(8))
    notes = db.Column(db.String(256))

    # Trello fields
    trello_card_id = db.Column(db.String(64), unique=True, nullable=True)
    trello_card_name = db.Column(db.String(256), nullable=True)
    trello_list_name = db.Column(db.String(128), nullable=True)
    trello_card_description = db.Column(db.String(512), nullable=True)
    trello_card_date = db.Column(db.Date, nullable=True)
    trello_card_labels = db.Column(db.String(256), nullable=True)

    def __repr__(self):
        return f"<Job {self.job} - {self.release} - {self.job_name}>"


def query_job_releases():
    results = Job.query.all()
    return pd.DataFrame(
        [
            {
                "Job #": r.job,
                "Release #": r.release,
                "Job": r.job_name,
                "Description": r.description,
                "Fab Hrs": r.fab_hrs,
                "Install HRS": r.install_hrs,
                "Paint color": r.paint_color,
                "PM": r.pm,
                "BY": r.by,
                "Released": r.released,
                "Fab Order": r.fab_order,
                "Cut start": r.cut_start,
                "Fitup comp": r.fitup_comp,
                "Welded": r.welded,
                "Paint Comp": r.paint_comp,
                "Ship": r.ship,  # Updated field name
                "Start install": r.start_install,  # Updated field name
                "Comp. ETA": r.comp_eta,
                "Job Comp": r.job_comp,
                "Invoiced": r.invoiced,
                "Notes": r.notes,
            }
            for r in results
        ]
    )
