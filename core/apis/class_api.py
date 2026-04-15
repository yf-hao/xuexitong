import json
import re
from typing import List
from bs4 import BeautifulSoup
from core.config import DEFAULT_FID


class ClassAPI:
    """班级、学生相关接口封装，依赖宿主提供 session、session_manager。"""

    def get_class_list(self, course_id: str, fid: str = None) -> List[dict]:
        """根据课程ID获取班级列表。"""
        sess_params = self.session_manager.course_params
        if fid is None:
            fid = sess_params.get("fid", DEFAULT_FID)

        url = "https://mobilelearn.chaoxing.com/v2/apis/class/getClassList"
        params = {
            "fid": fid,
            "courseId": course_id,
            "isHaveAuth": 1,
            "ifGetIsXueyin": 1,
            "isNewList": 1
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
            "Referer": "https://mooc2-gray.chaoxing.com/mycourse"
        }

        try:
            resp = self.session.get(url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if data.get("result") != 1:
                print(f"API returned error: {data.get('msg')}")
                return []

            classes = []
            class_array = data.get("data", {}).get("classArray", [])
            if not class_array:
                course_obj = data.get("data", {}).get("course", {})
                class_array = course_obj.get("data", [])
            if not class_array:
                class_array = data.get("data", {}).get("channelList", [])

            for item in class_array:
                c = {}
                if "id" in item and "name" in item:
                    c = {
                        "id": str(item["id"]),
                        "course_id": str(item.get("courseId", course_id)),
                        "name": item["name"],
                        "href": item.get("link", f"https://mobilelearn.chaoxing.com/widget/pc/index?courseId={course_id}&classId={item['id']}"),
                        "finished": bool(item.get("isFinished", False)),
                        "teachers": item.get("teacheractor", item.get("teachernames", "未知教师")),
                        "organization": item.get("schoolname", "未知机构")
                    }
                    classes.append(c)
                elif "content" in item:
                    c_content = item.get("content", {}).get("course", {}).get("data", [{}])[0]
                    if "id" in c_content:
                        c = {
                            "id": str(c_content["id"]),
                            "course_id": str(c_content.get("courseId", course_id)),
                            "name": c_content.get("name", "未知班级"),
                            "href": c_content.get("link", f"https://mobilelearn.chaoxing.com/widget/pc/index?courseId={course_id}&classId={c_content['id']}"),
                            "finished": bool(c_content.get("isFinished", False)),
                            "teachers": c_content.get("teacheractor", c_content.get("teachernames", "未知教师")),
                            "organization": c_content.get("schoolname", "未知机构")
                        }
                        classes.append(c)

                if c:
                    print(f"{c['course_id']} | {c['name']} | {c['href']} | {'已结课' if c['finished'] else '进行中'} | {c['teachers']} | {c['organization']}")

            return classes
        except Exception as e:
            print(f"Error fetching class list: {e}")
            return []

    def get_clazz_manage_list(self, course_id: str, clazz_id: str) -> List[dict]:
        """获取班级管理列表。"""
        params = self.session_manager.course_params
        cpi = params.get('cpi', '')

        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/clazz-manage"
        req_params = {
            "courseid": course_id,
            "clazzid": clazz_id,
            "v": "0",
            "cpi": cpi
        }

        referer = f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/course-manage?courseid={course_id}&clazzid={clazz_id}"
        headers = {
            "Accept": "text/html, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": referer,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        try:
            print(f"DEBUG get_clazz_manage_list req courseid={course_id}, clazzid={clazz_id}, cpi={cpi}")
            resp = self.session.get(url, params=req_params, headers=headers, timeout=10)
            print(f"DEBUG get_clazz_manage_list status={resp.status_code}, url={resp.url}")
            resp.raise_for_status()
            html = resp.text
            print(f"DEBUG get_clazz_manage_list html_len={len(html)}")

            soup = BeautifulSoup(html, "lxml")
            classes = []
            clazz_items = soup.find_all("li", class_="changeclazzlistli")
            print(f"DEBUG get_clazz_manage_list parsed_items={len(clazz_items)}")
            for item in clazz_items:
                c_id = item.get("data")
                name_p = item.find("p", class_="txt-w")
                if c_id and name_p:
                    classes.append({
                        "id": c_id,
                        "name": name_p.get_text(strip=True)
                    })
            print(f"DEBUG get_clazz_manage_list classes_len={len(classes)}")
            return classes
        except Exception as e:
            print(f"Error fetching clazz manage list: {e}")
            return []

    def get_clazz_student_html(
        self,
        course_id: str = None,
        clazz_id: str = None,
        require_stu: str = "",
        page_num: int = 1,
        page_show_num: int = 30,
        order_content: str = "ID",
        order: str = "up",
        v: str = "0",
    ) -> str:
        """获取班级学生列表原始 HTML，后续用于解析班级信息。"""
        params = self.session_manager.course_params
        course_id = course_id or params.get("courseid", "")
        clazz_id = clazz_id or params.get("clazzid", "")
        cpi = params.get("cpi", "")
        enc = params.get("enc", "")
        openc = params.get("openc", "")
        t = params.get("t", "")

        if not course_id or not clazz_id:
            print("DEBUG get_clazz_student_html: 缺少 course_id 或 clazz_id")
            return ""

        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/clazz-student"
        req_params = {
            "courseid": course_id,
            "clazzid": clazz_id,
            "requireStu": require_stu,
            "cpi": cpi,
            "pageNum": str(page_num),
            "pageShowNum": str(page_show_num),
            "orderContent": order_content,
            "v": v,
            "order": order,
        }
        headers = {
            "Accept": "text/html, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": (
                "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/course-manage"
                f"?courseid={course_id}&clazzid={clazz_id}&courseId={course_id}"
                f"&classId={clazz_id}&clazzId={clazz_id}&cpi={cpi}"
                f"&enc={enc}&openc={openc}&t={t}&ut=t&loadContentType=0"
            ),
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }

        try:
            print(
                "DEBUG get_clazz_student_html req "
                f"courseid={course_id}, clazzid={clazz_id}, cpi={cpi}, "
                f"pageNum={page_num}, pageShowNum={page_show_num}"
            )
            resp = self.session.get(url, params=req_params, headers=headers, timeout=15)
            print(f"DEBUG get_clazz_student_html status={resp.status_code}, url={resp.url}")
            resp.raise_for_status()
            html = resp.text
            print(f"DEBUG get_clazz_student_html html_len={len(html)}")
            return html
        except Exception as e:
            print(f"Error fetching clazz student html: {e}")
            return ""

    def parse_clazz_student_page(self, html: str) -> dict:
        """解析班级学生列表单页 HTML。"""
        result = {
            "total": 0,
            "page_num": 1,
            "students": [],
        }
        if not html:
            return result

        soup = BeautifulSoup(html, "lxml")

        total_text = soup.get_text(" ", strip=True)
        total_match = re.search(r"共\s*(\d+)\s*人", total_text)
        if total_match:
            result["total"] = int(total_match.group(1))

        page_num_tag = soup.find("input", id="pageNum")
        if page_num_tag and page_num_tag.get("value", "").isdigit():
            result["page_num"] = int(page_num_tag["value"])

        table = soup.find("table", id="studentTable")
        if not table:
            return result

        tbody = table.find("tbody")
        if not tbody:
            return result

        for row in tbody.find_all("tr", recursive=False):
            cols = row.find_all("td", recursive=False)
            if len(cols) < 7:
                continue

            person_id = cols[1].get_text(strip=True)
            name = cols[2].get_text(" ", strip=True)
            student_number = cols[3].get_text(" ", strip=True)
            department = cols[4].get_text(" ", strip=True)
            major = cols[5].get_text(" ", strip=True)
            class_name = cols[6].get_text(" ", strip=True)

            if not person_id:
                continue

            result["students"].append({
                "person_id": person_id,
                "name": name,
                "student_number": student_number,
                "department": department,
                "major": major,
                "class_name": class_name,
            })

        return result

    def get_clazz_student_map(
        self,
        course_id: str = None,
        clazz_id: str = None,
        page_show_num: int = 30,
    ) -> dict:
        """获取班级学生映射，返回 person_id -> 学生信息。"""
        student_map = {}
        page_num = 1

        while True:
            html = self.get_clazz_student_html(
                course_id=course_id,
                clazz_id=clazz_id,
                page_num=page_num,
                page_show_num=page_show_num,
            )
            parsed = self.parse_clazz_student_page(html)
            students = parsed.get("students", [])
            total = parsed.get("total", 0)

            for student in students:
                student_map[student["person_id"]] = student

            if not students:
                break

            if total and len(student_map) >= total:
                break

            if len(students) < page_show_num:
                break

            page_num += 1

        print(f"DEBUG get_clazz_student_map size={len(student_map)}")
        return student_map

    def rename_clazz(self, clazz_id: str, new_name: str) -> tuple[bool, str]:
        params = self.session_manager.course_params
        cpi = params.get('cpi', '')
        course_id = params.get('courseid', '')

        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/update-clazzname"
        req_params = {
            "courseid": course_id,
            "clazzName": new_name,
            "cpi": cpi,
            "clazzid": clazz_id
        }
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/course-manage?courseid={course_id}&clazzid={clazz_id}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"'
        }
        try:
            resp = self.session.get(url, params=req_params, headers=headers, timeout=10)
            resp.raise_for_status()
            res_data = resp.json()
            if res_data.get("status") == True or res_data.get("result") == 1:
                return True, "重命名成功"
            return False, f"重命名失败: {res_data.get('msg', '未知错误')}"
        except Exception as e:
            return False, f"网络请求失败: {e}"

    def create_clazz(self, course_id: str, clazz_name: str) -> tuple[bool, str]:
        params = self.session_manager.course_params
        cpi = params.get('cpi', '')
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/create-clazz"
        req_params = {
            "courseid": course_id,
            "newClazzName": clazz_name,
            "cpi": cpi,
        }
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/course-manage?courseid={course_id}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"'
        }
        try:
            resp = self.session.get(url, params=req_params, headers=headers, timeout=10)
            resp.raise_for_status()
            try:
                res_data = resp.json()
            except Exception:
                res_data = {}
            if res_data.get("status") == True or res_data.get("result") == 1:
                return True, "新建班级成功"
            return False, res_data.get("msg", resp.text[:200] or "新建失败")
        except Exception as e:
            return False, f"网络请求失败: {e}"

    def delete_clazz(self, clazz_id: str) -> tuple[bool, str]:
        """归档班级"""
        params = self.session_manager.course_params
        course_id = params.get("courseid", "")
        fid = params.get("fid", DEFAULT_FID)
        if not course_id:
            return False, "未找到课程ID"

        url = "https://mobilelearn.chaoxing.com/v2/apis/class/updateClassFiled"
        req_params = {
            "fid": fid,
            "courseId": course_id,
            "classId": clazz_id
        }
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": f"https://mobilelearn.chaoxing.com/page/class/classList?courseid={course_id}&clazzid={clazz_id}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"'
        }
        try:
            resp = self.session.get(url, params=req_params, headers=headers, timeout=10)
            resp.raise_for_status()
            try:
                res_data = resp.json()
            except Exception:
                res_data = {}
            if res_data.get("result") == 1 or res_data.get("status") is True:
                return True, "归档成功"
            return False, res_data.get("msg", resp.text[:200] or "归档失败")
        except Exception as e:
            return False, f"网络请求失败: {e}"

    def add_student_by_hand(self, student_id: str, name: str, clazz_id: str, course_id: str = None) -> tuple[bool, str]:
        params = self.session_manager.course_params
        cpi = params.get('cpi', '')
        fid = params.get('fid', DEFAULT_FID)

        if course_id is None:
            course_id = params.get('courseid', '')

        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/addstubyhand"
        req_params = {
            "loginName": student_id,
            "cpi": cpi,
            "realName": name,
            "fid": fid,
            "courseId": course_id,
            "handAddStudentType": "0",
            "clazzId": clazz_id,
            "ut": "t"
        }

        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/course-manage?courseid={course_id}&clazzid={clazz_id}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"'
        }

        try:
            resp = self.session.get(url, params=req_params, headers=headers, timeout=10)
            resp.raise_for_status()
            res_data = resp.json()

            if res_data.get("status") == True:
                return True, f"成功添加学生: {name} ({student_id})"
            else:
                return False, res_data.get("msg", "添加失败")
        except Exception as e:
            return False, f"网络请求失败: {e}"

    def add_students_batch(self, students: List[dict], clazz_id: str, course_id: str = None, progress_callback=None) -> tuple[int, int, list]:
        success_count = 0
        fail_count = 0
        failed_students = []
        total = len(students)

        for i, student in enumerate(students, 1):
            student_id = student.get("student_id")
            name = student.get("name")

            if progress_callback:
                progress_callback(i, total, name)

            success, message = self.add_student_by_hand(student_id, name, clazz_id, course_id)

            if success:
                success_count += 1
            else:
                fail_count += 1
                failed_students.append({
                    "student_id": student_id,
                    "name": name,
                    "error": message
                })

        return success_count, fail_count, failed_students
