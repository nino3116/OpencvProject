# 기업 연계 프로젝트 1
from flask import Flask, render_template

# flask-login에 있는 LoginManager를 import
from flask_login import LoginManager

# 마이그레이션 작업을 위해
from flask_migrate import Migrate  # type: ignore

# SQL작업을 위해
from flask_sqlalchemy import SQLAlchemy

# config 모듈을 import
from apps.config import config

# flask-wtf 모듈의 CSRFProtect import
from flask_wtf.csrf import CSRFProtect  # type: ignore

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
migrate = Migrate()


# create_app 함수 작성
def create_app(config_key):
    # 플라스크 인스턴스 생성
    app = Flask(__name__)

    # app에 config 설정
    # app에 config 설정- from_object를 이용
    app.config.from_object(config[config_key])

    # SQLAlchemy와 앱 연계
    db.init_app(app)
    # Migrate와 앱 연계
    Migrate(app, db)

    # csrf 앱 연계
    csrf.init_app(app)

    # login_manager를 app과 연계(*)
    login_manager.init_app(app)

    from apps.crud import views as crud_views

    app.register_blueprint(crud_views.crud, url_prefix="/crud")

    from apps.auth import views as auth_views

    app.register_blueprint(auth_views.auth, url_prefix="/auth")

    return app
