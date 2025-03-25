import datetime  # 날짜, 시간 라이브러리
import pytz  # 타임존 변환 라이브러리
from apps.app import db

# 한국 시간 설정
KST = pytz.timezone("Asia/Seoul")


# DB 모델 설정하기
class Cam(db.Model):
    __tablename__ = "cam"
    id = db.Column(db.Integer, primary_key=True)
    cam_name = db.Column(db.String(255), nullable=False)
    cam_url = db.Column(db.String)
    create_At = db.Column(db.DateTime, default=datetime.datetime.now(KST))
    update_At = db.Column(
        db.DateTime,
        default=datetime.datetime.now(KST),
        onupdate=datetime.datetime.now(KST),
    )

    def is_duplicate_url(self):
        return Cam.query.filter_by(cam_url=self.cam_url).first()
