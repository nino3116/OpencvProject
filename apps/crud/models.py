# 날짜 작업을 위해서 사용.
from datetime import datetime

# flask_login내에 UserMixin import
from flask_login import UserMixin

# password_hash 처리를 위한 모듈 import, check_password_hash 추가
from werkzeug.security import check_password_hash, generate_password_hash

# apps.app 모듈에서 db import, 추가 import login_manager
from apps.app import db, login_manager


class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.String(100), nullable=False, unique=True)
    password_hash = db.Column(db.String)
    email = db.Column(db.String(100), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    @property
    def password(self):
        raise AttributeError("읽어 들일 수 없음")

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_duplicate_email(self):
        return User.query.filter_by(email=self.email).first()

    def is_duplicate_user_id(self):
        return User.query.filter_by(user_id=self.user_id).first()


# 로그인하고 있는 사용자 정보를 얻는 함수를 작성
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)
