# 기업 연계 프로젝트 1

from flask import (
    Blueprint,
    redirect,
    render_template,
    url_for,
    jsonify,
    request,
    flash,
    current_app,
    send_from_directory,
    abort,
)
from flask_wtf.csrf import generate_csrf
from apps import db
from apps.app import (
    db,
    camera_streams,
    record_camera_with_context,
    stop_recording,
    stop_recording_all,
    start_recording_all,
)
from apps.cam.models import Cams, Videos
from apps.cam.forms import CameraForm, DeleteCameraForm, VideoSearchForm, ShutdownForm
from flask_login import login_required  # type: ignore
from pathlib import Path
from datetime import datetime, date, time

from collections import defaultdict
import os
from threading import Thread
import boto3

# from threading import Event

from S3upload.s3client import delete_file, generate_presigned_url
from S3upload.s3_config import BUCKET
import tempfile
import zipfile
from werkzeug.utils import secure_filename
from flask import send_file
from flask_paginate import Pagination, get_page_parameter
from sqlalchemy import and_
import threading
import socket
import logging

# Blueprint로 crud 앱을 생성한다.
cam = Blueprint(
    "cam",
    __name__,
    static_folder="static",
    template_folder="templates",
)


RECOGNITION_MODULE_HOST = "localhost"
RECOGNITION_MODULE_PORT = 8001
RECOGNITION_MODULE_STATUS_PORT = 8002  # 상태 확인용 새 포트

recognition_module_running = False


def check_recognition_module_status():
    """주기적으로 인식 모듈 상태를 확인하는 함수 (수정됨)"""
    global recognition_module_running
    import time

    while True:
        try:
            with socket.create_connection(
                (RECOGNITION_MODULE_HOST, RECOGNITION_MODULE_STATUS_PORT), timeout=1
            ):
                recognition_module_running = True
                logging.info("인식 모듈 연결됨 (상태 확인)")
        except (ConnectionRefusedError, TimeoutError):
            recognition_module_running = False
            logging.warning("인식 모듈 연결 끊김 또는 응답 없음 (상태 확인)")
        time.sleep(5)  # 5초마다 상태 확인


def start_status_check_thread():
    """인식 모듈 상태 확인 스레드 시작 (수정됨)"""
    import time

    time.sleep(2)  # 플라스크 앱 시작 후 2초 정도 대기
    status_check_thread = threading.Thread(
        target=check_recognition_module_status, daemon=True
    )
    status_check_thread.start()


# 플라스크 앱 시작 시 상태 확인 스레드 시작
start_status_check_thread()


@cam.route("/shutdown", methods=["POST"])
def shutdown_module():
    import time

    form = ShutdownForm()
    if form.validate_on_submit():
        if not recognition_module_running:
            logging.warning(
                "인식 모듈이 실행 중이 아닙니다. 종료 신호 전송을 건너뜁니다."
            )
            return "인식 모듈이 실행 중이 아닙니다.", 200  # 또는 다른 적절한 응답

        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(5)  # 연결 시도에 타임아웃 설정
            client_socket.connect((RECOGNITION_MODULE_HOST, RECOGNITION_MODULE_PORT))
            client_socket.sendall(b"shutdown")
            client_socket.close()
            logging.info("인식 모듈 종료 신호 전송 성공")
            return "인식 모듈에 종료 신호를 보냈습니다.", 200
        except ConnectionRefusedError:
            logging.error("인식 모듈의 종료 리스너에 연결할 수 없습니다.")
            return "인식 모듈의 종료 리스너에 연결할 수 없습니다.", 500
        except socket.timeout:
            logging.error("인식 모듈의 종료 리스너 연결 시간 초과.")
            return "인식 모듈의 종료 리스너 연결 시간 초과.", 500
        except Exception as e:
            logging.error(f"인식 모듈 종료 신호 전송 중 오류 발생: {e}")
            return f"인식 모듈 종료 신호 전송 중 오류 발생: {e}", 500
        finally:
            time.sleep(3)
            return redirect(url_for("cam.index"))
    return redirect(url_for("index"))  # 폼 유효성 검사 실패 시 리디렉션


