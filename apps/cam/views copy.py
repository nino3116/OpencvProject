# 기업 연계 프로젝트 1
from flask import Flask, Blueprint, render_template, redirect, Response
import cv2 as cv
from ultralytics import YOLO
import sys
import random
import time
from datetime import datetime
from flask_login import login_required
import os

cam = Blueprint(
    "cam",
    __name__,
    template_folder="templates",
)

camera_streams = {}
video_writers = {}
recording_status = {}


@cam.route("/")
def index():
    return render_template("cam/index.html")


@cam.route("/stream/<camera_id>")
@login_required
def camera_stream(camera_id):
    if camera_id == "camera1":
        return Response(
            generate_frames("http://192.168.0.124:8000/stream.mjpg", "Camera Server 1"),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )
    elif camera_id == "camera2":
        return Response(
            generate_frames("http://192.168.0.125:8000/stream.mjpg", "Camera Server 2"),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )
    elif camera_id == "camera3":
        return Response(
            generate_frames("http://192.168.0.130:8000/stream.mjpg", "Camera Server 3"),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )
    else:
        return "Invalid camera ID"


@cam.route("/stream_page/<camera_id>")
def stream_page(camera_id):
    return render_template("cam/stream.html", camera_id=camera_id)


def generate_frames(camera_url, camera_name):
    cap = cv.VideoCapture(camera_url)
    if not cap.isOpened():
        yield b"--frame\r\n" + b"Content-Type: image/jpeg\r\n\r\n" + open(
            "static/error.jpg", "rb"
        ).read() + b"\r\n"
        return

    model = YOLO("yolo11n.pt")

    # 사람별 색상 저장 딕셔너리
    person_colors = {}

    # 사람 클래스 ID 찾기
    person_class_id = None
    if hasattr(model, "names"):
        for class_id, class_name in model.names.items():
            if class_name == "person":
                person_class_id = class_id
                break

    if person_class_id is None:
        print("Warning: 'person' class not found in YOLO model.")

    # 타이머 설정
    start_time = time.time()
    file = open("log.txt", "a")
    file.write(f"========Loggin Start for {camera_name} at {datetime.now()}========\n")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            file.write(
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

                    # 사람별 색상 생성 (처음 등장하는 사람에 대해서만)
                    if track_id not in person_colors:
                        person_colors[track_id] = (
                            random.randint(0, 255),
                            random.randint(0, 255),
                            random.randint(0, 255),
                        )
                    color = person_colors[track_id]

                    cv.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                    confidence = results[0].boxes.conf[i].cpu().item()
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

        current_time = time.time()
        this_moment = datetime.now()
        if current_time - start_time >= 10:
            print(f"Detected {person_count} persons at {this_moment} on {camera_name}.")
            file.write(
                f"Detected {person_count} persons at {this_moment} on {camera_name}.\n"
            )
            start_time = current_time

        _, buffer = cv.imencode(".jpg", frame)
        frame_bytes = buffer.tobytes()
        yield (
            b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
        )

    file.write(
        f"========Stopped Logging for {camera_name} at {datetime.now()}========\n"
    )
    file.close()
    cap.release()
