import os
from flask import Blueprint, redirect, render_template, request, url_for, session, flash
from werkzeug.security import generate_password_hash
from apps.kakao.kakao_controller import Oauth
from apps import db
from apps.kakao.kakao_client import (
    CLIENT_ID,
    CLIENT_SECRET,
    REDIRECT_URI,
    SIGNOUT_REDIRECT_URI,
)
from apps.crud.models import User
from flask_login import login_user
import requests
import json
from apps.auth.forms import RegistrationForm


kakao = Blueprint(
    "kakao", __name__, static_folder="static", template_folder="templates"
)
# 불필요
# @kakao.route("/login")
# def kakao_login_page():
#     """카카오톡 로그인 페이지를 보여주는 라우트"""
#     return render_template("kakao/login.html")


@kakao.route("/")
def kakao_sign_in():
    # 카카오톡 로그인 버튼을 눌렀을때
    kakao_oauth_url = f"https://kauth.kakao.com/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code"

    return redirect(kakao_oauth_url)


@kakao.route("/callback")
def callback():
    code = request.args.get("code")

    if not code:
        print("Authorization code를 받지 못했습니다.")
        return {"message": "인증 실패"}, 400

    oauth = Oauth()
    auth_info = oauth.auth(code)

    if "error" in auth_info:
        print(
            f"에러가 발생했습니다: {auth_info.get('error_description', auth_info['error'])}"
        )
        return {"message": "인증 실패"}, 401

    access_token = auth_info.get("access_token")

    if access_token:
        user_info = oauth.userInfo("Bearer " + access_token)

        if user_info is None:
            print("카카오 사용자 정보를 가져오는데 실패했습니다.")
            return {"message": "사용자 정보 획득 실패"}, 500

        kakao_account = user_info["kakao_account"]
        profile = kakao_account.get("profile")
        name = (
            profile.get("nickname")
            if profile
            else kakao_account.get("nickname", "카카오사용자")
        )
        email = kakao_account.get("email", f"{name}@kakao.com")

        user = User.query.filter_by(email=email).first()

        if user is None:
            # 등록되지 않은 계정인 경우, 세션에 카카오 정보 저장 후 등록 페이지로 리다이렉트
            session["kakao_name"] = name
            session["kakao_email"] = email
            flash(
                "등록되지 않은 카카오 계정입니다. 아래에서 사용자 등록을 진행해주세요.",
                "info",
            )
            return redirect(url_for("kakao.register_form"))
        else:
            user.kakao_access_token = access_token
            db.session.commit()
            login_user(user)
            message = "카카오 계정으로 로그인에 성공하였습니다."
            # 카카오톡 메시지 보내기
            message_url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/x-www-form-urlencoded",
            }
            message_data_default = {
                "object_type": "text",
                "text": "웹 서비스에 로그인되었습니다.",
                "link": {
                    "web_url": url_for("cam.index", _external=True),
                    "mobile_web_url": url_for("cam.index", _external=True),
                },
            }
            template_object = json.dumps(message_data_default, ensure_ascii=False)
            data = {"template_object": template_object}
            try:
                response = requests.post(message_url, headers=headers, data=data)
                response.raise_for_status()
                print("카카오톡 메시지 전송 성공:", response.json())
            except requests.exceptions.RequestException as e:
                print(f"카카오톡 메시지 전송 실패: {e}")
                if hasattr(e.response, "text"):
                    print(f"카카오 API 응답 (Text): {e.response.text}")
                if hasattr(e.response, "json"):
                    try:
                        print(f"카카오 API 응답 (JSON): {e.response.json()}")
                    except json.JSONDecodeError:
                        print("카카오 API 응답 (JSON 디코드 실패)")

            value = {"status": 200, "result": "success", "message": message}
            print(value)
            return redirect(url_for("cam.index"))
    else:
        print("Access token 발급 실패")
        return {"message": "Access token 발급 실패"}, 401


@kakao.route("/register", methods=["GET"])
def register_form():
    """카카오 계정 기반 사용자 등록 폼 표시"""
    form = RegistrationForm()  # auth Blueprint의 RegistrationForm 사용
    kakao_name = session.get("kakao_name")
    kakao_email = session.get("kakao_email")
    return render_template(
        "auth/register_kakao.html",
        form=form,
        kakao_name=kakao_name,
        kakao_email=kakao_email,
    )


@kakao.route("/register", methods=["POST"])
def register_submit():
    """카카오 계정 기반 사용자 등록 처리"""
    form = RegistrationForm()
    if form.validate_on_submit():
        kakao_name = session.get("kakao_name")
        kakao_email = session.get("kakao_email")
        user_id = form.user_id.data
        password = form.password.data

        if not kakao_email:
            flash("카카오 계정 정보를 찾을 수 없습니다. 다시 로그인해주세요.", "kakao_danger")
            return redirect(url_for("kakao.kakao_sign_in"))

        # 이메일로 이미 등록된 사용자가 있는지 확인 (카카오 로그인 외 일반 가입 고려)
        existing_user_by_email = User.query.filter_by(email=kakao_email).first()
        if existing_user_by_email:
            flash(
                "이미 해당 이메일로 등록된 계정이 존재합니다. 일반 로그인 또는 비밀번호 찾기를 이용해주세요.",
                "warning",
            )
            return redirect(url_for("auth.login"))

        # 사용자 ID로 이미 등록된 사용자가 있는지 확인
        existing_user_by_id = User.query.filter_by(user_id=user_id).first()
        if existing_user_by_id:
            flash("이미 사용 중인 아이디입니다.", "kakao_warning")
            return render_template(
                "auth/register_kakao.html",
                form=form,
                kakao_name=kakao_name,
                kakao_email=kakao_email,
            )

        new_user = User(
            user_id=user_id,
            email=kakao_email,
            password=generate_password_hash(password),
            username=kakao_name,
            is_kakao=True,  # 카카오로 가입한 사용자임을 표시
        )
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        session.pop("kakao_name", None)  # 세션에서 카카오 정보 제거
        session.pop("kakao_email", None)
        flash("카카오 계정으로 사용자 등록이 완료되었습니다.", "kakao_success")
        return redirect(url_for("cam.index"))
    else:
        kakao_name = session.get("kakao_name")
        kakao_email = session.get("kakao_email")
        return render_template(
            "auth/register_kakao.html",
            form=form,
            kakao_name=kakao_name,
            kakao_email=kakao_email,
            errors=form.errors,
        )


@kakao.route("/signout")
def kakao_sign_out():
    # 카카오톡으로 로그아웃 버튼을 눌렀을 때
    kakao_logout_url = f"https://kauth.kakao.com/oauth/logout?client_id={CLIENT_ID}&logout_redirect_uri={SIGNOUT_REDIRECT_URI}"

    if session.get("email"):
        session.clear()
        value = {"status": 200, "result": "success"}
    else:
        value = {"status": 404, "result": "fail"}
    print(value)
    return redirect(kakao_logout_url)
