# 기업 연계 프로젝트 1
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, URL

# 카메라 등록 폼 클래스


class CameraAddForm(FlaskForm):
    name = StringField(
        "카메라 이름", validators=[DataRequired("카메라 이름은 필수 입니다.")]
    )
    group = StringField(
        "카메라 그룹",
        validators=[DataRequired("카메라 그룹은 필수 입니다.")],
    )
    url = StringField(
        "카메라 영상 주소",
        validators=[DataRequired("카메라 영상 주소는 필수 입니다.")],
    )
    submit = SubmitField("카메라 등록")
