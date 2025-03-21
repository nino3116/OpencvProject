import cv2 as cv
import sys
import numpy as np
from ultralytics import YOLO
import random
import time
from datetime import datetime

# CAMERA LIST
camera_list=["http://192.168.0.124:8000/stream.mjpg","http://192.168.0.125:8000/stream.mjpg","http://192.168.0.124:8001/stream.mjpg"]

def ProcessVideo(camera_url,camera_idx):
    # YOLO 모델 불러오기
    model = YOLO("yolo11n.pt")
    # 비디오 영상 불러오기
    cap = cv.VideoCapture(camera_url)

    if not cap.isOpened():
        sys.exit("Cannot open camera")

    # 사람별 색상 저장 딕셔너리
    person_colors = {}

    # 사람 클래스 ID 찾기
    person_class_id = None
    if hasattr(model, "names"):
        for class_id, class_name in model.names.items():
            if class_name == "person":
                person_class_id = class_id
                break

    if person_class_id is None:
        print("Warning: 'person' class not found in YOLO model.")

    # 타이머 설정
    start_time = time.time()
    file = open("log.txt", "a")
    file.write("========Loggin Start========\n")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        results = model.track(frame, persist=True, verbose=False, conf=0.2)

        person_count = 0
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
                    track_id = track_ids[i] if len(track_ids) > 0 else "N/A"

                    # 사람별 색상 생성 (처음 등장하는 사람에 대해서만)
                    if track_id not in person_colors:
                        person_colors[track_id] = (
                            random.randint(0, 255),
                            random.randint(0, 255),
                            random.randint(0, 255),
                        )
                    color = person_colors[track_id]

                    cv.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                    confidence = results[0].boxes.conf[i].cpu().item()
                    label = f"ID: {track_id}"
                    cv.putText(
                        frame, label, (x1, y1 - 10), cv.FONT_HERSHEY_SIMPLEX, 0.5, color, 2
                    )

                    person_count += 1

        cv.putText(
            frame,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            (10, 30),
            cv.FONT_HERSHEY_SIMPLEX,
            1,
            color=(255, 255, 255),
        )

        cv.imshow("Person Tracking by ByteTrack", frame)

        current_time = time.time()
        this_moment = datetime.now()
        if current_time - start_time >= 10:
            print(f"Camera{camera_idx} Detected {person_count} persons at {this_moment}.")
            file.write(
                f"Camera{camera_idx} Detected {person_count} persons at {this_moment}.\n"
            )

            start_time = current_time
            
        key = cv.waitKey(1)
        if key == ord("q"):
            break

    file.write("========Stopped Logging========\n")
    file.close()
    cap.release()
    cv.destroyAllWindows()


if __name__ == '__main__':
    import multiprocessing
    # freeze_support()
    ProcessArr = []

    for idx in range(len(camera_list)):
        ProcessArr.append(multiprocessing.Process(target=ProcessVideo, args = (camera_list[idx],idx)))

    print(ProcessArr)

    for p in ProcessArr:
        p.start()
    
    for p in ProcessArr:
        p.join()
