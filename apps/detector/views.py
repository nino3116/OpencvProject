# 기업 연계 프로젝트 1
from flask import Flask
import cv2 as cv
from ultralytics import YOLO
import sys


@detector.route("/detect")
def detect_camera():
    ret, frame = cv.VideoCapture("http://192.168.0.124:8000/stream.mjpg")
    if not ret:
        sys.exit("프레임 획득에 실패해 나갑니다.")
    model = YOLO("yolo11n.pt")
