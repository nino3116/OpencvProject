# 기업 연계 프로젝트 1

# redirect, url_for, request, flash 추가
from flask import Blueprint, flash, redirect, render_template, request, url_for

# 로그아웃을 위한 import
# 등록 정보를 세션에 공유
from flask_login import login_user  # type: ignore
from flask_login import logout_user

# db작업을 위한 db 객체 import
from apps import db

# 폼 클래스 import
from apps.auth.forms import LoginForm, SignUpForm

# 사용자 객체 정보를 위한 정보 User import
from apps.crud.models import User

# 파이썬에서 정규 표현식 사용을 위한 re 모듈 import
import re

# Blueprint를 사용하여 auth를 생성
auth = Blueprint(
    "auth",
    __name__,
    static_folder="static",
    template_folder="templates",
)


# 회원가입을 위한 엔드포인트
@auth.route("/signup/", methods=["GET", "POST"])
def signup():
    # SignUpForm 객체 생성
    form = SignUpForm()
    if form.validate_on_submit():
        user = User(
            user_id=form.user_id.data,
            username=form.username.data,
            password=form.password.data,
        )
        
        if user.is_duplicate_user_id():
            flash("지정 아이디는 이미 등록되어 있습니다.")
            return redirect(url_for("auth.signup"))

       
        if not re.match(r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}", form.password.data):
                flash("비밀번호는 영문, 숫자, 특수문자를 포함해야 합니다.")
                return redirect(url_for("auth.signup"))
            
        try:
            # DB등록
            db.session.add(user)
            db.session.commit()
            print("회원가입 성공","success")
        except Exception as e:
            print(f"회원가입 종 오류발생: {e}", "danger")
            db.session.rollback()
            return redirect(url_for("auth.signup"))

        # 사용자 정보를 세션에 저장
        login_user(user)
        # GET 파라미터에 next키가 존재하고, 값이 없는 경우 사용자의 일람 페이지로 리다이렉트
        # GET 파라미터 next에는 다음으로 이동할 경로 정보를 담는다.
        next_ = request.args.get("next")
        # next가 비어 있거나, "/"로 시작하지 않는 경우 -> 상대경로 접근X.
        if next_ is None or not next_.startswith("/"):
            # next의 값을 엔드포인트 crud.users로 지정
            next_ = url_for("auth.login")
        # redirect
        return redirect(next_)
    return render_template("auth/signup.html", form=form)


# 로그인 엔드포인트
@auth.route("/login", methods=["GET", "POST"])
def login():
    # LoginForm 객체 생성
    form = LoginForm()

    # auth/login.html에서 submit 처리한 경우..(post로 전달)
    if form.validate_on_submit():
        # 아이디로 데이터베이스에 사용자 있는지 확인.
        user = User.query.filter_by(user_id=form.user_id.data).first()

        # 사용자가 존재하고, 비밀번호가 일치하면 로그인 처리
        if user is not None and user.verify_password(password=form.password.data):
            login_user(user)  # 로그인 처리(LoginManager에 등록)
            return redirect(url_for("cam.index"))

        # 로그인 실패시 메시지를 설정
        flash("아이디 또는 비밀번호가 일치하지 않습니다.")
    return render_template("auth/login.html", form=form)


# 로그아웃 엔드포인트
@auth.route("/logout")
def logout():
    logout_user()  # 로그아웃
    return redirect(url_for("auth.login"))
