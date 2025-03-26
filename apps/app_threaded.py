import os
from dotenv import load_dotenv
from apps import create_app, db  # apps/__init__.py에서 create_app과 db를 import
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
now_day = datetime.now().strftime("%Y-%m-%d")


def record_camera(camera_url, camera_name):
    """
    특정 카메라 URL에서 영상을 녹화하고 1분마다 저장하며 사람을 감지 및 추적하는 함수
    """
    video_base_dir = Path(current_app.config["VIDEO_FOLDER"])
    snapshot_base_dir = Path(current_app.config["SNAPSHOT_FOLDER"])

    if not video_base_dir.exists():
        os.makedirs(video_base_dir)
    if not snapshot_base_dir.exists():
        os.makedirs(snapshot_base_dir)

    cap = cv.VideoCapture(camera_url)
    if not cap.isOpened():
        print(f"카메라 {camera_name} ({camera_url})를 열 수 없습니다.")
        return

    try:
        model = YOLO("yolo11n.pt")  # YOLO 모델 로드 (tracking 모델)
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
        fourcc = cv.VideoWriter_fourcc(*"mp4v")
        out = None
        current_record_filename = None

        while True:
            if not recording_status.get(camera_name, True):  # 녹화 중단 요청 확인
                break

            ret, frame = cap.read()
            if not ret:
                print(
                    f"카메라 {camera_name} ({camera_url})에서 프레임을 읽을 수 없습니다. 재연결을 시도합니다..."
                )
                cv.destroyAllWindows()
                time.sleep(5)  # 재연결 시도 전 잠시 대기
                cap = cv.VideoCapture(camera_url)  # 카메라 재연결 시도
                if not cap.isOpened():
                    print(f"카메라 {camera_name} ({camera_url}) 재연결 실패.")
                    break
                record_start_time = time.time()  # 재연결 후 녹화 시작 시간 갱신
                continue

            results = model.track(frame, persist=True)  # 객체 추적

            if results and results[0].boxes:
                tracked_objects = results[0].boxes.data.tolist()
                for box in tracked_objects:
                    x1, y1, x2, y2, track_id, class_id = map(int, box)
                    if class_id == person_class_id:  # 감지된 객체가 사람인 경우
                        color = person_colors.get(track_id)
                        if color is None:
                            color = (
                                random.randint(0, 255),
                                random.randint(0, 255),
                                random.randint(0, 255),
                            )
                            person_colors[track_id] = color
                        cv.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                        cv.putText(
                            frame,
                            f"Person {track_id}",
                            (x1, y1 - 10),
                            cv.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            color,
                            2,
                        )

                        # 스냅샷 저장 (각 사람별 최초 감지 시 또는 일정 간격으로)
                        snapshot_filename = (
                            snapshot_base_dir
                            / now_day
                            / camera_name
                            / f"person_{track_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                        )
                        if not snapshot_filename.parent.exists():
                            os.makedirs(snapshot_filename.parent)
                        cv.imwrite(str(snapshot_filename), frame)

            current_time = time.time()
            elapsed_time = current_time - record_start_time

            # 1분마다 비디오 파일 저장
            if elapsed_time >= 60:
                if out is not None:
                    out.release()
                    print(f"{current_record_filename} 저장 완료")
                now = datetime.now()
                timestamp = now.strftime("%Y%m%d_%H%M%S")
                now_day = now.strftime("%Y-%m-%d")
                video_dir = video_base_dir / now_day / camera_name
                if not video_dir.exists():
                    os.makedirs(video_dir)
                current_record_filename = str(
                    video_dir / f"{camera_name}_{timestamp}.mp4"
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

            # 필요하다면 화면에 프레임 표시
            # cv.imshow(camera_name, frame)
            # if cv.waitKey(1) & 0xFF == ord('q'):
            #     break

    except Exception as e:
        print(f"카메라 {camera_name} ({camera_url}) 녹화 중 오류 발생: {e}")
    finally:
        if out is not None:
            out.release()
            print(f"{current_record_filename} 저장 완료 (종료)")
        cap.release()
        cv.destroyAllWindows()
        del camera_streams[camera_name]  # 스트림 딕셔너리에서 제거
        if camera_name in recording_status:
            del recording_status[camera_name]


def start_recording_all():
    """
    데이터베이스에서 카메라 정보를 읽어와 모든 카메라 녹화를 시작하는 함수
    """
    with current_app.app_context():
        cameras = Cams.query.all()
        for camera in cameras:
            if camera.is_active:
                if camera.cam_name not in camera_streams:
                    recording_status[camera.cam_name] = (
                        True  # 녹화 상태를 True로 초기화
                    )
                    thread = Thread(
                        target=record_camera,
                        args=(camera.cam_url, camera.cam_name),
                        daemon=True,
                    )
                    camera_streams[camera.cam_name] = thread
                    thread.start()
                    print(
                        f"카메라 '{camera.cam_name}' 녹화 시작 (URL: {camera.cam_url})"
                    )
                else:
                    print(f"카메라 '{camera.cam_name}'는 이미 녹화 중입니다.")


def stop_recording(camera_name):
    """
    특정 카메라의 녹화를 중지하는 함수
    """
    if camera_name in recording_status:
        recording_status[camera_name] = False
        print(f"카메라 '{camera_name}' 녹화 중단 요청됨.")
        # 실제 종료는 record_camera 함수 내에서 이루어짐


def stop_recording_all():
    """
    모든 활성 카메라의 녹화를 중지하는 함수
    """
    with current_app.app_context():
        cameras = Cams.query.all()
        for camera in cameras:
            if camera.cam_name in recording_status:
                recording_status[camera.cam_name] = False
                print(f"카메라 '{camera.cam_name}' 녹화 중단 요청됨.")
        # 실제 종료는 record_camera 함수 내에서 이루어짐


if __name__ == "__main__":
    load_dotenv()
    app = create_app(os.getenv("FLASK_CONFIG") or "local")  # 환경 변수에서 설정 로드
    with app.app_context():
        db.create_all()  # 테이블 생성 (이미 존재하면 무시)
    start_recording_all()  # 애플리케이션 시작 시 모든 카메라 녹화 시작
    app.run(
        debug=True, use_reloader=False
    )  # use_reloader=False로 설정하여 개발 서버 재시작 방지 (Thread와의 충돌 방지)
