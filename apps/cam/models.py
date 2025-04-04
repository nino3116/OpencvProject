from datetime import datetime, date  # 날짜, 시간 라이브러리

# 타임존 변환 라이브러리
import pytz  # type:ignore
from apps import db


# # 한국 시간 설정
# KST = pytz.timezone("Asia/Seoul")


# DB 모델 설정하기
# class Cam(db.Model):
#     __tablename__ = "cam"
#     id = db.Column(db.Integer, primary_key=True)
#     cam_name = db.Column(db.VARCHAR(255), nullable=False)
#     cam_url = db.Column(db.VARCHAR)
#     create_At = db.Column(db.DateTime, default=datetime.datetime.now(KST))
#     update_At = db.Column(
#         db.DateTime,
#         default=datetime.datetime.now(KST),
#         onupdate=datetime.datetime.now(KST),
#     )


#     def is_duplicate_url(self):
#         return Cam.query.filter_by(cam_url=self.cam_url).first()
class Cams(db.Model):
    __tablename__ = "cams"
    id = db.Column(db.Integer, primary_key=True)
    cam_name = db.Column(db.String(255), unique=True, index=True)
    cam_url = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    is_active = db.Column(
        db.Boolean, default=True
    )  # 활성화 상태를 나타내는 속성 추가, 기본값은 True
    videos = db.relationship("Videos", backref="cam", foreign_keys="Videos.camera_id")
    videos_by_name = db.relationship(
        "Videos", backref="cam_by_name", foreign_keys="Videos.camera_name"
    )

    def is_duplicate_url(self):
        return Cams.query.filter_by(cam_url=self.cam_url).first()

    def __repr__(self):
        return f"<Cam {self.cam_name}>"


class Videos(db.Model):
    __tablename__ = "videos"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    camera_id = db.Column(db.Integer, db.ForeignKey("cams.id"))
    camera_name = db.Column(db.String(255), db.ForeignKey("cams.cam_name"))
    recorded_date = db.Column(db.Date)
    recorded_time = db.Column(db.Time)
    video_path = db.Column(db.String(255), unique=True)


class Camera_logs(db.Model):
    __tablename__ = "camera_log_tmp"  # camera_logs => camera_log_tmp 수정flask
    id = db.Column(db.Integer, primary_key=True)
    camera_name = db.Column(db.String(128), nullable=False)
    detection_time = db.Column(db.DateTime, nullable=False, default=datetime.now)
    person_count = db.Column(db.Integer, nullable=False)
    snapshot_path = db.Column(db.String(256), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def __repr__(self):
        return f"<CameraLog {self.camera_name} at {self.detection_time}>"
