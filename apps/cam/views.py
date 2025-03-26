from flask import (
    Flask,
    Blueprint,
    render_template,
    Response,
    stream_with_context,
    redirect,
    url_for,
    flash,
    send_from_directory,
    abort,
    request,
    current_app,
)
import cv2 as cv
from ultralytics import YOLO
import sys
import random
import time
from datetime import datetime
from flask_login import login_required
from apps.cam.forms import CameraForm, DeleteCameraForm, DeleteVideoForm
from flask_wtf.csrf import generate_csrf
from apps.cam.models import Cams, Videos
from apps.app import db, app
import os
import multiprocessing
import queue
from pathlib import Path

cam = Blueprint(
    "cam",
    __name__,
    template_folder="templates",
)

process_pool = {}
frame_queues = {}
# recording_status = {} # 더 이상 메인 프로세스에서 관리하지 않음
# video_writers = {} # 더 이상 메인 프로세스에서 관리하지 않음
recording_command_queues = {}  # 카메라별 녹화 명령 큐

now = datetime.now()
now_day = now.strftime("%Y-%m-%d")
now_str = now.strftime("%Y-%m-%d_%H-%M-%S")


def frame_producer(camera_url, camera_name, output_queue, record_command_queue):
    cap = cv.VideoCapture(camera_url)
    if not cap.isOpened():
        print(f"Error: Could not open camera stream for {camera_name}")
        output_queue.put(None)  # 에러 신호
        return

    model = YOLO("yolo11n.pt")
    person_colors = {}
    person_class_id = None
    if hasattr(model, "names"):
        for class_id, class_name in model.names.items():
            if class_name == "person":
                person_class_id = class_id
                break

    if person_class_id is None:
        print("Warning: 'person' class not found in YOLO model.")

    start_time = time.time()
    log_dir = "./apps/logs"
    os.makedirs(log_dir, exist_ok=True, mode=0o777)
    log_file = open(f"{log_dir}/log{now_day}.txt", "a")
    log_file.write(
        f"========Loggin Start for {camera_name} at {datetime.now()}========\n"
    )

    is_recording = False
    video_writer = None

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            log_file.write(
                f"========Stopped Logging for {camera_name} at {datetime.now()} - Frame capture failed========\n"
            )
            break

        # 녹화 명령 처리
        while not record_command_queue.empty():
            command = record_command_queue.get()
            if command == "start":
                if not is_recording:
                    fps = int(cap.get(cv.CAP_PROP_FPS))
                    width = int(cap.get(cv.CAP_PROP_FRAME_WIDTH))
                    height = int(cap.get(cv.CAP_PROP_FRAME_HEIGHT))
                    output_dir = (
                        Path("./apps/static/videos")
                        / now_day
                        / camera_name.replace(" ", "_").lower()
                    )
                    output_path = (
                        output_dir
                        / f"{camera_name.replace(' ', '_').lower()}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.mp4"
                    )
                    fourcc = cv.VideoWriter.fourcc(*"H264")
                    os.makedirs(output_dir, exist_ok=True, mode=0o777)
                    try:
                        video_writer = cv.VideoWriter(
                            output_path, fourcc, fps, (width, height)
                        )
                        is_recording = True
                        print(f"Recording started for {camera_name} at {output_path}")
                        log_file.write(
                            f"Recording started for {camera_name} at {output_path}\n"
                        )
                    except Exception as e:
                        print(f"Error starting recording for {camera_name}: {e}")
                        log_file.write(
                            f"Error starting recording for {camera_name}: {e}\n"
                        )
            elif command == "stop":
                if is_recording:
                    is_recording = False
                    if video_writer:
                        video_writer.release()
                        video_writer = None
                        print(f"Recording stopped for {camera_name}")
                        log_file.write(f"Recording stopped for {camera_name}\n")

        results = model.track(frame, persist=True, verbose=False, conf=0.2)
        person_count = 0
        if results and results[0].boxes:
            boxes = results[0].boxes.xyxy.cpu().numpy().astype(int)
            track_ids = (
                results[0].boxes.id.cpu().numpy().astype(int)
                if results[0].boxes.id is not None
                else []
            )
            classes = results[0].boxes.cls.cpu().numpy().astype(int)

            for i, (x1, y1, x2, y2) in enumerate(boxes):
                if classes[i] == person_class_id:
                    track_id = track_ids[i] if len(track_ids) > 0 else "N/A"
                    if track_id not in person_colors:
                        person_colors[track_id] = (
                            random.randint(0, 255),
                            random.randint(0, 255),
                            random.randint(0, 255),
                        )
                    color = person_colors[track_id]
                    cv.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    label = f"ID: {track_id}"
                    cv.putText(
                        frame,
                        label,
                        (x1, y1 - 10),
                        cv.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        color,
                        2,
                    )
                    person_count += 1

        cv.putText(
            frame,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            (10, 30),
            cv.FONT_HERSHEY_SIMPLEX,
            1,
            color=(255, 255, 255),
        )

        if is_recording and video_writer is not None:
            video_writer.write(frame)

        current_time = time.time()
        this_moment = datetime.now()
        if current_time - start_time >= 60:
            print(
                f"Detected {person_count} persons at {this_moment} on {camera_name}.\n"
            )
            log_file.write(
                f"Detected {person_count} persons at {this_moment} on {camera_name}.\n"
            )
            snapshot_dir = Path("./apps/static/snapshots") / now_day / camera_name
            snapshot_path = snapshot_dir / f"{camera_name}_{now}.jpg"
            os.makedirs(snapshot_dir, exist_ok=True, mode=0o777)
            cv.imwrite(snapshot_path, frame)
            log_file.write(f"snapshot saved to '{snapshot_path}'\n")
            start_time = current_time

        _, buffer = cv.imencode(".jpg", frame)
        frame_bytes = buffer.tobytes()
        output_queue.put(frame_bytes)  # 프레임 데이터를 큐에 전달

    if video_writer:
        video_writer.release()
        print(f"Recording stopped (stream ended) for {camera_name}")
        log_file.write(f"Recording stopped (stream ended) for {camera_name}\n")

    log_file.write(
        f"========Stopped Logging for {camera_name} at {datetime.now()}========\n"
    )
    log_file.close()
    cap.release()
    output_queue.put(None)  # 스트림 종료 신호


