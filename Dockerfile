#베이스 이미지의 지정
FROM python:3.9.13

#apt-get의 version을 갱신하고, SQLite3를 설치
RUN apt-get update && apt-get install -y sqlite3 && apt-get install -y libsqlite3-dev && apt-get install -y libgl1-mesa-glx &&apt-get clean

# 컨테이너의 워킹 디렉터리의 지정
WORKDIR /usr/src/

# 디렉터리와 파일의 복사
COPY ./apps /usr/src/apps                           
COPY ./S3upload /usr/src/S3upload                           
COPY ./libopenh264-1.8.0-linux64.4.so /usr/src/libopenh264-1.8.0-linux64.4.so                           

COPY ./requirements.txt /usr/src/requirements.txt
COPY ./yolo11n.pt /usr/src/yolo11n.pt

#pip의 version 갱신
RUN pip install --upgrade pip 

#필요한 라이브러리를 컨테이너 내의 환경에 설치
RUN pip install -r requirements.txt

# "builing..."표시하는 처리 
RUN echo "building..."

# 필요한 각 환경 변수 설정
ENV FLASK_APP="apps.app:create_app('deploy')"

# 특정 네트워크 포트를 컨테이너가 실행 시 Listen
EXPOSE 5000

# "docker run"명령어 실행 시 실행되는 명령어
CMD [ "flask", "run", "-h", "0.0.0.0"]

# Dockerfile을 통해서 Container 이미지를 생성
# FROM 도커이미지를 불러와 베이스 이미지로...
# FROM python:3.9

# # RUN은 이미지에서 실행시킬 명령어를 처리함. 
# RUN apt-get update && apt-get install -y sqlite3
# RUN apt-get install -y libsqlite3-dev
# RUN apt-get install -y libgl1-mesa-glx
# RUN apt-get clean

# # 컨테이너의 작업 디렉터리를 지정
# WORKDIR /application

# # COPY를 통해서 디렉터리 파일을 복사(이미지로...)
# COPY ./apps /application/apps
# COPY ./local.sqlite /application/local.sqlite
# COPY ./model.pt /application/apps/detector/model.pt
# COPY ./migrations /application/migrations
# COPY ./requirements-docker1.txt /application/requirements.txt

# RUN pip install --upgrade pip

# RUN pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# RUN pip install -r requirements.txt

# # ENV는 환경 변수 설정 - 컨테이너 내에 환경변수 설정
# ENV FLASK_APP="apps.app:create_app('local')"
# ENV IMAGE_URL="/storage/images/"

# # 특정 네트워크 포트를 컨테이너 실행 시 Listen
# EXPOSE 5000

# # 컨테이너 실행시(docker run시) 실행 시 명령어 설정
# CMD ["flask","run","-h","0.0.0.0"]