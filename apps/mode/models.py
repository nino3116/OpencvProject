from apps.app import db
from datetime import datetime
from apps.cam.models import Cams


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


class PlaceLogs(db.Model):
    __tablename__ = "place_logs"
    idx = db.Column(db.Integer, primary_key=True)
    tp_cnt = db.Column(db.Integer)
    dt_time = db.Column(db.DateTime, default=datetime.now)


class ModeDetected(db.Model):
    __tablename__ = "mode_detected"
    idx = db.Column(db.Integer, primary_key=True)
    mode_type = db.Column(db.Enum("Running", "Cleaning", "Secure"))
    person_reserved = db.Column(db.Integer)
    max_person_detected = db.Column(db.Integer)
    detected_time = db.Column(db.DateTime, default=datetime.now)
    dend_time = db.Column(db.DateTime, default=datetime.now)
    mode_schedule_id = db.Column(db.Integer)
    info = db.Column(db.String(256))


class CameraLogs(db.Model):
    __tablename__ = "camera_logs"
    idx = db.Column(db.Integer, primary_key=True)
    camera_idx = db.Column(db.Integer, db.ForeignKey(Cams.id, name="cam_id"))
    dp_cnt = db.Column(db.String(256))
    detected_time = db.Column(db.DateTime, default=datetime.now)
    plog_idx = db.Column(db.Integer, db.ForeignKey(PlaceLogs.idx, name="plog_id"))
