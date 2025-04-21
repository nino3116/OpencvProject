import os
from dotenv import load_dotenv
from apps import create_app, db
from apps.cam.models import Cams, Videos
from datetime import datetime
from pathlib import Path
from threading import Thread
from ultralytics import YOLO
from flask import current_app
import cv2 as cv
import time
import random
import logging
from S3upload.s3client import upload_file
from S3upload.s3_config import BUCKET

camera_streams: dict[int, Thread] = {}
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
        logging.error(f"ID가 {camera_id}인 카메라를 찾을 수 없습니다.")
        return

    cap = cv.VideoCapture(camera_url)
    if not cap.isOpened():
        logging.error(f"카메라 ID {camera_id} ({camera_url})를 열 수 없습니다.")
        camera.is_active = False
        camera.is_recording = False
        db.session.commit()
        return

    camera.is_active = True
    camera.is_recording = True
    db.session.commit()

    video_base_dir = Path(current_app.config["VIDEO_FOLDER"])
    # camera_name_safe = camera.cam_name.replace(" ", "_").lower()

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
        logging.info(f"카메라 ID {camera_id}: 녹화 스레드 시작")  # 추가
        while Cams.query.get(camera_id).is_recording and cap.isOpened():
            if (
                not Cams.query.get(camera_id).is_recording
                or camera_id not in camera_streams
            ):
                logging.warning(
                    f"카메라 ID {camera_id}의 녹화 중단 요청 감지. 즉시 중단합니다."
                )
                break

            ret, frame = cap.read()
            if not ret:
                logging.warning(
                    f"카메라 ID {camera_id} ({camera_url})에서 프레임을 읽을 수 없습니다."
                )
                break

            if frame_rate is None:
                frame_rate = current_app.config.get("VIDEO_FPS", 60)  # 기본 FPS 설정
                frame_height, frame_width, _ = frame.shape
                now = datetime.now()
                timestamp = now.strftime("%Y%m%d_%H%M%S")
                now_day_local = now.strftime("%Y-%m-%d")
                video_dir = video_base_dir / now_day_local / str(camera_id)
                if not video_dir.exists():
                    os.makedirs(video_dir)
                current_record_filename = str(
                    video_dir / f"{camera_id}_{timestamp}.mp4"
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
                s3_file_path = (
                    f"videos/{now_day_local}/{camera_id}/{camera_id}_{timestamp}.mp4"
                )
                record_start_time = now  # 최초 녹화 시작 시간 (datetime 객체)
                # print(record_start_time)

            if out is not None and frame_rate is not None:
                out.write(frame)

            current_time_sec = time.time()
            elapsed_time = (
                current_time_sec - record_start_time.timestamp()
            )  # datetime 객체로 비교
            if elapsed_time >= 30:
                # 10분이 경과하면 현재 파일을 저장하고 새로운 파일로 전환
                if out is not None:
                    out.release()

                    time.sleep(1)
                    upload_file(
                        current_record_filename,
                        s3_file_path,
                    )
                    logging.info(
                        f"{current_record_filename} -> s3://{BUCKET}/{s3_file_path} 저장 완료(10분경과)"
                    )
                    time.sleep(1)
                    os.remove(current_record_filename)
                    logging.info(f"로컬 파일 {current_record_filename} 삭제완료")
                    new_video = Videos(
                        camera_id=camera_id,
                        camera_name=camera.cam_name,
                        video_path=s3_file_path,
                        recorded_date=now_day_local,
                        recorded_time=record_start_time.time(),  # .time() 속성으로 시간만 저장
                    )
                    db.session.add(new_video)
                    db.session.commit()

                    now = datetime.now()
                    timestamp = now.strftime("%Y%m%d_%H%M%S")
                    now_day_local = now.strftime("%Y-%m-%d")
                    video_dir = video_base_dir / now_day_local / str(camera_id)
                    if not video_dir.exists():
                        os.makedirs(video_dir)
                    current_record_filename = str(
                        video_dir / f"{camera_id}_{timestamp}.mp4"
                    )
                    out = cv.VideoWriter(
                        current_record_filename,
                        fourcc,
                        frame_rate,
                        (frame_width, frame_height),
                    )
                    record_start_time = now  # 새로운 1분 세그먼트 시작 시간 업데이트
                    s3_file_path = f"videos/{now_day_local}/{camera_id}/{camera_id}_{timestamp}.mp4"

            time.sleep(0.01)
            if out is not None:
                out.write(frame)

    except Exception as e:
        logging.error(f"카메라 ID {camera_id} 녹화 중 오류 발생: {e}")
        camera = Cams.query.get(camera_id)
        if camera:
            camera.is_recording = False
            db.session.commit()
    finally:
        logging.info(f"카메라 ID {camera_id}: 녹화 스레드 종료")  # 추가
        if out is not None:
            out.release()
            time.sleep(1)
            upload_file(
                current_record_filename,
                s3_file_path,
            )
            logging.info(
                f"{current_record_filename} -> s3://{BUCKET}/{s3_file_path} 저장 완료(종료)"
            )
            time.sleep(1)
            os.remove(current_record_filename)
            logging.info(f"로컬 파일 {current_record_filename} 삭제완료")
            time.sleep(1)
            end_video = Videos(
                camera_id=camera_id,
                camera_name=camera.cam_name,
                video_path=s3_file_path,
                recorded_date=now_day_local,
                recorded_time=record_start_time.time(),  # 마지막 세그먼트 시작 시간
            )
            db.session.add(end_video)
            db.session.commit()

        time.sleep(1)
        cap.release()
        logging.info(f"카메라 ID {camera_id} ({camera_url}) 연결 종료 (녹화).")


def start_recording_all():
    with current_app.app_context():
        try:
            from apps.cam.models import Cams  # 순환 참조 방지

            cameras = Cams.query.all()
            logging.info(f"데이터베이스에서 가져온 카메라 수: {len(cameras)}")
            for camera in cameras:
                logging.info(
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
                    logging.info(
                        f"카메라 ID '{camera.id}' 원본 영상 녹화 시작 시도 (URL: {camera.cam_url})"
                    )
                elif camera.is_recording:
                    logging.warning(
                        f"카메라 ID '{camera.id}' 원본 영상 녹화가 이미 진행 중입니다."
                    )
                elif not camera.is_active:
                    logging.warning(f"카메라 ID '{camera.id}'가 비활성 상태입니다.")

        except Exception as e:
            logging.error(f"start_recording_all() 함수 내부 오류: {e}")


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
                logging.info(f"카메라 ID '{camera_id}' 원본 영상 녹화 중단 요청됨.")
                del camera_streams[camera_id]
                logging.info(f"카메라 ID '{camera_id}' 녹화 스레드 제거됨.")
            else:
                logging.error(
                    f"카메라 ID '{camera_id}'에 대한 녹화 스레드를 찾을 수 없습니다."
                )
        elif camera and not camera.is_recording:
            logging.warning(f"카메라 ID '{camera_id}'는 현재 녹화 중이 아닙니다.")
        else:
            logging.error(f"ID가 '{camera_id}'인 카메라를 찾을 수 없습니다.")


def stop_recording_all():
    with current_app.app_context():
        from apps.cam.models import Cams  # 순환 참조 방지

        cameras = Cams.query.all()
        for camera in cameras:
            if camera.is_recording:
                camera.is_recording = False
                db.session.commit()
                logging.info(f"카메라 ID '{camera.id}' 원본 영상 녹화 중단 요청됨.")
                if camera.id in camera_streams:
                    del camera_streams[camera.id]
                    logging.info(f"카메라 ID '{camera.id}' 녹화 스레드 제거됨.")


# def check_cam_periodically(app):  # Keep the 'app' argument
#     import logging

#     logging.info("카메라 상태 확인 백그라운드 스레드 시작")

#     while True:
#         # 각 루프마다 새로운 애플리케이션 컨텍스트를 생성
#         with app.app_context():
#             try:
#                 # 데이터베이스에서 모든 카메라 정보 조회
#                 cams = Cams.query.all()
#                 logging.debug(f"DB에서 {len(cams)}개 카메라 정보 조회")

#                 for cam in cams:
#                     cap = None  # cap 변수 초기화
#                     try:
#                         # cv2.VideoCapture를 사용하여 카메라 연결 시도
#                         logging.debug(f"카메라 연결 시도: {cam.cam_url}")
#                         cap = cv.VideoCapture(cam.cam_url)

#                         if not cap.isOpened():
#                             logging.warning(
#                                 f"카메라 {cam.id} ({cam.cam_url}) 연결 실패 또는 열 수 없음."
#                             )
#                             # 데이터베이스 상태 업데이트
#                             if cam.is_active:  # 상태 변경이 있을 때만 업데이트
#                                 cam.is_active = False
#                                 logging.info(f"카메라 {cam.id} 상태 비활성으로 변경.")
#                         else:
#                             logging.debug(f"카메라 {cam.id} ({cam.cam_url}) 연결 성공.")
#                             # 데이터베이스 상태 업데이트
#                             if not cam.is_active:  # 상태 변경이 있을 때만 업데이트
#                                 cam.is_active = True
#                                 logging.info(f"카메라 {cam.id} 상태 활성으로 변경.")

#                     except Exception as e:
#                         logging.error(
#                             f"카메라 {cam.id} ({cam.cam_url}) 확인 중 예외 발생: {e}"
#                         )
#                         # 오류 발생 시 비활성으로 표시
#                         if cam.is_active:  # 상태 변경이 있을 때만 업데이트
#                             cam.is_active = False
#                             logging.info(
#                                 f"카메라 {cam.id} 상태 비활성으로 변경 (오류 발생)."
#                             )
#                     finally:
#                         # VideoCapture 객체가 생성되었다면 반드시 해제
#                         if cap is not None and cap.isOpened():  # isOpened() 확인 추가
#                             cap.release()
#                             logging.debug(f"카메라 {cam.id} ({cam.cam_url}) 해제 완료.")

#                 # 모든 카메라 상태 업데이트 후 데이터베이스에 변경 사항 커밋
#                 db.session.commit()
#                 logging.info("카메라 상태 확인 및 DB 업데이트 완료 (백그라운드 스레드)")

#             except Exception as e:
#                 # 데이터베이스 조회/커밋 등 컨텍스트 내에서 발생한 다른 예외 처리
#                 logging.error(f"주기적 카메라 확인 루프 중 예외 발생: {e}")
#                 # 예외 발생 시 세션을 롤백하여 불안정한 상태 방지
#                 db.session.rollback()
#                 logging.info("DB 세션 롤백 완료.")

#         # 다음 확인까지 대기
#         time.sleep(60)  # 60초 대기
