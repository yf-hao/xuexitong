import json
from datetime import datetime, timedelta


class GroupAPI:
    """分组与签到相关接口。"""

    def get_groups(self, course_id: str, class_id: str = None) -> any:
        """
        Fetch the list of groups for a specific course.
        If the primary list is empty, try the fallback/plan list endpoint which
        auto-initializes a default group.
        """
        url = "https://mobilelearn.chaoxing.com/v2/apis/active/group/list"

        params = self.session_manager.course_params.copy()
        params["courseId"] = course_id
        if class_id:
            params["classId"] = class_id
            if not params.get("clazzid"):
                params["clazzid"] = class_id

        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }

        referer_base = "https://mobilelearn.chaoxing.com/page/active/activeList"
        ref_params = [
            f"fid={params.get('fid', '4311')}",
            f"courseId={course_id}",
            f"classId={class_id if class_id else ''}",
            "showInvitecode=1",
            f"cpi={params.get('cpi', '')}",
            f"enc={params.get('enc', '')}",
        ]
        headers["Referer"] = f"{referer_base}?{'&'.join(ref_params)}"

        try:
            print("DEBUG [v2.1]: 正在同步活动列表中转页以初始化 session (Referer)...")
            self.session.get(headers["Referer"], headers={"User-Agent": headers["User-Agent"]}, timeout=10)

            list_params = {
                "fid": params.get("fid", "4311"),
                "classId": class_id,
                "courseId": course_id,
                "cpi": params.get("cpi", ""),
                "enc": params.get("enc", ""),
                "t": params.get("t", int(datetime.now().timestamp() * 1000)),
            }

            print(f"DEBUG [v2.1]: 正在请求 group/list (Stage 2) URL: {url} 参数: {list_params}")
            resp = self.session.get(url, params=list_params, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            groups = data.get("data", [])

            if not groups and class_id:
                print("DEBUG [v2.1]: 分组列表为空，尝试通过 groupPlanList 接口初始化...")
                fallback_url = "https://mobilelearn.chaoxing.com/v2/apis/active/groupPlanList"
                fb_params = {
                    "courseId": course_id,
                    "classId": class_id,
                }

                try:
                    res_fb = self.session.get(fallback_url, params=fb_params, headers=headers, timeout=10)
                    data_fb = res_fb.json()
                    print(f"DEBUG [v2.1]: groupPlanList 响应: {json.dumps(data_fb, ensure_ascii=False)}")
                    if data_fb.get("result") == 1:
                        groups = data_fb.get("data", [])
                except Exception as fb_e:
                    print(f"DEBUG [v2.1]: groupPlanList 尝试失败: {fb_e}")

            if not groups and class_id:
                print("DEBUG [v2.0]: 自动初始化仍未返回数据，正在执行强制创建 (默认分组)...")
                create_success, create_msg = self.add_group(course_id, class_id, "默认分组")
                if create_success:
                    print(f"DEBUG [v2.0]: 强制创建成功: {create_msg}，正在重新拉取列表...")
                    import time

                    time.sleep(1)
                    res_final = self.session.get(url, params=list_params, headers=headers, timeout=10)
                    groups = res_final.json().get("data", [])
                else:
                    print(f"DEBUG [v2.0]: 强制创建失败: {create_msg}")

            print(f"DEBUG [v2.0]: 最终获取到 {len(groups)} 个分组")
            return groups
        except Exception as e:
            print(f"get_groups 异常: {e}")
            if "resp" in locals():
                print(f"最近响应内容: {resp.text[:3500]}")
            return f"获取分组列表失败: {e}"

    def rename_group(self, group_id: str, new_name: str) -> tuple[bool, str]:
        """Rename a group using the provided API."""
        url = "https://mobilelearn.chaoxing.com/ppt/taskAPI/updatetp"
        data = {
            "id": group_id,
            "name": new_name,
        }

        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://mobilelearn.chaoxing.com/page/active/activeList",
        }

        try:
            resp = self.session.post(url, data=data, headers=headers, timeout=10)
            resp.raise_for_status()
            try:
                result = resp.json()
                if result.get("result") == 1 or result.get("status") is True:
                    return True, "重命名成功"
                return False, f"API 错误: {result.get('msg', '未知错误')}"
            except Exception:
                if "success" in resp.text.lower():
                    return True, "重命名成功"
                return False, f"服务器返回: {resp.text[:100]}"
        except Exception as e:
            return False, f"网络请求失败: {e}"

    def publish_signin_task(self, course_id, class_id, plan_id, sign_code, title="签到", other_id=2, disposable_publishtime=None, **kwargs):
        """Publish a sign-in task."""
        url = "https://mobilelearn.chaoxing.com/v2/apis/sign/saveOrBegin"

        if not disposable_publishtime:
            now = datetime.now()
            tomorrow = now + timedelta(days=1)
            disposable_publishtime = tomorrow.strftime("%Y-%m-%d 08:00")

        params = {
            "courseId": course_id,
            "classId": class_id,
            "otherId": other_id,
            "title": title,
            "planId": plan_id,
            "signCode": sign_code,
            "disposable_publishtime": disposable_publishtime,
            "now": "0",
            "activeId": "",
            "isresult": "0",
            "isCourseware": "0",
            "ifphoto": "0",
            "ifrefreshewm": "1",
            "ewmRefreshTime": "10",
            "picId": "0",
            "classroomPlanId": "",
            "pageNum": "",
            "pageId": "",
            "timerCron": "",
            "dateCron": "",
            "isTeachingCalendar": "0",
            "fromtype": "",
            "ifopenAddress": "0",
            "locationText": "",
            "locationLatitude": "",
            "locationLongitude": "",
            "locationRange": "",
            "ifSkipWeek": "0",
            "ifSendToOtherClass": "0",
            "sendToOtherClassList": "",
            "onlyAttendForCurrentClass": "0",
            "fyktBigClassChatId": "",
            "isTeachingPlanLibrary": "0",
            "ifNeedVCode": "1",
            "lateMinute": "10",
            "fykbParas": "",
            "openCheckFaceFlag": "0",
            "openCheckWeChatFlag": "1",
            "knowledgePoints": "",
        }
        params.update(kwargs)
        if "timeLong" not in params:
            params["timeLong"] = "1800000"

        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "sec-ch-ua-platform": '"macOS"',
        }

        try:
            print(f"Publishing sign-in: {title} at {disposable_publishtime}")
            resp = self.session.get(url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()

            data = resp.json()
            if data.get("result") == 1:
                return True, "发布成功", data.get("data")
            return False, f"发布失败: {data.get('msg', '未知错误')}", None
        except Exception as e:
            return False, f"发布请求异常: {e}", None

    def delete_signin_task(self, active_id: str) -> tuple[bool, str]:
        """Delete a published sign-in task."""
        url = "https://mobilelearn.chaoxing.com/ppt/taskAPI/setdel"
        params = {
            "aid": active_id,
            "status": 1,
        }

        p = self.session_manager.course_params
        referer = (
            f"https://mobilelearn.chaoxing.com/page/active/activeList"
            f"?fid={p.get('fid', '')}&courseId={p.get('courseid', '')}"
            f"&classId={p.get('clazzid', '')}&showInvitecode=1&cpi={p.get('cpi', '')}"
            f"&enc={p.get('enc', '')}"
        )

        headers = {
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": referer,
        }

        try:
            print(f"Deleting sign-in task {active_id} ...")
            resp = self.session.get(url, params=params, headers=headers, timeout=10)
            print(f"Delete response: {resp.status_code} - {resp.text}")
            resp.raise_for_status()
            data = resp.json()

            if data.get("result") == 1 or data.get("status") == "1":
                return True, "删除成功"
            return False, f"删除失败: {data.get('msg', '未知错误')} (Status: {resp.status_code})"
        except Exception as e:
            print(f"Delete exception: {e}")
            return False, f"删除请求异常: {e}"

    def delete_group(self, group_id: str) -> tuple[bool, str]:
        """Delete a group using the provided API."""
        url = "https://mobilelearn.chaoxing.com/ppt/taskAPI/deltp"
        data = {"id": group_id}

        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://mobilelearn.chaoxing.com/page/active/activeList",
        }

        try:
            resp = self.session.post(url, data=data, headers=headers, timeout=10)
            resp.raise_for_status()
            try:
                result = resp.json()
                if result.get("result") == 1 or result.get("status") is True:
                    return True, "删除成功"
                return False, f"API 错误: {result.get('msg', '未知错误')}"
            except Exception:
                if "success" in resp.text.lower():
                    return True, "删除成功"
                return False, f"服务器返回: {resp.text[:100]}"
        except Exception as e:
            return False, f"网络请求失败: {e}"

    def add_group(self, course_id: str, class_id: str, name: str) -> tuple[bool, str]:
        """Create a new group using the provided API."""
        url = "https://mobilelearn.chaoxing.com/v2/apis/active/group/add"
        data = {
            "courseId": course_id,
            "classId": class_id,
            "name": name,
        }

        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://mobilelearn.chaoxing.com/page/active/activeList",
        }

        try:
            resp = self.session.post(url, data=data, headers=headers, timeout=10)
            resp.raise_for_status()
            try:
                result = resp.json()
                if result.get("result") == 1 or result.get("status") is True:
                    return True, "新增成功"
                return False, f"API 错误: {result.get('msg', '未知错误')}"
            except Exception:
                if "success" in resp.text.lower():
                    return True, "新增成功"
                return False, f"服务器返回: {resp.text[:100]}"
        except Exception as e:
            return False, f"网络请求失败: {e}"
