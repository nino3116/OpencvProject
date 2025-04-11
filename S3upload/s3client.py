import os
import boto3
from datetime import datetime
from S3upload.s3_config import ACCESS_KEY_ID, SECRET_ACCESS_KEY, DEFAULT_REGION, BUCKET

s3client = boto3.client(
    "s3",
    aws_access_key_id=ACCESS_KEY_ID,
    aws_secret_access_key=SECRET_ACCESS_KEY,
    region_name=DEFAULT_REGION,
)


def upload_file(file_name, key):
    try:
        s3client.upload_file(file_name, BUCKET, key)
        print(f"S3 버킷 '{BUCKET}'에 {file_name}를 {key}로 업로드했습니다.")
    except FileNotFoundError:
        print(f"Error: 파일 '{file_name}'을 찾을 수 없습니다.")
    except Exception as e:
        print(f"S3 업로드 오류: {e}")


def download_file(key, file_name):
    try:
        s3client.download_file(bucket, key, file_name)
        print(f"S3 버킷 '{BUCKET}'에서 {key}를 {file_name}로 다운로드했습니다.")
    except FileNotFoundError:
        print(f"Error: 파일 '{file_name}'을 찾을 수 없습니다.")

    except Exception as e:
        print(f"S3 다운로드 오류: {e}")


def delete_file(key):
    try:
        s3client.delete_object(Bucket=BUCKET, Key=key)
        print(f"S3 버킷 '{BUCKET}' 에서 {key}를 삭제했습니다.")
    except FileNotFoundError:
        print(f"Error: 파일 '{file_name}'을 찾을 수 없습니다.")
    except Exception as e:
        print(f"S3 삭제 오류: {e}")


def generate_presigned_url(key, operation="get_object", expiry=3600):
    """
    S3 객체에 대한 presigned URL을 생성합니다.

    Args:
        key (str): S3 객체 키.
        operation (str): 수행할 S3 작업 ('get_object', 'put_object' 등). 기본값은 'get_object'.
        expiry (int): URL 만료 시간 (초). 기본값은 3600초 (1시간).

    Returns:
        str: 생성된 presigned URL. None인 경우 오류 발생.
    """
    try:
        url = s3client.generate_presigned_url(
            ClientMethod=operation,
            Params={"Bucket": BUCKET, "Key": key},
            ExpiresIn=expiry,
        )
        return url
    except Exception as e:
        print(f"Presigned URL 생성 오류 ({operation}): {e}")
        return None
