import os
from dotenv import load_dotenv
from apps import create_app, db
from apps.cam.models import Cams, Camera_logs  # Import Camera_logs model
from datetime import datetime
from pathlib import Path
from threading import Thread, Event
from ultralytics import YOLO
from flask import current_app
import cv2 as cv
import time
import random

camera_streams = {}
person_colors = {}  # 추적 ID별 색상 저장
DETECTION_INTERVAL = 60  # 감지 및 로그 저장 간격 (초)
VIDEO_DURATION = 300  # 영상 녹화 최대 시간 (초)
camera_stop_events = {}  # 카메라별 종료 이벤트 객체 저장


def detect_and_track_person(camera_url, camera_name, stop_event):
    """
    주어진 카메라 URL에서 영상을 읽어와 사람을 인식하고 추적한 결과를 반환하는 제너레이터 함수.

    Args:
        camera_url (str): 카메라 URL.
        camera_name (str): 카메라 이름.
        stop_event (threading.Event): 스레드 종료 이벤트.


    Yields:
        tuple: (프레임 (numpy 배열), 검출 결과 (바운딩 박스 및 추적 ID 리스트)).
             검출 결과는 각 사람에 대해 ((x1, y1, x2, y2), track_id) 형태의 튜플 리스트입니다.
             track_id는 추적 ID (존재하지 않으면 None)입니다.
    주어진 카메라 URL에서 영상을 읽어와 사람을 인식하고 추적한 결과를 반환하는 제너레이터 함수.
    종료 이벤트를 사용하여 스레드 종료를 제어합니다.
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

        while not stop_event.is_set() and cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                print(
                    f"카메라 {camera_name} ({camera_url})에서 프레임을 읽을 수 없습니다."
                )
                break

            results = model.track(frame, persist=True, verbose=False, conf=0.2)
            detections = []
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
                        track_id = track_ids[i] if len(track_ids) > 0 else None
                        detections.append(((x1, y1, x2, y2), track_id))

            yield frame, detections

    except Exception as e:
        print(f"카메라 {camera_name} ({camera_url}) 감지 및 추적 중 오류 발생: {e}")
    finally:
        cap.release()
        print(f"카메라 {camera_name} ({camera_url}) 연결 종료 (감지 및 추적).")


def visualize_detections(frame, detections):
    """
    프레임에 검출 결과를 시각화하는 함수.
    """
    frame_with_detections = frame.copy()
    for (x1, y1, x2, y2), track_id in detections:
        color = person_colors.get(
            track_id,
            (
                random.randint(0, 255),
                random.randint(0, 255),
                random.randint(0, 255),
            ),
        )
        if track_id not in person_colors and track_id is not None:
            person_colors[track_id] = color
        cv.rectangle(frame_with_detections, (x1, y1), (x2, y2), color, 2)
        label = f"ID: {track_id}" if track_id is not None else "Person"
        cv.putText(
            frame_with_detections,
            label,
            (x1, y1 - 10),
            cv.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            2,
        )
    return frame_with_detections


def save_snapshot(frame, camera_name):
    """
    주어진 프레임을 스냅샷으로 저장하는 함수.
    """
    snapshot_base_dir = Path(current_app.config["SNAPSHOT_FOLDER"])
    camera_name_safe = camera_name.replace(" ", "_").lower()
    now = datetime.now()
    now_day_local = now.strftime("%Y-%m-%d")
    snapshot_dir = snapshot_base_dir / now_day_local / camera_name_safe
    snapshot_dir.mkdir(parents=True, exist_ok=True)  # pathlib를 이용한 디렉토리 생성
    snapshot_filename = (
        snapshot_dir / f"{camera_name_safe}_{now.strftime('%Y%m%d_%H%M%S')}.jpg"
    )
    cv.imwrite(str(snapshot_filename), frame)
    return snapshot_filename


def record_processed_video(camera_url, camera_name, stop_event):
    """
    주어진 카메라 URL에서 영상을 읽어와 사람을 인식, 추적하고 시각화하여 녹화 및 저장하고 로그를 남기는 함수.
    종료 이벤트를 사용하여 스레드 종료를 제어합니다.
    """
    cap = cv.VideoCapture(camera_url)
    if not cap.isOpened():
        print(f"카메라 {camera_name} ({camera_url})를 열 수 없습니다.")
        return

    video_base_dir = Path(current_app.config["VIDEO_FOLDER"])
    camera_name_safe = camera_name.replace(" ", "_").lower()
    video_base_dir.mkdir(parents=True, exist_ok=True)

    out = None
    current_record_filename = None
    record_start_time = time.time()
    frame_rate = current_app.config.get("VIDEO_FPS", 20)
    frame_width = None
    frame_height = None
    fourcc = cv.VideoWriter_fourcc(*"avc1")
    last_log_time = time.time()

    try:
        frame_generator = detect_and_track_person(camera_url, camera_name, stop_event)
        if frame_generator:
            for frame, detections in frame_generator:
                if stop_event.is_set():  # 종료 요청 확인
                    break

                if frame_height is None:
                    frame_height, frame_width, _ = frame.shape

                frame_with_detections = visualize_detections(frame, detections)

                current_time = time.time()
                elapsed_time = current_time - record_start_time

                if elapsed_time >= VIDEO_DURATION:
                    if out is not None:
                        out.release()
                        print(f"{current_record_filename} 저장 완료")
                    now = datetime.now()
                    timestamp = now.strftime("%Y%m%d_%H%M%S")
                    now_day_local = now.strftime("%Y-%m-%d")
                    video_dir = video_base_dir / now_day_local / camera_name_safe
                    video_dir.mkdir(parents=True, exist_ok=True)
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
                    out.write(frame_with_detections)

                # 로그 저장 (DETECTION_INTERVAL 간격으로)
                if current_time - last_log_time >= DETECTION_INTERVAL and detections:
                    snapshot_path = save_snapshot(frame_with_detections, camera_name)
                    now = datetime.now()
                    with current_app.app_context():
                        log = Camera_logs(
                            camera_name=camera_name,
                            detection_time=now,
                            person_count=len(detections),
                            snapshot_path=str(snapshot_path),
                        )
                        db.session.add(log)
                        db.session.commit()
                        print(
                            f"[{camera_name}] {now.strftime('%Y-%m-%d %H:%M:%S')} - 감지된 사람 수: {len(detections)}, 스냅샷: {snapshot_path}"
                        )
                    last_log_time = current_time

    except Exception as e:
        print(f"카메라 {camera_name} 녹화 중 오류 발생: {e}")
    finally:
        if out is not None:
            out.release()
            print(f"{current_record_filename} 저장 완료 (종료)")
        cap.release()
        print(f"카메라 {camera_name} ({camera_url}) 연결 종료 (녹화).")


def record_camera(camera_url, camera_name, stop_event):
    """
    주어진 카메라 URL과 이름으로 사람 인식 및 추적 후 영상을 녹화하는 메인 함수.
    종료 이벤트를 인자로 받습니다.
    """
    record_processed_video(camera_url, camera_name, stop_event)


def start_recording_all():
    with current_app.app_context():
        try:
            from apps.cam.models import Cams

            cameras = Cams.query.all()
            print(f"데이터베이스에서 가져온 카메라 수: {len(cameras)}")
            app = current_app._get_current_object()
            for camera in cameras:
                print(f"카메라 이름: {camera.cam_name}, 활성 상태: {camera.is_active}")
                if camera.is_active:
                    if camera.cam_name not in camera_streams:
                        stop_event = Event()  # 각 카메라별 종료 이벤트 생성
                        camera_stop_events[camera.cam_name] = stop_event
                        thread = Thread(
                            target=record_camera_with_context,
                            args=(app, camera.cam_url, camera.cam_name, stop_event),
                            daemon=True,
                        )
                        thread.start()
                        camera_streams[camera.cam_name] = thread
                        print(
                            f"카메라 '{camera.cam_name}' 녹화 시작 시도 (URL: {camera.cam_url})"
                        )
                    else:
                        print(f"카메라 '{camera.cam_name}'는 이미 녹화 중입니다.")
        except Exception as e:
            print(f"start_recording_all() 함수 내부 오류: {e}")


def record_camera_with_context(app, camera_url, camera_name, stop_event):
    """
    애플리케이션 컨텍스트를 설정하고 record_camera를 실행하는 래퍼 함수
    종료 이벤트를 인자로 받습니다.
    """
    with app.app_context():
        record_camera(camera_url, camera_name, stop_event)


def stop_recording(camera_name):
    if camera_name in camera_streams:
        if camera_name in camera_stop_events:
            camera_stop_events[camera_name].set()  # 종료 이벤트 설정
            del camera_streams[camera_name]
            del camera_stop_events[camera_name]
            print(f"카메라 '{camera_name}' 녹화 중단 요청됨.")
        else:
            print(f"카메라 '{camera_name}'에 대한 종료 이벤트가 없습니다.")
    else:
        print(f"카메라 '{camera_name}'는 현재 녹화 중이 아닙니다.")


def stop_recording_all():
    with current_app.app_context():
        from apps.cam.models import Cams

        cameras = Cams.query.all()
        for camera in cameras:
            if camera.cam_name in camera_streams:
                if camera.cam_name in camera_stop_events:
                    camera_stop_events[
                        camera.cam_name
                    ].set()  # 모든 카메라의 종료 이벤트 설정
                    del camera_streams[camera.cam_name]
                    del camera_stop_events[camera.cam_name]
                    print(f"카메라 '{camera.cam_name}' 녹화 중단 요청됨.")
                else:
                    print(f"카메라 '{camera.cam_name}'에 대한 종료 이벤트가 없습니다.")
            else:
                print(f"카메라 '{camera.cam_name}'는 현재 녹화 중이 아닙니다.")
