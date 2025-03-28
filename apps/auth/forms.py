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
    
    user_id = StringField(
        "아이디",
        validators=[
            DataRequired("아이디는 필수 입니다."),
            Length(4, 15, "4글자 이상 15글자 이내로 작성해 주세요."),
        ],
    )

    password = PasswordField(
        "비밀번호", validators=[DataRequired("비밀번호는 필수입니다.")]
    )
    submit = SubmitField("신규 등록")


# LoginForm 클래스
class LoginForm(FlaskForm):
    user_id = StringField(
        "아이디",
        validators=[
            DataRequired("아이디 필수입니다."),
        ],
    )
    password = PasswordField(
        "비밀번호",
        validators=[DataRequired("비밀번호는 필수입니다.")],
    )
    submit = SubmitField("로그인")
