import requests
from app.kakao_client import (
    CLIENT_ID,
    CLIENT_SECRET,
    REDIRECT_URI,
    SIGNOUT_REDIRECT_URI,
)


class Oauth:
    def __init__(self):
        self.auth_server = "https://kauth.kakao.com"
        self.api_server = "https://kapi.kakao.com"
        self.default_header = {
            "Content-type": "application/x-www-form-urlencoded;charset=utf-8",
            "Cache-Control": "no-cache",
        }

    def auth(self, code):
        return requests.post(
            url=self.auth_server % "/oauth/token",
            headers=self.default_header,
            date={
                "grant_type": "authorization_code",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
                "code": code,
            },
        ).json()

    def userInfo(self, bearer_token):
        return requests.post(
            url=self.api_server % "/v2/user/me",
            headers={
                **self.default_header,
                **{"Authorization": bearer_token},
            },
            # "property_keys": '["kakao_account.profile_image_url"]
            data={},
        ).json()
