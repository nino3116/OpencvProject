# 기업 연계 프로젝트 1
from flask_wtf import FlaskForm  # type: ignore
from wtforms import PasswordField, StringField, SubmitField  # type: ignore
from wtforms.validators import DataRequired, Email, Length  # type: ignore


#
class SignUpForm(FlaskForm):
    username = StringField(
        "사용자명",
        validators=[
            DataRequired("사용자명은 필수 입니다."),
            Length(2, 30, "2글자 이상 30글자 이내로 작성해 주세요."),
        ],
    )

    email = StringField(
        "메일 주소",
        validators=[
            DataRequired("메일 주소는 필수 입니다."),
            Email("메일 주소 형식으로 입력해 주세요."),
        ],
    )

    password = PasswordField(
        "비밀번호", validators=[DataRequired("비밀번호는 필수입니다.")]
    )
    submit = SubmitField("신규 등록")


# LoginForm 클래스
class LoginForm(FlaskForm):
    email = StringField(
        "메일 주소",
        validators=[
            DataRequired("이메일 주소는 필수입니다."),
            Email("이메일 주소 형식으로 입력하세요."),
        ],
    )
    password = PasswordField(
        "비밀번호",
        validators=[DataRequired("비밀번호는 필수입니다.")],
    )
    submit = SubmitField("로그인")