@cam.route("/", methods=["GET", "POST"])
@login_required
def index():
    form = ShutdownForm()
    return render_template(
        "cam/index.html",
        recognition_running=recognition_module_running,
        form=form,
    )


# 새로운 데이터 추가 (AJAX)
@cam.route("/add", methods=["GET", "POST"])
@login_required
def add_camera():
    form = CameraForm()
    if form.validate_on_submit():
        cam = Cams(cam_name=form.cam_name.data, cam_url=form.cam_url.data)
        if cam.is_duplicate_url():
            flash("지정 영상 주소는 이미 등록되어 있습니다.")
            return redirect(url_for("cam.add_camera"))
        db.session.add(cam)
        db.session.commit()
        next_ = request.args.get("next")
        # next가 비어 있거나, "/"로 시작하지 않는 경우 -> 상대경로 접근X.
        if next_ is None or not next_.startswith("/"):
            # next의 값을 엔드포인트 cam.cameras로 지정
            next_ = url_for("cam.cameras")
        # redirect
        return redirect(next_)
    return render_template("cam/addCamera.html", form=form)


@cam.route("/<camera_id>/edit", methods=["GET", "POST"])
@login_required
def edit_camera(camera_id):
    form = CameraForm()
    cam = Cams.query.filter_by(id=camera_id).first()

    # form 으로 부터 제출된경우는 사용자를 갱신하여 사용자의 일람 화면으로 리다이렉트
    if form.validate_on_submit():
        cam.cam_name = form.cam_name.data
        cam.cam_url = form.cam_url.data
        db.session.add(cam)
        db.session.commit()
        return redirect(url_for("cam.cameras"))

    # GET의 경우에는 HTML 반환
    return render_template("cam/editCamera.html", cam=cam, form=form)


@cam.route("/<camera_id>/delete", methods=["POST"])
@login_required
def delete_camera(camera_id):
    cam = Cams.query.filter_by(id=camera_id).first()
    db.session.delete(cam)
    db.session.commit()
    return redirect(url_for("cam.cameras"))


@cam.route("/cameras")
@login_required
def cameras():
    cams = Cams.query.all()
    csrf_token = generate_csrf()
    form = DeleteCameraForm()  # Instantiate the form
    return render_template(
        "cam/cameraDB.html", cams=cams, csrf_token=csrf_token, form=form
    )


@cam.route("/live")
def live():
    from apps.app import camera_streams  # 순환 참조 방지

    cams = Cams.query.all()
    return render_template("cam/live.html", cams=cams)


@cam.route("/status")
def cam_status():
    from apps.app import camera_streams  # 순환 참조 방지

    cams = Cams.query.all()
    # recording_status = {cam.cam_name: cam.cam_name in camera_streams for cam in cams}
    return render_template("cam/cam_status.html", cams=cams)


@cam.route("/start_record/<int:camera_id>")
@login_required
def start_record(camera_id):
    cam_info = Cams.query.get(camera_id)
    if cam_info:
        app = current_app._get_current_object()
        if not cam_info.is_recording:  # 이미 녹화 중이 아닌 경우에만 시작
            recording_thread = Thread(
                target=record_camera_with_context,
                args=(app, cam_info.cam_url, cam_info.id),
                daemon=True,
            )
            recording_thread.start()
            cam_info.is_recording = True
            camera_streams[cam_info.id] = recording_thread
            print(f"camera_streams (start): {camera_streams}")
            db.session.commit()
            print(f"카메라 '{cam_info.cam_name}' 녹화 시작 요청됨.")
        else:
            print(f"카메라 '{cam_info.cam_name}'은 이미 녹화 중입니다.")
    return redirect(url_for("cam.cam_status"))


@cam.route("/stop_record/<int:camera_id>")
@login_required
def stop_record_route(camera_id):
    stop_recording(camera_id)
    return redirect(url_for("cam.cam_status"))


