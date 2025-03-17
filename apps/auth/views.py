# 기업 연계 프로젝트 1
# redirect, url_for, request, flash 추가
from flask import Blueprint, flash, redirect, render_template, request, url_for

# 등록 정보를 세션에 공유
from flask_login import login_user, logout_user

# db작업을 위한 db 객체 import
from apps.app import db

# 폼 클래스 import
from apps.auth.forms import LoginForm, SignUpForm

# 사용자 객체 정보를 위한 정보 User import
from apps.crud.models import User

# Blueprint를 사용하여 auth를 생성
auth = Blueprint(
    "auth",
    __name__,
    static_folder="static",
    template_folder="templates",
)


# 테스트를 위한 엔드포인트
@auth.route("/")
def index():
    return render_template("auth/index.html")


# 회원가입을 위한 엔드포인트
@auth.route("/signup", methods=["GET", "POST"])
def signup():
    # SignUpForm 객체 생성
    form = SignUpForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            user_id=form.user_id.data,
            email=form.email.data,
            password=form.password.data,
        )

        # 이메일 중복 체크 : 중복시 GET으로 signup으로 전달
        if user.is_duplicate_email():
            flash("지정 이메일 주소는 이미 등록되어 있습니다.")
            return redirect(url_for("auth.signup"))

        # 아이디 중복 체크 : 중복시 GET으로 singup으로 전달
        if user.is_duplicate_id():
            flash("지정 아이디는 이미 등록되어 있습니다.")
            return redirect(url_for("auth.signup"))

        # DB등록
        db.session.add(user)
        db.session.commit()

        # 사용자 정보를 세션에 저장
        login_user(user)
        # GET 파라미터에 next키가 존재하고, 값이 없는 경우 사용자의 일람 페이지로 리다이렉트
        # GET 파라미터 next에는 다음으로 이동할 경로 정보를 담는다.
        # 회원가입 완료 시의 리다이렉트될 곳을 detector.index로 변경한다
        next_ = request.args.get("next")
        # next가 비어 있거나, "/"로 시작하지 않는 경우 -> 상대경로 접근X.
        if next_ is None or not next_.startswith("/"):
            # next의 값을 엔드포인트 crud.users로 지정
            next_ = url_for("detector.index")
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
        # 이메일 주소로 데이터베이스에 사용자 있는지 확인.
        user = User.query.filter_by(email=form.email.data).first()

        # 사용자가 존재하고, 비밀번호가 일치하면 로그인 처리
        if user is not None and user.verify_password(password=form.password.data):
            login_user(user)  # 로그인 처리(LoginManager에 등록)
            return redirect(url_for("detector.index"))

        # 로그인 실패시 메시지를 설정
        flash("메일 주소 또는 비밀번호가 일치하지 않습니다.")

    return render_template("auth/login.html", form=form)


# 로그아웃 엔드포인트
@auth.route("/logout")
def logout():
    logout_user()  # 로그아웃 -> 등록된 사용자 정보를 제거
    return redirect(url_for("auth.login"))
