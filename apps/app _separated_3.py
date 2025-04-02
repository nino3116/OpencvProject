import os
from dotenv import load_dotenv
from apps import create_app, db
from apps.cam.models import Cams, Camera_logs  # Import Camera_logs model
from datetime import datetime
from pathlib import Path
from threading import Thread
from ultralytics import YOLO
from flask import current_app
import cv2 as cv
import time
import random

camera_streams = {}
recording_status = {}
detection_status = {}  # To track if detection thread is running
person_colors = {}  # 추적 ID별 색상 저장
DETECTION_INTERVAL = 60  # 감지 및 로그 저장 간격 (초)


def detect_and_log_person(camera_url, camera_name):
    """
    주어진 카메라 URL에서 영상을 읽어와 사람을 인식하고 로그를 저장하는 함수 (상시 동작).

    Args:
        camera_url (str): 카메라 URL.
        camera_name (str): 카메라 이름.
    """
    cap = cv.VideoCapture(camera_url)
    if not cap.isOpened():
        print(f"카메라 {camera_name} ({camera_url})를 열 수 없습니다.")
        return

    try:
        model = YOLO("yolo11n.pt")
        person_class_id = None
        if hasattr(model, "names"):
            for class_id, class_name in model.names.items():
                if class_name == "person":
                    person_class_id = class_id
                    break

        last_detection_time = time.time()

        while detection_status.get(camera_name, False) and cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                print(
                    f"카메라 {camera_name} ({camera_url})에서 프레임을 읽을 수 없습니다."
                )
                break

            current_time = time.time()
            if current_time - last_detection_time >= DETECTION_INTERVAL:
                results = model(frame, verbose=False, conf=0.2)
                detections = []
                person_count = 0
                if results and results[0].boxes:
                    classes = results[0].boxes.cls.cpu().numpy().astype(int)
                    for class_id in classes:
                        if class_id == person_class_id:
                            person_count += 1

                    # 스냅샷 저장
                    snapshot_base_dir = Path(current_app.config["SNAPSHOT_FOLDER"])
                    camera_name_safe = camera_name.replace(" ", "_").lower()
                    now = datetime.now()
                    now_day_local = now.strftime("%Y-%m-%d")
                    snapshot_dir = snapshot_base_dir / now_day_local / camera_name_safe
                    if not snapshot_dir.exists():
                        os.makedirs(snapshot_dir)
                    snapshot_filename = (
                        snapshot_dir
                        / f"{camera_name_safe}_{now.strftime('%Y%m%d_%H%M%S')}.jpg"
                    )
                    cv.imwrite(str(snapshot_filename), frame)

                    # 로그 저장
                    with current_app.app_context():
                        log = Camera_logs(
                            camera_name=camera_name,
                            detection_time=now,
                            person_count=person_count,
                            snapshot_path=str(snapshot_filename),
                        )
                        db.session.add(log)
                        db.session.commit()
                        print(
                            f"[{camera_name}] {now.strftime('%Y-%m-%d %H:%M:%S')} - 감지된 사람 수: {person_count}, 스냅샷: {snapshot_filename}"
                        )

                last_detection_time = current_time

            time.sleep(1)  # CPU 사용량 감소

    except Exception as e:
        print(f"카메라 {camera_name} ({camera_url}) 감지 및 로깅 중 오류 발생: {e}")
    finally:
        time.sleep(1)
        cap.release()
        print(f"카메라 {camera_name} ({camera_url}) 연결 종료 (감지 및 로깅).")


def record_original_video(camera_url, camera_name):
    """
    주어진 카메라 URL에서 영상을 읽어와 원본 영상을 녹화하고 저장하는 함수.

    Args:
        camera_url (str): 카메라 URL.
        camera_name (str): 카메라 이름.
    """
    cap = cv.VideoCapture(camera_url)
    if not cap.isOpened():
        print(f"카메라 {camera_name} ({camera_url})를 열 수 없습니다.")
        return

    video_base_dir = Path(current_app.config["VIDEO_FOLDER"])
    camera_name_safe = camera_name.replace(" ", "_").lower()

    if not video_base_dir.exists():
        os.makedirs(video_base_dir)

    out = None
    current_record_filename = None
    record_start_time = time.time()
    frame_rate = None
    frame_width = None
    frame_height = None
    fourcc = cv.VideoWriter_fourcc(*"avc1")

    try:
        while recording_status.get(camera_name, False) and cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                print(
                    f"카메라 {camera_name} ({camera_url})에서 프레임을 읽을 수 없습니다."
                )
                break

            if frame_rate is None:
                frame_rate = current_app.config.get("VIDEO_FPS", 30)  # 기본 FPS 설정
                frame_height, frame_width, _ = frame.shape

            current_time = time.time()
            elapsed_time = current_time - record_start_time

            if elapsed_time >= 600:
                if out is not None:
                    out.release()
                    print(f"{current_record_filename} 저장 완료")
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
        print(f"카메라 {camera_name} 녹화 중 오류 발생: {e}")
    finally:
        if out is not None:
            out.release()
            print(f"{current_record_filename} 저장 완료 (종료)")
        time.sleep(1)
        cap.release()
        print(f"카메라 {camera_name} ({camera_url}) 연결 종료 (녹화).")


