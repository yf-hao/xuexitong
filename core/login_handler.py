import requests
import base64
import re
import time
from Crypto.Cipher import AES
from core.config import DEFAULT_FID

# Global session to match user's logic if needed, 
# although our ChaoxingSession will manage its own instance.
global_session = None

class ChaoxingLogin:
    def __init__(self, phone: str, password: str, fid: str = DEFAULT_FID):
        self.phone = phone
        self.password = password
        self.fid = fid
        self.transfer_key = "u2oh6Vu^HWe4_AES"
        
        global global_session
        if global_session is None:
            self.session = requests.Session()
            self.session.trust_env = False # Disable system proxies
            global_session = self.session
        else:
            self.session = global_session
            self.session.trust_env = False
            
        self.login_page_url = "https://passport2.chaoxing.com/login"
        self.login_post_url = "https://passport2.chaoxing.com/fanyalogin"

    @staticmethod
    def encrypt_by_aes_cbc(message: str, key: str) -> str:
        """
        AES-CBC + PKCS7 padding + Base64 output
        Key and IV use the same key
        """
        key_bytes = key.encode("utf-8")
        iv = key_bytes
        message_bytes = message.encode("utf-8")

        pad_len = 16 - len(message_bytes) % 16
        message_bytes += bytes([pad_len]) * pad_len

        cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
        encrypted_bytes = cipher.encrypt(message_bytes)
        return base64.b64encode(encrypted_bytes).decode("utf-8")

    def get_login_page(self):
        """
        GET login page to initialize Cookies
        """
        params = {"loginType": "4", "fid": self.fid, "newversion": "true", "refer": ""}
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": "Mozilla/5.0",
        }
        resp = self.session.get(
            self.login_page_url, headers=headers, params=params, timeout=15
        )
        if resp.status_code != 200:
            raise Exception(f"GET login page failed: {resp.status_code}")
        return resp

    def login(self):
        """
        POST login request
        """
        phone_enc = self.encrypt_by_aes_cbc(self.phone, self.transfer_key)
        password_enc = self.encrypt_by_aes_cbc(self.password, self.transfer_key)
        
        data_post = {
            "fid": self.fid,
            "uname": phone_enc,
            "password": password_enc,
            "refer": "http%3A%2F%2Fi.mooc.chaoxing.com",
            "t": "true",
            "forbidotherlogin": "0",
            "validate": "",
            "doubleFactorLogin": "0",
            "independentId": "0",
            "independentNameId": "",
        }

        headers_post = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://passport2.chaoxing.com",
            "Referer": f"{self.login_page_url}?loginType=4&fid={self.fid}&newversion=true&refer=",
            "User-Agent": "Mozilla/5.0",
            "X-Requested-With": "XMLHttpRequest",
        }

        resp = self.session.post(
            self.login_post_url, headers=headers_post, data=data_post, timeout=15
        )
        if resp.status_code != 200:
            raise Exception(f"POST login failed: {resp.status_code}")

        return resp.json(), self.session.cookies.get_dict()


class ChaoxingQRCodeLogin:
    """通过学习通登录页的二维码完成认证。"""

    login_page_url = "https://passport2.chaoxing.com/login"
    qr_image_url = "https://passport2.chaoxing.com/createqr"
    status_url = "https://passport2.chaoxing.com/getauthstatus/v2"
    def __init__(self, fid: str = DEFAULT_FID, refer: str = ""):
        self.fid = fid
        self.refer = refer
        self.session = requests.Session()
        self.session.trust_env = False
        self.uuid = ""
        self.enc = ""

    def prepare(self) -> None:
        self.session.close()
        self.session = requests.Session()
        self.session.trust_env = False
        response = self.session.get(
            self.login_page_url,
            params={
                "loginType": "4",
                "fid": self.fid,
                "newversion": "true",
                "refer": self.refer,
                "_": str(time.time_ns()),
            },
            headers={
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "User-Agent": "Mozilla/5.0",
            },
            timeout=15,
        )
        response.raise_for_status()
        self._set_qr_tokens(response.text)

    def get_qr_image(self) -> bytes:
        if not self.uuid:
            raise RuntimeError("二维码参数尚未初始化")
        response = self.session.get(
            self.qr_image_url,
            params={"uuid": self.uuid, "fid": self.fid, "_": str(time.time_ns())},
            headers={
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "User-Agent": "Mozilla/5.0",
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.content

    def poll_status(self) -> dict:
        response = self.session.post(
            self.status_url,
            data={
                "enc": self.enc,
                "uuid": self.uuid,
                "doubleFactorLogin": "0",
                "forbidotherlogin": "0",
            },
            headers={
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "User-Agent": "Mozilla/5.0",
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("二维码登录接口返回格式异常")
        return payload

    def wait_for_login(
        self, status_callback=None, qr_callback=None, stop_event=None
    ) -> requests.Session:
        self.prepare()
        if qr_callback is not None:
            qr_callback(self.get_qr_image())

        for _ in range(50):
            if stop_event is not None and stop_event.is_set():
                raise RuntimeError("二维码登录已取消")
            if stop_event is not None:
                if stop_event.wait(3):
                    raise RuntimeError("二维码登录已取消")
            else:
                time.sleep(3)
            if stop_event is not None and stop_event.is_set():
                raise RuntimeError("二维码登录已取消")
            payload = self.poll_status()
            if payload.get("status"):
                return self.session

            status_type = payload.get("type")
            if status_type == 4:
                if status_callback is not None:
                    status_callback("已扫码，请在学习通 App 中确认登录")
            elif status_type == 6:
                raise RuntimeError("扫码登录已取消")
            elif status_type == 7:
                raise RuntimeError(payload.get("mes") or "二维码登录失败")

        raise TimeoutError("二维码已失效，请刷新后重试")

    def _set_qr_tokens(self, html: str) -> None:
        self.uuid = self._extract_hidden_value(html, "uuid")
        self.enc = self._extract_hidden_value(html, "enc")
        if not self.uuid or not self.enc:
            raise RuntimeError("登录页未返回有效的二维码参数")

    @staticmethod
    def _extract_hidden_value(html: str, field_id: str) -> str:
        pattern = (
            r"<input\b"
            rf"(?=[^>]*\bid=[\"']{re.escape(field_id)}[\"'])"
            r"(?=[^>]*\bvalue=[\"']([^\"']*)[\"'])[^>]*>"
        )
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return match.group(1)
        return ""
