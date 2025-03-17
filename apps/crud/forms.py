# 기업 연계 프로젝트 1
from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length


# 사용자 신규 작성과 사용자 편집 폼 클래스
class UserForm(FlaskForm):
    # 사용자 폼의 username 속성의 라벨과 검증 설정
    username = StringField(
        name="사용자명",
        validators=[
            DataRequired(message="사용자명은 필수 입니다."),
            Length(min=2, max=25, message="사용자명은 2자 이상 입력해주세요"),
        ],
    )

    # user_id 속성의 레이블과 검증 설정
    user_id = StringField(
        name="사용자 ID",
        validators=[
            DataRequired(message="아이디는 필수 입니다."),
        ],
    )

    # email 속성의 레이블과 검증 설정
    email = StringField(
        name="이메일",
        validators=[
            DataRequired(message="이메일 주소는 필수 입니다."),
            Email(message="메일주소 형식으로 입력해 주세요."),
        ],
    )

    # 사용자 폼의 PasswordField
    password = PasswordField(
        name="비밀번호",
        validators=[DataRequired(message="비밀번호는 필수 입니다.")],
    )

    # 사용자 폼의 submit 문자를 설정
    submit = SubmitField("신규등록")
