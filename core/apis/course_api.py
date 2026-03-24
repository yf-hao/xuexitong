import re
from typing import List, Optional
from bs4 import BeautifulSoup
from models.data_types import Course
from core.config import DEFAULT_FID


class CourseAPI:
    """课程相关接口封装，依赖宿主提供 session、session_manager、_details_cache 等属性。"""

    def get_courses(self) -> List[Course]:
        """获取课程列表（教师端），返回 Course 数据对象列表。"""
        if not getattr(self, "is_logged_in", False):
            return []

        courses_url = "https://mooc2-gray.chaoxing.com/mooc2-ans/visit/courselistdata"
        headers = {
            "Accept": "text/html, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://mooc2-gray.chaoxing.com",
            "Referer": "https://mooc2-gray.chaoxing.com/mycourse",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }

        data = {
            "courseType": 0,
            "courseFolderId": 0,
            "query": "",
            "pageHeader": -1,
            "single": 0,
            "superstarClass": 0,
            "isFirefly": 0,
        }

        try:
            resp = self.session.post(courses_url, headers=headers, data=data, timeout=10)
            if resp.status_code != 200:
                print(f"Failed to fetch courses: HTTP {resp.status_code}")
                return []

            soup = BeautifulSoup(resp.text, 'lxml')
            course_items = soup.select("div.course.teachCourse")

            results = []
            for item in course_items:
                course_id = item.select_one("input.courseId")["value"]
                name_tag = item.select_one("span.course-name")
                name = name_tag.get_text(strip=True) if name_tag else "Unknown Course"

                teachers_tag = item.select_one("p.color3")
                teacher = teachers_tag.get_text(strip=True) if teachers_tag else "Unknown"

                finished_mark = item.select_one("span.course-mark-finish:not([style*='display: none'])")
                is_finished = bool(finished_mark)

                link_tag = item.select_one("h3 a")
                href = link_tag["href"] if link_tag else ""

                results.append(Course(id=course_id, name=name, teacher=teacher, is_finished=is_finished, href=href))

            return results
        except Exception as e:
            print(f"Error fetching courses: {e}")
            return []

    def get_course_details(self, course_id: str, url: str = None) -> dict:
        """获取课程详情及导航参数，使用缓存避免重复请求。"""
        cache_key = course_id
        if url:
            match = re.search(r'clazzid=(\d+)', url, re.I)
            if match:
                cache_key = f"{course_id}_{match.group(1)}"

        if cache_key in self._details_cache:
            return self._details_cache[cache_key]

        if not url:
            url = (
                "https://mooc2-gray.chaoxing.com/mooc2-ans/visit/coursedata"
                f"?courseId={course_id}&edit=true&v=2&pageHeader=-1&single=0&superstarClass=0"
            )

        headers = {
            "Referer": "https://mooc2-gray.chaoxing.com/mycourse",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        try:
            resp = self.session.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            html = resp.text

            soup = BeautifulSoup(html, "lxml")
            params = {}
            nav_links = []
            for input_id in ["courseid", "clazzid", "cpi", "enc", "t", "fid", "openc"]:
                tag = soup.find("input", id=input_id)
                params[input_id] = tag["value"] if tag and tag.has_attr("value") else ""

            if params.get("courseid") and params.get("clazzid"):
                scout_key = f"{params['courseid']}_{params['clazzid']}"
                urls_to_scout = [
                    f"https://mooc2-ans.chaoxing.com/mooc2-ans/mycourse/tchcourse?courseid={params['courseid']}&clazzid={params['clazzid']}&ut=t&cpi={params['cpi']}",
                    f"https://mooc2-ans.chaoxing.com/mooc2-ans/coursedata?courseid={params['courseid']}&clazzid={params['clazzid']}",
                ]
                for scout_url in urls_to_scout:
                    try:
                        scout_resp = self.session.get(scout_url, headers=headers, timeout=5)
                        if scout_resp.status_code == 200:
                            scout_soup = BeautifulSoup(scout_resp.text, "lxml")
                            for input_tag in scout_soup.find_all("input", value=True):
                                val = input_tag['value'].strip()
                                if len(val) == 32 and re.match(r'^[a-f0-9]+$', val):
                                    params[f"harvested_enc_{input_tag.get('id') or input_tag.get('name') or 'unknown'}"] = val

                            found_encs = re.findall(r'enc[=:]["\']?([a-f0-9]{32})["\']?', scout_resp.text)
                            for i, f_enc in enumerate(found_encs):
                                params[f"harvested_enc_raw_{i}"] = f_enc
                    except Exception:
                        pass

            for a_tag in soup.select("div.nav-content ul li a[data-url]"):
                title = a_tag.get("title", "").strip()
                url_path = a_tag.get("data-url", "").strip()
                if title and url_path:
                    nav_links.append({"title": title, "url": url_path})

            self.session_manager.course_params.update(params)
            res = {"params": params, "nav_links": nav_links}
            self._details_cache[cache_key] = res
            return res
        except Exception as e:
            print(f"Error getting course details: {e}")
            return {}

    def extract_course_params(self, course_id: str) -> dict:
        """兼容旧接口，获取并返回课程参数。"""
        details = self.get_course_details(course_id)
        return details.get("params", {})

    def create_course(self, name: str, teacher: str, cover_url: str, semester_name: str, semester_id: str,
                      course_type: str = "0", catalog_id: str = "0", semester_type: str = "0",
                      course_no: str = "", unit_fid: str = "", unit_id: str = "", unit_person_id: str = "") -> tuple[bool, str]:
        """创建课程，返回(success, message)。"""
        params = self.session_manager.course_params
        fid = unit_fid if unit_fid else params.get("fid", DEFAULT_FID)
        # 优先使用传入的 unit_person_id，否则从 session 获取
        person_id = unit_person_id if unit_person_id else (params.get("personid") or params.get("personId") or params.get("cpi", ""))
        group_id = unit_id if unit_id else (params.get("groupId") or params.get("groupid", ""))

        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/visit/createcourse"
        data = {
            "fid": fid,
            "name": name,
            "teachers": teacher,
            "courselogo": cover_url,
            "coursetype": course_type,
            "catalogid": catalog_id,
            "courseNo": course_no,
            "semesterType": semester_type,
            "semesterName": semester_name,
            "semesterId": semester_id,
            "personId": person_id,
            "allSemesterName": "",
            "groupId": group_id,
        }
        headers = {
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://mooc2-gray.chaoxing.com",
            "Referer": "https://mooc2-gray.chaoxing.com/visit/interaction?s=null",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"'
        }
        try:
            resp = self.session.post(url, data=data, headers=headers, timeout=10)
            resp.raise_for_status()
            res = resp.json()
            if res.get("status") is True:
                return True, res.get("msg", "新建课程成功")
            return False, res.get("msg", "新建课程失败")
        except Exception as e:
            return False, f"网络请求失败: {e}"

    def update_course_data(self, course_id: str, cpi: str, course_name: str, teachers: str,
                           group_id: str, info_content: str = "", unit_fid: str = DEFAULT_FID,
                           course_no: str = "", english_name: str = "") -> tuple[bool, str]:
        """修改课程基本信息，返回(success, message)。"""
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/updatecoursedata"
        data = {
            "courseId": course_id,
            "cpi": cpi,
            "courseName": course_name,
            "teachers": teachers,
            "infoContent": info_content,
            "group1": group_id,
            "courseNo": course_no,
            "studyModule": english_name,  # 课程英文名称提交给studyModule
            "v": "0",
            "subjectId": "", # 保持原样，分类通过单独接口修改
            "courseUnitFid": unit_fid
        }
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://mooc2-gray.chaoxing.com",
            "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/course-manage?courseid={course_id}&cpi={cpi}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }
        try:
            print(f"DEBUG: update_course_data posting to {url}")
            resp = self.session.post(url, data=data, headers=headers, timeout=10)
            print(f"DEBUG: update_course_data response: {resp.text}")
            resp.raise_for_status()
            res = resp.json()
            if res.get("status") is True:
                return True, res.get("msg", "基本信息更改成功")
            return False, res.get("msg", "基本信息更改失败")
        except Exception as e:
            print(f"DEBUG update_course_data error: {e}")
            return False, f"网络请求失败: {e}"

    def update_course_classify(self, course_id: str, cpi: str, school_id: str, category_id: str) -> tuple[bool, str]:
        """修改课程分类信息，返回(success, message)。"""
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/updatecourseclassify"
        params = {
            "courseId": course_id,
            "cpi": cpi,
            "schoolId": school_id,
            "categoryNoId": category_id
        }
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/course-manage?courseid={course_id}&cpi={cpi}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }
        try:
            print(f"DEBUG: update_course_classify requesting {url} with {params}")
            resp = self.session.get(url, params=params, headers=headers, timeout=10)
            print(f"DEBUG: update_course_classify response: {resp.text}")
            resp.raise_for_status()
            res = resp.json()
            if res.get("status") is True:
                return True, res.get("msg", "课程分类更新成功")
            return False, res.get("msg", "课程分类更新失败")
        except Exception as e:
            print(f"DEBUG update_course_classify error: {e}")
            return False, f"分类更新请求失败: {e}"

    def update_course_logo(self, course_id: str, cpi: str, image_url: str) -> tuple[bool, str]:
        """更新课程封面，返回(success, message)。"""
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/updatecourselogo"
        data = {
            "cpi": cpi,
            "courseId": course_id,
            "imageData": image_url
        }
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5",
            "Connection": "keep-alive",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://mooc2-gray.chaoxing.com",
            "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/course-manage?courseid={course_id}&cpi={cpi}",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"'
        }
        try:
            print(f"DEBUG: update_course_logo posting to {url}")
            print(f"DEBUG: update_course_logo data: cpi={cpi}, courseId={course_id}, imageData={image_url}")
            resp = self.session.post(url, data=data, headers=headers, timeout=10)
            print(f"DEBUG: update_course_logo response: {resp.text}")
            resp.raise_for_status()
            res = resp.json()
            if res.get("status") is True:
                return True, res.get("msg", "封面更新成功")
            return False, res.get("msg", "封面更新失败")
        except Exception as e:
            print(f"DEBUG update_course_logo error: {e}")
            return False, f"网络请求失败: {e}"

    def delete_course(self, course_id: str) -> tuple[bool, str]:
        """
        删除课程。
        URL: https://mooc2-gray.chaoxing.com/mooc2-ans/visit/doarchive/teacher?courseid={course_id}
        """
        url = f"https://mooc2-gray.chaoxing.com/mooc2-ans/visit/doarchive/teacher?courseid={course_id}"
        headers = {
            "Accept": "*/*",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://mooc2-gray.chaoxing.com/visit/interaction"
        }
        try:
            resp = self.session.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            res = resp.json()
            if res.get("status") is True:
                # 优先使用服务器返回的 msg，如果为空则使用更周全的默认提示
                msg = res.get("msg") or "课程已成功删除，后续可在“已删除课程”中找回"
                return True, msg
            return False, res.get("msg") or "操作失败，请检查网络或权限"
        except Exception as e:
            return False, f"网络请求失败: {e}"

    def archive_course(self, course_id: str) -> tuple[bool, str]:
        """
        结课（归档）课程。
        URL: https://mooc2-gray.chaoxing.com/mooc2-ans/visit/updatecoursestate?courseid={course_id}&cpi={cpi}&state=1
        """
        params = self.session_manager.course_params
        cpi = params.get("cpi", "")
        url = f"https://mooc2-gray.chaoxing.com/mooc2-ans/visit/updatecoursestate?courseid={course_id}&cpi={cpi}&state=1"
        headers = {
            "Accept": "*/*",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://mooc2-gray.chaoxing.com/visit/interaction"
        }
        try:
            resp = self.session.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            res = resp.json()
            if res.get("status") is True:
                return True, res.get("msg") or "课程已成功结课"
            return False, res.get("msg") or "结课失败"
        except Exception as e:
            return False, f"网络请求失败: {e}"

    # --- 克隆课程相关 (对标用户 Snippet 逻辑) ---

    def check_clone_verify_status(self, course_id: str, cpi: str) -> dict:
        """判断是否需要验证 (对标 need_verify)"""
        url = f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/getcurpersonphone?courseid={course_id}&cpi={cpi}"
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        }
        try:
            print(f"DEBUG: check_clone_verify_status request to {url}")
            resp = self.session.get(url, headers=headers, timeout=10)
            data = resp.json()
            print(f"DEBUG: check_clone_verify_status response: {data}")
            return data
        except Exception as e:
            print(f"DEBUG: check_clone_verify_status exception: {e}")
            return {"status": False, "msg": f"判定失败: {e}"}

    def get_clone_captcha(self, course_id: str, captcha_id: str = "bdkRWGLSXanasTjPqLk0g4tgkJeheD0r") -> dict:
        """获取验证码图片和相关 token (对标 get_img_url)"""
        import hashlib, uuid, time, re, json
        url = 'https://captcha.chaoxing.com/captcha/get/verification/image'
        
        times = str(int(time.time() * 1000))
        captcha_key = hashlib.md5(f'{times}{uuid.uuid4()}'.encode()).hexdigest()
        expire = str(int(times) + 0x493e0)
        token_md5 = hashlib.md5(f'{times}{captcha_id}slide{captcha_key}'.encode()).hexdigest()
        token = f'{token_md5}:{expire}'
        iv = hashlib.md5(f'{captcha_id}slide{times}{uuid.uuid4()}'.encode()).hexdigest()

        headers = {
            "Accept": "*/*",
            "Referer": "https://mooc2-gray.chaoxing.com/",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        }

        params = {
            "callback": "cx_captcha_function",
            "captchaId": captcha_id,
            "type": "slide",
            "version": "1.1.20",
            "captchaKey": captcha_key,
            "token": token,
            "referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/course-manage?courseid={course_id}",
            "iv": iv,
            "_": times,
        }
        
        try:
            print(f"DEBUG: get_clone_captcha request params: {params}")
            resp = self.session.get(url, params=params, headers=headers, timeout=10)
            text = resp.text
            print(f"DEBUG: get_clone_captcha response: {text}")

            match = re.search(r"cx_captcha_function\((.*)\)", text)
            if match:
                data = json.loads(match.group(1))
                if "imageVerificationVo" in data:
                    vo = data["imageVerificationVo"]
                    return {
                        "token": data.get("token"),
                        "shade_image": vo.get("shadeImage"),
                        "cutout_image": vo.get("cutoutImage"),
                        "iv": iv,
                        "success": True
                    }
        except Exception as e:
            print(f"DEBUG: get_clone_captcha exception: {e}")
        return {"success": False}

    def submit_clone_captcha(self, token: str, iv: str, x_coord: int, captcha_id: str = "bdkRWGLSXanasTjPqLk0g4tgkJeheD0r") -> str:
        """
        提交滑块结果并获取 validate (对标 get_result)
        """
        import time, re, json
        url = 'https://captcha.chaoxing.com/captcha/check/verification/result'
        
        headers = {
            "Accept": "*/*",
            "Referer": "https://mooc2-gray.chaoxing.com/",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        }

        params = {
            "callback": "cx_captcha_function",
            "captchaId": captcha_id,
            "type": "slide",
            "token": token,
            "textClickArr": f'[{{"x":{x_coord}}}]',
            "coordinate": "[]",
            "runEnv": "10",
            "version": "1.1.20",
            "t": "a",
            "iv": iv,
            "_": str(int(time.time() * 1000)),
        }
        
        try:
            print(f"DEBUG: submit_clone_captcha params: {params}")
            resp = self.session.get(url, params=params, headers=headers, timeout=10)
            text = resp.text
            print(f"DEBUG: submit_clone_captcha response: {text}")

            match = re.search(r"cx_captcha_function\((.*)\)", text)
            if match:
                data = json.loads(match.group(1))
                if data.get("result"):
                    extra_data = json.loads(data["extraData"])
                    return extra_data.get("validate")
                else:
                    print(f"DEBUG: submit_clone_captcha failure result: {data}")
        except Exception as e:
            print(f"DEBUG: submit_clone_captcha exception: {e}")
        return None

    def fetch_clone_verify_code(self, course_id: str, cpi: str, validate: str, clazz_id: str = "") -> dict:
        """
        使用滑块返回的 validate 获取课程 verifyCode (对标 get_course_verify_code)
        """
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/course/getverifycode"
        
        referer = f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/course-manage?courseid={course_id}&cpi={cpi}"
        if clazz_id:
            referer += f"&clazzid={clazz_id}"

        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": referer,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        }

        params = {
            "courseid": course_id,
            "cpi": cpi,
            "validate": validate,
        }
        
        try:
            print(f"DEBUG: fetch_clone_verify_code params: {params}")
            resp = self.session.get(url, params=params, headers=headers, timeout=10)
            print(f"DEBUG: fetch_clone_verify_code status: {resp.status_code} response: {resp.text}")
            return resp.json()
        except Exception as e:
            print(f"DEBUG: fetch_clone_verify_code exception: {e}")
            return {"result": False, "msg": f"请求异常: {str(e)}"}

    def submit_clone_verify_code(self, verify_code: str, course_id: str, cpi: str) -> dict:
        """
        校验手机验证码 (对标 validate_verify_code)
        """
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/course/validateverifycode"
        
        params = {
            "verifyCode": verify_code,
            "courseid": course_id,
            "cpi": cpi
        }
        
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/course-manage?courseid={course_id}&cpi={cpi}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }
        
        try:
            print(f"DEBUG: submit_clone_verify_code params: {params}")
            resp = self.session.get(url, params=params, headers=headers, timeout=10)
            data = resp.json()
            print(f"DEBUG: submit_clone_verify_code response: {data}")
            if data.get("status"):
                return {
                    "success": True,
                    "copymapenc": data.get("copymapenc"),
                    "copymaptime": data.get("copymaptime"),
                }
            return {"success": False, "msg": data.get("msg", "验证码错误")}
        except Exception as e:
            return {"success": False, "msg": f"校验请求异常: {e}"}

    def request_clone_course(self, payload: dict) -> dict:
        """
        执行最终的克隆操作 (对标 clone_course)
        """
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/course/clonecourse"
        
        course_id = payload.get("courseId")
        cpi = payload.get("cpi")
        
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/course-manage?courseid={course_id}&cpi={cpi}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }
        
        try:
            print(f"DEBUG: request_clone_course payload: {payload}")
            # ⭐ 关键：禁止自动跳转，方便判断是否被踢登录 (对标 Snippet)
            resp = self.session.get(url, params=payload, headers=headers, timeout=30, allow_redirects=False)
            print(f"DEBUG: request_clone_course status: {resp.status_code}")
            
            if resp.status_code == 302:
                 return {"status": False, "msg": "未登录或 Referer 校验失败 (302 Redirect)"}
            
            try:
                # 对标 Snippet: data = json.loads(clone_result.text.strip())
                res = resp.json()
                if res.get("status"):
                    # 对标 Snippet: print("✅ 克隆成功，新课程 ID:", data.get("newCourseid"))
                    return {"status": True, "msg": f"克隆成功！新课程 ID: {res.get('newCourseid')}"}
                else:
                    return {"status": False, "msg": f"克隆失败: {res.get('msg')}"}
            except Exception as e:
                if resp.status_code == 200:
                    return {"status": True, "msg": "克隆请求已发送 (200 OK)"}
                return {"status": False, "msg": f"解析克隆结果失败: {str(e)}"}
        except Exception as e:
            return {"status": False, "msg": f"克隆请求异常: {str(e)}"}
