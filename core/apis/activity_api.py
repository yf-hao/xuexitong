"""活动相关 API（签到、投票、抢答等）。"""
import time
from models.activity import ActivityList
from models.attendance_record import AttendanceDetail


class ActivityAPI:
    """活动相关接口：考勤签到、投票、抢答等活动数据。"""

    def get_activity_list(self, activity_type: str = None) -> ActivityList | str:
        """
        获取活动列表（签到、投票、抢答等）。
        
        Args:
            activity_type: 活动类型筛选，None 表示获取所有类型
                - "2": 签到
                - "4": 抢答
                - 其他类型待确认
        
        Returns:
            ActivityList 对象或错误信息字符串
        """
        params = self.session_manager.course_params
        if not params:
            return "错误：未找到课程参数，请先选择课程。"
        
        url = "https://mobilelearn.chaoxing.com/v2/apis/active/pcActivelist"
        query_params = {
            "fid": params.get("fid", ""),
            "courseId": params.get("courseid"),
            "classId": params.get("clazzid"),
            "types": activity_type or "",
            "userid": "",
            "groupId": "",
            "_": int(time.time() * 1000),
        }
        
        headers = {
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Referer": (
                f"https://mobilelearn.chaoxing.com/page/active/activeList"
                f"?fid={params.get('fid')}"
                f"&courseId={params.get('courseid')}"
                f"&classId={params.get('clazzid')}"
                f"&showInvitecode=1"
                f"&cpi={params.get('cpi')}"
            ),
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }
        
        try:
            resp = self.session.get(url, params=query_params, headers=headers, timeout=10)
            resp.raise_for_status()
            
            data = resp.json()
            
            if data.get("result") == 1 or data.get("status") is True:
                activity_list = ActivityList.from_dict(data.get("data", {}))
                print(f"获取到 {len(activity_list)} 个活动")
                return activity_list
            else:
                error_msg = data.get("msg", "未知错误")
                print(f"获取活动列表失败: {error_msg}")
                return f"获取活动列表失败: {error_msg}"
                
        except Exception as e:
            print(f"获取活动列表异常: {e}")
            return f"网络请求失败: {e}"
    
    def get_attendance_activities(self) -> ActivityList | str:
        """获取签到活动列表（考勤情况）。"""
        return self.get_activity_list(activity_type="2")
    
    def get_vote_activities(self) -> ActivityList | str:
        """获取投票活动列表。"""
        return self.get_activity_list(activity_type="4")
    
    def get_attendance_detail(self, active_id: str) -> AttendanceDetail | str:
        """
        获取签到详情（学生签到记录）。
        
        Args:
            active_id: 活动ID
        
        Returns:
            AttendanceDetail 对象或错误信息字符串
        """
        params = self.session_manager.course_params
        if not params:
            return "错误：未找到课程参数，请先选择课程。"
        
        url = "https://mobilelearn.chaoxing.com/widget/sign/pcTeaSignController/getAttendList"
        query_params = {
            "activeId": active_id,
            "appType": "15",
            "classId": params.get("clazzid"),
            "courseId": params.get("courseid"),
            "fid": params.get("fid", ""),
        }
        
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Referer": (
                f"https://mobilelearn.chaoxing.com/page/sign/endSign"
                f"?courseId={params.get('courseid')}"
                f"&classId={params.get('clazzid')}"
                f"&activeId={active_id}"
                f"&fid={params.get('fid')}"
                f"&cpi={params.get('cpi')}"
                f"&showOnScreenShare=true"
                f"&returnType=1"
            ),
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }
        
        try:
            resp = self.session.get(url, params=query_params, headers=headers, timeout=10)
            resp.raise_for_status()
            
            data = resp.json()
            
            if data.get("result") == 1:
                detail = AttendanceDetail.from_dict(data.get("data", {}))
                print(f"获取到 {len(detail)} 条签到记录")
                return detail
            else:
                error_msg = data.get("msg", "未知错误")
                print(f"获取签到详情失败: {error_msg}")
                return f"获取签到详情失败: {error_msg}"
                
        except Exception as e:
            print(f"获取签到详情异常: {e}")
            return f"网络请求失败: {e}"
