# 기업 연계 프로젝트 1

from flask_wtf import FlaskForm  # type: ignore
from wtforms import PasswordField, StringField, SubmitField  # type: ignore
from wtforms.validators import DataRequired, Email, Length  # type: ignore


# 사용자 신규 작성과 사용자 편집 폼 클래스
class UserForm(FlaskForm):
    # 사용자 폼의 username 속성의 라벨과 검증 설정
    username = StringField(
        "사용자명",
        validators=[
            DataRequired(message="사용자명은 필수입니다."),
            Length(min=2, max=30, message="최소 2글자부터 30문자 이내로 입력하세요"),
        ],
    )

     # user_id 속성의 레이블과 검증 설정
    user_id = StringField(
        name="아이디",
        validators=[
            DataRequired(message="아이디는 필수 입니다."),
            Length(min=4, max=15, message="최소 2글자부터 20문자 이내로 입력하세요"),
        ],
    )
        
    # # email 속성의 레이블과 검증 설정
    # email = StringField(
    #     "메일 주소",
    #     validators=[
    #         DataRequired(message="메일 주소는 필수입니다."),
    #         Email(message="메일 주소의 형식으로 입력해 주세요."),
    #     ],
    # )

    # 사용자 폼의 password 속성의 레이블과 검증 설정
    password = PasswordField(
        "비밀번호",
        validators=[DataRequired(message="비밀번호는 필수 입니다.")],
    )

    # 사용자 폼의 submit의 문자를 설정
    submit = SubmitField("신규 등록")
