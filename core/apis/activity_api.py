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
    
    def refresh_qrcode(self, active_id: str) -> tuple[bool, str, str, str]:
        """
        刷新签到二维码，获取 enc 和 signCode。
        
        Args:
            active_id: 活动ID
        
        Returns:
            (success, message, enc, sign_code) 元组，用于生成签到二维码
        """
        url = "https://mobilelearn.chaoxing.com/v2/apis/sign/refreshQRCode"
        params = {
            "activeId": active_id,
            "time": "",
        }
        
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }
        
        try:
            resp = self.session.get(url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            
            data = resp.json()
            if data.get("result") == 1:
                payload = data.get("data") or {}
                if isinstance(payload, dict):
                    enc = payload.get("enc") or ""
                    sign_code = payload.get("signCode") or payload.get("signcode") or ""
                else:
                    enc = payload or ""
                    sign_code = ""
                return True, "获取成功", str(enc), str(sign_code)
            else:
                return False, data.get("msg", "获取二维码失败"), "", ""
        except Exception as e:
            return False, f"网络请求失败: {e}", "", ""
    
    def start_active(self, active_id: str, course_id: str, class_id: str, active_type: int = 2) -> tuple[bool, str, dict]:
        """
        启动一个未开始的活动（如签到）。
        
        Args:
            active_id: 活动ID
            course_id: 课程ID
            class_id: 班级ID
            active_type: 活动类型，默认2(签到)
        
        Returns:
            (success, message, data) 元组，data 包含 timeLong/startTime 等
        """
        url = "https://mobilelearn.chaoxing.com/v2/apis/active/startActive"
        params = {
            "activeId": active_id,
            "courseId": course_id,
            "classId": class_id,
            "activeType": str(active_type),
            "fyktBigClassChatId": "",
        }
        
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }
        
        try:
            resp = self.session.get(url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            
            data = resp.json()
            import os
            log_path = os.path.join(os.path.expanduser("~"), "xuexitong_debug.log")
            with open(log_path, "a", encoding="utf-8") as f:
                from datetime import datetime
                f.write(f"\n[{datetime.now()}] startActive response: {data}\n")
            if data.get("result") == 1:
                return True, "启动成功", data.get("data") or {}
            else:
                error_msg = data.get("msg") or data.get("errorMsg") or "启动失败"
                return False, error_msg, {}
        except Exception as e:
            return False, f"网络请求失败: {e}", {}
    
    def end_active(self, active_id: str, active_type: int = 2) -> tuple[bool, str]:
        """
        结束一个进行中的活动（如签到）。
        
        Args:
            active_id: 活动ID
            active_type: 活动类型，默认2(签到)
        
        Returns:
            (success, message) 元组
        """
        url = "https://mobilelearn.chaoxing.com/widget/active/endActive"
        params = {
            "activeId": active_id,
            "activeType": str(active_type),
            "isLockTopic": "0",
        }
        
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }
        
        try:
            resp = self.session.get(url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            
            data = resp.json()
            if data.get("result") == 1:
                return True, data.get("msg") or "结束成功"
            else:
                error_msg = data.get("msg") or data.get("errorMsg") or "结束失败"
                return False, error_msg
        except Exception as e:
            return False, f"网络请求失败: {e}"
    
    def delete_active(self, active_id: str) -> tuple[bool, str]:
        """
        删除一个活动（签到）。
        
        Args:
            active_id: 活动ID
        
        Returns:
            (success, message) 元组
        """
        url = "https://mobilelearn.chaoxing.com/ppt/taskAPI/setdel"
        params = {
            "aid": active_id,
            "status": "1",
        }
        
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }
        
        try:
            resp = self.session.get(url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            
            data = resp.json()
            if data.get("status") == "1" or data.get("status") == 1:
                return True, data.get("messages") or "删除成功"
            else:
                return False, data.get("messages") or "删除失败"
        except Exception as e:
            return False, f"网络请求失败: {e}"
    
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

    def update_attendance_status(self, active_id: str, uid: int | str, status: int, remark: str = "") -> tuple[bool, str]:
        """更新指定学生的签到状态。"""
        params = self.session_manager.course_params
        if not params:
            return False, "错误：未找到课程参数，请先选择课程。"

        url = (
            "https://mobilelearn.chaoxing.com/pptSign/updateSignStatusByUidsV2"
            "?DB_STRATEGY=PRIMARY_KEY&STRATEGY_PARA=activeId"
            f"&activeId={active_id}"
        )
        data = {
            "uids": str(uid),
            "status": str(status),
            "remark": remark,
        }

        headers = {
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://mobilelearn.chaoxing.com",
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
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }

        try:
            resp = self.session.post(url, headers=headers, data=data, timeout=10)
            resp.raise_for_status()

            payload = resp.json()
            if payload.get("state") == "success":
                return True, "状态修改成功"
            return False, payload.get("msg") or payload.get("errorMsg") or "状态修改失败"
        except Exception as e:
            return False, f"网络请求失败: {e}"
