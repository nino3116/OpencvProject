from apps.app import db
from datetime import datetime


class ModeSchedule(db.Model):
    __tablename__ = "mode_schedule"
    id = db.Column(db.Integer, primary_key=True)
    mode_type = db.Column(db.Enum("Running", "Cleaning", "Secure"), nullable=False)
    people_cnt = db.Column(db.Integer)
    rep_name = db.Column(db.String(256))
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    memo = db.Column(db.String(256), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)