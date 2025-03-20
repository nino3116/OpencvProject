# 기업 연계 프로젝트 1

from flask import Blueprint, redirect, render_template, url_for

from apps.app import db

from apps.cam.models import Cam

from flask_login import login_required

# Blueprint로 crud 앱을 생성한다.
cam = Blueprint(
    "cam",
    __name__,
    static_folder="static",
    template_folder="templates",
)

@cam.route('/')
@login_required
def index():
    cams = Cam.query.all()
    return render_template("cam/index.html", cams=cams)

# 새로운 데이터 추가 (AJAX)
@cam.route('/add', methods=['POST'])
@login_required
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
@cam.route('/update/<int:id>', methods=['POST'])
@login_required
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
@cam.route('/delete/<int:id>', methods=['POST'])
@login_required
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