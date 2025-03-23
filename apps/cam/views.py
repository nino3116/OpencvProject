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
from apps.cam.forms import CameraForm, DeleteCameraForm
from flask_wtf.csrf import generate_csrf
from apps.cam.models import Cams
from apps.app import db
import os
import multiprocessing
import queue

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
    log_file = open(f"log{now_day}.txt", "a")
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
                    output_dir = f"./recordedVideo/{now_day}/{camera_name.replace(' ', '_').lower()}/"
                    output_path = f"{output_dir}{camera_name.replace(' ', '_').lower()}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.mp4"
                    fourcc = cv.VideoWriter.fourcc(*"mp4v")
                    os.makedirs(output_dir, exist_ok=True)
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
            snapshot_dir = f"./snapshot/{now_day}/{camera_name}/"
            snapshot_path = f"{snapshot_dir}{camera_name}_{now}.jpg"
            os.makedirs(snapshot_dir, exist_ok=True)
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


@cam.route("/video_list")
@login_required
def video_list():
    video_base_dir = "./recordedVideo/"
    if not os.path.exists(video_base_dir):
        return "No recorded videos found."

    date_directories = [
        d
        for d in os.listdir(video_base_dir)
        if os.path.isdir(os.path.join(video_base_dir, d))
    ]
    date_directories.sort(reverse=True)  # Sort by date, newest first

    videos_by_date = {}
    for date_dir in date_directories:
        video_dir = os.path.join(video_base_dir, date_dir)
        video_files = [f for f in os.listdir(video_dir) if f.endswith(".mp4")]
        if video_files:
            videos_by_date[date_dir] = video_files

    return render_template("cam/video_list.html", videos_by_date=videos_by_date)


@cam.route("/recorded_videos/<camera_id>")
@login_required
def recorded_videos(camera_id):
    cam_obj = Cams.query.filter_by(id=camera_id).first_or_404()
    camera_name_safe = cam_obj.name.replace(" ", "_").lower()
    recorded_video_base_dir = "./recordedVideo"
    video_list = []

    for date_dir in os.listdir(recorded_video_base_dir):
        date_path = os.path.join(recorded_video_base_dir, date_dir)
        if os.path.isdir(date_path):
            camera_dir_path = os.path.join(date_path, camera_name_safe)
            if os.path.isdir(camera_dir_path):
                for video_file in os.listdir(camera_dir_path):
                    if video_file.endswith(".mp4") and video_file.startswith(
                        f"{camera_name_safe}_"
                    ):
                        video_path = os.path.join(
                            date_dir, camera_name_safe, video_file
                        ).replace(
                            "\\", "/"
                        )  # 슬래시로 변경
                        video_list.append(
                            {
                                "filename": video_file,
                                "path": video_path,
                                "camera_name": cam_obj.name,
                                "camera_id": camera_id,
                                "date": date_dir,
                            }
                        )

    form = DeleteCameraForm()  # Instantiate the delete form
    return render_template(
        "cam/recorded_videos.html",
        camera_name=cam_obj.name,
        videos=video_list,
        form=form,
    )


@cam.route("/play_video_page/<camera_id>/<path:path>")
@login_required
def play_video_page(path, camera_id):
    return render_template("cam/play_video.html", video_path=path, camera_id=camera_id)


@cam.route("/play_video/<path:path>")
@login_required
def play_video(path):
    current_app.logger.info(f"Attempting to play video with path: {path}")
    recorded_video_base_dir = "./recordedVideo"
    current_app.logger.info(f"recorded_video_base_dir: {recorded_video_base_dir}")

    path = path.replace("\\", "/")
    parts = path.split("/")
    current_app.logger.info(f"Path split into: {parts}")

    if len(parts) == 3:
        date_dir = parts[0]
        camera_dir = parts[1]
        filename = parts[2]
        full_path = os.path.join(
            recorded_video_base_dir, date_dir, camera_dir, filename
        )
        current_app.logger.info(f"Full path for playback: {full_path}")
        if os.path.exists(full_path):
            relative_path = os.path.join(date_dir, camera_dir, filename).replace(
                "\\", "/"
            )
            return send_from_directory(recorded_video_base_dir, relative_path)
        else:
            current_app.logger.warning(f"File not found: {full_path}")
            abort(404)
    else:
        current_app.logger.warning(f"Unexpected path format: {path}")
        abort(404)


@cam.route("/download_video/<path:path>")
@login_required
def download_video(path):
    current_app.logger.info(f"Attempting to download video with path: {path}")
    recorded_video_base_dir = "./recordedVideo"
    current_app.logger.info(f"recorded_video_base_dir: {recorded_video_base_dir}")

    path = path.replace("\\", "/")
    parts = path.split("/")

    if len(parts) == 3:
        date_dir = parts[0]
        camera_dir = parts[1]
        filename = parts[2]
        full_path = os.path.join(
            recorded_video_base_dir, date_dir, camera_dir, filename
        )
        current_app.logger.info(f"Full path for download: {full_path}")
        if os.path.exists(full_path):
            relative_path = os.path.join(date_dir, camera_dir, filename).replace(
                "\\", "/"
            )
            return send_from_directory(
                recorded_video_base_dir,
                relative_path,
                as_attachment=True,
            )
        else:
            current_app.logger.warning(f"File not found: {download_path}")
            abort(404)
    else:
        current_app.logger.warning(f"Unexpected path format: {path}")
        abort(404)


@cam.route("/delete_recorded_video/<path:path>", methods=["POST"])
@login_required
def delete_recorded_video(path):
    recorded_video_base_dir = "./recordedVideo"
    try:
        path = path.replace("\\", "/")
        parts = path.split("/")
        if len(parts) == 3:
            date_dir = parts[0]
            camera_dir = parts[1]
            filename = parts[2]
            file_path = os.path.join(
                recorded_video_base_dir, date_dir, camera_dir, filename
            )
            if os.path.exists(file_path):
                os.remove(file_path)
                flash(
                    f"'{os.path.basename(file_path)}' 영상이 삭제되었습니다.", "success"
                )
            else:
                flash("삭제하려는 영상을 찾을 수 없습니다.", "error")
        else:
            flash(f"잘못된 파일 경로입니다: {path}", "error")
            abort(400)
    except Exception as e:
        flash(f"영상 삭제 중 오류가 발생했습니다: {e}", "error")

    # Extract camera_id from the URL parameter
    camera_id = request.args.get("camera_id")
    if camera_id:
        return redirect(url_for("cam.recorded_videos", camera_id=camera_id))
    else:
        return redirect(url_for("cam.cameras"))


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
        log_file_path = f"log{now_day}.txt"  # 로그 파일 경로를 변수로 저장
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
    form = CameraAddForm()
    if form.validate_on_submit():
        cam = Cams(name=form.name.data, group=form.group.data, url=form.url.data)
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
        cam.group = form.group.data
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