def generate_frames_from_queue(output_queue):
    while True:
        frame_bytes = output_queue.get()
        if frame_bytes is None:
            break
        yield (
            b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
        )


@cam.route("/")
@login_required
def index():
    cams = Cams.query.all()
    return render_template("cam/index.html", cams=cams)


@cam.route("/stream/<camera_id>")
@login_required
def camera_stream(camera_id):
    cam_obj = Cams.query.filter_by(id=camera_id).first_or_404()
    camera_name = cam_obj.name
    camera_url = cam_obj.url

    if camera_name not in process_pool:
        frame_queue = multiprocessing.Queue(maxsize=10)  # 큐 크기 제한
        record_command_queue = multiprocessing.Queue()  # 녹화 명령 큐 생성
        process = multiprocessing.Process(
            target=frame_producer,
            args=(camera_url, camera_name, frame_queue, record_command_queue),
        )
        process.daemon = True  # 메인 프로세스 종료 시 함께 종료
        process.start()
        process_pool[camera_name] = process
        frame_queues[camera_name] = frame_queue
        recording_command_queues[camera_name] = record_command_queue
    elif camera_name in frame_queues and frame_queues[camera_name].empty():
        # 프로세스가 살아있지만 큐가 비어있다면 재시작을 고려할 수 있습니다.
        if process_pool[camera_name].is_alive():
            pass  # 아직 처리 중이거나 종료된 상태
        else:
            frame_queue = multiprocessing.Queue(maxsize=10)
            record_command_queue = multiprocessing.Queue()
            process = multiprocessing.Process(
                target=frame_producer,
                args=(camera_url, camera_name, frame_queue, record_command_queue),
            )
            process.daemon = True
            process.start()
            process_pool[camera_name] = process
            frame_queues[camera_name] = frame_queue
            recording_command_queues[camera_name] = record_command_queue

    if camera_name in frame_queues:
        return Response(
            stream_with_context(generate_frames_from_queue(frame_queues[camera_name])),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )
    else:
        return "Error: Could not start camera stream process."


@cam.route("/stream_page/<camera_id>")
def stream_page(camera_id):
    cam_obj = Cams.query.filter_by(id=camera_id).first_or_404()
    camera_name = cam_obj.name
    return render_template(
        "cam/stream.html",
        camera_name=camera_name,
        camera_id=camera_id,
    )


