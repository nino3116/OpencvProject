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

def ProcessVideo(camera_url,camera_idx,q,pipe):
    # --- 영상 녹화 저장 경로 설정 ---
    # 스크립트가 실행되는 위치 아래에 'recordings' 폴더 생성 (없으면)
    # recordings 폴더 아래에 카메라 ID별 폴더 생성
    base_recording_folder = "recordings"
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
        # 폴더 생성 실패 시 녹화 기능 비활성화 또는 다른 경로 사용 등의 처리 필요
        # 여기서는 일단 진행하지만, 실제로는 오류 처리 후 종료하는 것이 안전할 수 있음
        pass

    # YOLO 모델 불러오기
    try:
        model = YOLO("yolo11n.pt")
        logging.info(f"[Cam {camera_idx}] YOLO model loaded successfully.")
    except Exception as e:
        logging.error(f"[Cam {camera_idx}] Failed to load YOLO model: {e}")
        return  
    
    # 비디오 영상 불러오기
    cap = cv.VideoCapture(camera_url)

    if not cap.isOpened():
        sys.exit("Cannot open camera")
        
    if not cap.isOpened():
        logging.error(f"[Cam {camera_idx}] Cannot open camera stream: {camera_url}")
        sys.exit(f"Cannot open camera {camera_idx}")  # 구체적인 에러 메시지와 함께 프로세스 종료
    
    # 비디오 저장을 위한 변수
    fps = int(cap.get(cv.CAP_PROP_FPS))
    width = int(cap.get(cv.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv.CAP_PROP_FRAME_HEIGHT))
    
    # --- 코덱 설정 ---
    fourcc = cv.VideoWriter.fourcc(*"avc1")
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

    if person_class_id is None:
        print("Warning: 'person' class not found in YOLO model.")

    # 타이머 설정
    log_interval = 30
    start_time = time.time()
    
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
        if results and results[0].boxes:
            boxes = (
                results[0].boxes.xyxy.cpu().numpy().astype(int)
                if results[0].boxes.xyxy is not None
                else []
            )
            track_ids = (
                results[0].boxes.id.cpu().numpy().astype(int)
                if results[0].boxes.id is not None
                else []
            )
            classes = (
                results[0].boxes.cls.cpu().numpy().astype(int)
                if results[0].boxes.cls is not None
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
        )
        
        current_time = time.time()
        this_moment = datetime.now()
        this_moment_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        try:
            if pipe.poll() == True:
                msg = pipe.recv()
                print(msg + str(camera_idx))
                if msg == 'REC ON':
                    if is_recording == False:
                        output_path = f"{this_moment_str}_{camera_idx}.mp4"
                        video_writer = cv.VideoWriter(output_path, fourcc, fps, (width, height))
                        is_recording = True
                elif msg == 'REC OFF':
                    if is_recording == True:
                        
                        is_recording = False
                        video_writer.release()
        except:
            pass
        
        if is_recording == True:
            video_writer.write(frame)
        
        if current_time - start_time >= 30:
            # print(f"Camera{camera_idx} Detected {person_count} persons at {this_moment}.")            
            q.put([camera_idx,person_count,this_moment])

            start_time = current_time
    
        key = cv.waitKey(1)
        if key == ord("q"):
            break
    
    try:
        video_writer.release()
    except:
        print("REALEASE ERROR")
        pass
    
    cap.release()
    cv.destroyAllWindows()


if __name__ == '__main__':
    import multiprocessing
    # freeze_support()
    
    # Load Camera List from Database
    conn = dbconnect()
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute("select * from cams")
    camera_list = cur.fetchall()
    # print(camera_list)
    
    parent_conn, child_conn = multiprocessing.Pipe()
    
    ProcessArr = []
    q = multiprocessing.Queue()
    ppipes = []

    for row in camera_list:
        ppipe, cpipe = multiprocessing.Pipe()
        ProcessArr.append(multiprocessing.Process(target=ProcessVideo, args = (row['cam_url'], int(row['id']),q,cpipe)))
        ppipes.append(ppipe)

    # print(ProcessArr)

    for p in ProcessArr:
        p.start() 
    
    camera_idxs = []
    for row in camera_list:
        camera_idxs.append(row['id'])
    logs = []
    for i in camera_idxs:
        logs.append([])
    
    cflag = False
    current = []
    
    while True:
        try:
            if q.empty():
                for p in ProcessArr:
                    if p.is_alive() == True:
                        flag = True
                        break
                    else:
                        flag = False
                if flag == False:
                    break
            else:
                pd = q.get(block=False)
                
                if cflag == False:
                    cflag = True
                    start_time = pd[2]
                    current.append(pd)
                elif (pd[2] - start_time).seconds < 3: 
                    # 시작 시점 기준으로 3초 이내의 데이터 함께 처리
                    current.append(pd)
                else:
                    tmp = []
                    for i in current: # 카메라 중복 확인
                        tmp.append(i[0])
                        
                    if len(tmp) != len(set(tmp)):
                        print("ERROR: duplicated camera logs")
                    else:
                        total = 0
                        for obj in current:
                            total += obj[1]
                        sql = "insert into Place_Logs (tp_cnt, dt_time) values("+str(total)+",'"+str(start_time)+"')"
                        cur.execute(sql)
                        conn.commit()
                        idx = cur.lastrowid
                        for obj in current:
                            sql = "insert into Camera_Logs (camera_idx, dp_cnt, detected_time, plog_idx) values("+str(obj[0])+","+str(obj[1])+",'"+str(obj[2])+"',"+str(idx)+")"
                            cur.execute(sql)
                            conn.commit()
                        cur.execute("select * from mode_schedule where end_time >= now() and start_time <= now();")
                        mode_now = cur.fetchall()
                        
                        if mode_now[0]['mode_type'] == 'Running':
                            if total > mode_now[0]['people_cnt']:
                                print(str(start_time)+": 예약 인원 초과 감지: 총 "+str(total)+"명 감지 / 예약 인원 "+str(mode_now[0]['people_cnt'])+"명")
                                sql = "insert into Mode_Detected (mode_type, person_reserved, person_detected, detected_time) values('"+str(mode_now[0]['mode_type'])+"',"+str(mode_now[0]['people_cnt'])+","+str(total)+",'"+str(start_time)+"')"
                                for p in ppipes:
                                    try:
                                        p.send('REC ON')
                                    except:
                                        ppipes.remove(p)
                                cur.execute(sql)
                                conn.commit()
                            else:
                                for p in ppipes:
                                    p.send('REC OFF')
                        elif mode_now[0]['mode_type'] == 'Secure':
                            if total > 0:
                                print(str(start_time)+": 방범 모드 중 인물 감지: 총"+str(total)+"명 감지")
                        
                    # 처리한 뒤 초기화: 이후 데이터는 새로운 row로 처리
                    current = []
                    start_time = pd[2]
                    current.append(pd)
        except Exception as e:
            traceback.print_exc()

    for p in ProcessArr:
        p.join()
        
    q.put("finish")

    conn.close()