from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Job(db.Model):
    __tablename__ = "job_releases"
    id = db.Column(db.Integer, primary_key=True)
    job = db.Column(db.Integer, nullable=False)
    release = db.Column(db.Integer, nullable=False)
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
    ship_start = db.Column(db.String(8))
    install = db.Column(db.String(8))
    comp_eta = db.Column(db.String(16))
    job_comp = db.Column(db.String(8))
    invoiced = db.Column(db.String(8))
    notes = db.Column(db.String(256))

    def __repr__(self):
        return f"<Job {self.job} - {self.release} - {self.job_name}>"
