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
import smtplib  # Import for email functionality
from email.mime.text import MIMEText  # Import for email message creation
from email.mime.multipart import MIMEMultipart
from email_config import EMAIL_PASSWORD, EMAIL_RECEIVER, EMAIL_SENDER

# 로그 설정
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

baseDir = Path(__file__).parent.parent  # 추가
VIDEO_FOLDER = baseDir / "apps" / "dt_videos"  # 추가


def send_email(subject, body):
    """Sends an email with the given subject and body."""
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECEIVER

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:  # Use Gmail SMTP
            smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
            smtp.send_message(msg)
        logging.info("Email sent successfully!")
    except Exception as e:
        logging.error(f"Failed to send email: {e}")
        traceback.print_exc()


def send_html_email(info, to_email):

    # # 다운로드 링크 생성
    # download_url = f"http://yourserver.com/videos/{info['filename']}"

    # HTML 템플릿에 데이터 삽입
    html_template = open("./Process/email_template.html", "r", encoding="utf-8").read()
    html_content = (
        html_template.replace("{{event}}", info["event"]).replace(
            "{{timestamp}}", info["timestamp"]
        )
        # .replace("{{filename}}", info["filename"])
        # .replace("{{download_url}}", download_url)
    )

    # 이메일 구성
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[경고] {info['event']} - {info['timestamp']}"
    msg["From"] = EMAIL_SENDER
    msg["To"] = to_email
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
            print("이메일 전송 성공")
    except Exception as e:
        print("이메일 전송 실패:", e)


