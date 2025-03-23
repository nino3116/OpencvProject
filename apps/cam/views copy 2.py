from flask import (
    Flask,
    Blueprint,
    render_template,
    Response,
    stream_with_context,
    redirect,
    url_for,
    flash,
    request,
)
import cv2 as cv
from ultralytics import YOLO
import sys
import random
import time
from datetime import datetime
from flask_login import login_required
from apps.cam.forms import CameraAddForm
from apps.cam.models import Cams
from apps.app import db
import os

cam = Blueprint(
    "cam",
    __name__,
    template_folder="templates",
)

camera_streams = {}
video_writers = {}
recording_status = {}
now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
now_day = datetime.now().strftime("%Y-%m-%d")


def generate_frames(camera_url, camera_name):
    cap = cv.VideoCapture(camera_url)
    if not cap.isOpened():
        yield b"--frame\r\n" + b"Content-Type: image/jpeg\r\n\r\n" + open(
            "static/error.jpg", "rb"
        ).read() + b"\r\n"
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

    camera_streams[camera_name] = cap

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            log_file.write(
                f"========Stopped Logging for {camera_name} at {datetime.now()} - Frame capture failed========\n"
            )
            break

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

        camera_name_key = camera_name.replace(" ", "_").lower()
        if camera_name_key in recording_status and recording_status[camera_name_key]:
            if (
                camera_name_key in video_writers
                and video_writers[camera_name_key] is not None
            ):
                video_writers[camera_name_key].write(frame)

        current_time = time.time()
        this_moment = datetime.now()
        if current_time - start_time >= 10:
            print(f"Detected {person_count} persons at {this_moment} on {camera_name}.")
            log_file.write(
                f"Detected {person_count} persons at {this_moment} on {camera_name}.\n"
            )
            snapshot_dir = f"./snapshot/{now_day}/"
            snapshot_path = f"{snapshot_dir}{camera_name}_{now}.jpg"
            os.makedirs(snapshot_dir, exist_ok=True)
            cv.imwrite(snapshot_path, frame)
            # print(f"snapshot saved to {snapshot_path}")
            log_file.write(f"snapshot saved to '{snapshot_path}")
            start_time = current_time

        _, buffer = cv.imencode(".jpg", frame)
        frame_bytes = buffer.tobytes()
        yield (
            b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
        )

    log_file.write(
        f"========Stopped Logging for {camera_name} at {datetime.now()}========\n"
    )
    log_file.close()
    cap.release()
    if camera_name in camera_streams:
        del camera_streams[camera_name]
    camera_name_key = camera_name.replace(" ", "_").lower()
    if camera_name_key in video_writers and video_writers[camera_name_key] is not None:
        video_writers[camera_name_key].release()
        del video_writers[camera_name_key]
        del recording_status[camera_name_key]


@cam.route("/")
@login_required
def index():
    cams = Cams.query.all()
    return render_template("cam/index.html", cams=cams)


@cam.route("/stream/<camera_id>")
@login_required
def camera_stream(camera_id):
    cam_obj = Cams.query.filter_by(id=camera_id).first_or_404()
    return Response(
        generate_frames(cam_obj.url, cam_obj.name),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@cam.route("/stream_page/<camera_id>")
def stream_page(camera_id):
    return render_template("cam/stream.html", camera_id=camera_id)


@cam.route("/start_record/<camera_id>")
def start_record(camera_id):
    cam_obj = Cams.query.filter_by(id=camera_id).first_or_404()
    camera_name = cam_obj.name
    camera_url = cam_obj.url

    cap = camera_streams.get(camera_name)
    if cap is None or not cap.isOpened():
        return "Error: Camera stream not available."

    fps = int(cap.get(cv.CAP_PROP_FPS))
    width = int(cap.get(cv.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv.CAP_PROP_FRAME_HEIGHT))
    output_dir = f"./recordedVideo/{now_day}/"
    output_path = f"{output_dir}{camera_id}_{now}.mp4"
    fourcc = cv.VideoWriter.fourcc(*"mp4v")

    # Ensure the directory exists
    os.makedirs(output_dir, exist_ok=True)

    fourcc = cv.VideoWriter.fourcc(*"mp4v")
    video_writers[camera_name.replace(" ", "_").lower()] = cv.VideoWriter(
        output_path, fourcc, fps, (width, height)
    )
    recording_status[camera_name.replace(" ", "_").lower()] = True
    return f"Recording started for {camera_id} at {output_path}"


@cam.route("/stop_record/<camera_id>")
def stop_record(camera_id):
    cam_obj = Cams.query.filter_by(id=camera_id).first_or_404()
    camera_name = cam_obj.name
    camera_name_key = camera_name.replace(" ", "_").lower()
    if camera_name_key in recording_status and recording_status[camera_name_key]:
        recording_status[camera_name_key] = False
        if (
            camera_name_key in video_writers
            and video_writers[camera_name_key] is not None
        ):
            video_writers[camera_name_key].release()
            video_writers[camera_name_key] = None
            return f"Recording stopped for {camera_id}"
        else:
            return f"Error: No active recording found for {camera_id}"
    else:
        return f"No active recording found for {camera_id}"


@cam.route("/video_list/<camera_id>")
def video_list():
    video_dir = f"./recordedVideo/{now_day}/"
    video_files = [f for f in os.listdir(video_dir) if f.endswith(".mp4")]


@cam.route("/get_log")
def get_log():
    try:
        with open(f"log{now_day}.txt", "r") as f:  # 파일 열기 모드를 "r"로 변경
            log_content = f.read()
        return log_content.replace("\n", "<br>")
    except FileNotFoundError:
        return "Log file not found."


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
    return render_template("cam/cameraDB.html", cams=cams)


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


@cam.route("/cameras/{id}/delete", methods=["POST"])
@login_required
def delete_camera(id):
    cam = Cams.query.filter_by(id=id).first()
    db.session.delete(cam)
    db.session.commit()
    return redirect(url_for("cam.cameras"))
