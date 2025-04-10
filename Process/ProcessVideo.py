from queue import Full
import cv2 as cv
import sys
import numpy as np
from ultralytics import YOLO
import random
import time
from datetime import datetime

import pymysql
from dbconfig import dbconnect

import traceback, logging
import os
from pathlib import Path

import s3client
from S3upload.s3_config import ACCESS_KEY_ID, SECRET_ACCESS_KEY, DEFAULT_REGION, BUCKET

# 로그 설정
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


baseDir = Path(__file__).parent.parent  # 추가
VIDEO_FOLDER = baseDir / "dt_videos"  # 추가

def ProcessVideo(camera_url, camera_idx, q, pipe):

    # YOLO 모델 불러오기
    try:
        model = YOLO("yolo11n.pt")  # 모델 파일 경로 확인
        logging.info(f"[Cam {camera_idx}] YOLO model loaded successfully.")
    except Exception as e:
        logging.error(f"[Cam {camera_idx}] Failed to load YOLO model: {e}")
        return  # 모델 로드 실패 시 프로세스 종료

    # 비디오 영상 불러오기
    cap = cv.VideoCapture(camera_url)

    if not cap.isOpened():
        logging.error(f"[Cam {camera_idx}] Cannot open camera stream: {camera_url}")
        sys.exit(f"Cannot open camera {camera_idx}")  # 구체적인 에러 메시지와 함께 종료

    # 비디오 저장을 위한 변수
    fps = int(cap.get(cv.CAP_PROP_FPS))
    width = int(cap.get(cv.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv.CAP_PROP_FRAME_HEIGHT))

    # 코덱 설정
    fourcc = cv.VideoWriter.fourcc(*"avc1")  # 또는 "mp4v", "h264" 등 시도
    # fourcc = cv.VideoWriter.fourcc(*"mp4v")
    logging.info(
        f"[Cam {camera_idx}] Video properties: {width}x{height} @ {fps}fps, FourCC: {''.join(chr((fourcc >> 8*i) & 0xFF) for i in range(4))}"
    )

    if width == 0 or height == 0 or fps == 0:
        logging.warning(
            f"[Cam {camera_idx}] Invalid video properties obtained from camera. Recording might fail. W:{width}, H:{height}, FPS:{fps}"
        )

    # 사람별 색상 저장 딕셔너리
    person_colors = {}

    # 사람 클래스 ID 찾기
    person_class_id = None
    if hasattr(model, "names"):
        try:
            person_class_id = [k for k, v in model.names.items() if v == "person"][0]
            logging.info(
                f"[Cam {camera_idx}] 'person' class ID found: {person_class_id}"
            )
        except IndexError:
            logging.warning(
                "[Cam {camera_idx}] 'person' class not found in YOLO model names."
            )
    else:
        logging.warning(
            "[Cam {camera_idx}] Model does not have 'names' attribute. Cannot find 'person' class ID."
        )

    if person_class_id is None:
        logging.warning(
            "[Cam {camera_idx}] 'person' class ID not set. Person detection might not work as expected."
        )

    # 타이머 설정 (30초마다 DB 전송용)
    log_interval = 30  # 초
    last_log_time = time.time()

    # 녹화 관련 변수
    is_recording = False
    video_writer = None  # 명시적으로 None으로 초기화

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            logging.warning(
                f"[Cam {camera_idx}] Failed to read frame from camera or stream ended."
            )
            break

        # 객체 추적 수행
        try:
            results = model.track(frame, persist=True, verbose=False, conf=0.2)
        except Exception as e:
            logging.error(f"[Cam {camera_idx}] Error during YOLO tracking: {e}")
            continue  # 현재 프레임 건너뛰기

        person_count = 0
        # 결과 처리 및 프레임에 그리기
        if results and results[0].boxes:
            # CPU로 데이터 이동 및 타입 변환 (오류 방지)
            boxes = (
                results[0].boxes.xyxy.cpu().numpy().astype(int)
                if results[0].boxes.xyxy is not None
                else []
            )
            classes = (
                results[0].boxes.cls.cpu().numpy().astype(int)
                if results[0].boxes.cls is not None
                else []
            )
            track_ids = (
                results[0].boxes.id.cpu().numpy().astype(int)
                if results[0].boxes.id is not None
                else []
            )
            confidences = (
                results[0].boxes.conf.cpu().numpy()
                if results[0].boxes.conf is not None
                else []
            )

            # track_ids가 있을 경우에만 처리 (없으면 추적 실패)
            if len(track_ids) > 0 and len(boxes) == len(classes) == len(
                track_ids
            ) == len(confidences):
                for i, (x1, y1, x2, y2) in enumerate(boxes):
                    current_class = classes[i]
                    track_id = track_ids[i]
                    confidence = confidences[i]

                    # 'person' 클래스인 경우
                    if current_class == person_class_id:
                        person_count += 1

                        # 사람별 색상 생성 (처음 등장하는 사람에 대해서만)
                        if track_id not in person_colors:
                            person_colors[track_id] = (
                                random.randint(0, 255),
                                random.randint(0, 255),
                                random.randint(0, 255),
                            )
                        color = person_colors[track_id]

                        # 바운딩 박스 그리기
                        cv.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                        # 레이블(ID) 및 신뢰도 표시
                        label = f"ID: {track_id}"  # Conf: {confidence:.2f} # 필요시 신뢰도 추가
                        cv.putText(
                            frame,
                            label,
                            (x1, y1 - 10),
                            cv.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            color,
                            2,
                        )

        # 현재 시간 표시
        current_timestamp_display = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv.putText(
            frame,
            current_timestamp_display,
            (10, 30),
            cv.FONT_HERSHEY_SIMPLEX,
            1,
            (255, 255, 255),
            2,
            cv.LINE_AA,
        )  # 흰색, 외곽선 추가

        # 인원 수 표시
        person_count_text = f"Persons: {person_count}"
        cv.putText(
            frame,
            person_count_text,
            (10, height - 10),
            cv.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2,
            cv.LINE_AA,
        )  # 녹색

        # 화면 출력
        cv.imshow(
            f"Person Tracking - Cam {camera_idx}", frame
        )  # 창 제목에 카메라 ID 추가

        # Pipe 메시지 처리 (녹화 제어)
        try:
            if pipe.poll():
                msg = pipe.recv()
                logging.info(f"[Cam {camera_idx}] Received message: {msg}")
                if msg == "REC ON":
                    if not is_recording:
                        # 영상 녹화 저장 경로 설정
                        base_recording_folder = VIDEO_FOLDER  # 수정
                        camera_recording_folder = os.path.join(base_recording_folder, f"cam_{camera_idx}")
                        
                        try:
                            os.makedirs(camera_recording_folder, exist_ok=True)
                            # logging.info(
                            #     f"[Cam {camera_idx}] Recordings will be saved to: {camera_recording_folder}"
                            # )
                        except OSError as e:
                            logging.error(
                                f"[Cam {camera_idx}] Failed to create recording directory {camera_recording_folder}: {e}"
                            )
                            pass
                        
                        # 파일 이름 생성 (콜론 제거, 안전한 형식)
                        now = datetime.now()
                        safe_timestamp = now.strftime("%Y%m%d_%H%M%S")
                        output_filename = f"{safe_timestamp}_cam{camera_idx}.mp4"
                        output_path = os.path.join(
                            camera_recording_folder, output_filename
                        )
                        now_day_local = now.strftime("%Y-%m-%d")
                        s3_file_path = f"videos/{now_day_local}/{camera_idx}/{camera_idx}_{safe_timestamp}_AD.mp4"
                        record_start_time = datetime.now().time()  # 최초 녹화 시작 시간 기록
                        record_start_time_sec = time.time()
                        
                        # VideoWriter 생성
                        video_writer = cv.VideoWriter(
                            output_path, fourcc, fps, (width, height)
                        )

                        # VideoWriter 생성 성공 여부 확인
                        if video_writer.isOpened():
                            is_recording = True
                            logging.info(
                                f"[Cam {camera_idx}] Started recording to: {output_path}"
                            )
                        else:
                            logging.error(
                                f"[Cam {camera_idx}] Failed to open VideoWriter for path: {output_path}. Check codec ({''.join(chr((fourcc >> 8*i) & 0xFF) for i in range(4))}), path, permissions, and video properties."
                            )
                            video_writer = None  # 실패 시 None으로 유지
                    else:
                        logging.warning(
                            f"[Cam {camera_idx}] Received 'REC ON' but already recording."
                        )
                elif msg == "REC OFF":
                    if is_recording and video_writer is not None:
                        is_recording = False
                        video_writer.release()  # 파일 저장 완료
                        s3client.upload_file(
                            output_path,
                            s3_file_path,
                        )
                        try:
                            os.remove(output_path)
                            logging.info(
                                f"로컬 파일 {output_path} 삭제완료"
                            )
                        except:
                            logging.error(
                                f"로컬 파일 {output_path} 삭제실패"
                            )
                        try:
                            conn = dbconnect()
                            cur = conn.cursor(pymysql.cursors.DictCursor)
                            rend_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            sql_video = "INSERT INTO videos (camera_id, camera_name, recorded_date, recorded_time, video_path, is_dt, rend_date, rend_time) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
                            cur.execute(
                                sql_video,
                                (
                                    camera_idx,
                                    "Camera "+str(camera_idx),
                                    safe_timestamp[0:safe_timestamp.find('_')],
                                    safe_timestamp[safe_timestamp.find('_')+1:len(safe_timestamp)],
                                    s3_file_path,
                                    1,
                                    rend_timestamp[0:safe_timestamp.find('_')],
                                    rend_timestamp[safe_timestamp.find('_')+1:len(safe_timestamp)]
                                ),
                            )  # 시간 포맷 맞춰주기
                            conn.commit()
                        except pymysql.Error as e:
                            logging.error(f"Database error: {e}")
                            sys.exit(1)  # DB 오류 시 종료
                        except ConnectionError as e:
                            logging.error(f"Database connection error: {e}")
                            sys.exit(1)
                        except Exception as e:  # 예상치 못한 다른 오류
                            logging.error(f"An unexpected error occurred during DB setup: {e}")
                            traceback.print_exc()
                            sys.exit(1)
                        
                        logging.info(
                            f"[Cam {camera_idx}] Stopped recording. File saved."
                        )
                        video_writer = None  # 녹화 종료 후 객체 참조 제거
                    else:
                        logging.warning(
                            f"[Cam {camera_idx}] Received 'REC OFF' but not recording or writer is invalid."
                        )

        except (EOFError, BrokenPipeError) as e:
            logging.error(
                f"[Cam {camera_idx}] Pipe connection error: {e}. Stopping process."
            )
            break  # 파이프 오류 시 루프 종료
        except Exception as e:
            logging.error(f"[Cam {camera_idx}] Error processing pipe message: {e}")
            traceback.print_exc()  # 상세 오류 출력

        # --- 프레임 녹화 ---
        if is_recording and video_writer is not None:
            try:
                video_writer.write(frame)
            except Exception as e:
                logging.error(
                    f"[Cam {camera_idx}] Error writing frame to video file: {e}"
                )
                # 녹화 중단 또는 오류 처리 로직 추가 가능
                is_recording = False
                video_writer.release()
                video_writer = None

        # 주기적 로그 전송
        current_time = time.time()
        if current_time - last_log_time >= log_interval:
            log_time = datetime.now()  # 로그 시점의 정확한 시간 기록
            # logging.info(f"[Cam {camera_idx}] Sending log: Count={person_count} at {log_time}")
            try:
                q.put(
                    [camera_idx, person_count, log_time], block=False
                )
            except Full:  # Queue가 가득 찼을 경우 (메인 프로세스 처리 지연)
                logging.warning(
                    f"[Cam {camera_idx}] Queue is full. Log data might be lost."
                )
            except Exception as e:
                logging.error(f"[Cam {camera_idx}] Failed to put data into queue: {e}")

            last_log_time = current_time  # 마지막 로그 시간 갱신

        # 종료 키 처리 ('q')
        key = cv.waitKey(1) & 0xFF
        if key == ord("q"):
            logging.info(f"[Cam {camera_idx}] 'q' key pressed. Exiting loop.")
            break

    # 루프 종료 후 정리
    logging.info(f"[Cam {camera_idx}] Cleaning up resources...")
    if is_recording and video_writer is not None:
        try:
            logging.info(
                f"[Cam {camera_idx}] Releasing video writer due to loop exit..."
            )
            video_writer.release()
            s3client.upload_file(
                output_path,
                s3_file_path,
            )
            logging.info(
                f"{output_path} -> s3://{BUCKET}/{s3_file_path} 저장 완료(움직임 감지 녹화 중 프로세스 종료)"
            )
            time.sleep(1)
            try:
                os.remove(output_path)
                logging.info(
                    f"로컬 파일 {output_path} 삭제완료"
                )
            except:
                logging.error(
                    f"로컬 파일 {output_path} 삭제실패"
                )
            
            if is_recording == True:
                try:
                    conn = dbconnect()
                    cur = conn.cursor(pymysql.cursors.DictCursor)
                    rend_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    sql_video = "INSERT INTO videos (camera_id, camera_name, recorded_date, recorded_time, video_path, is_dt, rend_date, rend_time) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
                    cur.execute(
                        sql_video,
                        (
                            camera_idx,
                            "Camera "+str(camera_idx),
                            safe_timestamp[0:safe_timestamp.find('_')],
                            safe_timestamp[safe_timestamp.find('_')+1:len(safe_timestamp)],
                            s3_file_path,
                            1,
                            rend_timestamp[0:safe_timestamp.find('_')],
                            rend_timestamp[safe_timestamp.find('_')+1:len(safe_timestamp)]
                        ),
                    )  # 시간 포맷 맞춰주기
                    conn.commit()
                except pymysql.Error as e:
                    logging.error(f"Database error: {e}")
                    sys.exit(1)  # DB 오류 시 종료
                except ConnectionError as e:
                    logging.error(f"Database connection error: {e}")
                    sys.exit(1)
                except Exception as e:  # 예상치 못한 다른 오류
                    logging.error(f"An unexpected error occurred during DB setup: {e}")
                    traceback.print_exc()
                    sys.exit(1)
        except Exception as e:
            logging.error(
                f"[Cam {camera_idx}] Error releasing video writer during cleanup: {e}"
            )

    if cap is not None and cap.isOpened():
        cap.release()
    cv.destroyAllWindows()
    logging.info(f"[Cam {camera_idx}] Process finished.")