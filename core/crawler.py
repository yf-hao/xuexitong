from core.session import ChaoxingSession
from core.apis.auth_api import AuthAPI
from core.apis.captcha_api import CaptchaAPI
from core.apis.course_api import CourseAPI
from core.apis.class_api import ClassAPI
from core.apis.stats_api import StatsAPI
from core.apis.group_api import GroupAPI
from core.apis.teacher_api import TeacherAPI
from core.apis.course_manage_api import CourseManageAPI
from core.apis.question_bank_api import QuestionBankAPI
from core.apis.material_api import MaterialAPI
from core.apis.activity_api import ActivityAPI
from core.apis.homework_api import HomeworkAPI


class XuexitongCrawler(
    AuthAPI,
    CaptchaAPI,
    CourseAPI,
    ClassAPI,
    StatsAPI,
    GroupAPI,
    TeacherAPI,
    CourseManageAPI,
    QuestionBankAPI,
    MaterialAPI,
    ActivityAPI,
    HomeworkAPI,
):
    """聚合各业务域 API 的门面类，仅保留会话与聚合职责。"""

    BASE_URL = "https://passport2.chaoxing.com"
    I_CHAOXING_URL = "https://i.chaoxing.com"

    def __init__(self):
        """初始化共享会话与基础状态。"""
        self.session_manager = ChaoxingSession()
        self.is_logged_in = False
        self._details_cache = {}  # course_id -> details dict

    @property
    def session(self):
        """暴露底层 requests session 给各 API mixin 使用。"""
        return self.session_manager.session

    # 具体能力由各业务域 mixin 提供：
    # AuthAPI / CaptchaAPI / CourseAPI / ClassAPI / StatsAPI / GroupAPI /
    # TeacherAPI / CourseManageAPI / QuestionBankAPI / MaterialAPI / ActivityAPI / HomeworkAPI
