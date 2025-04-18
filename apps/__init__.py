from flask import Flask, redirect, url_for
from apps.config import config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
import os
from dotenv import load_dotenv
import threading


# 소켓통신을 위해
import socket
import logging
import json

RECOGNITION_MODULE_HOST = "localhost"
RECOGNITION_MODULE_PORT = 8001
RECOGNITION_MODULE_STATUS_PORT = 8002  # 상태 확인용 새 포트

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

    from apps.kakao import views as kakao_views

    app.register_blueprint(kakao_views.kakao, url_prefix="/oauth/kakao")

    @app.route("/")
    def to_index():

        return redirect(url_for("cam.index"))

    @app.context_processor
    def inject_camera_counts():
        from apps.cam.models import Cams

        num_total_cams = Cams.query.count()
        num_active_cams = Cams.query.filter_by(is_active=True).count()
        num_recording_cams = Cams.query.filter_by(is_recording=True).count()
        num_dt_cams = 0
        try:
            with socket.create_connection(
                (RECOGNITION_MODULE_HOST, RECOGNITION_MODULE_STATUS_PORT), timeout=1
            ) as sock:
                data = sock.recv(2048).decode("utf-8")
                data = json.loads(data)
                for v in data:
                    if data[v]["dt_active"] == True:
                        num_dt_cams += 1

        except (ConnectionRefusedError, TimeoutError):
            logging.warning("인식 모듈 연결 끊김 또는 응답 없음 (상태 확인)")
        except:
            pass

        return dict(
            num_total_cams=num_total_cams,
            num_active_cams=num_active_cams,
            num_recording_cams=num_recording_cams,
            num_dt_cams=num_dt_cams,
        )

    # 백그라운드 스레드 시작
    from apps.app import check_cam_periodically

    thread = threading.Thread(target=check_cam_periodically, args=(app,))
    thread.daemon = True  # 메인 프로세스 종료 시 함께 종료
    thread.start()
    logging.info("카메라 상태 확인 스레드 시작")

    return app
