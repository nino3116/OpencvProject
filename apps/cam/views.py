# 기업 연계 프로젝트 1
from flask import Flask, Blueprint, render_template, redirect
import cv2 as cv
from ultralytics import YOLO
import sys

cam = Blueprint(
    "cam",
    __name__,
    template_folder="templates",
)


@cam.route("/")
def index():
    return render_template("cam/index.html")


@cam.route("/cam")
def detect_camera():
    ret, frame = cv.VideoCapture("http://192.168.0.124:8000/stream.mjpg")
    if not ret:
        sys.exit("프레임 획득에 실패해 나갑니다.")
    model = YOLO("yolo11n.pt")