@cam.route("/start_record/<camera_id>")
def start_record(camera_id):
    cam_obj = Cams.query.filter_by(id=camera_id).first_or_404()
    camera_name = cam_obj.name
    camera_name_key = camera_name.replace(" ", "_").lower()

    if camera_name in recording_command_queues:
        recording_command_queues[camera_name].put("start")
        return f"Recording started for {camera_id}"
    else:
        return "Error: Camera stream process not found."


@cam.route("/stop_record/<camera_id>")
def stop_record(camera_id):
    cam_obj = Cams.query.filter_by(id=camera_id).first_or_404()
    camera_name = cam_obj.name
    camera_name_key = camera_name.replace(" ", "_").lower()

    if camera_name in recording_command_queues:
        recording_command_queues[camera_name].put("stop")
        return f"Recording stopped for {camera_id}"
    else:
        return "Error: Camera stream process not found."


@cam.route("/admin/update_videos")
@login_required
def update_videos():
    video_base_dir = Path(current_app.config["VIDEO_FOLDER"])
    if not video_base_dir.exists():
        flash(f"Recorded video directory not found at: {video_base_dir}", "error")
        return redirect(url_for("cam.cameras"))

    cameras = Cams.query.all()
    camera_names_safe = {cam.id: cam.name.replace(" ", "_").lower() for cam in cameras}
    existing_video_paths = {video.video_path: video for video in Videos.query.all()}
    new_videos_count = 0
    updated_videos_count = 0

    for date_dir in video_base_dir.iterdir():
        if date_dir.is_dir():
            for cam_id_int, camera_name_safe in camera_names_safe.items():
                camera_dir = date_dir / camera_name_safe
                if camera_dir.is_dir():
                    for video_file in camera_dir.iterdir():
                        if (
                            video_file.is_file()
                            and video_file.suffix == ".webm"
                            or video_file.suffix == ".mp4"
                            and video_file.stem.startswith(camera_name_safe + "_")
                        ):
                            print(f"Processing file: {video_file.stem}")
                            relative_path = (
                                Path(date_dir.name) / camera_name_safe / video_file.name
                            )
                            video_path_str = relative_path.as_posix()

                            try:
                                parts = video_file.stem.split("_")
                                print(f"Parts: {parts}")
                                recorded_time_str = None
                                recorded_datetime = None
                                if len(parts) > 2:
                                    date_part = parts[-2]
                                    time_part = parts[-1]
                                    try:
                                        recorded_datetime = datetime.strptime(
                                            f"{date_part}_{time_part}",
                                            "%Y-%m-%d_%H-%M-%S",
                                        )
                                        recorded_time_str = recorded_datetime.strftime(
                                            "%Y-%m-%d %H:%M:%S"
                                        )
                                    except ValueError as e:
                                        print(
                                            f"ValueError (combined): {e} for file: {video_file.stem}"
                                        )
                                elif len(parts) > 1:
                                    try:
                                        recorded_datetime = datetime.strptime(
                                            parts[-1], "%Y-%m-%d_%H-%M-%S"
                                        )
                                        recorded_time_str = recorded_datetime.strftime(
                                            "%Y-%m-%d %H:%M:%S"
                                        )
                                    except ValueError as e:
                                        print(
                                            f"ValueError (single): {e} for file: {video_file.stem}"
                                        )

                                print(f"Recorded Time String: {recorded_time_str}")

                                cam = Cams.query.filter_by(id=cam_id_int).first()
                                camera_name = cam.name if cam else "Unknown Camera"

                                if video_path_str in existing_video_paths:
                                    existing_video = existing_video_paths[
                                        video_path_str
                                    ]
                                    updated = False
                                    if existing_video.camera_name != camera_name:
                                        existing_video.camera_name = camera_name
                                        updated = True
                                    if (
                                        (
                                            existing_video.recorded_time
                                            and recorded_time_str
                                            and existing_video.recorded_time.strftime(
                                                "%Y-%m-%d %H:%M:%S"
                                            )
                                            != recorded_time_str
                                        )
                                        or (
                                            existing_video.recorded_time is None
                                            and recorded_time_str is not None
                                        )
                                        or (
                                            existing_video.recorded_time is not None
                                            and recorded_time_str is None
                                        )
                                    ):
                                        try:
                                            existing_video.recorded_time = (
                                                recorded_datetime
                                            )
                                            updated = True
                                        except ValueError as e:
                                            print(
                                                f"Error setting recorded_time: {e} for {video_path_str}"
                                            )
                                    if updated:
                                        updated_videos_count += 1
                                        print(f"Updated video: {video_path_str}")
                                else:
                                    try:
                                        new_video = Videos(
                                            camera_name=camera_name,
                                            recorded_time=recorded_datetime,
                                            video_path=video_path_str,
                                            camera_id=cam_id_int,
                                        )
                                        db.session.add(new_video)
                                        new_videos_count += 1
                                        print(f"Added new video: {video_path_str}")
                                    except Exception as e:
                                        print(
                                            f"Error adding new video {video_path_str}: {e}"
                                        )

                            except Exception as e:
                                flash(
                                    f"Error processing {video_path_str}: {e}",
                                    "error",
                                )

    try:
        print(f"New videos count: {new_videos_count}")
        print(f"Updated videos count: {updated_videos_count}")
        print("Committing changes to the database.")
        db.session.commit()
        flash(
            f"{new_videos_count} new videos found and added, {updated_videos_count} videos updated.",
            "success",
        )
        print("Changes committed successfully.")
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating videos: {e}", "error")
        print(f"Error during commit: {e}")

    return redirect(url_for("cam.video_list"))


