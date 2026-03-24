import requests
import base64
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
        resp = self.session.get(self.login_page_url, headers=headers, params=params)
        if resp.status_code != 200:
            raise Exception(f"GET login page failed: {resp.status_code}")
        return resp

    def login(self):
        """
        POST login request
        """
        password_enc = self.encrypt_by_aes_cbc(self.password, self.transfer_key)
        
        data_post = {
            "fid": self.fid,
            "uname": self.phone,
            "password": password_enc,
            "refer": "http%3A%2F%2Fi.mooc.chaoxing.com",
            "t": "true",
            "forbidotherlogin": "0",
            "validate": "",
            "doubleFactorLogin": "0",
            "independentId": "0",
        }

        headers_post = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://passport2.chaoxing.com",
            "Referer": f"{self.login_page_url}?loginType=4&fid={self.fid}&newversion=true&refer=",
            "User-Agent": "Mozilla/5.0",
            "X-Requested-With": "XMLHttpRequest",
        }

        resp = self.session.post(self.login_post_url, headers=headers_post, data=data_post)
        if resp.status_code != 200:
            raise Exception(f"POST login failed: {resp.status_code}")

        return resp.json(), self.session.cookies.get_dict()
