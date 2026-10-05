from core.config import DEFAULT_FID


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