@cam.route("/video_list")
@login_required
def video_list():
    videos = Videos.query.all()  # 모든 비디오 정보를 데이터베이스에서 가져옵니다.

    videos_by_date = {}

    for video in videos:
        try:
            # video_path에서 날짜 추출 (저장 형식에 따라 수정 필요)
            parts = video.video_path.split("/")
            if len(parts) >= 3:
                date_dir_name = parts[0]  # 예: '2025-03-24'
                filename = parts[2]
                full_path = video.video_path

                if date_dir_name not in videos_by_date:
                    videos_by_date[date_dir_name] = []

                # 파일명과 전체 경로를 함께 저장하여 템플릿에서 사용하기 편리하게 함
                videos_by_date[date_dir_name].append(
                    {
                        "filename": filename,
                        "path": full_path,
                        "camera_name": video.camera_name,
                    }
                )

        except Exception as e:
            print(f"Error processing video path: {video.video_path} - {e}")

    # 날짜별로 정렬 (최신 날짜가 먼저 오도록)
    sorted_videos_by_date = dict(
        sorted(videos_by_date.items(), key=lambda item: item[0], reverse=True)
    )
    form = DeleteVideoForm()  # 폼 인스턴스 생성
    return render_template(
        "cam/video_list.html",
        videos_by_date=sorted_videos_by_date,
        videos=videos,
        form=form,
    )


@cam.route("/recorded_videos/<int:camera_id>")
@login_required
def recorded_videos(camera_id):
    cam = Cams.query.get_or_404(camera_id)
    videos = Videos.query.filter_by(camera_name=cam.name).all()
    video_list = []
    for video in videos:
        video_list.append(
            {
                "id": video.id,
                "path": video.video_path,
                "recorded_time": (
                    video.recorded_time.strftime("%Y-%m-%d %H:%M:%S")
                    if video.recorded_time
                    else None
                ),
                "camera_name": cam.name,
            }
        )

    form = DeleteVideoForm()
    return render_template(
        "cam/recorded_videos.html", camera_name=cam.name, videos=video_list, form=form
    )


# @cam.route("/play_video_page/<int:camera_id>/<int:video_id>")
# @login_required
# def play_video_page(camera_id, video_id):
#     video = Videos.query.get_or_404(video_id)
#     return render_template(
#         "cam/play_video_page.html", camera_id=camera_id, video_id=video_id, video=video
#     )


@cam.route("/play_video/<int:video_id>")
@login_required
def play_video(video_id):
    video = Videos.query.get_or_404(video_id)
    current_app.logger.info(
        f"Attempting to play video with id: {video_id}, path: {video.video_path}"
    )
    recorded_video_base_dir = Path(current_app.config["VIDEO_FOLDER"])
    current_app.logger.info(f"recorded_video_base_dir: {recorded_video_base_dir}")

    path_obj = Path(video.video_path)
    full_path = recorded_video_base_dir / path_obj
    print(f"Full path: {full_path}")

    if full_path.exists():
        # video_path는 이미 static/videos 폴더를 기준으로 하는 상대 경로이므로
        # url_for('static', filename=...)에 직접 전달할 수 있습니다.
        video_url = url_for(
            "static", filename="videos/" + video.video_path.replace("\\", "/")
        )
        print(f"Video URL: {video_url}")
        return render_template(
            "cam/play_video_page.html", video_path=video_url, video_id=video_id
        )
    else:
        current_app.logger.warning(f"File not found: {full_path}")
        abort(404)


