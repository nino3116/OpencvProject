import os
from dotenv import load_dotenv
from apps import create_app, db
from apps.cam.models import Cams
from datetime import datetime
from pathlib import Path
from threading import Thread
from ultralytics import YOLO
from flask import current_app
import cv2 as cv
import time
import random

# 전역 변수 (각 카메라별 상태 관리를 위해 딕셔너리 사용)
camera_streams = {}
video_writers = {}
recording_status = {}


def record_camera(camera_url, camera_name):
    video_base_dir = Path(current_app.config["VIDEO_FOLDER"])
    snapshot_base_dir = Path(current_app.config["SNAPSHOT_FOLDER"])
    camera_name_safe = camera_name.replace(" ", "_").lower()

    if not video_base_dir.exists():
        os.makedirs(video_base_dir)
    if not snapshot_base_dir.exists():
        os.makedirs(snapshot_base_dir)

    cap = cv.VideoCapture(camera_url)
    if not cap.isOpened():
        print(f"카메라 {camera_name} ({camera_url})를 열 수 없습니다.")
        return

    try:
        model = YOLO("yolo11n.pt")
        person_colors = {}
        person_class_id = None
        if hasattr(model, "names"):
            for class_id, class_name in model.names.items():
                if class_name == "person":
                    person_class_id = class_id
                    break

        frame_rate = int(cap.get(cv.CAP_PROP_FPS))
        frame_width = int(cap.get(cv.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv.CAP_PROP_FRAME_HEIGHT))

        record_start_time = time.time()
        fourcc = cv.VideoWriter_fourcc(*"avc1")
        out = None
        current_record_filename = None

        camera_streams[camera_name] = cap
        recording_status[camera_name] = True

        while recording_status.get(camera_name, False) and cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                print(
                    f"카메라 {camera_name} ({camera_url})에서 프레임을 읽을 수 없습니다. 재연결을 시도합니다..."
                )
                cv.destroyAllWindows()
                time.sleep(5)
                cap = cv.VideoCapture(camera_url)
                if not cap.isOpened():
                    print(f"카메라 {camera_name} ({camera_url}) 재연결 실패.")
                    break
                record_start_time = time.time()
                continue

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

                        now = datetime.now()
                        now_day_local = now.strftime("%Y-%m-%d")
                        snapshot_dir = (
                            snapshot_base_dir / now_day_local / camera_name_safe
                        )
                        if not snapshot_dir.exists():
                            os.makedirs(snapshot_dir)
                        snapshot_filename = (
                            snapshot_dir
                            / f"{camera_name_safe}_{now.strftime('%Y%m%d_%H%M%S')}.jpg"
                        )
                        cv.imwrite(str(snapshot_filename), frame)

            current_time = time.time()
            elapsed_time = current_time - record_start_time

            if elapsed_time >= 60:
                if out is not None:
                    out.release()
                    print(f"{current_record_filename} 저장 완료")
                    os.system(f"aws s3 sync")
                now = datetime.now()
                timestamp = now.strftime("%Y%m%d_%H%M%S")
                now_day_local = now.strftime("%Y-%m-%d")
                video_dir = video_base_dir / now_day_local / camera_name_safe
                if not video_dir.exists():
                    os.makedirs(video_dir)
                current_record_filename = str(
                    video_dir / f"{camera_name_safe}_{timestamp}.mp4"
                )
                out = cv.VideoWriter(
                    current_record_filename,
                    fourcc,
                    frame_rate,
                    (frame_width, frame_height),
                )
                record_start_time = current_time

            if out is not None:
                out.write(frame)

    except Exception as e:
        print(f"카메라 {camera_name} ({camera_url}) 녹화 중 오류 발생: {e}")
    finally:
        if camera_name in camera_streams:
            if isinstance(camera_streams[camera_name], cv.VideoCapture):
                camera_streams[camera_name].release()
            del camera_streams[camera_name]
        if camera_name in recording_status:
            del recording_status[camera_name]
        if out is not None:
            out.release()
            print(f"{current_record_filename} 저장 완료 (종료)")
        if cap.isOpened():
            cap.release()
        cv.destroyAllWindows()


def start_recording_all():
    # print("start_recording_all() 함수 시작 (flask run)")
    with current_app.app_context():
        # print("start_recording_all() 내부 - 애플리케이션 컨텍스트 시작")
        try:
            cameras = Cams.query.all()
            print(f"데이터베이스에서 가져온 카메라 수: {len(cameras)}")
            for camera in cameras:
                print(f"카메라 이름: {camera.cam_name}, 활성 상태: {camera.is_active}")
                if camera.is_active:
                    if camera.cam_name not in camera_streams:
                        app = current_app._get_current_object()
                        thread = Thread(
                            target=record_camera_with_context,
                            args=(app, camera.cam_url, camera.cam_name),
                            daemon=True,
                        )
                        thread.start()
                        print(
                            f"카메라 '{camera.cam_name}' 녹화 시작 시도 (URL: {camera.cam_url})"
                        )
                    else:
                        print(f"카메라 '{camera.cam_name}'는 이미 녹화 중입니다.")
        except Exception as e:
            print(f"start_recording_all() 함수 내부 오류: {e}")
        # print("start_recording_all() 내부 - 애플리케이션 컨텍스트 종료")
    # print("start_recording_all() 함수 종료 (flask run)")


def record_camera_with_context(app, camera_url, camera_name):
    """
    애플리케이션 컨텍스트를 설정하고 record_camera를 실행하는 래퍼 함수
    """
    with app.app_context():
        record_camera(camera_url, camera_name)


def stop_recording(camera_name):
    if camera_name in recording_status:
        recording_status[camera_name] = False
        print(f"카메라 '{camera_name}' 녹화 중단 요청됨.")


def stop_recording_all():
    with current_app.app_context():
        cameras = Cams.query.all()
        for camera in cameras:
            if camera.cam_name in recording_status:
                recording_status[camera.cam_name] = False
                print(f"카메라 '{camera.cam_name}' 녹화 중단 요청됨.")
