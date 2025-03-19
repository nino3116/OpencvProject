import os
import datetime
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate  #type: ignore
import pytz  # 타임존 변환 라이브러리


app = Flask(__name__)


# MySQL 연결 설정하기 
# app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:root1234@localhost:3306/camera'
# app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://root:"root1234"@localhost:3306/camera'
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{Path(__file__).parent.parent / 'local.sqlite'}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


db = SQLAlchemy(app)

# 마이그레이션 설정하기 
Migrate(app, db)


# 저장할 이미지 경로 설정하기
IMAGE_SAVE_PATH = 'capture_images'
if not os.path.exists(IMAGE_SAVE_PATH):
    os.mkdir(IMAGE_SAVE_PATH)

# 한국 시간 설정
KST = pytz.timezone('Asia/Seoul')

# DB 모델 설정하기
class Cam(db.Model):
    __tablename__ ='camera'
    id = db.Column(db.Integer, primary_key=True)
    cam_name = db.Column(db.String(255), nullable=False)
    cam_group = db.Column(db.String(255))
    num_person = db.Column(db.Integer)
    create_At = db.Column(db.DateTime, default = datetime.datetime.now(KST))
    update_At = db.Column(db.DateTime, default = datetime.datetime.now(KST), onupdate=datetime.datetime.now(KST))
    

@app.route('/')
def index():
    cams = Cam.query.all()
    return render_template("index.html", cams=cams)

# 새로운 데이터 추가 (AJAX)
@app.route('/add', methods=['POST'])
def add_cam():
    data = request.get_json(force=True)
    new_cam = Cam(
        cam_name = data['cam_name'],
        cam_group = data.get('cam_group'),
        num_person = data.get('num_person', 0)
    )
    db.session.add(new_cam)
    db.session.commit()
    
    save_image(new_cam.id)  # 파일 생성
    return jsonify({'message': '카메라 추가 성공!'})

# 데이터 수정 (AJAX)
@app.route('/update/<int:id>', methods=['POST'])
def update_cam(id):
    cam = Cam.query.get(id)
    if not cam:
        return jsonify({'message': '카메라 없음'}), 404

    data = request.get_json(force=True)
    cam.cam_name = data.get('cam_name', cam.cam_name)
    cam.cam_group = data.get('cam_group', cam.cam_group)
    cam.num_person = data.get('num_person', cam.num_person)

    db.session.commit()
    
    save_image(cam.id)  # 파일 생성
    return jsonify({'message': '카메라 수정 성공!'})

# 데이터 삭제 (AJAX)
@app.route('/delete/<int:id>', methods=['POST'])
def delete_cam(id):
    cam = Cam.query.get(id)
    if not cam:
        return jsonify({'message': '카메라 없음'}), 404

    db.session.delete(cam)
    db.session.commit()
    return jsonify({'message': '카메라 삭제 성공!'})

# 파일 저장 함수 (이미지 캡처)
def save_image(cam_id):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"cam_{cam_id}_{timestamp}.jpg"
    filepath = os.path.join(IMAGE_SAVE_PATH, filename)

    # 더미 이미지 생성 (실제 환경에서는 캡처된 이미지 저장)
    with open(filepath, "wb") as f:
        f.write(os.urandom(1024))  # 임의의 데이터를 넣어 더미 이미지 생성

    print(f"이미지 저장됨: {filepath}")


    

    






