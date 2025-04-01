# 기업 연계 프로젝트 1

from datetime import datetime

# flask-login 내에 UserMixin 을 import
from flask_login import UserMixin  # type: ignore

# password_hash 처리를 위한 모듈 import, check_password_hash 추가
from werkzeug.security import check_password_hash, generate_password_hash

# apps.app 모듈에서 db import, 추가 import login_manager
from apps import db, login_manager


# db.model을 상속한 User 클래스 상속, 더하여 UserMixin 상속
class User(db.Model, UserMixin):
    # 테이블명을 지정한다.
    __tablename__ = "users"
    # 컬럼 정의
    id = db.Column(db.Integer, primary_key=True)  # primary_key 속성 부여
    username = db.Column(db.String(100), index=True)  # index 색인
    user_id = db.Column(db.String(100), nullable=False, unique=True)
    email = db.Column(db.String(255), index=True, unique=True)  # unique, index 설정
    password_hash = db.Column(db.String(255))
    is_kakao = db.Column(db.Boolean, default=False)
    created_at = db.Column(
        db.DateTime, default=datetime.now
    )  # default는 기본값(현재시간)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    # onupdate는 데이터를 수정할때마다 시간이 업데이트될 수 있게

    # backref를 이용하여 릴레이션 정보를 설정한다.
    # user_images = db.relationship("UserImage", backref="user", order_by="desc(UserImage.id)")

    # 비밀번호를 설정하기 위한 프로퍼티
    @property
    def password(self):
        raise AttributeError("읽어 들일 수 없음")  # raise 예외발생시키는 것

    # 비밀번호 설정하기 위해 setter 함수로 해시화한 비밀번호를 설정한다.
    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    # 비밀번호 체크(패스워드 확인)
    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    # # 이메일 주소 중복 체크
    # def is_duplicate_email(self):
    #     return User.query.filter_by(email=self.email).first()
    def is_duplicate_user_id(self):
        return User.query.filter_by(user_id=self.user_id).first()

    # 로그인하고 있는 사용자 정보를 얻는 함수를 작성
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(user_id)
