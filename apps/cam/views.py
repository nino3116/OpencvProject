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
)
from flask_wtf.csrf import generate_csrf
from apps import db
from apps.app import (
    start_recording_all,
    record_camera,
    stop_recording,
    stop_recording_all,
    recording_status,
    camera_streams,
)
from apps.cam.models import Cams, Videos
from apps.cam.forms import CameraForm, DeleteCameraForm
from flask_login import login_required  # type: ignore
import datetime
import os


# Blueprint로 crud 앱을 생성한다.
cam = Blueprint(
    "cam",
    __name__,
    static_folder="static",
    template_folder="templates",
)


@cam.route("/")
@login_required
def index():
    cams = Cams.query.all()
    return render_template("cam/index.html", cams=cams)


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

    # form 으로 부터 제출된경우는 사용자를 갱시낳여 사용자의 일람 화면으로 리다이렉트
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
    return render_template("cam/cameraDB.html", cams=cams, csrf_token=csrf_token)


@cam.route("/live")
def live():
    cams = Cams.query.all()
    return render_template(
        "cam/live.html", cams=cams, recording_status=recording_status
    )


@cam.route("/status")
def cam_status():
    cams = Cams.query.all()
    return render_template(
        "cam/cam_status.html", cams=cams, recording_status=recording_status
    )


IMAGE_SAVE_PATH = "capture_images"
if not os.path.exists(IMAGE_SAVE_PATH):
    os.mkdir(IMAGE_SAVE_PATH)


# 파일 저장 함수 (이미지 캡처)
def save_image(cam_id):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"cam_{cam_id}_{timestamp}.jpg"
    filepath = os.path.join(IMAGE_SAVE_PATH, filename)

    # 더미 이미지 생성 (실제 환경에서는 캡처된 이미지 저장)
    with open(filepath, "wb") as f:
        f.write(os.urandom(1024))  # 임의의 데이터를 넣어 더미 이미지 생성

    print(f"이미지 저장됨: {filepath}")


@cam.route("/start_record/<camera_name>")
def start_record(camera_name):
    cam_info = Cams.query.filter_by(cam_name=camera_name).first()
    if cam_info:
        record_camera(cam_info.cam_url, cam_info.cam_name)
    return redirect(url_for("cam.cam_status"))


@cam.route("/stop_record/<camera_name>")
def stop_record_route(camera_name):
    stop_recording(camera_name)
    return redirect(url_for("cam.cam_status"))


@cam.route("/stop_all_records")
def stop_all_records():
    stop_recording_all()
    return redirect(url_for("cam.cam_status"))


@cam.route("/start_all_records")
def start_all_records():
    start_recording_all()
    return redirect(url_for("cam.cam_status"))


@cam.route("/videos")
def list_videos():
    """저장된 비디오 목록을 보여주는 페이지"""
    videos = Videos.query.all()
    return render_template("cam/videoList.html", videos=videos)


@cam.route("/update_videos")
def update_videos():
    video_folder = current_app.config["VIDEO_FOLDER"]
    updated_count = 0
    added_count = 0

    for root, _, files in os.walk(video_folder):
        for filename in files:
            if filename.endswith(".mp4"):
                file_path = os.path.join(root, filename)
                parts = filename.replace(".mp4", "").split("_")
                if len(parts) == 2:
                    camera_name = parts[0]
                    timestamp_str = parts[1]
                    try:
                        recorded_datetime = datetime.strptime(
                            timestamp_str, "%Y%m%d_%H%M%S"
                        )
                        recorded_date = recorded_datetime.date()
                        recorded_time = recorded_datetime.time()

                        cam = Cams.query.filter_by(cam_name=camera_name).first()
                        if cam:
                            existing_video = Videos.query.filter_by(
                                video_path=file_path
                            ).first()
                            if existing_video:
                                # 정보 갱신 (필요하다면)
                                existing_video.camera_id = cam.id
                                existing_video.camera_name = camera_name
                                existing_video.recorded_date = recorded_date
                                existing_video.recorded_time = recorded_time
                                db.session.commit()
                                updated_count += 1
                            else:
                                new_video = Videos(
                                    camera_id=cam.id,
                                    camera_name=camera_name,
                                    recorded_date=recorded_date,
                                    recorded_time=recorded_time,
                                    video_path=file_path,
                                )
                                db.session.add(new_video)
                                db.session.commit()
                                added_count += 1
                    except ValueError as e:
                        print(f"Error parsing filename: {filename} - {e}")

    print(f"비디오 스캔 완료: {added_count}개 추가됨, {updated_count}개 업데이트됨.")
    return redirect(url_for("cam.list_videos"))