def record_camera(camera_url, camera_name):
    """
    주어진 카메라 URL과 이름으로 사람 인식 및 추적 후 영상을 녹화하는 메인 함수.
    이 함수는 이제 감지 및 로깅, 원본 영상 녹화를 각각 시작합니다.
    """
    # 더 이상 사용하지 않음
    pass


def start_recording_all():
    # print("start_recording_all() 함수 시작 (flask run)")
    with current_app.app_context():
        # print("start_recording_all() 내부 - 애플리케이션 컨텍스트 시작")
        try:
            from apps.cam.models import Cams  # 순환 참조 방지

            cameras = Cams.query.all()
            print(f"데이터베이스에서 가져온 카메라 수: {len(cameras)}")
            for camera in cameras:
                print(f"카메라 이름: {camera.cam_name}, 활성 상태: {camera.is_active}")
                if camera.is_active:
                    # 시작: 사람 인식 및 로그 저장
                    if camera.cam_name not in camera_streams:
                        app = current_app._get_current_object()
                        detection_thread = Thread(
                            target=record_camera_with_context,
                            args=(app, camera.cam_url, camera.cam_name, "detect"),
                            daemon=True,
                        )
                        detection_thread.start()
                        camera_streams[camera.cam_name] = detection_thread
                        detection_status[camera.cam_name] = True
                        print(
                            f"카메라 '{camera.cam_name}' 사람 인식 및 로그 저장 시작 시도 (URL: {camera.cam_url})"
                        )
                    else:
                        print(
                            f"카메라 '{camera.cam_name}' 사람 인식 및 로그 저장 스레드가 이미 실행 중입니다."
                        )

                    # 시작: 원본 영상 녹화
                    if (
                        f"{camera.cam_name}_record" not in recording_status
                        or not recording_status[camera.cam_name]
                    ):
                        app = current_app._get_current_object()
                        recording_thread = Thread(
                            target=record_camera_with_context,
                            args=(app, camera.cam_url, camera.cam_name, "record"),
                            daemon=True,
                        )
                        recording_thread.start()
                        recording_status[camera.cam_name] = True
                        print(
                            f"카메라 '{camera.cam_name}' 원본 영상 녹화 시작 시도 (URL: {camera.cam_url})"
                        )
                    else:
                        print(
                            f"카메라 '{camera.cam_name}' 원본 영상 녹화가 이미 진행 중입니다."
                        )

        except Exception as e:
            print(f"start_recording_all() 함수 내부 오류: {e}")
        # print("start_recording_all() 내부 - 애플리케이션 컨텍스트 종료")
    # print("start_recording_all() 함수 종료 (flask run)")


def record_camera_with_context(app, camera_url, camera_name, mode="detect"):
    """
    애플리케이션 컨텍스트를 설정하고 감지/로깅 또는 녹화 기능을 실행하는 래퍼 함수
    """
    with app.app_context():
        if mode == "detect":
            detect_and_log_person(camera_url, camera_name)
        elif mode == "record":
            record_original_video(camera_url, camera_name)


def stop_recording(camera_name):
    if camera_name in recording_status:
        recording_status[camera_name] = False
        print(f"카메라 '{camera_name}' 원본 영상 녹화 중단 요청됨.")
    if camera_name in detection_status:
        detection_status[camera_name] = False
        print(f"카메라 '{camera_name}' 사람 인식 및 로깅 중단 요청됨.")


def stop_recording_all():
    with current_app.app_context():
        from apps.cam.models import Cams  # 순환 참조 방지

        cameras = Cams.query.all()
        for camera in cameras:
            if camera.cam_name in recording_status:
                recording_status[camera.cam_name] = False
                print(f"카메라 '{camera.cam_name}' 원본 영상 녹화 중단 요청됨.")
            if camera.cam_name in detection_status:
                detection_status[camera.cam_name] = False
                print(f"카메라 '{camera.cam_name}' 사람 인식 및 로깅 중단 요청됨.")