def ProcessVideo(camera_url, camera_idx, q, pipe):
    # 영상 녹화 저장 경로 설정
    base_recording_folder = VIDEO_FOLDER  # 수정
    camera_recording_folder = os.path.join(base_recording_folder, f"cam_{camera_idx}")
    try:
        os.makedirs(camera_recording_folder, exist_ok=True)
        logging.info(
            f"[Cam {camera_idx}] Recordings will be saved to: {camera_recording_folder}"
        )
    except OSError as e:
        logging.error(
            f"[Cam {camera_idx}] Failed to create recording directory {camera_recording_folder}: {e}"
        )
        pass

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
                        # 파일 이름 생성 (콜론 제거, 안전한 형식)
                        safe_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        output_filename = f"{safe_timestamp}_cam{camera_idx}.mp4"
                        output_path = os.path.join(
                            camera_recording_folder, output_filename
                        )

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

                        try:
                            conn = dbconnect()
                            cur = conn.cursor(pymysql.cursors.DictCursor)
                            sql_video = "INSERT INTO videos (camera_id, camera_name, recorded_date, recorded_time, video_path, is_dt) VALUES (%s, %s, %s, %s, %s, %d)"
                            cur.execute(
                                sql_video,
                                (
                                    camera_idx,
                                    "Camera " + str(camera_idx),
                                    safe_timestamp[0 : safe_timestamp.find("_")],
                                    safe_timestamp[
                                        safe_timestamp.find("_")
                                        + 1 : len(safe_timestamp)
                                    ],
                                    output_path,
                                    1,
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
                            logging.error(
                                f"An unexpected error occurred during DB setup: {e}"
                            )
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
                q.put([camera_idx, person_count, log_time], block=False)
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
            if is_recording == True:
                try:
                    conn = dbconnect()
                    cur = conn.cursor(pymysql.cursors.DictCursor)
                    sql_video = "INSERT INTO videos (camera_id, camera_name, recorded_date, recorded_time, video_path, is_dt) VALUES (%d, %s, %s, %s, %s, %s)"
                    cur.execute(
                        sql_video,
                        (
                            camera_idx,
                            "Camera " + str(camera_idx),
                            safe_timestamp[0 : safe_timestamp.find("_")],
                            safe_timestamp[
                                safe_timestamp.find("_") + 1 : len(safe_timestamp)
                            ],
                            f"cam_{camera_idx}"
                            + "/"
                            + f"{safe_timestamp}_cam{camera_idx}.mp4",
                            1,
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


if __name__ == "__main__":
    import multiprocessing
    from queue import Full, Empty

    logging.info("Main process started.")

    # Load Camera List from Database
    conn = None
    cur = None
    try:
        conn = dbconnect()
        if conn is None:
            raise ConnectionError("Failed to establish database connection.")
        cur = conn.cursor(pymysql.cursors.DictCursor)
        cur.execute("SELECT * FROM cams")
        camera_list = cur.fetchall()
        logging.info(f"Loaded {len(camera_list)} cameras from database.")
        if not camera_list:
            logging.warning("No cameras found in the database. Exiting.")
            sys.exit(0)
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

    # Multiprocessing 설정
    q = multiprocessing.Queue()
    ProcessArr = []
    ppipes = {}

    # Initialize email sent flag for each camera
    email_sent_flags = {}
    for row in camera_list:
        if "id" not in row or "cam_url" not in row:
            logging.warning(
                f"Skipping camera entry due to missing 'id' or 'cam_url': {row}"
            )
            continue
        camera_id = int(row["id"])
        email_sent_flags[camera_id] = False

    for row in camera_list:
        if "id" not in row or "cam_url" not in row:
            logging.warning(
                f"Skipping camera entry due to missing 'id' or 'cam_url': {row}"
            )
            continue

        camera_id = int(row["id"])
        camera_url = row["cam_url"]

        # 부모-자식 파이프 생성
        parent_pipe, child_pipe = multiprocessing.Pipe()

        # 프로세스 생성
        process = multiprocessing.Process(
            target=ProcessVideo,
            args=(camera_url, camera_id, q, child_pipe),
            daemon=True,  # 데몬 프로세스로 설정
        )
        ProcessArr.append(process)
        ppipes[camera_id] = parent_pipe  # 카메라 ID를 키로 부모 파이프 저장

    logging.info(f"Created {len(ProcessArr)} processes.")

    # 프로세스 시작
    for p in ProcessArr:
        p.start()
    logging.info("All processes started.")

    # 로그 처리 및 모드 확인 로직
    cflag = False
    current_batch = []
    batch_start_time = None  # 배치 시작 시간

    main_loop_active = True

    while main_loop_active:
        try:
            # 자식 프로세스 상태 확인 (모든 자식 프로세스가 종료되었는지)
            if not any(p.is_alive() for p in ProcessArr):
                logging.info("All child processes have terminated. Exiting main loop.")
                main_loop_active = False
                continue

            # 큐에서 데이터 가져오기 (Non-blocking)
            try:
                pd = q.get(block=False)
                # logging.debug(f"Received data from queue: {pd}") # 디버깅 시 주석 해제
            except Empty:  # 큐가 비어있으면 잠시 대기 후 다시 시도
                time.sleep(0.1)  # CPU 사용률 감소
                continue

            # 데이터 처리 로직 (3초 단위 배치)
            if not cflag:  # 첫 데이터 도착
                cflag = True
                batch_start_time = pd[2]
                current_batch.append(pd)
            elif (
                pd[2] - batch_start_time
            ).total_seconds() < 3:  # 이전 데이터 시간 기준으로 3초 미만
                current_batch.append(pd)
            else:  # 3초 경과, 이전 배치 처리
                if current_batch:
                    # 중복 카메라 로그 확인 (배치 내)
                    cam_ids_in_batch = [item[0] for item in current_batch]
                    if len(cam_ids_in_batch) != len(set(cam_ids_in_batch)):
                        logging.error(
                            f"Duplicate camera logs detected in batch starting around {batch_start_time}. Batch data: {current_batch}"
                        )
                        # 오류 처리 로직 (예: 해당 배치 건너뛰기)
                    else:
                        # 정상 배치 처리: DB 저장 및 모드 확인
                        total_persons = sum(item[1] for item in current_batch)
                        log_timestamp = (
                            batch_start_time  # 배치 시작 시간 기준으로 DB 기록
                        )

                        try:
                            # 1. Place_Logs 저장
                            sql_place_log = "INSERT INTO Place_Logs (tp_cnt, dt_time) VALUES (%s, %s)"
                            cur.execute(
                                sql_place_log,
                                (
                                    total_persons,
                                    log_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                                ),
                            )  # 시간 포맷 맞춰주기
                            conn.commit()
                            plog_idx = cur.lastrowid
                            # logging.info(f"Inserted into Place_Logs: Total={total_persons}, Time={log_timestamp}, ID={plog_idx}")

                            # 2. Camera_Logs 저장
                            sql_camera_log = "INSERT INTO Camera_Logs (camera_idx, dp_cnt, detected_time, plog_idx) VALUES (%s, %s, %s, %s)"
                            log_entries = [
                                (
                                    item[0],
                                    item[1],
                                    item[2].strftime("%Y-%m-%d %H:%M:%S"),
                                    plog_idx,
                                )
                                for item in current_batch
                            ]
                            cur.executemany(
                                sql_camera_log, log_entries
                            )  # executemany 사용
                            conn.commit()
                            # logging.info(f"Inserted {len(log_entries)} entries into Camera_Logs for plog_idx={plog_idx}")

                            # 3. 현재 모드 확인 및 처리
                            sql_mode = "SELECT * FROM mode_schedule WHERE end_time >= NOW() AND start_time <= NOW()"
                            cur.execute(sql_mode)
                            active_modes = (
                                cur.fetchall()
                            )  # 여러 모드가 겹칠 수 있으므로 fetchall 사용

                            should_record = False  # 녹화 시작 플래그
                            if active_modes:
                                for (
                                    mode
                                ) in active_modes:  # 현재 활성화된 모든 모드 검사
                                    mode_type = mode.get("mode_type", "Unknown")
                                    people_cnt_limit = mode.get(
                                        "people_cnt"
                                    )  # Running 모드용
                                    mode_id = mode.get("id", "N/A")  # 로그용

                                    logging.debug(
                                        f"Active mode check: Type={mode_type}, Limit={people_cnt_limit}, Total Detected={total_persons}"
                                    )

                                    if (
                                        mode_type == "Running"
                                        and people_cnt_limit is not None
                                    ):
                                        # Access the camera ID from the current batch
                                        camera_id_batch = current_batch[0][
                                            0
                                        ]  # Get camera ID from batch

                                        if total_persons > people_cnt_limit:
                                            logging.warning(
                                                f"[{log_timestamp}] Exceeded person limit! Detected: {total_persons}, Limit: {people_cnt_limit} (Mode ID: {mode_id})"
                                            )
                                            should_record = True
                                            # Mode_Detected 테이블에 기록
                                            sql_mode_detected = "INSERT INTO Mode_Detected (mode_type, person_reserved, person_detected, detected_time, mode_schedule_id) VALUES (%s, %s, %s, %s, %s)"
                                            cur.execute(
                                                sql_mode_detected,
                                                (
                                                    mode_type,
                                                    people_cnt_limit,
                                                    total_persons,
                                                    log_timestamp,
                                                    mode_id,
                                                ),
                                            )
                                            conn.commit()

                                            # SEND EMAIL
                                            if not email_sent_flags[camera_id_batch]:
                                                # email_subject = "Person Limit Exceeded"
                                                # email_body = f"The person limit of {people_cnt_limit} has been exceeded.  Currently {total_persons} persons are detected. Camera : {camera_id_batch} time {log_timestamp}"
                                                # send_email(email_subject, email_body)
                                                # email_sent_flags[camera_id_batch] = True
                                                info = {
                                                    "event": "Person Limit Exceeded",
                                                    "timestamp": str(log_timestamp),
                                                }
                                                send_html_email(
                                                    info, to_email=EMAIL_RECEIVER
                                                )
                                                email_sent_flags[camera_id_batch] = True
                                    elif mode_type == "Secure":
                                        if total_persons > 0:
                                            logging.warning(
                                                f"[{log_timestamp}] Person detected during Secure mode! Detected: {total_persons} (Mode ID: {mode_id})"
                                            )
                                            should_record = True
                                            # Mode_Detected 테이블에 기록
                                            sql_mode_detected = "INSERT INTO Mode_Detected (mode_type, person_reserved, person_detected, detected_time, mode_schedule_id) VALUES (%s, %s, %s, %s, %s)"
                                            # Secure 모드는 예약 인원 개념이 없으므로 NULL 또는 0 처리 (DB 스키마에 따라)
                                            cur.execute(
                                                sql_mode_detected,
                                                (
                                                    mode_type,
                                                    0,
                                                    total_persons,
                                                    log_timestamp,
                                                    mode_id,
                                                ),
                                            )
                                            conn.commit()
                                            # SEND EMAIL
                                            if not email_sent_flags[camera_id_batch]:
                                                email_subject = (
                                                    "Person Detected during Secure Mode"
                                                )
                                                email_body = f"Person Detected During Secure Mode.  Currently {total_persons} persons are detected. Camera : {camera_id_batch} time {log_timestamp}"
                                                send_email(email_subject, email_body)
                                                email_sent_flags[camera_id_batch] = True
                            else:  # 활성화된 모드가 없을 때
                                logging.debug(
                                    f"[{log_timestamp}] No active mode schedule found."
                                )

                            # 녹화 제어 메시지 전송
                            # should_record 플래그를 기반으로 모든 활성 카메라 프로세스에 메시지 전송
                            message_to_send = "REC ON" if should_record else "REC OFF"
                            active_pipes = []
                            for cam_id, pipe_conn in list(
                                ppipes.items()
                            ):  # list()로 복사본 순회 (삭제 대비)
                                process_alive = False
                                for p in ProcessArr:
                                    if p.is_alive():  # 간단히 모든 활성 프로세스에 전송
                                        process_alive = True  # 실제로는 특정 cam_id에 해당하는 프로세스만 확인해야 함
                                        try:
                                            pipe_conn.send(message_to_send)
                                            # logging.debug(f"Sent '{message_to_send}' to pipe for cam_id {cam_id}") # 디버그 로그
                                        except (BrokenPipeError, EOFError):
                                            logging.warning(
                                                f"Pipe for Cam ID {cam_id} seems broken. Removing."
                                            )
                                            pipe_conn.close()
                                            del ppipes[cam_id]  # 고장난 파이프 제거
                                        except Exception as e:
                                            logging.error(
                                                f"Error sending message to pipe for Cam ID {cam_id}: {e}"
                                            )

                        except pymysql.Error as db_err:
                            logging.error(
                                f"Database error during batch processing: {db_err}"
                            )
                            conn.rollback()  # 오류 발생 시 트랜잭션 롤백
                        except Exception as proc_err:
                            logging.error(
                                f"Unexpected error during batch processing: {proc_err}"
                            )
                            traceback.print_exc()
                            conn.rollback()
                # Reset the flag for sending email, a new evaluation of mode starts
                for camera_id in email_sent_flags:
                    email_sent_flags[camera_id] = False

                # 현재 데이터로 새 배치 시작
                current_batch = [pd]
                batch_start_time = pd[2]

        except Empty:
            time.sleep(0.1)  # 잠시 대기
        except KeyboardInterrupt:  # Ctrl+C 처리
            logging.info("KeyboardInterrupt received. Shutting down...")
            main_loop_active = False  # 메인 루프 종료 플래그 설정
        except Exception as e:
            logging.error(f"An error occurred in the main loop: {e}")
            traceback.print_exc()
            # 오류 발생 시 잠시 대기 후 계속 (상황에 따라 종료 결정)
            time.sleep(1)

    # 메인 루프 종료 후 처리
    logging.info("Main loop finished. Cleaning up...")

    # 모든 자식 프로세스가 종료될 때까지 대기 (join)
    logging.info("Waiting for child processes to terminate...")
    for p in ProcessArr:
        try:
            p.join(timeout=10)  # 최대 10초 대기
            if p.is_alive():
                logging.warning(
                    f"Process {p.pid} did not terminate gracefully. Forcing termination."
                )
                p.terminate()  # 강제 종료
                p.join()  # 강제 종료 후 대기
        except Exception as e:
            logging.error(f"Error joining process {p.pid}: {e}")

    q.close()
    q.join_thread()

    # DB 연결 닫기
    if cur:
        cur.close()
    if conn:
        conn.close()
    logging.info("Main process finished.")
