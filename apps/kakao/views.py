import os
from flask import Blueprint, redirect, render_template, request, url_for, session
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

kakao = Blueprint(
    "kakao", __name__, static_folder="static", template_folder="templates"
)


# @kakao.route("/")
# def kakao_sign_in():
#     # 카카오톡 로그인 버튼을 눌렀을때
#     kakao_oauth_url = f"https://kauth.kakao.com/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code"
#     return redirect(kakao_oauth_url)


# @kakao.route("/callback")
# def callback():
#     code = request.args["code"]

#     # 전달받은 authorization code를 통해서 access_token 발급
#     oauth = Oauth()
#     auth_info = oauth.auth(code)

#     # error 발생시 로그인 페이지로 redirect
#     if "error" in auth_info:
#         print("에러가 발생했습니다.")
#         return {"message": "인증 실패"}, 404

#     # 아닐시
#     user = oauth.userInfo("Bearer " + auth_info["access_token"])

#     print(user)
#     kakao_account = user["kakao_account"]
#     profile = kakao_account["profile"]
#     name = profile["nickname"]
#     if "email" in kakao_account:
#         email = kakao_account["email"]
#     else:
#         email = f"{name}@kakao.com"

#     if user is None:
#         # 유저 테이블에 추가
#         user = User(name, email, generate_password_hash(name))
#         db.session.add(user)
#         db.session.commit()

#         message = "회원 가입이 완료되었습니다."
#         value = {"status": 200, "result": "success", "message": message}

#     session["email"] = user.email
#     session["isKakao"] = True
#     message = "로그인에 성공하였습니다."
#     value = {"status": 200, "result": "success", "message": message}
#     print(value)

#     return redirect(url_for("cam.index"))


# @kakao.route("/signout")
# def kakao_sign_out():
#     # 카카오톡으로 로그아웃 버튼을 눌렀을 때
#     kakao_oauth_url = f"https://kauth.kakao.com/oauth/logout?client_id={CLIENT_ID}&logout_redirect_uri={SIGNOUT_REDIRECT_URI}"


#     if session.get("email"):
#         session.clear()
#         value = {"status": 200, "result": "success"}
#     else:
#         value = {"status": 404, "result": "fail"}
#     print(value)
#     return redirect(kakao_oauth_url)
@kakao.route("/login")
def kakao_login_page():
    """카카오톡 로그인 페이지를 보여주는 라우트"""
    return render_template("kakao/login.html")


@kakao.route("/")
def kakao_sign_in():
    # 카카오톡 로그인 버튼을 눌렀을때
    # kakao_oauth_url = f"https://kauth.kakao.com/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code"
    kakao_oauth_url = f"https://kauth.kakao.com/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=account_email,profile_nickname,talk_message"
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

        print(user_info)
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
            user = User(
                user_id=email,
                username=name,
                email=email,
                password=generate_password_hash(name),
                is_kakao=True,
            )
            db.session.add(user)
            db.session.commit()
            login_user(user)
            message = "카카오 계정으로 회원 가입 및 로그인이 완료되었습니다."
        else:
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

        session["email"] = user.email
        session["is_kakao"] = True

        value = {"status": 200, "result": "success", "message": message}
        print(value)
        return redirect(url_for("cam.index"))
    else:
        print("Access token 발급 실패")
        return {"message": "Access token 발급 실패"}, 401


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