@cam.route("/stop_all_records")
@login_required
def stop_all_records_route():
    print(f"camera_streams (stop all): {camera_streams}")
    stop_recording_all()
    return redirect(url_for("cam.cam_status"))


@cam.route("/start_all_records")
@login_required
def start_all_records_route():
    start_recording_all()
    print(f"camera_streams (start all): {camera_streams}")
    return redirect(url_for("cam.cam_status"))


@cam.route("/video/<path:filename>")
@login_required
def serve_video(filename):
    return send_from_directory(current_app.config["VIDEO_FOLDER"], filename)


@cam.route("/dt_video/<path:filename>")
@login_required
def serve_dt_video(filename):
    return send_from_directory(current_app.config["DT_VIDEO_FOLDER"], filename)


@cam.route("/play_video/<int:video_id>")
@login_required
def play_video(video_id):
    video = Videos.query.get_or_404(video_id)
    current_app.logger.info(
        f"Attempting to play video with id: {video_id}, path: {video.video_path}"
    )

    if video.is_dt:
        recorded_video_base_dir = Path(current_app.config["DT_VIDEO_FOLDER"])
    else:
        recorded_video_base_dir = Path(current_app.config["VIDEO_FOLDER"])

    current_app.logger.info(f"recorded_video_base_dir: {recorded_video_base_dir}")

    path_obj = Path(video.video_path)
    full_path = recorded_video_base_dir / path_obj
    print(f"Full path: {full_path}")

    try:
        if not full_path.exists():
            flash(f"비디오 파일을 찾을 수 없습니다: {full_path}", "play_error")
            return redirect(url_for("cam.list_videos"))
        if video.is_dt:
            video_url = url_for(
                "cam.serve_dt_video", filename=video.video_path.replace("\\", "/")
            )
        else:
            video_url = url_for(
                "cam.serve_video", filename=video.video_path.replace("\\", "/")
            )
        if video.is_dt:
            video_url = url_for(
                "cam.serve_dt_video", filename=video.video_path.replace("\\", "/")
            )
        else:
            video_url = url_for(
                "cam.serve_video", filename=video.video_path.replace("\\", "/")
            )
        print(f"Video URL: {video_url}")
        return render_template(
            "cam/play_video_page.html", video_path=video_url, video_id=video_id
        )
    except Exception as e:
        current_app.logger.error(
            f"비디오 재생 중 오류 발생 (ID: {video_id}, 경로: {video.video_path}): {e}"
        )
        flash(f"비디오 재생 중 오류가 발생했습니다: {e}", "play_error")
        return redirect(url_for("cam.list_videos"))


@cam.route("/play_origin_video/<int:video_id>")
@login_required
def play_origin_video(video_id):
    """특정 ID의 비디오 파일을 S3에서 재생할 수 있는 presigned URL을 생성하고 템플릿에 전달합니다."""
    video = Videos.query.get_or_404(video_id)
    s3_key = video.video_path

    try:
        presigned_url = generate_presigned_url(s3_key)
        if presigned_url:
            current_app.logger.info(
                f"Generated S3 presigned URL for playback: {presigned_url}"
            )
            return render_template(
                "cam/play_video_page.html", video_path=presigned_url, video_id=video_id
            )
        else:
            flash("재생 URL 생성에 실패했습니다.", "play_error")
            return redirect(url_for("cam.list_videos"))
    except Exception as e:
        current_app.logger.error(
            f"S3 비디오 재생 중 오류 발생 (ID: {video_id}, 경로: {video.video_path}): {e}"
        )
        flash(f"비디오 재생 중 오류가 발생했습니다: {e}", "play_error")
        return redirect(url_for("cam.list_videos"))


# @cam.route("/videos", methods=["GET", "POST"])
# @login_required
# def list_videos():
#     """저장된 비디오 목록을 보여주는 페이지 (날짜/녹화시간 순)"""
#     form = VideoSearchForm(request.form)

#     # 카메라 이름 목록을 가져와 choices 설정
#     camera_names = sorted(list(set(video.camera_name for video in Videos.query.all())))
#     form.camera_name.choices = [("", "전체")] + [(name, name) for name in camera_names]

