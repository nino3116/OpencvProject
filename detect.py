import cv2 as cv
import sys
import numpy as np
from ultralytics import YOLO
import random
import time
from datetime import datetime

# YOLO 모델 불러오기
model = YOLO("yolo11n.pt")

# 비디오 영상 불러오기
cap = cv.VideoCapture("http://192.168.0.124:8000/stream.mjpg")
# cap = cv.VideoCapture("http://192.168.0.125:8000/stream.mjpg")

if not cap.isOpened():
    sys.exit("Cannot open camera")

# 클래스별 색상 생성 (랜덤 색상)
class_colors = {}

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

while cap.isOpened():
    # 프레임 읽기
    ret, frame = cap.read()
    if not ret:
        break

    # 물체 감지 및 추적 수행 (ByteTrack 사용)
    results = model.track(frame, persist=True, verbose=False, conf=0.3)

    # 추적 결과 처리 (사람만 필터링)
    person_count = 0  # 매 프레임마다 감지된 사람 수를 저장할 변수 초기화
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
                # 클래스별 색상 생성 (처음 등장하는 클래스에 대해서만)
                if person_class_id not in class_colors:
                    class_colors[person_class_id] = (
                        random.randint(0, 255),
                        random.randint(0, 255),
                        random.randint(0, 255),
                    )
                color = class_colors[person_class_id]

                # 바운딩 박스 그리기
                cv.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                # 클래스 이름과 신뢰도 표시 (좌측 상단)
                confidence = results[0].boxes.conf[i].cpu().item()
                label = f"person ID: {track_id}"
                cv.putText(
                    frame, label, (x1, y1 - 10), cv.FONT_HERSHEY_SIMPLEX, 0.5, color, 2
                )

                # 사람 감지 카운트 (매 프레임마다)
                person_count += 1

    # 10초마다 감지 결과 출력
    current_time = time.time()
    this_moment = datetime.now()
    if current_time - start_time >= 10:
        print(f"Detected {person_count} persons at {this_moment}.")  # 수정된 부분
        start_time = current_time

    # 결과 이미지 표시
    cv.imshow("Person Tracking by ByteTrack", frame)
    key = cv.waitKey(1)
    if key == ord("q"):
        break

cap.release()
cv.destroyAllWindows()
