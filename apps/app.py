import os
from dotenv import load_dotenv
from apps import create_app, db
from apps.cam.models import Cams, Camera_logs, Videos
from datetime import datetime
from pathlib import Path
from threading import Thread
from ultralytics import YOLO
from flask import current_app
import cv2 as cv
import time
import random
from S3upload.s3client import upload_file
from S3upload.s3_config import BUCKET

camera_streams: dict[str, Thread] = {}
# recording_status: dict[str, bool] = {}


def record_original_video(camera_url, camera_id):
    """
    주어진 카메라 URL에서 영상을 읽어와 원본 영상을 녹화하고 저장하는 함수 (ID 사용).

    Args:
        camera_url (str): 카메라 URL.
        camera_id (int): 카메라 ID.
    """
    camera = Cams.query.get(camera_id)
    if not camera:
        print(f"ID가 {camera_id}인 카메라를 찾을 수 없습니다.")
        return

    cap = cv.VideoCapture(camera_url)
    if not cap.isOpened():
        print(f"카메라 ID {camera_id} ({camera_url})를 열 수 없습니다.")
        camera.is_active = False
        camera.is_recording = False
        db.session.commit()
        return

    camera.is_active = True
    camera.is_recording = True
    db.session.commit()

    video_base_dir = Path(current_app.config["VIDEO_FOLDER"])
    camera_name_safe = camera.cam_name.replace(" ", "_").lower()

    if not video_base_dir.exists():
        os.makedirs(video_base_dir)

    out = None
    current_record_filename = None
    record_start_time = time.time()
    frame_rate = None
    frame_width = None
    frame_height = None
    fourcc = cv.VideoWriter_fourcc(*"avc1")
    file_path = None

    try:
        while Cams.query.get(camera_id).is_recording and cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                print(
                    f"카메라 ID {camera_id} ({camera_url})에서 프레임을 읽을 수 없습니다."
                )
                break

            if frame_rate is None:
                frame_rate = current_app.config.get("VIDEO_FPS", 30)  # 기본 FPS 설정
                frame_height, frame_width, _ = frame.shape
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
                file_path = current_record_filename.replace(
                    str(video_base_dir) + os.sep, ""
                ).replace(os.sep, "/")
                s3_file_path = f"videos/{now_day_local}/{camera_name_safe}/{camera_name_safe}_{timestamp}.mp4"
                record_start_time = datetime.now().time()  # 최초 녹화 시작 시간 기록
                record_start_time_sec = time.time()
                # print(record_start_time)

            if out is not None and frame_rate is not None:
                out.write(frame)

            current_time = time.time()
            elapsed_time = current_time - record_start_time_sec

            if elapsed_time >= 600:
                if out is not None:
                    out.release()
                    time.sleep(1)
                    upload_file(
                        current_record_filename,
                        f"videos/{now_day_local}/{camera_name_safe}/{camera_name_safe}_{timestamp}.mp4",
                    )
                    print(
                        f"{current_record_filename} -> s3://{BUCKET}/{s3_file_path} 저장 완료(10분경과)"
                    )
                    time.sleep(1)
                    os.remove(current_record_filename)
                    print(f"로컬 파일 {current_record_filename} 삭제완료")
                    time.sleep(1)
                    new_video = Videos(
                        camera_id=camera_id,
                        camera_name=camera.cam_name,
                        # video_path=file_path,
                        video_path=s3_file_path,
                        recorded_date=now_day_local,
                        recorded_time=record_start_time,
                    )
                    db.session.add(new_video)
                    db.session.commit()

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
        print(f"카메라 ID {camera_id} 녹화 중 오류 발생: {e}")
        camera = Cams.query.get(camera_id)
        if camera:
            camera.is_recording = False
            db.session.commit()
    finally:
        if out is not None:
            out.release()
            time.sleep(1)
            upload_file(
                current_record_filename,
                f"videos/{now_day_local}/{camera_name_safe}/{camera_name_safe}_{timestamp}.mp4",
            )
            print(
                f"{current_record_filename} -> s3://{BUCKET}/{s3_file_path} 저장 완료(종료)"
            )
            time.sleep(1)
            os.remove(current_record_filename)
            print(f"로컬 파일 {current_record_filename} 삭제완료")
            time.sleep(1)
            new_video = Videos(
                camera_id=camera_id,
                camera_name=camera.cam_name,
                # video_path=file_path,
                video_path=s3_file_path,
                recorded_date=now_day_local,
                recorded_time=record_start_time,
            )
            db.session.add(new_video)
            db.session.commit()

        time.sleep(1)
        cap.release()
        print(f"카메라 ID {camera_id} ({camera_url}) 연결 종료 (녹화).")


def start_recording_all():
    with current_app.app_context():
        try:
            from apps.cam.models import Cams  # 순환 참조 방지

            cameras = Cams.query.all()
            print(f"데이터베이스에서 가져온 카메라 수: {len(cameras)}")
            for camera in cameras:
                print(
                    f"카메라 ID: {camera.id}, 이름: {camera.cam_name}, 활성 상태: {camera.is_active}, 녹화 상태: {camera.is_recording}"
                )
                if camera.is_active and not camera.is_recording:
                    app = current_app._get_current_object()
                    recording_thread = Thread(
                        target=record_camera_with_context,
                        args=(app, camera.cam_url, camera.id),
                        daemon=True,
                    )
                    recording_thread.start()
                    camera_streams[camera.id] = recording_thread
                    print(
                        f"카메라 ID '{camera.id}' 원본 영상 녹화 시작 시도 (URL: {camera.cam_url})"
                    )
                elif camera.is_recording:
                    print(
                        f"카메라 ID '{camera.id}' 원본 영상 녹화가 이미 진행 중입니다."
                    )
                elif not camera.is_active:
                    print(f"카메라 ID '{camera.id}'가 비활성 상태입니다.")

        except Exception as e:
            print(f"start_recording_all() 함수 내부 오류: {e}")


def record_camera_with_context(app, camera_url, camera_id):
    """
    애플리케이션 컨텍스트를 설정하고 녹화 기능을 실행하는 래퍼 함수 (ID 사용).
    """
    with app.app_context():
        record_original_video(camera_url, camera_id)


def stop_recording(camera_id):
    with current_app.app_context():
        camera = Cams.query.get(camera_id)
        if camera and camera.is_recording:
            camera.is_recording = False
            db.session.commit()
            if camera_id in camera_streams:
                print(f"카메라 ID '{camera_id}' 원본 영상 녹화 중단 요청됨.")
            else:
                print(f"카메라 ID '{camera_id}'에 대한 녹화 스레드를 찾을 수 없습니다.")
        elif camera and not camera.is_recording:
            print(f"카메라 ID '{camera_id}'는 현재 녹화 중이 아닙니다.")
        else:
            print(f"ID가 '{camera_id}'인 카메라를 찾을 수 없습니다.")


def stop_recording_all():
    with current_app.app_context():
        from apps.cam.models import Cams  # 순환 참조 방지

        cameras = Cams.query.all()
        for camera in cameras:
            if camera.is_recording:
                camera.is_recording = False
                db.session.commit()
                print(f"카메라 ID '{camera.id}' 원본 영상 녹화 중단 요청됨.")
