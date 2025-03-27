from pathlib import Path

SECRET_KEY = "DM5Fq1G9XtMzWAeqYWNR"
SQLALCHEMY_DATABASE_URI = f"sqlite:///{Path(__file__).parent.parent / 'local.sqlite'}"
# __file__ : 현재파일인 경로를 알려준다.
SQLALCHEMY_TRACK_MODIFICATIONS = False
# SQL 콘솔 로그에 출력
SQLALCHEMY_ECHO = True
WTF_CSRF_SECRET_KEY = "El1oD921KMdGKONsydDa"
