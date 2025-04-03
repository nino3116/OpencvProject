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

camera_streams = {}
recording_status = {}
person_colors = {}  # 추적 ID별 색상 저장


def detect_and_track_person(camera_url, camera_name):
    """
    주어진 카메라 URL에서 영상을 읽어와 사람을 인식하고 추적한 결과를 반환하는 제너레이터 함수.

    Args:
        camera_url (str): 카메라 URL.
        camera_name (str): 카메라 이름.

    Yields:
        tuple: (프레임 (numpy 배열), 검출 결과 (바운딩 박스 및 추적 ID 리스트)).
             검출 결과는 각 사람에 대해 ((x1, y1, x2, y2), track_id) 형태의 튜플 리스트입니다.
             track_id는 추적 ID (존재하지 않으면 None)입니다.
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

        while recording_status.get(camera_name, False) and cap.isOpened():
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
        print(f"카메라 {camera_name} ({camera_url}) 연결 종료.")


def visualize_detections(frame, detections):
    """
    프레임에 검출 결과를 시각화하는 함수.

    Args:
        frame (numpy 배열): 프레임 이미지.
        detections (list): 검출 결과 리스트 (각 사람에 대해 ((x1, y1, x2, y2), track_id)).

    Returns:
        numpy 배열: 검출 결과가 그려진 프레임.
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

    Args:
        frame (numpy 배열): 저장할 프레임 이미지.
        camera_name (str): 카메라 이름.
    """
    snapshot_base_dir = Path(current_app.config["SNAPSHOT_FOLDER"])
    camera_name_safe = camera_name.replace(" ", "_").lower()
    now = datetime.now()
    now_day_local = now.strftime("%Y-%m-%d")
    snapshot_dir = snapshot_base_dir / now_day_local / camera_name_safe
    if not snapshot_dir.exists():
        os.makedirs(snapshot_dir)
    snapshot_filename = (
        snapshot_dir / f"{camera_name_safe}_{now.strftime('%Y%m%d_%H%M%S')}.jpg"
    )
    cv.imwrite(str(snapshot_filename), frame)


def record_video(frame_generator, camera_name):
    """
    프레임 제너레이터를 받아 영상을 녹화하고 사람 인식 결과에 따라 스냅샷을 저장하는 함수.

    Args:
        frame_generator (generator): (프레임, 검출 결과) 튜플을 생성하는 제너레이터.
        camera_name (str): 카메라 이름.
    """
    video_base_dir = Path(current_app.config["VIDEO_FOLDER"])
    snapshot_base_dir = Path(current_app.config["SNAPSHOT_FOLDER"])
    camera_name_safe = camera_name.replace(" ", "_").lower()

    if not video_base_dir.exists():
        os.makedirs(video_base_dir)
    if not snapshot_base_dir.exists():
        os.makedirs(snapshot_base_dir)

    out = None
    current_record_filename = None
    record_start_time = time.time()
    frame_rate = None
    frame_width = None
    frame_height = None
    fourcc = cv.VideoWriter_fourcc(*"avc1")

    try:
        for frame, detections in frame_generator:
            if frame_rate is None:
                frame_rate = current_app.config.get("VIDEO_FPS", 20)  # 기본 FPS 설정
                frame_height, frame_width, _ = frame.shape

            frame_with_detections = visualize_detections(frame, detections)

            person_detected = bool(detections)
            if person_detected:
                save_snapshot(frame_with_detections, camera_name)

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
                out.write(frame_with_detections)

    except Exception as e:
        print(f"카메라 {camera_name} 녹화 중 오류 발생: {e}")
    finally:
        if out is not None:
            out.release()
            print(f"{current_record_filename} 저장 완료 (종료)")


def record_camera(camera_url, camera_name):
    """
    주어진 카메라 URL과 이름으로 사람 인식 및 추적 후 영상을 녹화하는 메인 함수.
    """
    frame_generator = detect_and_track_person(camera_url, camera_name)
    if frame_generator:
        record_video(frame_generator, camera_name)


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
                    if camera.cam_name not in camera_streams:
                        app = current_app._get_current_object()
                        thread = Thread(
                            target=record_camera_with_context,
                            args=(app, camera.cam_url, camera.cam_name),
                            daemon=True,
                        )
                        thread.start()
                        camera_streams[camera.cam_name] = thread
                        recording_status[camera.cam_name] = True
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
        from apps.cam.models import Cams  # 순환 참조 방지

        cameras = Cams.query.all()
        for camera in cameras:
            if camera.cam_name in recording_status:
                recording_status[camera.cam_name] = False
                print(f"카메라 '{camera.cam_name}' 녹화 중단 요청됨.")
