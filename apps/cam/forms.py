# 기업 연계 프로젝트 1
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, DateField
from wtforms.validators import DataRequired, URL, Optional

# 카메라 등록 폼 클래스


class CameraForm(FlaskForm):
    cam_name = StringField(
        "카메라 이름", validators=[DataRequired("카메라 이름은 필수 입니다.")]
    )
    cam_url = StringField(
        "카메라 영상 주소",
        validators=[DataRequired("카메라 영상 주소는 필수 입니다.")],
    )
    submit = SubmitField("카메라 등록")


class DeleteCameraForm(FlaskForm):
    submit = SubmitField("삭제")


class VideoSearchForm(FlaskForm):
    camera_name = SelectField(
        "카메라 이름", choices=[("", "전체")], validators=[Optional()]
    )
    date = DateField("날짜 (YYYY-MM-DD)", validators=[Optional()])
    submit = SubmitField("검색")
