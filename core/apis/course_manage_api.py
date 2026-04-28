from bs4 import BeautifulSoup


class CourseManageAPI:
    """课程创建、设置与封面相关接口。"""

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

            teacher_name = ''
            teacher_input = soup.find('input', id='teachers')
            if teacher_input:
                teacher_name = teacher_input.get('value', '').strip()
            if not teacher_name:
                teacher_input = soup.find('input', {'name': 'teachers'})
                if teacher_input:
                    teacher_name = teacher_input.get('value', '').strip()
            if not teacher_name:
                teacher_input = soup.find('input', {'placeholder': '请输入课程教师'})
                if teacher_input:
                    teacher_name = teacher_input.get('value', '').strip()

            units = []
            select_items = soup.find_all('li', class_=lambda x: x and 'select-item' in str(x))
            print(f"DEBUG 找到 {len(select_items)} 个select-item")

            for item in select_items:
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
        try:
            url = "https://mooc2-gray.chaoxing.com/mooc2-ans/coursemanage/getgroupclassifylist"
            params = {
                "courseId": course_id,
                "v": "0",
                "fid": fid,
                "refergroupdata": "1",
                "cpi": cpi
            }

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

            result = response.json()

            if not result.get("status"):
                print(f"DEBUG get_group_list (新接口) 返回失败: {result}，回退到旧接口")
                return self._get_group_list_fallback(fid)

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
            groups = []
            select_items = soup.find_all('li', class_=lambda x: x and 'select-item' in str(x))
            print(f"DEBUG (旧接口) 找到 {len(select_items)} 个select-item（院系）")

            for item in select_items:
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
            semesters = []
            select_items = soup.find_all('li', class_=lambda x: x and 'select-item' in str(x))
            print(f"DEBUG 找到 {len(select_items)} 个select-item（学期）")

            for item in select_items:
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

    def upload_cover_image(
        self,
        image_path: str,
        course_id: str = "",
        cpi: str = "",
        upload_variant: str = "cover",
    ) -> dict:
        """上传图片到超星服务器，返回图片URL"""
        try:
            import html
            import time
            import re
            import os
            import requests
            from core.config import DATA_DIR

            log_tag = "QUESTION_UPLOAD" if upload_variant == "question" else "COVER_UPLOAD"
            log_filename = "question_upload_debug.log" if upload_variant == "question" else "cover_upload_debug.log"
            log_path = os.path.join(DATA_DIR, log_filename)

            def log(message: str):
                line = f"[{log_tag}] {message}"
                print(line)
                try:
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(line + "\n")
                except Exception:
                    pass

            def parse_upload_url(html_text: str, source: str) -> str:
                if not html_text:
                    return ""
                full_upload_match = re.search(
                    r'((?:https:)?//mooc1\.chaoxing\.com/upload-ans/edit/uploadBase64\?[^"\'\s>]+|/upload-ans/edit/uploadBase64\?[^"\'\s>]+)',
                    html_text,
                )
                if not full_upload_match:
                    return ""
                found_url = html.unescape(full_upload_match.group(1)).replace("\\/", "/")
                if found_url.startswith("//"):
                    found_url = f"https:{found_url}"
                elif found_url.startswith("/"):
                    found_url = f"https://mooc1.chaoxing.com{found_url}"
                url_match = re.search(r"[?&]uid=([^&]+).*?[?&]enc2=([^&]+).*?[?&]t=([^&]+)", found_url)
                if url_match:
                    nonlocal_uid[0] = nonlocal_uid[0] or url_match.group(1)
                    nonlocal_enc2[0] = url_match.group(2)
                    nonlocal_upload_timestamp[0] = url_match.group(3)
                log(f"从{source}解析完整上传URL={found_url}")
                return found_url

            params = getattr(self.session_manager, "course_params", {}) or {}
            course_id = course_id or params.get("courseid", "") or params.get("courseId", "")
            cpi = cpi or params.get("cpi", "")
            clazz_id = params.get("clazzid", "") or params.get("classId", "") or params.get("clazzId", "")
            enc = params.get("enc", "")
            openc = params.get("openc", "")
            manage_t = params.get("t", "")
            uid = params.get("uid", "") or params.get("_uid", "")
            if not uid:
                uid = next((cookie.value for cookie in self.session.cookies if cookie.name in {"UID", "_uid"}), "")
            log(
                "上下文 "
                f"variant={upload_variant}, "
                f"course_id={course_id}, clazz_id={clazz_id}, cpi={cpi}, "
                f"enc={enc}, openc={openc}, t={manage_t}, uid={uid}"
            )

            upload_timestamp = str(int(time.time() * 1000))
            upload_url = ""
            enc2 = ""
            nonlocal_uid = [uid]
            nonlocal_enc2 = [enc2]
            nonlocal_upload_timestamp = [upload_timestamp]

            if upload_variant == "cover" and course_id and cpi:
                manage_url = (
                    "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/course-manage"
                    f"?courseid={course_id}&clazzid={clazz_id}&courseId={course_id}"
                    f"&classId={clazz_id}&clazzId={clazz_id}&cpi={cpi}"
                    f"&enc={enc}&openc={openc}&t={manage_t or upload_timestamp}&ut=t&loadContentType=0"
                )
                manage_headers = {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Pragma": "no-cache",
                    "Referer": "https://mooc2-gray.chaoxing.com/",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-User": "?1",
                    "Upgrade-Insecure-Requests": "1",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
                    "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"macOS"',
                }
                manage_response = self.session.get(manage_url, headers=manage_headers, timeout=10)
                log(f"课程管理页 status={manage_response.status_code} url={manage_url}")
                if manage_response.status_code == 200:
                    upload_url = parse_upload_url(manage_response.text, "课程管理页") or upload_url

                log("访问课程设置页面获取 uploadEnc")
                setting_url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/getcoursesetting"
                setting_params = {
                    "courseId": course_id,
                    "cpi": cpi,
                    "v": "0",
                    "leftNavigation": "0",
                }
                setting_headers = {
                    "Accept": "text/html, */*; q=0.01",
                    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Pragma": "no-cache",
                    "Referer": manage_url,
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-origin",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
                    "X-Requested-With": "XMLHttpRequest",
                    "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"macOS"',
                }
                setting_response = self.session.get(setting_url, params=setting_params, headers=setting_headers, timeout=10)
                log(f"课程设置页 status={setting_response.status_code} url={setting_response.url}")
                if setting_response.status_code == 200:
                    setting_html = setting_response.text
                    upload_url = parse_upload_url(setting_html, "课程设置页") or upload_url
                    hidden_fields = re.findall(
                        r'<input[^>]*type=["\']hidden["\'][^>]*id=["\']([^"\']+)["\'][^>]*value=["\']([^"\']*)["\']',
                        setting_html,
                        flags=re.IGNORECASE,
                    )
                    if hidden_fields:
                        log(f"课程设置页 hidden_fields={hidden_fields[:20]}")

                    current_time_match = re.search(
                        r'id=["\']currentTime["\'][^>]*value=["\']([^"\']+)["\']',
                        setting_html,
                    )
                    if current_time_match:
                        nonlocal_upload_timestamp[0] = current_time_match.group(1)
                        log(f"课程设置页 hidden currentTime={nonlocal_upload_timestamp[0]}")
                    else:
                        upload_timestamp_match = re.search(
                            r'id=["\']uploadTimeStamp["\'][^>]*value=["\']([^"\']+)["\']',
                            setting_html,
                        )
                        if upload_timestamp_match:
                            nonlocal_upload_timestamp[0] = upload_timestamp_match.group(1)
                            log(f"课程设置页 hidden uploadTimeStamp={nonlocal_upload_timestamp[0]}")

                    upload_enc_match = re.search(r'id=["\']uploadEnc["\'][^>]*value=["\']([a-fA-F0-9]+)["\']', setting_html)
                    if upload_enc_match:
                        enc2 = upload_enc_match.group(1)
                        nonlocal_enc2[0] = enc2
                        log(f"课程设置页 hidden uploadEnc={enc2}，已作为封面上传 enc2")
                    else:
                        log("课程设置页未找到 uploadEnc")

            uid = nonlocal_uid[0]
            enc2 = nonlocal_enc2[0]
            upload_timestamp = nonlocal_upload_timestamp[0]

            should_use_boxtip = not (upload_variant == "cover" and enc2)
            if should_use_boxtip:
                log("访问课程创建页面获取 uid/enc2")
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
                log(f"课程创建页 status={response.status_code}")

                html_text = response.text
                if not upload_url:
                    upload_url = parse_upload_url(html_text, "boxtip页面") or upload_url

                pattern = r'uploadBase64\?uid=(\d+)&enc2=([a-f0-9]+)&t=(\d+)'
                match = re.search(pattern, html_text)

                if match:
                    uid = uid or match.group(1)
                    enc2 = enc2 or match.group(2)
                    upload_timestamp = match.group(3)
                    log(f"从 boxtip 解析 uid={uid}, enc2={enc2}, t={upload_timestamp}")
                elif not enc2:
                    log("未能从 boxtip 解析 enc2，尝试 cookies")
                    try:
                        cookies_dict = {cookie.name: cookie.value for cookie in self.session.cookies}
                        uid = uid or cookies_dict.get("UID", "") or cookies_dict.get("_uid", "")
                        enc2 = cookies_dict.get("xxtenc", "")
                        log(f"从 cookies 获取 uid={uid}, xxtenc={enc2}")
                        upload_timestamp = str(int(time.time() * 1000))
                    except Exception as e:
                        log(f"获取 cookies 失败: {e}")
            else:
                log("cover 场景已从课程设置页拿到 enc2，跳过 boxtip")

            if not enc2:
                enc2 = self.session_manager.course_params.get('enc2', '')

            log(f"最终使用 uid={uid}, enc2={enc2}, variant={upload_variant}")

            if not upload_url:
                timestamp = upload_timestamp or str(int(time.time() * 1000))
                upload_url = f"https://mooc1.chaoxing.com/upload-ans/edit/uploadBase64?uid={uid}&enc2={enc2}&t={timestamp}"

            referer_url = "https://mooc2-gray.chaoxing.com/"

            headers = {
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Origin': 'https://mooc2-gray.chaoxing.com',
                'Pragma': 'no-cache',
                'Referer': referer_url,
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-site',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
                'sec-ch-ua': '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"macOS"'
            }
            log(f"上传请求头={headers}")
            log(f"上传URL={upload_url}")
            log(f"文件路径={image_path}, 原始文件名={os.path.basename(image_path)}")

            ext = os.path.splitext(image_path)[1].lower()
            mime_type_map = {
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.gif': 'image/gif',
                '.bmp': 'image/bmp'
            }
            mime_type = mime_type_map.get(ext, 'image/png')
            from datetime import datetime, timezone
            utc_now = datetime.now(timezone.utc)
            filename_timestamp = utc_now.strftime("%Y-%m-%dT%H-%M-%S-") + f"{int(utc_now.microsecond / 1000):03d}Z"
            filename_ext = ext if ext in mime_type_map else ".png"
            filename = f"course-{filename_timestamp}{filename_ext}"

            log(f"MIME类型={mime_type}, 生成文件名={filename}")

            with open(image_path, 'rb') as f:
                import secrets

                file_bytes = f.read()
                boundary = f"----WebKitFormBoundary{secrets.token_hex(8)}"
                body = (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="filePart"; filename="{filename}"\r\n'
                    f"Content-Type: {mime_type}\r\n\r\n"
                ).encode("utf-8") + file_bytes + (
                    f"\r\n--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="fileType"\r\n\r\n'
                    f"{filename_ext.lstrip('.')}\r\n"
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="name"\r\n\r\n'
                    f"{filename}\r\n"
                    f"--{boundary}--\r\n"
                ).encode("utf-8")
                log(
                    "上传 multipart: "
                    f"filePart={filename}, fileType={filename_ext.lstrip('.')}, name={filename}, "
                    f"boundary={boundary}, bytes={len(body)}, cookies=none"
                )
                upload_headers = headers.copy()
                upload_headers['Content-Type'] = f'multipart/form-data; boundary={boundary}'
                upload_headers['Content-Length'] = str(len(body))
                log(f"最终上传请求头={upload_headers}")
                response = requests.post(upload_url, data=body, headers=upload_headers, timeout=30)

            response.encoding = 'utf-8'

            log(f"上传响应 status={response.status_code}")
            log(f"上传响应 body={response.text[:500]}")

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
            try:
                log(f"异常: {e}")
            except Exception:
                print(f"DEBUG upload_cover_image error: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": f"上传失败: {e}"}

    def get_course_category_list(self, course_id: str, fid: str, cpi: str) -> dict:
        """获取课程分类列表及所属院系列表"""
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

            if result.get('status'):
                import json
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
        """获取课程基本信息设置"""
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

            html_content = response.text
            print(f"DEBUG get_course_setting html length: {len(html_content)}")
            if len(html_content) < 5000:
                print(f"DEBUG get_course_setting full html:\n{html_content}")
            else:
                print(f"DEBUG get_course_setting html snippet (first 3000):\n{html_content[:3000]}")

            soup = BeautifulSoup(html_content, 'html.parser')
            data = {"success": True}

            img_tag = soup.find('img', id='cloneCourseImg')
            if img_tag:
                data['default_cover'] = img_tag.get('src', '')
                print(f"DEBUG found cover: {data['default_cover']}")

            name_tag = soup.find('p', id='courseName')
            if name_tag:
                data['name'] = name_tag.get_text().strip()
                print(f"DEBUG found name from p#courseName: {data['name']}")
            else:
                name_input = soup.find('input', id='changeCourseName')
                if name_input:
                    data['name'] = name_input.get('value', '')
                    print(f"DEBUG found name from input#changeCourseName: {data['name']}")

            en_name_tag = soup.find('p', id='courseEnglish')
            if en_name_tag:
                data['english_name'] = en_name_tag.get_text().strip()
                print(f"DEBUG found english_name from p#courseEnglish: {data['english_name']}")
            else:
                en_name_input = soup.find('input', id='changeCourseEnglish')
                if en_name_input:
                    data['english_name'] = en_name_input.get('value', '')
                    print(f"DEBUG found english_name from input#changeCourseEnglish: {data['english_name']}")

            teacher_tag = soup.find('p', id='courseTeachers')
            if teacher_tag:
                data['teacher'] = teacher_tag.get_text().strip()
                print(f"DEBUG found teacher from p#courseTeachers: {data['teacher']}")
            else:
                teacher_input = soup.find('input', id='changeCourseTeachers')
                if teacher_input:
                    data['teacher'] = teacher_input.get('value', '')
                    print(f"DEBUG found teacher from input#changeCourseTeachers: {data['teacher']}")

            unit_tag = soup.find('p', id='showCourseUnitName')
            if unit_tag:
                data['unit_name'] = unit_tag.get_text().strip()
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

            dept_tag = soup.find('p', id='showCourseGroupName') or soup.find('p', id='secondSelectInput')
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

            desc_textarea = soup.find('textarea', id='changeCourseSchools')
            if desc_textarea:
                data['description'] = desc_textarea.get_text().strip()
                print(f"DEBUG found description: {data['description'][:50]}...")
            else:
                desc_tag = soup.find('p', id='courseSchools')
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
        """使用AI生成课程封面"""
        try:
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

            soup = BeautifulSoup(response.text, 'html.parser')
            token_input = soup.find('input', {'id': 'checkUserToken'})

            if not token_input or not token_input.get('value'):
                print(f"DEBUG 未找到checkUserToken，HTML片段: {response.text[:500]}")
                return {"success": False, "error": "未找到checkUserToken"}

            check_user_token = token_input.get('value')
            print(f"DEBUG checkUserToken: {check_user_token}")

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
