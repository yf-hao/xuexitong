from core.config import DEFAULT_FID
from core.login_handler import ChaoxingQRCodeLogin


class AuthAPI:
    """登录态相关接口。"""

    def login_by_password(self, phone, password, fid=DEFAULT_FID) -> bool:
        """
        Implement password login logic using ChaoxingSession.
        """
        self.session_manager.phone = phone
        self.session_manager.password = password
        self.session_manager.course_params['fid'] = fid
        self.last_login_error = ""
        try:
            self.is_logged_in = self.session_manager.login()
        except Exception as e:
            print(f"Login failed: {e}")
            self.is_logged_in = False
            self.last_login_error = str(e)
        return self.is_logged_in

    def logout(self):
        self.session.cookies.clear()
        self.session_manager.logged_in = False
        self.is_logged_in = False

    def login_by_qrcode(
        self, status_callback=None, qr_callback=None, stop_event=None
    ) -> bool:
        """使用二维码认证，并复用现有业务会话。"""
        qr_login = ChaoxingQRCodeLogin(
            fid=self.session_manager.course_params.get("fid", DEFAULT_FID)
        )
        authenticated_session = qr_login.wait_for_login(
            status_callback=status_callback,
            qr_callback=qr_callback,
            stop_event=stop_event,
        )
        self.session_manager.adopt_authenticated_session(authenticated_session)
        self.is_logged_in = True
        return True