#     # 녹화 날짜 내에서 녹화 시간으로 정렬하여 비디오 목록 가져오기
#     videos = Videos.query.order_by(
#         Videos.recorded_date.desc(), Videos.recorded_time
#     ).all()

#     if form.validate_on_submit():
#         search_camera_name = form.camera_name.data
#         search_date = form.date.data

#         filtered_videos = []
#         for video in videos:
#             match_camera = True
#             if search_camera_name and search_camera_name != "전체":
#                 if search_camera_name.lower() not in video.camera_name.lower():
#                     match_camera = False

#             match_date = True
#             if search_date:
#                 if isinstance(search_date, str):
#                     try:
#                         search_date_obj = datetime.strptime(
#                             search_date, "%Y-%m-%d"
#                         ).date()
#                         if (
#                             not video.recorded_date
#                             or video.recorded_date.date() != search_date_obj
#                         ):
#                             match_date = False
#                     except ValueError:
#                         flash("잘못된 날짜 형식입니다. (YYYY-MM-DD)", "error")
#                         match_date = False
#                 elif isinstance(search_date, date):
#                     if not video.recorded_date or video.recorded_date != search_date:
#                         match_date = False

#             if match_camera and match_date:
#                 filtered_videos.append(video)

#         videos = filtered_videos

#     grouped_videos = defaultdict(list)  # 카메라 이름별 그룹화 제거
#     for video in videos:
#         if video.recorded_date:
#             date_str = video.recorded_date.strftime("%Y-%m-%d")
#             grouped_videos[date_str].append(video)

#         else:
#             grouped_videos["알 수 없는 날짜"].append(video)


#     return render_template(
#         "cam/videoList.html",
#         grouped_videos=grouped_videos,
#         form=form,
#     )
@cam.route("/videos", methods=["GET", "POST"])
@login_required
def list_videos():
    """저장된 비디오 목록을 보여주는 페이지 (날짜/녹화시간 순)"""
    form = VideoSearchForm(request.form)

    # 카메라 이름 목록을 가져와 choices 설정
    camera_names = sorted(list(set(video.camera_name for video in Videos.query.all())))
    form.camera_name.choices = [("", "전체")] + [(name, name) for name in camera_names]

    page = request.args.get(get_page_parameter(), type=int, default=1)
    per_page = 20  # 한 페이지에 보여줄 개수

    # 기본 쿼리 구성
    query = Videos.query.order_by(Videos.recorded_date.desc(), Videos.recorded_time)

    if form.validate_on_submit():
        conditions = []

        # 카메라 이름으로 필터링
        if form.camera_name.data and form.camera_name.data != "전체":
            query = query.filter(Videos.camera_name.ilike(f"%{form.camera_name.data}%"))

        # 날짜 범위로 필터링
        start_date = form.start_date.data
        end_date = form.end_date.data

        if start_date and end_date:
            query = query.filter(Videos.recorded_date.between(start_date, end_date))
        elif start_date:
            query = query.filter(Videos.recorded_date >= start_date)
        elif end_date:
            query = query.filter(Videos.recorded_date <= end_date)

    # 페이지네이션 적용 (필터링된 쿼리 사용)
    total = query.count()
    videos = query.offset((page - 1) * per_page).limit(per_page).all()
    pagination = Pagination(
        page=page,
        total=total,
        per_page=per_page,
        record_name="videos",
        css_framework="bootstrap5",
    )

    grouped_videos = defaultdict(list)
    for video in videos:
        if video.recorded_date:
            date_str = video.recorded_date.strftime("%Y-%m-%d")
        else:
            date_str = "알 수 없는 날짜"
        grouped_videos[date_str].append(video)

    return render_template(
        "cam/videoList.html",
        grouped_videos=grouped_videos,
        pagination=pagination,
        form=form,
    )


