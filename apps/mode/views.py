# redirect, url_for, request, flash 추가
from flask import Blueprint, flash, redirect, render_template, request, url_for

# 로그아웃을 위한 import
# 등록 정보를 세션에 공유
from flask_login import login_user  # type: ignore
from flask_login import logout_user
from flask_login import login_required  # type: ignore

import pymysql
from Process.dbconfig import dbconnect

from apps.mode.forms import ScheduleForm

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
    conn = dbconnect()
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute("select * from mode_schedule")
    schedules = cur.fetchall()
    return render_template("mode/index.html", schedules=schedules)

@mode.route("/schedule/", methods=["GET", "POST"])
@login_required
def schedule():
    form = ScheduleForm()
    if form.validate_on_submit():
        # GET 파라미터 next에는 다음으로 이동할 경로 정보를 담는다.
        next_ = request.args.get("next")
        # next가 비어 있거나, "/"로 시작하지 않는 경우 -> 상대경로 접근X.
        if next_ is None or not next_.startswith("/"):
            # next의 값을 엔드포인트 crud.users로 지정
            next_ = url_for("mode.index")
        # redirect
        return redirect(next_)
    return render_template("mode/schedule.html",form=form)