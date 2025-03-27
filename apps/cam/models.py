from datetime import datetime  # 날짜, 시간 라이브러리
import pytz  # 타임존 변환 라이브러리
from apps import db


# # 한국 시간 설정
# KST = pytz.timezone("Asia/Seoul")


# DB 모델 설정하기
# class Cam(db.Model):
#     __tablename__ = "cam"
#     id = db.Column(db.Integer, primary_key=True)
#     cam_name = db.Column(db.String(255), nullable=False)
#     cam_url = db.Column(db.String)
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
    cam_name = db.Column(db.String, nullable=False)
    cam_url = db.Column(db.String, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    is_active = db.Column(
        db.Boolean, default=True
    )  # 활성화 상태를 나타내는 속성 추가, 기본값은 True

    def is_duplicate_url(self):
        return Cams.query.filter_by(cam_url=self.cam_url).first()


class Videos(db.Model):
    __tablename__ = "videos"
    id = db.Column(db.Integer, primary_key=True)
    camera_id = db.Column(db.Integer, db.ForeignKey(Cams.id))
    camera_name = db.Column(db.String, db.ForeignKey(Cams.cam_name))
    recorded_date = db.Column(db.DateTime)
    recorded_time = db.Column(db.Time)
    video_path = db.Column(db.String, unique=True)