@cam.route("/delete_video/<int:video_id>", methods=["POST"])
@login_required
def delete_video(video_id):
    """특정 ID의 비디오를 삭제하는 기능"""
    video = Videos.query.get_or_404(video_id)
    file_path = os.path.join(
        current_app.config["VIDEO_FOLDER"],
        video.video_path.replace("apps/videos/", ""),
    )
    filename = video.video_path.split("/")[-1].split("\\")[-1]  # 파일 이름 추출
    s3_filename = video.video_path
    try:
        db.session.delete(video)
        db.session.commit()
        delete_file(s3_filename)
        flash(
            f"'{filename}' 파일이 삭제되었습니다.", "success"
        )  # 추출한 파일 이름 사용
    except FileNotFoundError:
        db.session.delete(video)
        db.session.commit()
        flash(
            f"데이터베이스에서 '{filename}' 정보를 삭제했습니다. 파일이 존재하지 않습니다.",
            "warning",
        )  # 추출한 파일 이름 사용
    except Exception as e:
        flash(
            f"'{filename}' 파일 삭제 중 오류가 발생했습니다: {e}", "danger"
        )  # 추출한 파일 이름 사용
        db.session.rollback()
    return redirect(url_for("cam.list_videos"))


@cam.route("/delete_selected_videos", methods=["POST"])
@login_required
def delete_selected_videos():
    video_ids = request.form.getlist("video_ids")
    deleted, warnings, errors = [], [], []

    for vid in video_ids:
        video = Videos.query.get(vid)
        if not video:
            warnings.append(f"ID {vid} 없음")
            continue

        file_path = os.path.join(
            current_app.config["VIDEO_FOLDER"],
            video.video_path.replace("apps/videos/", ""),
        )
        filename = os.path.basename(file_path)

        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            else:
                warnings.append(f"{filename} 파일 없음")
            delete_file(video.video_path)
            db.session.delete(video)
            deleted.append(filename)
        except Exception as e:
            db.session.rollback()
            errors.append(str(e))

    db.session.commit()

    if deleted:
        flash(f"{len(deleted)}개 파일 삭제 완료", "success")
    if warnings:
        flash(f"경고: {len(warnings)}개 파일 없음", "warning")
    if errors:
        flash(f"오류 발생: {len(errors)}개", "danger")

    return redirect(url_for("cam.list_videos"))


@cam.route("/download_video/<int:video_id>")
@login_required
def download_video(video_id):
    """특정 ID의 비디오 파일을 S3에서 다운로드할 수 있는 presigned URL을 생성하고 리다이렉트합니다."""
    video = Videos.query.get_or_404(video_id)
    s3_key = video.video_path

    try:
        presigned_url = generate_presigned_url(s3_key)
        if presigned_url:
            current_app.logger.info(
                f"Generated S3 presigned URL for download: {presigned_url}"
            )
            return redirect(presigned_url)
        else:
            flash("다운로드 URL 생성에 실패했습니다.", "error")
            return redirect(url_for("cam.list_videos"))
    except Exception as e:
        flash(f"다운로드 오류: {e}", "error")
        return redirect(url_for("cam.list_videos"))


@cam.route("/download_selected_videos", methods=["POST"])
@login_required
def download_selected_videos():
    """선택된 ID의 비디오 파일을 압축파일로 다운로드 합니다."""
    video_ids = request.form.getlist("video_ids")

    # 아무것도 선택 안 하면 warning flash 후 redirect
    if not video_ids:
        flash("선택된 비디오가 없습니다.", "warning")
        return redirect(url_for("cam.list_videos"))

    s3 = boto3.client("s3")
    bucket_name = BUCKET

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_zip:
        with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
            for vid in video_ids:
                video = Videos.query.get(vid)
                if not video:
                    continue
                s3_key = video.video_path
                filename = secure_filename(s3_key.split("/")[-1])

                # s3 객체 다운로드 -> 메모리에 저장
                obj = s3.get_object(Bucket=bucket_name, Key=s3_key)
                zipf.writestr(filename, obj["Body"].read())

        tmp_zip_path = tmp_zip.name

    # send_file로 zip 전송 (다운로드 시작)

    return send_file(
        tmp_zip_path,
        mimetype="application/zip",
        as_attachment=True,
        download_name="selected_videos.zip",
    )
