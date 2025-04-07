from flask import Blueprint, redirect, request, url_for, session, render_template
from google_auth_oauthlib.flow import Flow  #type:ignore
# import google.auth.transport.requests
import requests  #type:ignore

from apps.google.google_client import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_DISCOVERY_URL


google = Blueprint(
    "google", __name__, static_folder='static', template_folder='templates'
)


flow = Flow.from_client_secrets_file(
    client_secrets_file='client_secret.json',  # 클라이언트 보안 비밀 파일 경로
    scopes=['https://www.googleapis.com/auth/userinfo.profile', 'https://www.googleapis.com/auth/userinfo.email'],
    redirect_uri='http://127.0.0.1:5000/google/callback'
)


@google.route('/login')
def google_login():
    authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')
    session['state'] = state
    return redirect(authorization_url)

@google.route('/callback')
def google_callback():
    state = session['state']
    flow.fetch_token(authorization_response=request.url)
    if not state == request.args['state']:
        return 'Invalid state parameter', 401

    credentials = flow.credentials
    request_session = requests.session()
    cached_request = google.auth.transport.requests.AuthorizedSession(credentials, request_session)

    user_info = cached_request.get(GOOGLE_DISCOVERY_URL).json()

    # 사용자 정보 처리 (예: 데이터베이스에 저장, 세션 설정 등)
    session['google_id'] = user_info['sub']
    session['google_name'] = user_info['name']
    session['google_email'] = user_info['email']

    return redirect(url_for('index'))  # 로그인 후 이동할 페이지


@google.route('/')
def index():
    if 'google_id' in session:
        return f'Welcome, {session["google_name"]}! <a href="/google/logout">Logout</a>'
    else:
        return '<a href="/google/login">Login with Google</a>'

@goole.route('/logout')
def google_logout():
    session.pop('google_id', None)
    session.pop('google_name', None)
    session.pop('google_email', None)
    return redirect(url_for('index'))