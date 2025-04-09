import pymysql
import sys
import traceback, logging
import time

from dbconfig import dbconnect
from ProcessVideo import ProcessVideo


if __name__ == "__main__":
    import multiprocessing
    from queue import Full, Empty

    logging.info("Main process started.")

    # Load Camera List from Database
    conn = None
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
