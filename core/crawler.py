import requests
import json
from bs4 import BeautifulSoup
from typing import List, Optional
from models.data_types import Course, Material
from core.session import ChaoxingSession
from core.config import DEFAULT_FID
from core.apis.course_api import CourseAPI
from core.apis.class_api import ClassAPI
import re
from datetime import datetime, timedelta

class XuexitongCrawler(CourseAPI, ClassAPI):
    BASE_URL = "https://passport2.chaoxing.com"
    I_CHAOXING_URL = "https://i.chaoxing.com"
    
    def detect_slider_displacement(self, shade_image_bytes: bytes, cutout_image_bytes: bytes) -> int:
        """
        使用 OpenCV 计算滑块缺口偏移量。
        """
        import cv2
        import numpy as np
        
        # 将 bytes 转换为 numpy 数组并解码为图像
        shade_np = np.frombuffer(shade_image_bytes, np.uint8)
        cutout_np = np.frombuffer(cutout_image_bytes, np.uint8)
        
        shade_img = cv2.imdecode(shade_np, cv2.IMREAD_GRAYSCALE)
        cutout_img = cv2.imdecode(cutout_np, cv2.IMREAD_GRAYSCALE)
        
        print(f"DEBUG: detect_slider_displacement shade_img shape: {shade_img.shape if shade_img is not None else 'None'}")
        print(f"DEBUG: detect_slider_displacement cutout_img shape: {cutout_img.shape if cutout_img is not None else 'None'}")
        
        if shade_img is None or cutout_img is None:
            print("DEBUG: detect_slider_displacement failed due to None image")
            return 0
            
        def _get_canny(image):
            image = cv2.GaussianBlur(image, (3, 3), 0)
            return cv2.Canny(image, 50, 150)
            
        # 边缘检测
        shade_canny = _get_canny(shade_img)
        cutout_canny = _get_canny(cutout_img)
        
        # 模板匹配
        res = cv2.matchTemplate(shade_canny, cutout_canny, cv2.TM_CCOEFF_NORMED)
        # 获取匹配结果
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        
        # 对标用户 snippet: top_left = max_loc[0]
        print(f"DEBUG: detect_slider_displacement max_val={max_val}, max_loc={max_loc}")
        return max_loc[0]
    
    def __init__(self):
        # Use the singleton session
        self.session_manager = ChaoxingSession()
        self.is_logged_in = False
        self._details_cache = {} # course_id -> details dict

    @property
    def session(self):
        return self.session_manager.session

    def login_by_password(self, phone, password, fid=DEFAULT_FID) -> bool:
        """
        Implement password login logic using ChaoxingSession.
        """
        self.session_manager.phone = phone
        self.session_manager.password = password
        self.session_manager.course_params['fid'] = fid
        try:
            self.is_logged_in = self.session_manager.login()
        except Exception as e:
            print(f"Login failed: {e}")
            self.is_logged_in = False
        return self.is_logged_in

    # get_courses 实现在 CourseAPI 混入

    # get_course_details / extract_course_params 实现在 CourseAPI 混入

    # get_class_list 实现在 ClassAPI 混入

    # get_clazz_manage_list 实现在 ClassAPI 混入

    # rename_clazz 实现在 ClassAPI 混入

    # create_clazz 实现在 ClassAPI 混入

    # delete_clazz 实现在 ClassAPI 混入

    # add_student_by_hand 实现在 ClassAPI 混入
    
    # create_course 实现在 CourseAPI 混入

    # add_students_batch 实现在 ClassAPI 混入

    def get_materials(self, course_id: str) -> List[Material]:
        """
        Fetch material/resource list for a specific course.
        Injects necessary parameters (clazzid, cpi, etc.) from session.
        """
        # Ensure params are loaded into session
        details = self.get_course_details(course_id)
        if not details:
            return []
            
        params = self.session_manager.course_params
        # At this point, params['clazzid'], params['cpi'], params['enc'] are available
        
        # Find the "资料" link
        material_url_path = None
        for link in details["nav_links"]:
            if "资料" in link["title"]:
                material_url_path = link["url"]
                break
        
        if not material_url_path:
            print(f"No material link found for course {course_id}.")
            return []
            
        print(f"Injecting params for material fetch - clazzid: {params.get('clazzid')}, cpi: {params.get('cpi')}")
        
        # In the next step, we will use these params to call the data fetching API
        # For now, return a status item showing the injection worked
        return [
            Material(
                id=params.get("clazzid", "0"),
                name=f"班级资料 (ID: {params.get('clazzid')})",
                type="folder"
            )
        ]

    def _get_stats_reports(self, seltables: str, report_name: str = "统计", trigger_export: bool = True) -> any:
        """
        Generic method to fetch stats reports (attendance, quiz, homework, etc.).
        
        Args:
            seltables: The seltables parameter for the export API (e.g., "12" for attendance, "8" for quiz)
            report_name: Name of the report type for logging (e.g., "考勤", "测验")
            trigger_export: Whether to trigger a new export request before fetching the list
        
        Returns:
            List of report dictionaries or error message string
        """
        params = self.session_manager.course_params
        if not params:
            return "错误：未找到课程参数，请先选择课程。"

        # 1. First, trigger the export request
        export_url = "https://stat2-ans.chaoxing.com/stat2/teach-data/export"
        export_params = {
            "clazzid": params.get("clazzid"),
            "courseid": params.get("courseid"),
            "cpi": params.get("cpi"),
            "ut": "t",
            "pEnc": "",
            "seltables": seltables,
            "type": "1",
            "exportType": "0",
            "fr": "stat2"
        }
        export_headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://stat2-ans.chaoxing.com/teach-data/index?courseid={params.get('courseid')}&clazzid={params.get('clazzid')}&cpi={params.get('cpi')}&ut=t",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        
        try:
            if trigger_export:
                print(f"正在触发{report_name}数据预导出 (Export)...")
                self.session.get(export_url, params=export_params, headers=export_headers, timeout=10)
            else:
                print(f"跳过触发{report_name}预导出，执行增量刷新...")
        except Exception as e:
            print(f"预导出请求失败(忽略): {e}")

        # 2. Proceed to TCM download center to get the result list (with pagination)
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/downloadcenter"
        headers = {
            "Referer": f"https://stat2-ans.chaoxing.com/teach-data/index?courseid={params.get('courseid')}&clazzid={params.get('clazzid')}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        
        all_items = []
        page_num = 1
        max_pages = 1  # 仅获取第一页
        
        try:
            while page_num <= max_pages:
                query_params = {
                    "courseId": params.get("courseid"),
                    "pageNum": str(page_num),
                    "cpi": params.get("cpi"),
                    "order": "down"
                }
                
                print(f"正在获取{report_name}下载列表 (第 {page_num} 页): {url}")
                resp = self.session.get(url, params=query_params, headers=headers, timeout=10)
                resp.raise_for_status()
                
                # Parse the specific ul.dataBody_td structure provided by user
                soup = BeautifulSoup(resp.text, "lxml")
                rows = soup.select("ul.dataBody_td")
                
                # If no rows found on this page, we've reached the end
                if not rows:
                    print(f"第 {page_num} 页无数据，已获取所有页面")
                    break
                
                page_items = []
                for row in rows:
                    lis = row.find_all("li")
                    if len(lis) >= 3:
                        name_tag = lis[0].select_one("span.nameText")
                        name = name_tag.get_text(strip=True) if name_tag else "未知名称"
                        time = lis[1].get_text(strip=True)
                        status = lis[2].get_text(strip=True)
                        
                        link_tag = lis[3].select_one("a.download_ic") if len(lis) > 3 else None
                        download_url = link_tag.get("href") if link_tag else None
                        
                        # Try to find report ID for deletion
                        # Strategy 0: Check the row (ul) 'data' attribute (observed in real HTML)
                        # We use attrs.get to be absolutely sure we're getting the raw attribute
                        report_id = row.attrs.get("data") or row.get("id")
                        
                        if not report_id:
                            # Strategy 1: Look for any tag with 'delete', 'remove', 'del' in onclick or class
                            del_tag = lis[3].select_one("a[onclick*='delete'], a[onclick*='remove'], a[onclick*='del'], a.delete_ic, a.btn-delete, a.deleteOrCancel") if len(lis) > 3 else None
                            
                            if del_tag:
                                onclick = del_tag.get("onclick", "")
                                id_match = re.search(r"['\"](\d+)['\"]", onclick) or re.search(r"\((\d+)\)", onclick)
                                if id_match:
                                    report_id = id_match.group(1)
                                
                                if not report_id:
                                    report_id = del_tag.attrs.get("data-id") or del_tag.get("id") or del_tag.attrs.get("data")
                        
                        # Fallback: Check if download URL has id (USE WORD BOUNDARY to avoid matching customUserId)
                        if not report_id and download_url:
                            # \b ensures we match 'id=' and not 'userId='
                            id_match = re.search(r"[?&]\bid=(\d+)", download_url) or \
                                       re.search(r"[?&]\bresId=(\d+)", download_url)
                            if id_match:
                                report_id = id_match.group(1)
                            
                        if not report_id or report_id == "14632912":
                            if report_id == "14632912": report_id = None
                        
                        page_items.append({
                            "name": name,
                            "time": time,
                            "status": status,
                            "url": download_url,
                            "id": report_id
                        })
                
                if page_items:
                    all_items.extend(page_items)
                    print(f"第 {page_num} 页获取到 {len(page_items)} 条记录")
                    page_num += 1
                else:
                    # No items parsed from this page, stop
                    print(f"第 {page_num} 页解析结果为空，停止分页")
                    break
            
            if not all_items:
                return "💡 提示: 未发现有效的导出记录，可能正在生成中，请稍后刷新。"
            
            print(f"共获取 {len(all_items)} 条{report_name}记录")
            return all_items
        except Exception as e:
            return f"获取下载列表具体错误: {e}"

    def delete_stats_report(self, report_id: str) -> tuple[bool, str]:
        """
        Delete a stats report item from the download center.
        """
        params = self.session_manager.course_params
        if not params:
            return False, "未找到课程参数"
            
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/deleteDownloadCenter"
        query_params = {
            "courseId": params.get("courseid"),
            "id": report_id,
            "cpi": params.get("cpi")
        }
        
        headers = {
            "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/downloadcenter?courseId={params.get('courseid')}&cpi={params.get('cpi')}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest"
        }
        
        try:
            resp = self.session.get(url, params=query_params, headers=headers, timeout=10)
            resp.raise_for_status()
            
            # The response is usually a JSON string like {"result":1} or similar
            try:
                result = resp.json()
                if result.get("result") == 1 or result.get("status") is True:
                    return True, "删除成功"
                return False, f"删除失败: {result.get('msg', '未知错误')}"
            except:
                if "1" in resp.text: # Simple check for success if not JSON
                    return True, "删除成功"
                return False, f"服务器返回: {resp.text[:100]}"
        except Exception as e:
            return False, f"删除请求失败: {e}"

    def get_stats_reports(self, stats_type: str, trigger_export: bool = True) -> any:
        """
        通用的统计报告获取方法（配置驱动）
        
        Args:
            stats_type: 统计类型
            trigger_export: 是否触发预导出
        """
        from core.config import STATS_TYPES
        
        config = STATS_TYPES.get(stats_type)
        if not config:
            available_types = ", ".join(STATS_TYPES.keys())
            return f"❌ 未知的统计类型: {stats_type}。可用类型: {available_types}"
        
        return self._get_stats_reports(
            seltables=config["seltables"], 
            report_name=config["name"],
            trigger_export=trigger_export
        )

    def get_attendance_reports(self) -> any:
        """
        获取考勤报告（便捷方法）
        Uses seltables=12 for attendance data.
        """
        return self.get_stats_reports("attendance")

    def get_quiz_reports(self) -> any:
        """
        获取测验报告（便捷方法）
        Uses seltables=8 for quiz data.
        """
        return self.get_stats_reports("quiz")
    
    def get_homework_reports(self) -> any:
        """
        获取作业报告（便捷方法）
        Uses seltables=6 for homework data.
        """
        return self.get_stats_reports("homework")

    def get_grade_weights(self) -> dict:
        """
        Fetch current grade weights from Xuexitong.
        Returns a dictionary mapping display names to their current values.
        """
        params = self.session_manager.course_params
        if not params:
            print("Crawler: No course params found for weights")
            return {}

        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/scoreweightdata"
        # 注意：这里严格遵循学习通的大小写
        query_params = {
            "courseId": params.get("courseid"),
            "clazzId": params.get("clazzid"),
            "cpi": params.get("cpi")
        }

        # 添加完整的 Headers 以绕过 403
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/course-manage?courseid={params.get('courseid')}&clazzid={params.get('clazzid')}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Upgrade-Insecure-Requests": "1"
        }

        try:
            resp = self.session.get(url, params=query_params, headers=headers, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            mapping = {
                "video": "章节任务点",
                "ceyan": "章节测验",
                "work": "作业",
                "test": "考试",
                "aiEvaluate": "AI实践",
                "pbl": "分组任务(PBL)",
                "attend": "签到",
                "active": "课程积分",
                "bbs": "讨论"
            }

            weights = {}
            print(f"\n--- 权重同步调试 (班级ID: {params.get('clazzid')}) ---")
            for field, display_name in mapping.items():
                # 优先在 ID 中查找，学习通 HTML 中常见 id="videokWeight" 等
                inputs = soup.find_all("input", {"name": field})
                val = 0
                for inp in inputs:
                    v_str = inp.get("value")
                    if v_str and v_str.strip():
                        try:
                            # 学习通有时会返回 "20.0" 这样的字符串，先转 float 再转 int
                            val = int(float(v_str))
                            break
                        except:
                            continue
                
                weights[display_name] = val
                print(f"  > {display_name} ({field}): {val}%")
            print("--- 同步结束 ---\n")
            
            return weights
        except Exception as e:
            print(f"Error fetching weights: {e}")
            return {}

    def set_grade_weights(self, weights: dict, class_ids: list = None) -> (bool, str):
        """
        Set course grade weights.
        
        Args:
            weights: Dictionary mapping type names to percentage values.
            class_ids: Optional list of class IDs to apply these weights to.
        """
        params = self.session_manager.course_params
        if not params:
            return False, "未找到课程参数"

        current_clazzid = params.get("clazzid")
        # 构建班级 ID 字符串，格式为 "ID1,ID2,ID3,"
        if class_ids:
            # 确保当前选中的班级在列表首位（学习通通常习惯这样）
            unique_ids = []
            if current_clazzid in class_ids:
                unique_ids.append(current_clazzid)
            for cid in class_ids:
                if cid != current_clazzid:
                    unique_ids.append(cid)
            class_id_str = ",".join([str(cid) for cid in unique_ids]) + ","
        else:
            class_id_str = f"{current_clazzid},"

        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/setWeights"
        
        # Build form data
        data = {
            "offlineName": "",
            "courseId": params.get("courseid"),
            "clazzId": current_clazzid,
            "cpi": params.get("cpi"),
            "video": weights.get("章节任务点", 0),
            "ceyan": weights.get("章节测验", 0),
            "work": weights.get("作业", 0),
            "test": weights.get("考试", 0),
            "aiEvaluateType": "0",
            "aiEvaluate": weights.get("AI实践", 0),
            "pbl": weights.get("分组任务(PBL)", 0),
            "attend": weights.get("签到", 0),
            "attendStatisticType": "0",
            "active": weights.get("课程积分", 0),
            "activeLimit": "300",
            "bbs": weights.get("讨论", 0),
            "bbsStatisticType": "0",
            "visitTime": "0",
            "visitTimeLimit": "",
            "readTime": "0",
            "readTimeLimit": "",
            "liveTime": "0",
            "liveStatisticType": "1",
            "liveViewingRate": "",
            "liveTimeLimit": "",
            "interactiveQuestion": "0",
            "chaoxingClassTime": "0",
            "chaoxingClassType": "0",
            "chaoxingClassLimit": "",
            "chaoxingClassRate": "",
            "offline": "0",
            "attendAttendance": "0",
            "bbsLimit": "2.0",
            "bbsReplyLimit": "2.0",
            "bbsPraiseLimit": "1.0",
            "cleanCustomScoreVal": "0",
            "customWeightJson": "[]",
            "classIdStr": class_id_str
        }

        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/course-manage?courseid={params.get('courseid')}&clazzid={current_clazzid}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        try:
            resp = self.session.post(url, data=data, headers=headers, timeout=10)
            resp.raise_for_status()
            res_json = resp.json()
            if res_json.get("result") == 1 or res_json.get("status") is True:
                target_desc = "所有班级" if class_ids and len(class_ids) > 1 else "当前班级"
                return True, f"权重设置已成功保存至{target_desc}！"
            else:
                return False, res_json.get("msg", "保存失败，服务器返回异常")
        except Exception as e:
            return False, f"网络请求失败: {e}"

    def get_groups(self, course_id: str, class_id: str = None) -> any:
        """
        Fetch the list of groups for a specific course.
        If the primary list is empty, try the fallback/plan list endpoint which
        auto-initializes a default group.
        """
        url = "https://mobilelearn.chaoxing.com/v2/apis/active/group/list"
        
        # Build base parameters
        params = self.session_manager.course_params.copy()
        params["courseId"] = course_id
        if class_id:
            params["classId"] = class_id 
            if not params.get("clazzid"): params["clazzid"] = class_id
        
        # Build headers matching the user's curl precisely
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }
        
        # Build Referer
        referer_base = "https://mobilelearn.chaoxing.com/page/active/activeList"
        ref_params = [
            f"fid={params.get('fid', '4311')}",
            f"courseId={course_id}",
            f"classId={class_id if class_id else ''}",
            "showInvitecode=1",
            f"cpi={params.get('cpi', '')}",
            f"enc={params.get('enc', '')}"
        ]
        headers["Referer"] = f"{referer_base}?{'&'.join(ref_params)}"
        
        try:
            # Stage 1: Visit page (HTML) to ensure session/state is ready
            # This handles any server-side logic triggered by the page load
            print(f"DEBUG [v2.1]: 正在同步活动列表中转页以初始化 session (Referer)...")
            self.session.get(headers["Referer"], headers={"User-Agent": headers["User-Agent"]}, timeout=10)

            # Stage 2: Try group/list with standard parameters
            # Note: We use CamelCase (courseId/classId) as the lowercase version may trigger 500 error
            list_params = {
                "fid": params.get("fid", "4311"),
                "classId": class_id,
                "courseId": course_id,
                "cpi": params.get("cpi", ""),
                "enc": params.get("enc", ""),
                "t": params.get("t", int(datetime.now().timestamp() * 1000))
            }
            
            print(f"DEBUG [v2.1]: 正在请求 group/list (Stage 2) URL: {url} 参数: {list_params}")
            resp = self.session.get(url, params=list_params, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            groups = data.get("data", [])
            
            # Stage 3: Try groupPlanList fallback (Initialization) 
            if not groups and class_id:
                print("DEBUG [v2.1]: 分组列表为空，尝试通过 groupPlanList 接口初始化...")
                fallback_url = "https://mobilelearn.chaoxing.com/v2/apis/active/groupPlanList"
                fb_params = {
                    "courseId": course_id,
                    "classId": class_id
                }
                
                try:
                    res_fb = self.session.get(fallback_url, params=fb_params, headers=headers, timeout=10)
                    data_fb = res_fb.json()
                    print(f"DEBUG [v2.1]: groupPlanList 响应: {json.dumps(data_fb, ensure_ascii=False)}")
                    if data_fb.get("result") == 1:
                        groups = data_fb.get("data", [])
                except Exception as fb_e:
                    print(f"DEBUG [v2.1]: groupPlanList 尝试失败: {fb_e}")

            # Stage 4: Forced Initialization (The "Last Resort")
            # If the server still says it's empty after all checks, we manually create '默认分组'
            if not groups and class_id:
                print(f"DEBUG [v2.0]: 自动初始化仍未返回数据，正在执行强制创建 (默认分组)...")
                create_success, create_msg = self.add_group(course_id, class_id, "默认分组")
                if create_success:
                    print(f"DEBUG [v2.0]: 强制创建成功: {create_msg}，正在重新拉取列表...")
                    import time
                    time.sleep(1) # Give server a moment to index
                    res_final = self.session.get(url, params=list_params, headers=headers, timeout=10)
                    groups = res_final.json().get("data", [])
                else:
                    print(f"DEBUG [v2.0]: 强制创建失败: {create_msg}")

            print(f"DEBUG [v2.0]: 最终获取到 {len(groups)} 个分组")
            return groups
        except Exception as e:
            print(f"get_groups 异常: {e}")
            if 'resp' in locals():
                print(f"最近响应内容: {resp.text[:3500]}")
            return f"获取分组列表失败: {e}"

    def rename_group(self, group_id: str, new_name: str) -> tuple[bool, str]:
        """
        Rename a group using the provided API.
        """
        url = "https://mobilelearn.chaoxing.com/ppt/taskAPI/updatetp"
        data = {
            "id": group_id,
            "name": new_name
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
            
            # The API might return "success" or a JSON result
            # Assuming typical Chaoxing behavior: result 1 means success
            try:
                result = resp.json()
                if result.get("result") == 1 or result.get("status") == True:
                    return True, "重命名成功"
                return False, f"API 错误: {result.get('msg', '未知错误')}"
            except:
                if "success" in resp.text.lower():
                    return True, "重命名成功"
                return False, f"服务器返回: {resp.text[:100]}"
                
        except Exception as e:
            return False, f"网络请求失败: {e}"

    def publish_signin_task(self, course_id, class_id, plan_id, sign_code, title="签到", other_id=2, disposable_publishtime=None, **kwargs):
        """
        Publish a sign-in task.
        
        Args:
            course_id: Course ID
            class_id: Class ID
            plan_id: Plan ID (Group ID)
            sign_code: The sign-in code (e.g. "1FMJPY")
            title: Title of the sign-in task
            other_id: Default 2
            disposable_publishtime: Optional release time string. 
                                    If None, defaults to tomorrow at 08:00 relative to now.
            **kwargs: Other optional parameters to override defaults
        """
        url = "https://mobilelearn.chaoxing.com/v2/apis/sign/saveOrBegin"
        
        # Calculate default time if not provided
        if not disposable_publishtime:
            now = datetime.now()
            tomorrow = now + timedelta(days=1)
            # Format: 2026-01-20 08:00 (Click button's next day morning 8:00)
            # Note: The curl command shows encoded space as + or %20. Requests handles encoding.
            disposable_publishtime = tomorrow.strftime("%Y-%m-%d 08:00")
            
        params = {
            "courseId": course_id,
            "classId": class_id,
            "otherId": other_id,
            "title": title,
            "planId": plan_id,
            "signCode": sign_code,
            "disposable_publishtime": disposable_publishtime,
            
            # Defaults as per curl command
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
            "knowledgePoints": ""
        }
        
        # Override with any provided kwargs
        params.update(kwargs)
        
        # Only timeLong is missing from the defaults list but present in curl as 1800000 (30 mins?)
        # Let's add it if not in kwargs
        if "timeLong" not in params:
             params["timeLong"] = "1800000"

        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "sec-ch-ua-platform": '"macOS"'
        }
        
        # Inject cookie/headers from session
        # The session object automatically handles cookies.
        
        try:
            print(f"Publishing sign-in: {title} at {disposable_publishtime}")
            resp = self.session.get(url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            
            data = resp.json()
            # Check for success. Usually result=1 or similar.
            # The curl response isn't shown, but standard Chaoxing is result=1.
            if data.get("result") == 1:
                return True, "发布成功", data.get("data")
            else:
                return False, f"发布失败: {data.get('msg', '未知错误')}", None
                
        except Exception as e:
            return False, f"发布请求异常: {e}", None

    def delete_signin_task(self, active_id: str) -> tuple[bool, str]:
        """
        Delete a published sign-in task using the provided API.
        
        Args:
            active_id (str): The 'aid' (activeId) of the sign-in task.
        
        Returns:
            (bool, str): Success status and message.
        """
        url = "https://mobilelearn.chaoxing.com/ppt/taskAPI/setdel"
        params = {
            "aid": active_id,
            "status": 1
        }
        
        # Construct Referer to mimic browser behavior
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
            "Referer": referer
        }
        
        try:
            print(f"Deleting sign-in task {active_id} ...")
            resp = self.session.get(url, params=params, headers=headers, timeout=10)
            print(f"Delete response: {resp.status_code} - {resp.text}")
            resp.raise_for_status()
            data = resp.json()
            
            # success response: {"status": "1", "messages": "成功"}
            if data.get("result") == 1 or data.get("status") == "1":
                return True, "删除成功"
            else:
                return False, f"删除失败: {data.get('msg', '未知错误')} (Status: {resp.status_code})"
        except Exception as e:
            print(f"Delete exception: {e}")
            return False, f"删除请求异常: {e}"

    def delete_group(self, group_id: str) -> tuple[bool, str]:
        """
        Delete a group using the provided API.
        """
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
                if result.get("result") == 1 or result.get("status") == True:
                    return True, "删除成功"
                return False, f"API 错误: {result.get('msg', '未知错误')}"
            except:
                if "success" in resp.text.lower():
                    return True, "删除成功"
                return False, f"服务器返回: {resp.text[:100]}"
                
        except Exception as e:
            return False, f"网络请求失败: {e}"

    def add_group(self, course_id: str, class_id: str, name: str) -> tuple[bool, str]:
        """
        Create a new group using the provided API.
        """
        url = "https://mobilelearn.chaoxing.com/v2/apis/active/group/add"
        data = {
            "courseId": course_id,
            "classId": class_id,
            "name": name
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
                if result.get("result") == 1 or result.get("status") == True:
                    return True, "新增成功"
                return False, f"API 错误: {result.get('msg', '未知错误')}"
            except:
                if "success" in resp.text.lower():
                    return True, "新增成功"
                return False, f"服务器返回: {resp.text[:100]}"
                
        except Exception as e:
            return False, f"网络请求失败: {e}"

    def get_teachers_for_clazz(self, course_id: str, clazz_id: str) -> list:
        """
        获取管理页面的教师列表 (teacher-team-manage)

        Args:
            course_id: 课程ID
            clazz_id: 班级ID (UNUSED in this specific endpoint, but kept for signature compatibility)

        Returns:
            教师列表，每个教师包含 id, name, workId, role, organization, selected 等信息
        """
        params = self.session_manager.course_params
        cpi = params.get('cpi', '')
        
        # URL and params based on the provided curl
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/teacher-team-manage"
        req_params = {
            "courseid": course_id,
            "requireTea": "",
            "cpi": cpi,
            "orderContentTeam": "ID",
            "orderTeam": "up",
            "role": "0"
        }

        headers = {
            "Accept": "text/html, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/course-manage?courseid={course_id}&clazzid={clazz_id}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
        }

        try:
            resp = self.session.get(url, params=req_params, headers=headers, timeout=10)
            print(f"教师列表(team-manage)请求状态码: {resp.status_code}")
            resp.raise_for_status()
            html = resp.text
            print(f"返回HTML长度: {len(html)}")

            # 解析HTML获取教师信息
            soup = BeautifulSoup(html, "lxml")
            teachers = []

            # Structure provided by user:
            # <ul class="dataBody_td" uid="30047383">
            #     <li class="dataBody_disabled operationBtnShowHide"></li>
            #     <li class="dataBody_name">郝玉锋</li>
            #     <li class="dataBody_read">创建者</li>
            #     <li class="dataBody_down"> 11113 </li>
            #     <li class="dataBody_depart"> 工学部 </li>
            # </ul>

            # Find all uls with class dataBody_td
            teacher_rows = soup.find_all("ul", class_="dataBody_td")
            
            print(f"找到教师行数: {len(teacher_rows)}")

            for row in teacher_rows:
                # Debug attributes to find if personid exists
                # print(f"DEBUG: Teacher Row Attributes: {row.attrs}")

                # 获取教师ID (uid attr vs personId)
                # User analysis shows: <ul class="dataBody_td" personId="..." teamTeachId="..." role="..." uid="...">
                # We need 'personId' for removal operations.
                
                # Check for 'personId' (case-sensitive or lowercase depending on bs4 parser, usually lowercase for HTML)
                # But let's check both just in case or iterate attrs
                teacher_personid = row.get("personId") or row.get("personid")
                teacher_uid = row.get("uid")
                
                # Use personId as primary ID if available, as that's what remove API needs
                teacher_id = teacher_personid if teacher_personid else teacher_uid
                
                # Store uid separately if needed, or put it in data
                # internal 'id' of item will be used for removal, so it MUST be personId if removing
                
                # 获取姓名
                name_li = row.find("li", class_="dataBody_name")
                name = name_li.get_text(strip=True) if name_li else "未知"

                # 获取角色 (dataBody_read)
                role_li = row.find("li", class_="dataBody_read")
                role = role_li.get_text(strip=True) if role_li else ""

                # 获取工号 (dataBody_down)
                work_li = row.find("li", class_="dataBody_down")
                work_id = work_li.get_text(strip=True) if work_li else ""

                # 获取院系/机构 (dataBody_depart)
                dept_li = row.find("li", class_="dataBody_depart")
                organization = dept_li.get_text(strip=True) if dept_li else ""

                # Check if it's the current user or disabled (though the HTML snippet shows disabled for creator)
                # We can assume they are all 'selected' or part of the team if they appear here.
                selected = True 

                print(f"教师信息(Parsed): id={teacher_id}, name={name}, workId={work_id}, role={role}, dept={organization}")

                teachers.append({
                    "id": teacher_id,
                    "name": name,
                    "workId": work_id,
                    "role": role,
                    "dept": organization, # Use 'dept' key to match search result struct if needed, or 'organization'
                    "organization": organization,
                    "selected": selected
                })

            print(f"解析教师团队列表成功，共 {len(teachers)} 名教师")
            return teachers
        except Exception as e:
            print(f"获取教师列表失败: {e}")
            import traceback
            traceback.print_exc()
            return []

    def search_teacher(self, query_name: str) -> dict:
        """
        搜索教师

        Args:
            query_name: 教师姓名（支持部分匹配）

        Returns:
            {
                "success": bool,
                "teachers": [
                    {
                        "id": "教师ID",
                        "enc": "加密参数",
                        "name": "姓名",
                        "workId": "工号",
                        "dept": "院系"
                    },
                    ...
                ],
                "error": str  # 仅在失败时有值
            }
        """
        params = self.session_manager.course_params
        course_id = params.get('courseid')
        cpi = params.get('cpi')
        fid = params.get('fid', '4311')

        if not course_id:
            return {"success": False, "error": "缺少课程ID"}

        try:
            # 先访问教师团队管理页面，获取 stuBankGetStuEnc 参数
            manage_url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/teacher-team-manage"
            manage_params = {
                "courseid": course_id,
                "cpi": cpi,
                "orderContentTeam": "ID",
                "orderTeam": "up",
                "role": "0"
            }
            manage_headers = {
                "Accept": "text/html, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6",
                "Connection": "keep-alive",
                "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/course-manage?courseid={course_id}",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin"
            }

            manage_resp = self.session.get(manage_url, params=manage_params, headers=manage_headers, timeout=10)
            print(f"访问教师团队管理页面状态码: {manage_resp.status_code}")

            # 检查是否返回了真正的错误页面（参数被篡改）
            manage_html = manage_resp.text
            if "参数被篡改" in manage_html and "nullMain" in manage_html:
                print("DEBUG: 访问教师团队管理页面返回真正的错误页面（参数被篡改）")
                print(f"错误页面内容: {manage_html[:500]}")
                return {"success": False, "error": "访问教师团队管理页面失败"}

            soup = BeautifulSoup(manage_html, "lxml")

            # 从页面中获取 stuBankGetStuEnc 参数
            enc_input = soup.find("input", id="stuBankGetStuEnc")
            enc_param = ""
            if enc_input:
                enc_param = enc_input.get("value", "")
                print(f"DEBUG: 从 stuBankGetStuEnc 提取到 enc 参数: {enc_param}")
            else:
                print("DEBUG: 未找到 stuBankGetStuEnc 元素")
                return {"success": False, "error": "无法从页面中获取 enc 参数"}

            # 获取其他可能的参数
            fid_param = fid
            fid_input = soup.find("input", id="queryFid")
            if fid_input:
                fid_param = fid_input.get("value", fid)
                print(f"DEBUG: 提取到 fid 参数: {fid_param}")

            ut_param = "t"  # 根据 curl 命令，ut 参数应该是 "t"
            groupid_param = "0"

            print(f"DEBUG: 最终使用的参数 - enc={enc_param}, ut={ut_param}, groupid={groupid_param}, fid={fid_param}")

            url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/searchteacher"
            req_params = {
                "courseId": course_id,
                "queryName": query_name,
                "groupid": groupid_param,
                "pageNum": "1",
                "enc": enc_param,
                "isAssistant": "false",
                "fid": fid_param,
                "ut": ut_param
            }

            headers = {
                "Accept": "*/*",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6",
                "Connection": "keep-alive",
                "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/course-manage?courseid={course_id}",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin"
            }

            resp = self.session.get(url, params=req_params, headers=headers, timeout=10)
            print(f"搜索教师请求状态码: {resp.status_code}")
            print(f"查询参数: {req_params}")
            resp.raise_for_status()
            html = resp.text
            print(f"返回HTML长度: {len(html)}")

            # 解析HTML获取教师信息
            soup = BeautifulSoup(html, "lxml")
            teachers = []

            # 查找所有教师行 - 使用更灵活的方式
            # 方法1：通过class属性查找
            teacher_rows = soup.find_all("ul", class_=lambda c: c and any("dataBody_addtea" in cls for cls in c) if isinstance(c, list) else False)

            # 方法2：如果方法1没找到，通过字符串匹配查找ul标签
            if not teacher_rows:
                # 使用字符串匹配
                from bs4 import Tag
                for ul in soup.find_all("ul"):
                    class_str = str(ul.get("class", []))
                    if "dataBody_addtea" in class_str:
                        teacher_rows.append(ul)

            print(f"找到教师行数: {len(teacher_rows)}")

            # 如果没找到，打印调试信息
            if not teacher_rows:
                print("DEBUG: 未找到教师行，打印HTML前1200字符:")
                print(html[:1200])

                # 尝试查找所有ul标签，看看有哪些
                print("DEBUG: 查找所有ul标签的class属性:")
                all_uls = soup.find_all("ul")
                for i, ul in enumerate(all_uls[:10]):  # 只打印前10个
                    classes = ul.get("class", [])
                    print(f"  ul[{i}]: class={classes}")

            for idx, row in enumerate(teacher_rows):
                # 打印每一行的HTML内容用于调试
                print(f"DEBUG: 教师行{idx+1} HTML:")
                print(str(row)[:500])

                # 获取personId和enc（注意：personid是全小写的）
                person_id = row.get("personid", "")  # 改为小写 personid
                enc = row.get("enc", "")

                # 获取姓名
                name_span = row.find("span", class_="txt-w")
                name = name_span.get_text(strip=True) if name_span else "未知"

                # 获取工号（第二个li，带有colorIn类）
                all_lis = row.find_all("li", class_="colorIn")
                work_id = ""
                dept = ""
                if len(all_lis) >= 1:
                    work_id = all_lis[0].get_text(strip=True)
                if len(all_lis) >= 2:
                    dept = all_lis[1].get_text(strip=True)

                print(f"搜索结果教师信息: personId={person_id}, enc={enc}, name={name}, workId={work_id}, dept={dept}")

                teachers.append({
                    "id": person_id,
                    "enc": enc,
                    "name": name,
                    "workId": work_id,
                    "dept": dept
                })

            print(f"搜索教师成功，共 {len(teachers)} 名教师")
            return {
                "success": True,
                "teachers": teachers
            }
        except Exception as e:
            print(f"搜索教师失败: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": f"搜索教师失败: {str(e)}"}

    def add_team_teacher(self, course_id: str, teacher_info_list: list) -> tuple[bool, str]:
        """
        添加教师到教学团队
        
        Args:
            course_id: 课程ID
            teacher_info_list: 包含 {"personId": "...", "enc": "..."} 的字典列表
            
        Returns:
            (success, message): 是否成功及结果消息
        """
        params = self.session_manager.course_params
        cpi = params.get('cpi', '')
        
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/addteamteacher"
        
        # Construct userDataStr JSON
        import json
        user_data_str = json.dumps(teacher_info_list)
        
        req_params = {
            "courseId": course_id,
            "cpi": cpi,
            "isAssistant": "false",
            "userDataStr": user_data_str
        }
        
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/course-manage?courseid={course_id}&cpi={cpi}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
        }
        
        try:
            print(f"DEBUG: Adding teachers params: {req_params}")
            resp = self.session.get(url, params=req_params, headers=headers, timeout=10)
            print(f"Add teacher response: {resp.status_code} - {resp.text}")
            resp.raise_for_status()
            
            try:
                res_data = resp.json()
            except Exception:
                return False, f"解析响应失败: {resp.text[:100]}"
            
            # Response format: {"msg":"添加成功","addTeacherCount":1,"status":true}
            if res_data.get("status") == True:
                msg = res_data.get("msg", "添加成功")
                count = res_data.get("addTeacherCount", 0)
                return True, f"{msg} (成功添加 {count} 人)"
            else:
                return False, res_data.get("msg", "添加失败")
                
        except Exception as e:
            return False, f"网络请求失败: {e}"

    def remove_team_teacher(self, course_id: str, teacher_ids: list) -> tuple[bool, str]:
        """
        移除教学团队中的教师
        
        Args:
            course_id: 课程ID
            teacher_ids: 包含要移除教师 personId 的列表 (strings)
            
        Returns:
            (success, message): 是否成功及结果消息
        """
        params = self.session_manager.course_params
        cpi = params.get('cpi', '')
        clazz_id = params.get('clazzid') or params.get('classId') or ''
        
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/removeteamteaher"
        
        # personIds as comma-separated string
        person_ids_str = ",".join(teacher_ids)
        
        req_params = {
            "courseId": course_id,
            "cpi": cpi,
            "personIds": person_ids_str
        }
        
        import time
        t_param = str(int(time.time() * 1000))
        
        # Construct a rich Referer mimicking browser behavior
        # Note: The server likely checks for clazzid/enc/ut in the referer context
        referer = (
            f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/course-manage"
            f"?courseid={course_id}&clazzid={clazz_id}"
            f"&courseId={course_id}&classId={clazz_id}&clazzId={clazz_id}"
            f"&cpi={cpi}&enc={params.get('enc', '')}"
            f"&openc={params.get('openc', '')}&t={t_param}&ut=t&loadContentType=0"
        )

        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": referer,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
        }
        
        try:
            print(f"DEBUG: Removing teachers params: {req_params}")
            print(f"DEBUG: Referer: {referer}")
            resp = self.session.get(url, params=req_params, headers=headers, timeout=10)
            print(f"Remove teacher response: {resp.status_code} - {resp.text}")
            resp.raise_for_status()
            
            try:
                res_data = resp.json()
            except Exception:
                return False, f"解析响应失败: {resp.text[:100]}"
            
            # Response handling based on proper behavior
            # Successful response: {"success": true, "msg": "移除成功"} or similar keys
            # Failed response often: {"status": false, "msg": "移除失败的：..."}
            # Special case: "无权限设置！" actually means success per user feedback
            msg = res_data.get("msg", "")
            
            if "无权限设置" in msg:
                return True, "移除成功"
                
            if res_data.get("result") == 1 or res_data.get("status") == True:
                return True, msg or "移除成功"
            else:
                return False, msg or "移除失败"
                
        except Exception as e:
            return False, f"网络请求失败: {e}"

    def get_course_creation_data(self) -> dict:
        """
        获取课程创建页面的初始数据，包括课程教师和所属单位列表
        """
        try:
            url = "https://mooc2-gray.chaoxing.com/mooc2-ans/visit/course/boxtip"
            params = {
                "type": "5",
                "isFirefly": "0"
            }

            # 添加必要的headers
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Connection": "keep-alive",
                "Referer": "https://mooc2-gray.chaoxing.com/visit/interaction",
                "Sec-Fetch-Dest": "iframe",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
            }

            response = self.session.get(url, params=params, headers=headers, timeout=10)
            response.encoding = 'utf-8'

            if response.status_code != 200:
                print(f"DEBUG get_course_creation_data HTTP错误: {response.status_code}")
                print(f"DEBUG 响应内容: {response.text[:500]}")
                return {"success": False, "error": f"HTTP错误: {response.status_code}"}

            soup = BeautifulSoup(response.text, 'html.parser')

            # 提取课程教师 - 尝试多种查找方式
            teacher_name = ''
            # 方法1: 按id查找
            teacher_input = soup.find('input', id='teachers')
            if teacher_input:
                teacher_name = teacher_input.get('value', '').strip()
            # 方法2: 按name属性查找
            if not teacher_name:
                teacher_input = soup.find('input', {'name': 'teachers'})
                if teacher_input:
                    teacher_name = teacher_input.get('value', '').strip()
            # 方法3: 按placeholder查找
            if not teacher_name:
                teacher_input = soup.find('input', {'placeholder': '请输入课程教师'})
                if teacher_input:
                    teacher_name = teacher_input.get('value', '').strip()

            # 提取所属单位列表 - 从li元素中提取
            units = []  # 存储完整的单位信息：{"name": "名称", "data": "data值", "fid": "fid值"}

            # 查找所有包含单位信息的li元素（class包含select-item）
            select_items = soup.find_all('li', class_=lambda x: x and 'select-item' in str(x))
            print(f"DEBUG 找到 {len(select_items)} 个select-item")

            for item in select_items:
                # 在li中查找包含单位名称的div（class包含list-name）
                list_name_div = item.find('div', class_=lambda x: x and 'list-name' in str(x))
                if list_name_div:
                    unit_text = list_name_div.get_text(strip=True)
                    unit_data = list_name_div.get('data', '')
                    unit_fid = list_name_div.get('fid', '')
                    if unit_text:
                        unit_info = {
                            "name": unit_text,
                            "data": unit_data,
                            "fid": unit_fid
                        }
                        units.append(unit_info)
                        print(f"DEBUG 找到单位: {unit_text}, data={unit_data}, fid={unit_fid}")

            print(f"DEBUG get_course_creation_data: teacher='{teacher_name}', units数量={len(units)}")

            return {
                "success": True,
                "teacher": teacher_name,
                "units": units
            }
        except Exception as e:
            print(f"DEBUG get_course_creation_data error: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": f"获取数据失败: {e}"}

    def get_group_list(self, fid: str, cpi: str = "", course_id: str = "0") -> dict:
        """
        获取院系列表（优先使用 getgroupclassifylist 接口，失败时回退到 creategrouplist）
        :param fid: 单位的fid值
        :param cpi: 所属单位的data值（personId）
        :param course_id: 课程ID，新建课程时为"0"
        :return: 包含院系列表的字典
        """
        # 优先尝试使用 getgroupclassifylist 接口（需要权限）
        try:
            url = "https://mooc2-gray.chaoxing.com/mooc2-ans/coursemanage/getgroupclassifylist"
            params = {
                "courseId": course_id,
                "v": "0",
                "fid": fid,
                "refergroupdata": "1",
                "cpi": cpi
            }

            # 添加必要的headers
            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5",
                "Connection": "keep-alive",
                "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/course-manage?courseid={course_id}&cpi={cpi}",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest"
            }

            response = self.session.get(url, params=params, headers=headers, timeout=10)
            response.encoding = 'utf-8'

            if response.status_code != 200:
                print(f"DEBUG get_group_list (新接口) HTTP错误: {response.status_code}，回退到旧接口")
                return self._get_group_list_fallback(fid)

            # 解析JSON响应
            result = response.json()

            if not result.get("status"):
                print(f"DEBUG get_group_list (新接口) 返回失败: {result}，回退到旧接口")
                return self._get_group_list_fallback(fid)

            # 提取院系列表
            departments = result.get("departments", [])
            groups = []

            for dept in departments:
                group_info = {
                    "name": dept.get("name", ""),
                    "data": str(dept.get("id", ""))
                }
                groups.append(group_info)
                print(f"DEBUG 找到院系: {group_info['name']}, id={group_info['data']}")

            print(f"DEBUG get_group_list (新接口): fid={fid}, cpi={cpi}, course_id={course_id}, groups数量={len(groups)}")

            return {
                "success": True,
                "groups": groups
            }
        except Exception as e:
            print(f"DEBUG get_group_list (新接口) 异常: {e}，回退到旧接口")
            return self._get_group_list_fallback(fid)

    def _get_group_list_fallback(self, fid: str) -> dict:
        """
        使用旧接口获取院系列表（备用方案）
        :param fid: 单位的fid值
        :return: 包含院系列表的字典
        """
        try:
            from bs4 import BeautifulSoup
            url = "https://mooc2-gray.chaoxing.com/mooc2-ans/visit/creategrouplist"
            params = {"fid": fid}

            # 添加必要的headers
            headers = {
                "Accept": "text/html, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Connection": "keep-alive",
                "Referer": "https://mooc2-gray.chaoxing.com/mooc2-ans/visit/course/boxtip?type=5&isFirefly=0",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest"
            }

            response = self.session.get(url, params=params, headers=headers, timeout=10)
            response.encoding = 'utf-8'

            if response.status_code != 200:
                print(f"DEBUG get_group_list_fallback HTTP错误: {response.status_code}")
                return {"success": False, "error": f"HTTP错误: {response.status_code}"}

            soup = BeautifulSoup(response.text, 'html.parser')

            # 提取院系列表 - 从li元素中提取
            groups = []

            # 查找所有包含院系信息的li元素（class包含select-item）
            select_items = soup.find_all('li', class_=lambda x: x and 'select-item' in str(x))
            print(f"DEBUG (旧接口) 找到 {len(select_items)} 个select-item（院系）")

            for item in select_items:
                # 在li中查找包含院系名称的div（class包含list-name）
                list_name_div = item.find('div', class_=lambda x: x and 'list-name' in str(x))
                if list_name_div:
                    group_text = list_name_div.get_text(strip=True)
                    group_data = list_name_div.get('data', '')
                    if group_text:
                        group_info = {
                            "name": group_text,
                            "data": group_data
                        }
                        groups.append(group_info)
                        print(f"DEBUG (旧接口) 找到院系: {group_text}, data={group_data}")

            print(f"DEBUG get_group_list_fallback: fid={fid}, groups数量={len(groups)}")

            return {
                "success": True,
                "groups": groups
            }
        except Exception as e:
            print(f"DEBUG get_group_list_fallback error: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": f"获取院系列表失败: {e}"}

    def get_semester_list(self, fid: str, course_id: str = "0") -> dict:
        """
        获取学期列表
        :param fid: 单位的fid值
        :param course_id: 课程ID，默认为"0"
        :return: 包含学期列表的字典
        """
        try:
            url = "https://mooc2-gray.chaoxing.com/mooc2-ans/visit/createcoursetermlist"
            params = {
                "fid": fid,
                "courseId": course_id
            }

            # 添加必要的headers
            headers = {
                "Accept": "text/html, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Connection": "keep-alive",
                "Referer": "https://mooc2-gray.chaoxing.com/mooc2-ans/visit/course/boxtip?type=5&isFirefly=0",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest"
            }

            response = self.session.get(url, params=params, headers=headers, timeout=10)
            response.encoding = 'utf-8'

            if response.status_code != 200:
                print(f"DEBUG get_semester_list HTTP错误: {response.status_code}")
                return {"success": False, "error": f"HTTP错误: {response.status_code}"}

            soup = BeautifulSoup(response.text, 'html.parser')

            # 提取学期列表 - 从li元素中提取
            semesters = []  # 存储完整的学期信息：{"name": "名称", "data": "data值"}

            # 查找所有包含学期信息的li元素（class包含select-item）
            select_items = soup.find_all('li', class_=lambda x: x and 'select-item' in str(x))
            print(f"DEBUG 找到 {len(select_items)} 个select-item（学期）")

            for item in select_items:
                # 在li中查找包含学期名称的div（class包含list-name）
                list_name_div = item.find('div', class_=lambda x: x and 'list-name' in str(x))
                if list_name_div:
                    semester_text = list_name_div.get_text(strip=True)
                    semester_data = list_name_div.get('data', '')
                    if semester_text:
                        semester_info = {
                            "name": semester_text,
                            "data": semester_data
                        }
                        semesters.append(semester_info)
                        print(f"DEBUG 找到期: {semester_text}, data={semester_data}")

            print(f"DEBUG get_semester_list: fid={fid}, course_id={course_id}, semesters数量={len(semesters)}")

            return {
                "success": True,
                "semesters": semesters
            }
        except Exception as e:
            print(f"DEBUG get_semester_list error: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": f"获取学期列表失败: {e}"}

    def upload_cover_image(self, image_path: str) -> dict:
        """上传图片到超星服务器，返回图片URL"""
        try:
            import base64
            import time

            # 先访问课程创建页面获取uid和enc2参数
            print(f"DEBUG 访问课程创建页面获取uid和enc2...")
            boxtip_url = "https://mooc2-gray.chaoxing.com/mooc2-ans/visit/course/boxtip"
            params = {
                "type": "5",
                "isFirefly": "0"
            }
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Connection": "keep-alive",
                "Referer": "https://mooc2-gray.chaoxing.com/visit/interaction",
                "Sec-Fetch-Dest": "iframe",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
            }

            response = self.session.get(boxtip_url, params=params, headers=headers, timeout=10)
            print(f"DEBUG 课程创建页面状态: {response.status_code}")

            # 从HTML中解析enc2参数
            uid = ""
            enc2 = ""
            upload_timestamp = None

            # 查找包含uploadBase64的JavaScript代码
            html_text = response.text
            import re

            # 尝试从JavaScript中解析enc2
            # 模式: uploadBase64?uid=30047383&enc2=eafc71c2e5ef6ebff7ec345338b727d6&t=...
            pattern = r'uploadBase64\?uid=(\d+)&enc2=([a-f0-9]+)&t=(\d+)'
            match = re.search(pattern, html_text)

            if match:
                uid = match.group(1)
                enc2 = match.group(2)
                upload_timestamp = match.group(3)
                print(f"DEBUG 从HTML解析: uid={uid}, enc2={enc2}, t={upload_timestamp}")
            else:
                print(f"DEBUG 未能从HTML中解析enc2，尝试备用方法...")
                # 备用：从cookies中获取
                try:
                    cookies_dict = {cookie.name: cookie.value for cookie in self.session.cookies}
                    uid = cookies_dict.get("UID", "")
                    enc2 = cookies_dict.get("xxtenc", "")
                    print(f"DEBUG 从cookies获取: UID={uid}, xxtenc={enc2}")
                    # 生成新的timestamp
                    upload_timestamp = str(int(time.time() * 1000))
                except Exception as e:
                    print(f"DEBUG 获取cookies时出错: {e}")

            # 如果还是没有，尝试从course_params中获取
            if not uid:
                uid = self.session_manager.course_params.get('uid', '')
            if not enc2:
                enc2 = self.session_manager.course_params.get('enc2', '')

            print(f"DEBUG 最终获取: uid={uid}, enc2={enc2}")

            # 构建上传URL，使用从HTML解析的timestamp
            # 如果没有从HTML解析到timestamp，则使用当前时间
            if upload_timestamp:
                upload_url = f"https://mooc-upload-ans.chaoxing.com/edit/uploadBase64?uid={uid}&enc2={enc2}&t={upload_timestamp}"
            else:
                timestamp = int(time.time() * 1000)
                upload_url = f"https://mooc-upload-ans.chaoxing.com/edit/uploadBase64?uid={uid}&enc2={enc2}&t={timestamp}"

            # 使用课程创建页面作为Referer
            referer_url = "https://mooc2-gray.chaoxing.com/"

            # 构建表单数据 - requests会自动设置正确的Content-Type
            # 使用文件对象而不是字节数据
            import os
            headers = {
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5',
                'Connection': 'keep-alive',
                'Origin': 'https://mooc2-gray.chaoxing.com',
                'Referer': referer_url,
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-site',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36',
                'sec-ch-ua': '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"macOS"'
            }
            # 注意：不要手动设置Content-Type，requests会自动处理multipart/form-data和boundary

            # 关键步骤：先访问上传域名以获取必要的cookies (jroseupload, k8s-upload, route)
            print(f"DEBUG 正在获取上传所需的cookies...")
            upload_domain = "https://mooc-upload-ans.chaoxing.com/"
            try:
                self.session.get(upload_domain, timeout=10)
                # 打印获取到的上传相关cookies
                upload_cookies = [c for c in self.session.cookies if 'upload' in c.domain or c.name in ['jroseupload', 'k8s-upload', 'route']]
                print(f"DEBUG 获取到的上传cookies数量: {len(upload_cookies)}")
                for cookie in upload_cookies:
                    print(f"DEBUG   - {cookie.name}: {cookie.value[:30]}...")
            except Exception as e:
                print(f"DEBUG 访问上传域名时出错（继续尝试）: {e}")

            print(f"DEBUG 上传URL: {upload_url}")
            print(f"DEBUG 文件路径: {image_path}")
            print(f"DEBUG 原始文件名: {os.path.basename(image_path)}")

            # 根据文件扩展名确定MIME类型
            ext = os.path.splitext(image_path)[1].lower()
            mime_type_map = {
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.gif': 'image/gif',
                '.bmp': 'image/bmp'
            }
            mime_type = mime_type_map.get(ext, 'image/png')
            file_type = ext[1:] if ext else 'png'  # 去掉点号，例如 '.png' -> 'png'
            
            # 生成文件名（与前端JavaScript一致的格式：course-时间戳.png）
            from datetime import datetime
            timestamp = datetime.now().isoformat().replace(':', '-').replace('.', '-')
            filename = f"course-{timestamp}.png"
            
            print(f"DEBUG MIME类型: {mime_type}")
            print(f"DEBUG 文件类型字段: {file_type}")
            print(f"DEBUG 生成的文件名: {filename}")
            
            # 使用 multipart/form-data 上传（与前端一致）
            # 关键：包含 filePart (文件), fileType, name 三个字段
            with open(image_path, 'rb') as f:
                files = {
                    'filePart': (filename, f, mime_type)
                }
                data = {
                    'fileType': file_type,
                    'name': filename
                }
                
                print(f"DEBUG 上传multipart/form-data: filePart={filename}, fileType={file_type}, name={filename}")
                
                # 移除Content-Type让requests自动设置
                upload_headers = headers.copy()
                upload_headers.pop('Content-Type', None)
                
                response = self.session.post(upload_url, files=files, data=data, headers=upload_headers, timeout=30)
            
            response.encoding = 'utf-8'

            print(f"DEBUG upload_cover_image status: {response.status_code}")
            print(f"DEBUG upload_cover_image response: {response.text[:500]}")

            if response.status_code != 200:
                return {"success": False, "error": f"上传失败: HTTP {response.status_code}"}

            result = response.json()

            if result.get('status'):
                return {
                    "success": True,
                    "url": result.get('url', ''),
                    "objectid": result.get('objectid', ''),
                    "objectIdEnc": result.get('objectIdEnc', '')
                }
            else:
                error_msg = result.get('msg', '服务器返回失败状态')
                return {"success": False, "error": f"上传失败: {error_msg}"}

        except Exception as e:
            print(f"DEBUG upload_cover_image error: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": f"上传失败: {e}"}

    def get_course_category_list(self, course_id: str, fid: str, cpi: str) -> dict:
        """获取课程分类列表及所属院系列表
        
        Args:
            course_id: 课程ID
            fid: 机构ID
            cpi: CPI参数
            
        Returns:
            dict: {"success": bool, "categories": list, "departments": list, "default_category": str, "error": str}
        """
        try:
            url = "https://mooc2-gray.chaoxing.com/mooc2-ans/coursemanage/getgroupclassifylist"
            params = {
                "courseId": course_id,
                "v": "0",
                "fid": fid,
                "refergroupdata": "0",
                "cpi": cpi
            }
            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Connection": "keep-alive",
                "X-Requested-With": "XMLHttpRequest",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
            }
            
            print(f"DEBUG: get_course_category_list requesting {url} with {params}")
            response = self.session.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code != 200:
                print(f"DEBUG: get_course_category_list HTTP Error: {response.status_code}")
                return {"success": False, "error": f"获取列表失败: HTTP {response.status_code}"}
                
            result = response.json()
            # print(f"DEBUG: get_course_category_list full result: {result}") # Keeping this in case we need deeper debug
            
            if result.get('status'):
                import json
                
                # 1. 解析课程分类 (categoryListArray)
                categories = []
                cat_json = result.get('categoryListArray')
                if isinstance(cat_json, str) and cat_json:
                    try:
                        cat_data = json.loads(cat_json)
                    except:
                        cat_data = []
                else:
                    cat_data = cat_json if isinstance(cat_json, list) else []
                
                if isinstance(cat_data, list):
                    for cat in cat_data:
                        categories.append({
                            "id": str(cat.get('id') or ''),
                            "name": str(cat.get('word') or cat.get('name') or '')
                        })
                
                # 2. 解析院系列表 (departments)
                departments = []
                dept_data = result.get('departments')
                if isinstance(dept_data, list):
                    for dept in dept_data:
                        departments.append({
                            "id": str(dept.get('id') or ''),
                            "name": str(dept.get('name') or '')
                        })
                
                default_category = result.get('courseClassifyName', '')
                print(f"DEBUG: 成功解析出 {len(categories)} 个分类, {len(departments)} 个院系. 默认分类: {default_category}")
                
                return {
                    "success": True, 
                    "categories": categories,
                    "departments": departments,
                    "default_category": default_category
                }
            else:
                print(f"DEBUG: get_course_category_list status is False. msg: {result.get('msg')}")
                return {"success": False, "error": f"接口返回状态为 False: {result.get('msg')}"}
        except Exception as e:
            print(f"DEBUG: get_course_category_list exception: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def get_course_setting(self, course_id: str, cpi: str) -> dict:
        """获取课程基本信息设置
        
        Args:
            course_id: 课程ID
            cpi: CPI参数
            
        Returns:
            dict: 包含解析出的课程信息
        """
        try:
            url = f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/getcoursesetting"
            params = {
                "courseId": course_id,
                "cpi": cpi,
                "v": "0",
                "leftNavigation": "0"
            }
            headers = {
                "Accept": "text/html, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Connection": "keep-alive",
                "X-Requested-With": "XMLHttpRequest",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
            }
            
            print(f"DEBUG get_course_setting requesting: {url} with params {params}")
            response = self.session.get(url, params=params, headers=headers, timeout=10)
            print(f"DEBUG get_course_setting status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"DEBUG get_course_setting failed with status {response.status_code}")
                return {"success": False, "error": f"获取信息失败: HTTP {response.status_code}"}
            
            # 增加调试：如果内容太短，打印全部；否则打印前 3000
            html_content = response.text
            print(f"DEBUG get_course_setting html length: {len(html_content)}")
            if len(html_content) < 5000:
                print(f"DEBUG get_course_setting full html:\n{html_content}")
            else:
                print(f"DEBUG get_course_setting html snippet (first 3000):\n{html_content[:3000]}")
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            data = {"success": True}
            
            # 1. 封面
            img_tag = soup.find('img', id='cloneCourseImg')
            if img_tag:
                data['default_cover'] = img_tag.get('src', '')
                print(f"DEBUG found cover: {data['default_cover']}")
            
            # 2. 课程名称
            name_tag = soup.find('p', id='courseName')
            if name_tag:
                data['name'] = name_tag.get_text().strip()
                print(f"DEBUG found name from p#courseName: {data['name']}")
            else:
                name_input = soup.find('input', id='changeCourseName')
                if name_input:
                    data['name'] = name_input.get('value', '')
                    print(f"DEBUG found name from input#changeCourseName: {data['name']}")
            
            # 3. 课程英文名称
            en_name_tag = soup.find('p', id='courseEnglish')
            if en_name_tag:
                data['english_name'] = en_name_tag.get_text().strip()
                print(f"DEBUG found english_name from p#courseEnglish: {data['english_name']}")
            else:
                en_name_input = soup.find('input', id='changeCourseEnglish')
                if en_name_input:
                    data['english_name'] = en_name_input.get('value', '')
                    print(f"DEBUG found english_name from input#changeCourseEnglish: {data['english_name']}")
                
            # 4. 课程教师
            teacher_tag = soup.find('p', id='courseTeachers')
            if teacher_tag:
                data['teacher'] = teacher_tag.get_text().strip()
                print(f"DEBUG found teacher from p#courseTeachers: {data['teacher']}")
            else:
                teacher_input = soup.find('input', id='changeCourseTeachers')
                if teacher_input:
                    data['teacher'] = teacher_input.get('value', '')
                    print(f"DEBUG found teacher from input#changeCourseTeachers: {data['teacher']}")
                
            # 5. 课程归属单位
            unit_tag = soup.find('p', id='showCourseUnitName')
            if unit_tag:
                data['unit_name'] = unit_tag.get_text().strip()
                # 尝试抓取 ID
                uid_input = soup.find('input', id='oldSingleSelect') or soup.find('input', id='singSelectInput')
                if uid_input:
                    data['unit_id'] = uid_input.get('data-id', '')
                print(f"DEBUG found unit from p#showCourseUnitName: {data['unit_name']} ({data.get('unit_id', '')})")
            else:
                unit_input = soup.find('input', id='singSelectInput')
                if unit_input:
                    data['unit_id'] = unit_input.get('data-id', '')
                    data['unit_name'] = unit_input.get('value', '')
                    print(f"DEBUG found unit from input#singSelectInput: {data['unit_name']} ({data['unit_id']})")
                
            # 6. 课程所属院系
            dept_tag = soup.find('p', id='showCourseGroupName') or soup.find('p', id='secondSelectInput') # 有时可能是p
            if dept_tag and dept_tag.name == 'p':
                data['dept_name'] = dept_tag.get_text().strip()
                did_input = soup.find('input', id='oldGroup') or soup.find('input', id='secondSelectInput')
                if did_input:
                    data['dept_id'] = did_input.get('data-id', '') or did_input.get('data-groupid', '')
                print(f"DEBUG found dept from p#showCourseGroupName: {data['dept_name']} ({data.get('dept_id', '')})")
            else:
                dept_input = soup.find('input', id='secondSelectInput')
                if dept_input:
                    data['dept_id'] = dept_input.get('data-id', '')
                    data['dept_name'] = dept_input.get('value', '')
                    print(f"DEBUG found dept from input#secondSelectInput: {data['dept_name']} ({data['dept_id']})")
                
            # 7. 课程分类
            cat_tag = soup.find('p', id='courseClassifyName')
            if cat_tag:
                data['category'] = cat_tag.get_text().strip()
                print(f"DEBUG found category from p#courseClassifyName: {data['category']}")
            else:
                cat_input = soup.find('input', id='courseClassifyNameInput')
                if cat_input:
                    cat_val = cat_input.get('value', '')
                    data['category'] = cat_val if cat_val else "本校课程"
                    print(f"DEBUG found category from input: {data['category']}")
                else:
                    data['category'] = "本校课程"
                
            # 8. 课程说明
            desc_textarea = soup.find('textarea', id='changeCourseSchools')
            if desc_textarea:
                data['description'] = desc_textarea.get_text().strip()
                print(f"DEBUG found description: {data['description'][:50]}...")
            else:
                desc_tag = soup.find('p', id='courseSchools') # 猜测
                if desc_tag:
                    data['description'] = desc_tag.get_text().strip()
                    print(f"DEBUG found description from p: {data['description'][:50]}...")
            
            return data
            
        except Exception as e:
            print(f"DEBUG get_course_setting error: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def generate_ai_cover(self, course_name: str) -> dict:
        """使用AI生成课程封面
        
        Args:
            course_name: 课程名称
            
        Returns:
            dict: {"success": bool, "url": str, "objectId": str, "error": str}
        """
        try:
            # 步骤1: 访问课程创建页面获取 checkUserToken
            print(f"DEBUG 获取 checkUserToken...")
            boxtip_url = "https://mooc2-gray.chaoxing.com/mooc2-ans/visit/course/boxtip"
            params = {
                "type": "5",
                "isFirefly": "0"
            }
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5",
                "Connection": "keep-alive",
                "Referer": "https://mooc2-gray.chaoxing.com/visit/interaction",
                "Sec-Fetch-Dest": "iframe",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
            }
            
            response = self.session.get(boxtip_url, params=params, headers=headers, timeout=10)
            print(f"DEBUG boxtip页面状态: {response.status_code}")
            
            if response.status_code != 200:
                return {"success": False, "error": f"获取checkUserToken失败: HTTP {response.status_code}"}
            
            # 解析 checkUserToken
            soup = BeautifulSoup(response.text, 'html.parser')
            token_input = soup.find('input', {'id': 'checkUserToken'})
            
            if not token_input or not token_input.get('value'):
                print(f"DEBUG 未找到checkUserToken，HTML片段: {response.text[:500]}")
                return {"success": False, "error": "未找到checkUserToken"}
            
            check_user_token = token_input.get('value')
            print(f"DEBUG checkUserToken: {check_user_token}")
            
            # 步骤2: 调用AI生成接口
            print(f"DEBUG 调用AI生成封面接口...")
            generate_url = "https://mooc2-gray.chaoxing.com/mooc2-ans/visit/generateCourseCover"
            gen_params = {
                "courseName": course_name,
                "checkUserToken": check_user_token
            }
            gen_headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5",
                "Connection": "keep-alive",
                "Referer": f"{boxtip_url}?type=5&isFirefly=0",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest"
            }
            
            gen_response = self.session.get(generate_url, params=gen_params, headers=gen_headers, timeout=30)
            print(f"DEBUG AI生成响应状态: {gen_response.status_code}")
            print(f"DEBUG AI生成响应: {gen_response.text}")
            
            if gen_response.status_code != 200:
                return {"success": False, "error": f"AI生成失败: HTTP {gen_response.status_code}"}
            
            result = gen_response.json()
            
            if result.get('status'):
                # 解析嵌套的JSON字符串
                msg_data = result.get('msg', '{}')
                if isinstance(msg_data, str):
                    import json
                    msg_data = json.loads(msg_data)
                
                url = msg_data.get('url', '')
                object_id = msg_data.get('objectId', '')
                
                print(f"DEBUG AI生成成功: url={url}, objectId={object_id}")
                
                return {
                    "success": True,
                    "url": url,
                    "objectId": object_id
                }
            else:
                error_msg = result.get('msg', 'AI生成失败')
                return {"success": False, "error": f"AI生成失败: {error_msg}"}
                
        except Exception as e:
            print(f"DEBUG generate_ai_cover error: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": f"AI生成异常: {e}"}


    def get_question_folders(self, course_id: str = None, clazz_id: str = None) -> list:
        """
        获取题库文件夹列表
        
        Args:
            course_id: 课程ID，如果不提供则从 session 中获取
            clazz_id: 班级ID，如果不提供则从 session 中获取
        
        Returns:
            文件夹列表，每个元素是 QuestionFolder 对象的字典表示
        """
        params = self.session_manager.course_params
        
        if not course_id:
            course_id = params.get("courseid", "")
        if not clazz_id:
            clazz_id = params.get("clazzid", "")
        
        cpi = params.get("cpi", "")
        
        # 使用正确的 API：POST /mooc2-ans/qbank/search
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/qbank/search"
        
        headers = {
            "Accept": "text/html, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/qbank/questionlist?courseid={course_id}&clazzid={clazz_id}&cpi={cpi}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            "Origin": "https://mooc2-gray.chaoxing.com",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        
        # POST 数据
        data = {
            "courseid": course_id,
            "microTopicId": "0",
            "cpi": cpi,
            "dirId": "0",  # 0 表示根目录
            "courseIds": course_id,
            "qTypes": "",
            "eTypes": "",
            "difficulty": "-1",
            "sw": "",
            "pageNum": "0",
            "orderType": "",
            "orderByType": "",
            "orderByRight": "",
            "orderByName": "",
            "rightPercentFrom": "",
            "rightPercentTo": "",
            "pageSize": "30",
            "fromEdit": "false",
            "topicIds": "",
            "courseTargetIds": "",
            "labelIds": "",
            "createrId": "",
            "needHtml": "true",
            "hideEditBtn": "false",
            "qbanksystem": "0",
            "hideLockDir": "false",
            "dirCourseId": course_id
        }
        
        try:
            from bs4 import BeautifulSoup
            import re
            
            print(f"DEBUG get_question_folders: courseid={course_id}, clazzid={clazz_id}, cpi={cpi}")
            
            resp = self.session.post(url, data=data, headers=headers, timeout=15)
            print(f"题库文件夹列表请求状态码: {resp.status_code}")
            resp.raise_for_status()
            
            # 尝试解析 JSON 响应
            try:
                result = resp.json()
                print(f"DEBUG: JSON 响应类型: {type(result)}")
                if isinstance(result, dict):
                    print(f"DEBUG: JSON keys: {result.keys()}")
                    # 检查是否有 html 字段
                    html_content = result.get("html", "") or result.get("data", "")
                    if html_content:
                        return self._parse_question_folders_html(html_content, course_id)
                elif isinstance(result, list):
                    print(f"DEBUG: JSON 是列表，长度: {len(result)}")
                    return self._parse_question_folders_json(result, course_id)
            except Exception as json_e:
                print(f"DEBUG: 不是 JSON 响应，尝试解析 HTML: {json_e}")
            
            # 如果不是 JSON，尝试直接解析 HTML
            return self._parse_question_folders_html(resp.text, course_id)
            
        except Exception as e:
            print(f"获取题库文件夹失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _parse_question_folders_html(self, html_content: str, course_id: str) -> list:
        """从 HTML 内容解析文件夹列表"""
        from bs4 import BeautifulSoup
        import re
        
        soup = BeautifulSoup(html_content, "lxml")
        folders = []
        
        # 查找文件夹项 - 使用实际的 class 结构
        # <li class="list directory showitems list-new-build-fold clearaft list-folder" id="..." ...>
        folder_items = soup.find_all("li", class_="list-folder")
        print(f"DEBUG: 找到 li.list-folder 元素数量: {len(folder_items)}")
        
        for item in folder_items:
            try:
                # 提取文件夹 ID (直接在 li 的 id 属性中)
                folder_id = item.get("id", "")
                if not folder_id:
                    continue
                
                # 提取课程 ID
                folder_course_id = item.get("courseid", course_id)
                
                # 提取是否共享
                is_share = item.get("isshare", "0") == "1"
                
                # 提取创建者 ID
                creator_id = item.get("createrid", "")
                
                # 提取用户 ID
                user_id = item.get("userid", "")
                
                # 提取文件夹名称 - 在 <span class="dirname"> 中
                dirname_span = item.find("span", class_="dirname")
                name = dirname_span.get_text(strip=True) if dirname_span else "未命名"
                
                # 提取题目数量 - 在 <span class="question-num"> 中
                # 格式: "共 85 题"
                count = 0
                question_num_span = item.find("span", class_="question-num")
                if question_num_span:
                    num_match = re.search(r'(\d+)', question_num_span.get_text())
                    if num_match:
                        count = int(num_match.group(1))
                
                folder_data = {
                    "id": folder_id,
                    "name": name,
                    "count": count,
                    "course_id": folder_course_id,
                    "is_share": is_share,
                    "creator_id": creator_id,
                    "user_id": user_id,
                    "parent_id": None,
                    "children": []
                }
                
                folders.append(folder_data)
                print(f"解析文件夹: id={folder_id}, name={name}, count={count}")
                
            except Exception as e:
                print(f"DEBUG: 解析文件夹项失败: {e}")
                continue
        
        print(f"共获取到 {len(folders)} 个题库文件夹")
        return folders
    
    def _parse_question_folders_json(self, data: list, course_id: str) -> list:
        """从 JSON 数据解析文件夹列表"""
        folders = []
        
        for item in data:
            try:
                folder_data = {
                    "id": str(item.get("id", "") or item.get("folderId", "")),
                    "name": item.get("name", "") or item.get("folderName", "") or "未命名",
                    "count": item.get("questionNum", 0) or item.get("count", 0),
                    "course_id": course_id,
                    "is_share": item.get("isShare", False) or item.get("isShare", "0") == "1",
                    "creator_id": str(item.get("creatorId", "") or item.get("createrId", "")),
                    "user_id": str(item.get("userId", "")),
                    "parent_id": str(item.get("parentId", "")) if item.get("parentId") else None,
                    "children": []
                }
                
                if folder_data["id"]:
                    folders.append(folder_data)
                    print(f"解析文件夹(JSON): id={folder_data['id']}, name={folder_data['name']}")
                    
            except Exception as e:
                print(f"DEBUG: 解析 JSON 文件夹项失败: {e}")
                continue
        
        return folders
    
    def get_question_subfolders(self, folder_id: str, course_id: str = None) -> list:
        """
        获取子文件夹列表
        
        Args:
            folder_id: 父文件夹 ID
            course_id: 课程 ID
        
        Returns:
            子文件夹列表
        """
        params = self.session_manager.course_params
        
        if not course_id:
            course_id = params.get("courseid", "")
        
        cpi = params.get("cpi", "")
        
        # 使用正确的 API：POST /mooc2-ans/qbank/search
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/qbank/search"
        
        headers = {
            "Accept": "text/html, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/qbank/questionlist?courseid={course_id}&cpi={cpi}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            "Origin": "https://mooc2-gray.chaoxing.com",
        }
        
        # POST 数据 - 只获取子文件夹
        data = {
            "courseid": course_id,
            "microTopicId": "0",
            "cpi": cpi,
            "dirId": folder_id,  # 指定父文件夹 ID
            "courseIds": course_id,
            "qTypes": "",
            "eTypes": "",
            "difficulty": "-1",
            "sw": "",
            "pageNum": "1",
            "orderType": "",
            "orderByType": "",
            "orderByRight": "",
            "orderByName": "",
            "rightPercentFrom": "",
            "rightPercentTo": "",
            "pageSize": "30",
            "fromEdit": "false",
            "topicIds": "",
            "courseTargetIds": "",
            "labelIds": "",
            "createrId": "",
            "needHtml": "true",
            "hideEditBtn": "false",
            "qbanksystem": "0",
            "hideLockDir": "false",
            "dirCourseId": course_id
        }
        
        try:
            resp = self.session.post(url, data=data, headers=headers, timeout=15)
            resp.raise_for_status()
            
            # 尝试解析 JSON 响应
            try:
                result = resp.json()
                if isinstance(result, dict):
                    html_content = result.get("html", "") or result.get("data", "")
                    if html_content:
                        return self._parse_question_folders_html(html_content, course_id)
                elif isinstance(result, list):
                    return self._parse_question_folders_json(result, course_id)
            except:
                pass
            
            # 如果不是 JSON，直接解析 HTML
            return self._parse_question_folders_html(resp.text, course_id)
            
        except Exception as e:
            print(f"获取子文件夹失败: {e}")
            return []

    def delete_question_folder(self, folder_id: str, course_id: str = None) -> bool:
        """
        删除题库文件夹
        
        Args:
            folder_id: 文件夹 ID
            course_id: 课程 ID
        
        Returns:
            是否删除成功
        """
        params = self.session_manager.course_params
        
        if not course_id:
            course_id = params.get("courseid", "")
        
        cpi = params.get("cpi", "")
        
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/qbank/deal-recycle"
        
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/qbank/questionlist?courseid={course_id}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            "Origin": "https://mooc2-gray.chaoxing.com",
        }
        
        data = {
            "courseid": course_id,
            "id": folder_id,
            "status": "2",  # 删除状态
            "cpi": cpi,
            "type": "0"
        }
        
        try:
            resp = self.session.post(url, data=data, headers=headers, timeout=15)
            resp.raise_for_status()
            
            result = resp.json()
            print(f"DEBUG delete_question_folder: {result}")
            
            # 检查是否成功: {"msg":"文件夹已经放入回收站!","status":true}
            if isinstance(result, dict):
                status = result.get("status", False)
                msg = result.get("msg", "")
                print(f"删除结果: status={status}, msg={msg}")
                return status is True
            
            return True
            
        except Exception as e:
            print(f"删除文件夹失败: {e}")
            return False

    def create_question_folder(self, name: str, parent_id: str = "0", course_id: str = None) -> dict:
        """
        创建题库文件夹
        
        Args:
            name: 文件夹名称
            parent_id: 父文件夹 ID，"0" 表示根目录
            course_id: 课程 ID
        
        Returns:
            {"success": bool, "id": str, "msg": str}
        """
        params = self.session_manager.course_params
        
        if not course_id:
            course_id = params.get("courseid", "")
        
        cpi = params.get("cpi", "")
        
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/qbank/insertdir"
        
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/qbank/questionlist?courseid={course_id}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            "Origin": "https://mooc2-gray.chaoxing.com",
        }
        
        data = {
            "dirName": name,
            "courseid": course_id,
            "pid": parent_id,
            "cpi": cpi
        }
        
        try:
            resp = self.session.post(url, data=data, headers=headers, timeout=15)
            resp.raise_for_status()
            
            result = resp.json()
            print(f"DEBUG create_question_folder: {result}")
            
            # 返回格式: {"msg":"添加成功","newDirName":"demo","id":253784987,"status":true}
            if isinstance(result, dict):
                status = result.get("status", False)
                if status is True:
                    return {
                        "success": True,
                        "id": str(result.get("id", "")),
                        "name": result.get("newDirName", name),
                        "msg": result.get("msg", "创建成功")
                    }
                else:
                    return {
                        "success": False,
                        "msg": result.get("msg", "创建失败")
                    }
            
            return {"success": False, "msg": "未知错误"}
            
        except Exception as e:
            print(f"创建文件夹失败: {e}")
            return {"success": False, "msg": str(e)}

    def rename_question_folder(self, folder_id: str, new_name: str, parent_id: str = "0", course_id: str = None) -> bool:
        """
        重命名题库文件夹
        
        Args:
            folder_id: 文件夹 ID
            new_name: 新名称
            parent_id: 父文件夹 ID
            course_id: 课程 ID
        
        Returns:
            是否成功
        """
        params = self.session_manager.course_params
        
        if not course_id:
            course_id = params.get("courseid", "")
        
        cpi = params.get("cpi", "")
        
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/qbank/update-dirname"
        
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/qbank/questionlist?courseid={course_id}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            "Origin": "https://mooc2-gray.chaoxing.com",
        }
        
        data = {
            "dirName": new_name,
            "courseid": course_id,
            "pid": parent_id,
            "cpi": cpi,
            "id": folder_id
        }
        
        try:
            resp = self.session.post(url, data=data, headers=headers, timeout=15)
            resp.raise_for_status()
            
            result = resp.json()
            print(f"DEBUG rename_question_folder: {result}")
            
            # 返回格式: {"msg":"操作成功","status":true}
            if isinstance(result, dict):
                status = result.get("status", False)
                return status is True
            
            return False
            
        except Exception as e:
            print(f"重命名文件夹失败: {e}")
            return False

    def add_question(self, folder_id: str, question_data: dict, course_id: str = None) -> dict:
        """
        添加题目到题库
        
        Args:
            folder_id: 文件夹 ID
            question_data: 题目数据，包含:
                - content: 题目内容
                - q_type: 题目类型 (0=单选, 1=多选, 2=判断, 3=填空)
                - options: 选项列表 [{"key": "A", "value": "选项内容"}, ...]
                - answer: 正确答案 (如 "A" 或 "A,B,C")
                - analysis: 答案解析
                - difficulty: 难度系数 (0.1-1.0, 难=0.1-0.2, 中=0.3-0.7, 易=0.8-1.0)
                - easy: 难度等级 (0=易, 1=中, 2=难)
            course_id: 课程 ID
        
        Returns:
            {"success": bool, "msg": str, "question_id": str}
        """
        params = self.session_manager.course_params
        
        if not course_id:
            course_id = params.get("courseid", "")
        
        cpi = params.get("cpi", "")
        clazzid = params.get("clazzid", "")
        
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/qbank/add_question"
        
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/qbank/create-question?courseid={course_id}&cpi={cpi}&dirId={folder_id}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            "Origin": "https://mooc2-gray.chaoxing.com",
        }
        
        # 构建题目数据
        content = question_data.get("content", "")
        q_type = question_data.get("q_type", 0)  # 默认单选
        options = question_data.get("options", [])
        answer = question_data.get("answer", "")
        analysis = question_data.get("analysis", "")
        difficulty = question_data.get("difficulty", 0.5)  # 默认中等难度
        easy = question_data.get("easy", 1)  # 默认中等难度 (0=易, 1=中, 2=难)

        # LaTeX/math 公式渲染并替换为图片占位符
        import re
        import tempfile
        import base64
        from io import BytesIO

        # 每次上传题库时清除公式缓存，确保使用最新的渲染逻辑
        self._math_img_cache = {}

        def render_math_expr(expr: str):
            """用 matplotlib.mathtext 渲染表达式为图片并上传，返回 (url, width, height, plain_text)"""
            print(f"DEBUG render_math_expr: 开始渲染，表达式长度={len(expr)}")
            img_w, img_h = 0, 0
            try:
                import matplotlib
                matplotlib.use("Agg")
                from matplotlib import mathtext
                import re as re2

                expr_render = expr.strip()
                print(f"DEBUG render_math_expr: 表达式前100字符: {expr_render[:100]}")
                
                # 检查是否只包含普通字符（不需要渲染为图片）
                # 普通字符：字母、数字、括号、基本运算符、下标上标符号
                # 如果只包含普通字符，返回转换后的文本
                plain_chars_pattern = r'^[a-zA-Z0-9\s\(\)\[\]\{\}_\^+\-=<>,\.\';:\!]+$'
                if re2.match(plain_chars_pattern, expr_render):
                    print(f"DEBUG render_math_expr: 只包含普通字符，返回文本: {expr_render}")
                    return None, 0, 0, expr_render
                
                # LaTeX 命令转换为 Unicode 符号（用于保留为文本显示）
                expr_text = expr_render.replace(r"\iff", "⟺")  # 当且仅当
                expr_text = expr_text.replace(r"\implies", "⇒")  # 蕴含
                expr_text = expr_text.replace(r"\land", "∧")  # 逻辑与
                expr_text = expr_text.replace(r"\lor", "∨")  # 逻辑或
                expr_text = expr_text.replace(r"\lnot", "¬")  # 逻辑非
                expr_text = expr_text.replace(r"\neg", "¬")  # 逻辑非
                expr_text = expr_text.replace(r"\forall", "∀")  # 全称量词
                expr_text = expr_text.replace(r"\exists", "∃")  # 存在量词
                expr_text = expr_text.replace(r"\to", "→")  # 箭头
                expr_text = expr_text.replace(r"\rightarrow", "→")  # 箭头
                expr_text = expr_text.replace(r"\leftrightarrow", "↔")  # 双向箭头
                expr_text = expr_text.replace(r"\leq", "≤")  # 小于等于
                expr_text = expr_text.replace(r"\geq", "≥")  # 大于等于
                expr_text = expr_text.replace(r"\neq", "≠")  # 不等于
                expr_text = expr_text.replace(r"\in", "∈")  # 属于
                expr_text = expr_text.replace(r"\notin", "∉")  # 不属于
                expr_text = expr_text.replace(r"\subset", "⊂")  # 子集
                expr_text = expr_text.replace(r"\supset", "⊃")  # 超集
                expr_text = expr_text.replace(r"\cup", "∪")  # 并集
                expr_text = expr_text.replace(r"\cap", "∩")  # 交集
                expr_text = expr_text.replace(r"\wedge", "∧")  # 逻辑与
                expr_text = expr_text.replace(r"\vee", "∨")  # 逻辑或
                expr_text = expr_text.replace("...", "…")  # 省略号
                expr_text = expr_text.replace(r"\ldots", "…")  # 省略号
                expr_text = expr_text.replace(r"&", "")  # 移除对齐符 &
                expr_text = expr_text.replace(r"\lrarr", "↔")  # 双向箭头
                
                # 再次检查：如果转换后只包含普通字符和Unicode符号，也跳过渲染
                # 扩展普通字符模式，包含Unicode数学符号
                extended_pattern = r'^[a-zA-Z0-9\s\(\)\[\]\{\}_\^+\-=<>,\.\';:\!¬∀∃∧∨→↔⇒⟺∈∉⊂⊃⊆⊇∪∩∅≤≥≠≈≡±×÷∞∂∇∑∏∫√…]+$'
                print(f"DEBUG render_math_expr: LaTeX转Unicode后: {expr_text}")
                if re2.match(extended_pattern, expr_text):
                    print(f"DEBUG render_math_expr: 转换后只包含Unicode符号，返回文本: {expr_text}")
                    return None, 0, 0, expr_text
                
                # 预处理：替换不支持的命令为 matplotlib 支持的命令（用于渲染）
                
                # Unicode 符号转换为 LaTeX 命令（后面加空格避免粘连）
                # 逻辑符号
                expr_render = expr_render.replace("¬", r"\neg ")  # 逻辑非
                expr_render = expr_render.replace("∀", r"\forall ")  # 全称量词
                expr_render = expr_render.replace("∃", r"\exists ")  # 存在量词
                expr_render = expr_render.replace("∧", r"\wedge ")  # 逻辑与
                expr_render = expr_render.replace("∨", r"\vee ")  # 逻辑或
                expr_render = expr_render.replace("→", r"\rightarrow ")  # 箭头
                expr_render = expr_render.replace("↔", r"\leftrightarrow ")  # 双向箭头
                expr_render = expr_render.replace("⇒", r"\Rightarrow ")  # 蕴含
                expr_render = expr_render.replace("⇔", r"\Leftrightarrow ")  # 等价
                expr_render = expr_render.replace("⟺", r"\leftrightarrow ")  # 当且仅当 (iff)
                expr_render = expr_render.replace("⊤", r"\top ")  # 真
                expr_render = expr_render.replace("⊥", r"\bot ")  # 假
                expr_render = expr_render.replace("…", r"\ldots ")  # 省略号
                # 集合符号
                expr_render = expr_render.replace("∈", r"\in ")  # 属于
                expr_render = expr_render.replace("∉", r"\notin ")  # 不属于
                expr_render = expr_render.replace("⊂", r"\subset ")  # 真子集
                expr_render = expr_render.replace("⊃", r"\supset ")  # 真超集
                expr_render = expr_render.replace("⊆", r"\subseteq ")  # 子集
                expr_render = expr_render.replace("⊇", r"\supseteq ")  # 超集
                expr_render = expr_render.replace("∪", r"\cup ")  # 并集
                expr_render = expr_render.replace("∩", r"\cap ")  # 交集
                expr_render = expr_render.replace("∅", r"\emptyset ")  # 空集
                # 关系符号
                expr_render = expr_render.replace("≤", r"\leq ")  # 小于等于
                expr_render = expr_render.replace("≥", r"\geq ")  # 大于等于
                expr_render = expr_render.replace("≠", r"\neq ")  # 不等于
                expr_render = expr_render.replace("≈", r"\approx ")  # 约等于
                expr_render = expr_render.replace("≡", r"\equiv ")  # 恒等于
                expr_render = expr_render.replace("±", r"\pm ")  # 正负号
                expr_render = expr_render.replace("×", r"\times ")  # 乘号
                expr_render = expr_render.replace("÷", r"\div ")  # 除号
                # 其他符号
                expr_render = expr_render.replace("∞", r"\infty ")  # 无穷
                expr_render = expr_render.replace("∂", r"\partial ")  # 偏导
                expr_render = expr_render.replace("∇", r"\nabla ")  # 梯度
                expr_render = expr_render.replace("∑", r"\sum ")  # 求和
                expr_render = expr_render.replace("∏", r"\prod ")  # 求积
                expr_render = expr_render.replace("∫", r"\int ")  # 积分
                expr_render = expr_render.replace("√", r"\sqrt ")  # 根号
                # 清理多余空格
                expr_render = re2.sub(r'\s+', ' ', expr_render).strip()
                
                # 检测是否是多行公式
                is_multiline = re2.search(r"\\begin\{align\}|\\\\", expr_render)
                print(f"DEBUG render_math_expr: is_multiline={bool(is_multiline)}")
                
                actual_line_count = 1  # 记录实际行数
                
                if is_multiline:
                    print("DEBUG render_math_expr: 检测到多行公式，开始拆分")
                    # 多行公式：拆分并分别渲染
                    # 移除 align 环境
                    expr_render = re2.sub(r"\\begin\{align\}", "", expr_render)
                    expr_render = re2.sub(r"\\end\{align\}", "", expr_render)
                    expr_render = re2.sub(r"\\begin\{aligned\}", "", expr_render)
                    expr_render = re2.sub(r"\\end\{aligned\}", "", expr_render)
                    
                    # 按 \\ 拆分
                    lines = re2.split(r"\\\\", expr_render)
                    lines = [line.strip() for line in lines if line.strip()]
                    print(f"DEBUG render_math_expr: 拆分出 {len(lines)} 行")
                    
                    # 渲染每行
                    line_images = []
                    max_width = 0
                    total_height = 0
                    line_spacing = 4  # 行间距
                    
                    import matplotlib.pyplot as plt
                    for i, line in enumerate(lines):
                        line_expr = line.strip()
                        if not line_expr:
                            continue
                        print(f"DEBUG render_math_expr: 渲染第 {i+1} 行: {line_expr[:50]}...")
                        if not line_expr.startswith("$"):
                            line_expr = f"${line_expr}$"
                        
                        fig = plt.figure(figsize=(2, 1))
                        fig.text(0.5, 0.5, line_expr, ha="center", va="center", fontsize=16)
                        buf = BytesIO()
                        plt.savefig(buf, dpi=260, format="png", bbox_inches="tight", pad_inches=0.05, transparent=True)
                        plt.close(fig)
                        
                        from PIL import Image
                        line_im = Image.open(BytesIO(buf.getvalue()))
                        print(f"DEBUG render_math_expr: 第 {i+1} 行渲染成功，尺寸={line_im.width}x{line_im.height}")
                        line_images.append(line_im)
                        max_width = max(max_width, line_im.width)
                        total_height += line_im.height + line_spacing
                    
                    if not line_images:
                        print("DEBUG render_math_expr: 没有成功渲染的行")
                        return None, 0, 0
                    
                    actual_line_count = len(line_images)  # 记录实际行数
                    print(f"DEBUG render_math_expr: 实际行数={actual_line_count}")
                    
                    # 垂直拼接所有行
                    total_height -= line_spacing  # 移除最后一行的间距
                    print(f"DEBUG render_math_expr: 拼接 {len(line_images)} 行，总尺寸={max_width}x{total_height}")
                    combined = Image.new("RGBA", (max_width, total_height), (0, 0, 0, 0))
                    y_offset = 0
                    for line_im in line_images:
                        x_offset = 0  # 左对齐
                        combined.paste(line_im, (x_offset, y_offset))
                        y_offset += line_im.height + line_spacing
                    
                    img_w, img_h = combined.width, combined.height
                    buf2 = BytesIO()
                    combined.save(buf2, format="PNG")
                    png_bytes = buf2.getvalue()
                else:
                    print("DEBUG render_math_expr: 单行公式")
                    # 单行公式
                    if not expr_render.startswith("$"):
                        expr_render = f"${expr_render}$"
                    
                    import matplotlib.pyplot as plt
                    fig = plt.figure(figsize=(2, 1))
                    fig.text(0.5, 0.5, expr_render, ha="center", va="center", fontsize=16)
                    buf = BytesIO()
                    plt.savefig(buf, dpi=260, format="png", bbox_inches="tight", pad_inches=0.05, transparent=True)
                    plt.close(fig)
                    png_bytes = buf.getvalue()
                    
                    from PIL import Image
                    im = Image.open(BytesIO(png_bytes))
                    img_w, img_h = im.width, im.height

                # 缩放：限制最大宽度，并缩放到合适的高度
                from PIL import Image
                im = Image.open(BytesIO(png_bytes))
                
                # 计算目标高度：使用实际行数
                target_height = actual_line_count * 24
                
                # 缩放到目标高度
                if im.height > target_height:
                    scale = target_height / im.height
                    new_w = int(im.width * scale)
                    im = im.resize((new_w, target_height), Image.LANCZOS)
                    print(f"DEBUG render_math_expr: 缩放图片从 {img_w}x{img_h} 到 {new_w}x{target_height}")
                
                # 限制最大宽度
                max_w = 800
                if im.width > max_w:
                    new_h = int(im.height * max_w / im.width)
                    im = im.resize((max_w, new_h), Image.LANCZOS)
                    
                img_w, img_h = im.width, im.height
                print(f"DEBUG render_math_expr: 最终尺寸={img_w}x{img_h}")
                
                buf2 = BytesIO()
                im.save(buf2, format="PNG", optimize=True)
                png_bytes = buf2.getvalue()
            except Exception as e:
                print(f"DEBUG 渲染公式失败 {expr}: {e}")
                import traceback
                traceback.print_exc()
                return None, 0, 0, None

            # 上传图片，复用 upload_cover_image 通过临时文件
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp.write(png_bytes)
                    tmp_path = tmp.name
                upload_result = self.upload_cover_image(tmp_path)
                if upload_result.get("success"):
                    return upload_result.get("url", ""), img_w, img_h, None
                else:
                    print(f"DEBUG 公式上传失败: {upload_result}")
                    return None, 0, 0, None
            finally:
                if tmp_path:
                    try:
                        import os
                        os.remove(tmp_path)
                    except Exception:
                        pass

        def replace_math(text: str):
            # 仅当含有 $ 或 \[ 时才尝试解析，避免无关文本的正则开销
            if not text or not re.search(r"\$|\\\[", text):
                return text, {}
            # 改进正则：支持 $$ 后有空行的情况
            pattern = re.compile(r"\$\$\s*(.+?)\s*\$\$|\$\s*(.+?)\s*\$|\\\[\s*(.+?)\s*\\\]", re.DOTALL)
            replacements = {}
            new_text = text
            for idx, m in enumerate(pattern.finditer(text)):
                expr = m.group(1) or m.group(2) or m.group(3) or ""
                expr = expr.strip()
                print(f"DEBUG: 匹配到公式表达式: {expr[:100]}...")
                if not expr:
                    continue
                    
                if expr in self._math_img_cache:
                    cache_info = self._math_img_cache[expr]
                    if cache_info and cache_info[0] == "text":
                        # 缓存标记为纯文本
                        url, w, h, plain_text = None, 0, 0, cache_info[3]
                    elif isinstance(cache_info, tuple) and len(cache_info) == 4:
                        url, w, h, plain_text = cache_info
                    elif isinstance(cache_info, tuple):
                        url, w, h = cache_info
                        plain_text = None
                    else:
                        url, w, h = cache_info, 0, 48 # 兼容旧缓存
                        plain_text = None
                else:
                    result = render_math_expr(expr)
                    if result is None or len(result) < 4:
                        url, w, h = result[0] if result else None, result[1] if result else 0, result[2] if result else 0
                        plain_text = None
                    else:
                        url, w, h, plain_text = result
                    if url:
                        self._math_img_cache[expr] = (url, w, h, plain_text)
                    elif plain_text:
                        self._math_img_cache[expr] = ("text", 0, 0, plain_text)  # 缓存纯文本
                        
                if plain_text:
                    # 纯文本模式：直接替换为转换后的文本（去掉 $ 符号）
                    placeholder = f"__MATH_TEXT_{len(replacements)}__"
                    replacements[placeholder] = plain_text
                    new_text = new_text.replace(m.group(0), placeholder, 1)
                elif url:
                    # 图片模式：替换为图片标签
                    placeholder = f"__MATH_IMG_{len(replacements)}__"
                    # 根据实际高度计算行数，每行高度 24px
                    if h > 0:
                        import math
                        lines = math.ceil(h / 24)  # 向上取整得到行数
                        img_h = lines * 24  # 最终高度 = 行数 * 24
                        img_html = f'<img src="{url}" alt="{expr}" style="vertical-align:middle; height:{img_h}px;"  />'
                    else:
                        img_html = f'<img src="{url}" alt="{expr}" style="vertical-align:middle; height:24px;"  />'
                    
                    replacements[placeholder] = img_html
                    new_text = new_text.replace(m.group(0), placeholder, 1)
                # 如果既没有plain_text也没有url，保留原样（不替换）
            return new_text, replacements

        content, content_repl = replace_math(content)
        analysis, analysis_repl = replace_math(analysis)

        processed_options = []
        for opt in options:
            val = opt.get("value", "")
            val_new, val_repl = replace_math(val)
            processed_options.append({"key": opt.get("key", ""), "value": val_new, "repl": val_repl})

        # 将内容转为 HTML 格式：每行包裹 <p>，空格/制表符转为 &nbsp; 保留缩进
        # 支持占位符替换（如公式图片 <img>），在转义后执行 replacements
        def to_html(text, replacements=None):
            import html
            if text is None:
                return ""
            lines = str(text).splitlines() or [""]
            html_lines = []
            for line in lines:
                # 先转义 HTML，再替换空格/制表符
                escaped = html.escape(line)
                escaped = escaped.replace("\t", "&nbsp;&nbsp;&nbsp;&nbsp;")
                escaped = escaped.replace(" ", "&nbsp;")
                if escaped == "":
                    escaped = "&nbsp;"  # 空行占位
                html_lines.append(f"<p>{escaped}</p>")
            html_str = "".join(html_lines)
            if replacements:
                for k, v in replacements.items():
                    html_str = html_str.replace(k, v)
            return html_str
        
        # 构建表单数据
        data = {
            "courseid": course_id,
            "microTopicId": "0",
            "questionBankId": "",
            "clazzid": clazzid,
            "cpi": cpi,
            "qType": str(q_type),
            "courseQuestionTypeId": "0",
            "originType": str(q_type),  # 与 qType 保持一致
            "systemType": "",
            "wrapAnswer": "",
            "answerForTF": "true" if q_type == 3 else "",  # 判断题
            "continueOperate": "false",
            "dirId": folder_id,
            "isEdit": "false",
            "curCourseId": course_id,
            "uploadtype": "question",
            "uploadTimeStamp": "",
            "uploadEnc": "",
            "updateSignal": "true",
            "content": to_html(content, content_repl),
            "defAnswer": answer,
            "answerAnalysis": to_html(analysis, analysis_repl),
            "difficulty": str(difficulty),
            "easy": str(easy),  # 难度等级 (0=易, 1=中, 2=难)
            "topicId": "",
            "schoolTopicIds": "",
            "labelIdArr": ""
        }
        
        # 添加选项 (A, B, C, D, E, F...)
        option_keys = ["A", "B", "C", "D", "E", "F", "G", "H"]
        for i, opt in enumerate(processed_options):
            if i < len(option_keys):
                key = option_keys[i]
                data[key] = to_html(opt.get("value", ""), opt.get("repl", {}))
        
        # 对于判断题，设置默认选项
        if q_type == 3:
            data["A"] = "<p>正确</p>"
            data["B"] = "<p>错误</p>"
            data["defAnswer"] = "A" if answer in ["正确", "对", "T", "True", "A"] else "B"
        
        try:
            resp = self.session.post(url, data=data, headers=headers, timeout=30)
            resp.raise_for_status()
            
            result = resp.json()
            print(f"DEBUG add_question: {result}")
            
            if isinstance(result, dict):
                status = result.get("status", False)
                if status is True or status == "true":
                    return {
                        "success": True,
                        "msg": result.get("msg", "添加成功"),
                        "question_id": str(result.get("id", ""))
                    }
                else:
                    return {
                        "success": False,
                        "msg": result.get("msg", "添加失败")
                    }
            
            return {"success": False, "msg": "未知错误"}
            
        except Exception as e:
            print(f"添加题目失败: {e}")
            return {"success": False, "msg": str(e)}

    def logout(self):
        self.session.cookies.clear()
        self.session_manager.logged_in = False
        self.is_logged_in = False
