# redirect, url_for, request, flash 추가
from flask import Blueprint, flash, redirect, render_template, request, url_for


# 등록 정보를 세션에 공유
from flask_login import login_required, current_user  # type: ignore
from flask_login import login_required, current_user  # type: ignore

import pymysql


# from Process.dbconfig import dbconnect
from apps.app import db
from apps.mode.forms import ScheduleForm, DeleteScheduleForm
from apps.mode.models import ModeSchedule

from apps.kakao.kakao_client import CLIENT_ID, CLIENT_SECRET
from apps.kakao.kakao_controller import Oauth
import requests
import json


# Blueprint로 crud 앱을 생성한다.
mode = Blueprint(
    "mode",
    __name__,
    static_folder="static",
    template_folder="templates",
)


@mode.route("/")
@login_required
def index():
    #  conn = dbconnect()
    # cur = conn.cursor(pymysql.cursors.DictCursor)
    # cur.execute("select * from mode_schedule")
    # schedules = cur.fetchall()#
    schedules = ModeSchedule.query.all()
    delete_form = DeleteScheduleForm()
    print(f"가져온 스케줄 목록: {schedules}")  # 추가
    return render_template("mode/index.html", schedules=schedules, form=delete_form)


@mode.route("/schedule", methods=["GET", "POST"])
@login_required
def schedule():
    form = ScheduleForm()
    if form.validate_on_submit():
        schedule = ModeSchedule(
            mode_type=form.mode_type.data,
            people_cnt=form.people_cnt.data,
            rep_name=form.rep_name.data,
            start_time=form.start_time.data,
            end_time=form.end_time.data,
            memo=form.memo.data,
        )
        db.session.add(schedule)
        db.session.commit()

        # 현재 로그인한 사용자가 카카오 계정으로 로그인했고 Access Token이 있는 경우
        if (
            current_user.is_authenticated
            and getattr(current_user, "is_kakao", True)
            and getattr(current_user, "kakao_access_token", None)
        ):
            access_token = current_user.kakao_access_token
            message_url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/x-www-form-urlencoded",
            }
            message_data_default = {
                "object_type": "text",
                "text": f"새로운 스케줄이 추가되었습니다.\n\n모드 종류: {schedule.mode_type}\n인원 수: {schedule.people_cnt}\n담당자: {schedule.rep_name}\n시작 시간: {schedule.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n종료 시간: {schedule.end_time.strftime('%Y-%m-%d %H:%M:%S')}\n메모: {schedule.memo or '-'}",
                "link": {
                    "web_url": url_for("mode.index", _external=True),
                    "mobile_web_url": url_for("mode.index", _external=True),
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
        else:
            print("카카오 계정으로 로그인되지 않았거나 Access Token이 없습니다.")

        # GET 파라미터 next에는 다음으로 이동할 경로 정보를 담는다.
        next_ = request.args.get("next")
        # next가 비어 있거나, "/"로 시작하지 않는 경우 -> 상대경로 접근X.
        if next_ is None or not next_.startswith("/"):
            # next의 값을 엔드포인트 crud.users로 지정
            next_ = url_for("mode.index")
        # redirect
        return redirect(next_)
    return render_template("mode/schedule.html", form=form)


@mode.route("/schedule/delete/<int:schedule_id>", methods=["POST"])
def delete_schedule(schedule_id):
    schedule_to_delete = ModeSchedule.query.get_or_404(schedule_id)
    db.session.delete(schedule_to_delete)
    db.session.commit()
    return redirect(url_for("mode.index"))


@mode.route("/schedules/<int:schedule_id>")
@login_required
def mode_logs(schedule_id):
    schedule = ModeSchedule.query.get_or_404(schedule_id)
    return render_template("mode/modeLogs.html", schedule=schedule)
