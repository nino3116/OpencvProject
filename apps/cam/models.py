from apps.app import db
from datetime import datetime


class Cams(db.Model):
    __tablename__ = "cams"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    group = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def is_duplicate_url(self):
        return Cams.query.filter_by(url=self.url).first()