@cam.route("/download_video/<int:video_id>")
@login_required
def download_video(video_id):
    video = Videos.query.get_or_404(video_id)
    current_app.logger.info(
        f"Attempting to download video with id: {video_id}, path: {video.video_path}"
    )
    recorded_video_base_dir = current_app.config["VIDEO_FOLDER"]
    current_app.logger.info(f"recorded_video_base_dir: {recorded_video_base_dir}")

    path_obj = Path(video.video_path)
    full_path = recorded_video_base_dir / path_obj
    current_app.logger.info(f"Full path for download: {full_path}")

    if full_path.exists():
        return send_from_directory(
            current_app.config["VIDEO_FOLDER"],
            video.video_path,
            as_attachment=True,
        )
    else:
        current_app.logger.warning(f"File not found: {full_path}")
        abort(404)


@cam.route("/delete_recorded_video/<int:video_id>", methods=["POST"])
@login_required
def delete_recorded_video(video_id):
    recorded_video_base_dir = Path(current_app.config["VIDEO_FOLDER"])
    try:
        video_record = Videos.query.get_or_404(video_id)
        path_obj = Path(video_record.video_path)
        file_path = recorded_video_base_dir / path_obj
        if file_path.exists():
            file_path.unlink()
            db.session.delete(video_record)
            db.session.commit()
            flash(f"'{file_path.name}' 영상이 삭제되었습니다.", "success")
        else:
            flash("삭제하려는 영상을 찾을 수 없습니다.", "error")
    except Exception as e:
        flash(f"영상 삭제 중 오류가 발생했습니다: {e}", "error")

    camera_id = request.args.get("camera_id")
    if camera_id:
        return redirect(url_for("cam.recorded_videos", camera_id=camera_id))
    else:
        return redirect(url_for("cam.video_list"))


# @cam.route("/get_log")
# def get_log():
#     try:
#         with open(f"log{now_day}.txt", "r") as f:  # 파일 열기 모드를 "r"로 변경
#             log_content = f.read()
#         return log_content.replace("\n", "<br>")
#     except FileNotFoundError:
#         return "Log file not found."


@cam.route("/log_stream")
def log_stream():
    def event_stream():
        last_position = 0
        log_file_path = f"./apps/logs/log{now_day}.txt"  # 로그 파일 경로를 변수로 저장
        while True:
            try:
                with open(log_file_path, "r") as f:  # 파일 열기 모드를 "r"로 변경
                    f.seek(last_position)
                    new_content = f.read()
                    if new_content:
                        escaped_content = new_content.replace("\n", "<br>")
                        yield "data: " + escaped_content + "\n\n"
                        last_position = f.tell()
            except FileNotFoundError:
                yield "data: Log file not found.<br>\n\n"
            except Exception as e:
                yield "data: Error reading log file: " + str(e) + "<br>\n\n"
            time.sleep(1)  # Check for new content every 1 second

    return Response(stream_with_context(event_stream()), mimetype="text/event-stream")


@cam.route("/cameras")
@login_required
def cameras():
    cams = Cams.query.all()
    csrf_token = generate_csrf()
    form = DeleteCameraForm()  # Instantiate the form
    return render_template("cam/cameraDB.html", cams=cams, csrf_token=csrf_token)


@cam.route("/cameras/add", methods=["GET", "POST"])
@login_required
def add_camera():
    form = CameraForm()
    if form.validate_on_submit():
        cam = Cams(name=form.name.data, url=form.url.data)
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


@cam.route("/cameras/<camera_id>/edit", methods=["GET", "POST"])
@login_required
def edit_camera(camera_id):
    form = CameraForm()
    cam = Cams.query.filter_by(id=camera_id).first()

    # form 으로 부터 제출된경우는 사용자를 갱시낳여 사용자의 일람 화면으로 리다이렉트
    if form.validate_on_submit():
        cam.name = form.name.data
        cam.url = form.url.data
        db.session.add(cam)
        db.session.commit()
        return redirect(url_for("cam.cameras"))

    # GET의 경우에는 HTML 반환
    return render_template("cam/editCamera.html", cam=cam, form=form)


@cam.route("/cameras/<camera_id>/delete", methods=["POST"])
@login_required
def delete_camera(camera_id):
    cam = Cams.query.filter_by(id=camera_id).first()
    db.session.delete(cam)
    db.session.commit()
    return redirect(url_for("cam.cameras"))
