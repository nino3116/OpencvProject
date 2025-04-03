from flask import Flask, redirect, url_for
from apps.config import config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
import os
from dotenv import load_dotenv

db = SQLAlchemy()
csrf = CSRFProtect()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = ""


def create_app(config_key):
    app = Flask(__name__)
    app.config.from_object(config[config_key])

    db.init_app(app)
    Migrate(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    from apps.crud import views as crud_views

    app.register_blueprint(crud_views.crud, url_prefix="/crud")

    from apps.auth import views as auth_views

    app.register_blueprint(auth_views.auth, url_prefix="/auth")

    from apps.cam import views as cam_views

    app.register_blueprint(cam_views.cam, url_prefix="/cam")
    
    from apps.mode import views as mode_views

    app.register_blueprint(mode_views.mode, url_prefix="/mode")

    @app.route("/")
    def to_index():
        return redirect(url_for("cam.index"))

    # start_recording_all 함수를 create_app 내에서 호출
    with app.app_context():
        from apps.app import start_recording_all

        # print("create_app 내부에서 start_recording_all 호출 시도")
        # start_recording_all()
        # print("create_app 내부에서 start_recording_all 호출 완료")

    return app
