import requests
from core.login_handler import ChaoxingLogin
from core.config import DEFAULT_FID

class ChaoxingSession:
    _instance = None

    def __new__(cls, phone=None, password=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, phone=None, password=None):
        if self._initialized:
            return
        self.phone = phone
        self.password = password
        self.session = requests.Session()
        self.session.trust_env = False  # Disable system proxies to avoid ProxyError
        self.menu_links = {}
        self.course_params = {} # Store extracted course parameters
        self.logged_in = False
        self._initialized = True

    def login(self):
        if not self.logged_in:
            if ChaoxingLogin is None:
                raise ImportError("Cannot login: fanya.ChaoxingLogin is missing.")
            
            fid = self.course_params.get('fid', DEFAULT_FID)
            chaoxing = ChaoxingLogin(self.phone, self.password, fid=fid)
            chaoxing.get_login_page()
            chaoxing.login()
            self.session = chaoxing.session
            self.logged_in = True
            
            # Extract fid from cookies if available to replace the default
            fid_cookie = self.session.cookies.get("fid")
            if fid_cookie:
                self.course_params['fid'] = fid_cookie

        return self.logged_in
