import smtplib  # Import for email functionality
from email.mime.text import MIMEText  # Import for email message creation
from email.mime.multipart import MIMEMultipart
from email_config import EMAIL_PASSWORD, EMAIL_RECEIVER, EMAIL_SENDER

import traceback, logging

def send_email(subject, body):
    """Sends an email with the given subject and body."""
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECEIVER

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:  # Use Gmail SMTP
            smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
            smtp.send_message(msg)
        logging.info("Email sent successfully!")
    except Exception as e:
        logging.error(f"Failed to send email: {e}")
        traceback.print_exc()


def send_html_email(info, to_email):

    # # 다운로드 링크 생성
    # download_url = f"http://yourserver.com/videos/{info['filename']}"

    # HTML 템플릿에 데이터 삽입
    html_template = open("./email_template.html", "r", encoding="utf-8").read()
    html_content = (
        html_template.replace("{{event}}", info["event"]).replace(
            "{{timestamp}}", info["timestamp"]
        )
        # .replace("{{filename}}", info["filename"])
        # .replace("{{download_url}}", download_url)
    )

    # 이메일 구성
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[경고] {info['event']} - {info['timestamp']}"
    msg["From"] = EMAIL_SENDER
    msg["To"] = to_email
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
            print("이메일 전송 성공")
    except Exception as e:
        print("이메일 전송 실패:", e)
