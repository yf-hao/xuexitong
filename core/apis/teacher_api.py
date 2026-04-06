import json

from bs4 import BeautifulSoup


class TeacherAPI:
    """教学团队相关接口。"""

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
        cpi = params.get("cpi", "")

        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/teacher-team-manage"
        req_params = {
            "courseid": course_id,
            "requireTea": "",
            "cpi": cpi,
            "orderContentTeam": "ID",
            "orderTeam": "up",
            "role": "0",
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

            soup = BeautifulSoup(html, "lxml")
            teachers = []
            teacher_rows = soup.find_all("ul", class_="dataBody_td")
            print(f"找到教师行数: {len(teacher_rows)}")

            for row in teacher_rows:
                teacher_personid = row.get("personId") or row.get("personid")
                teacher_uid = row.get("uid")
                teacher_id = teacher_personid if teacher_personid else teacher_uid

                name_li = row.find("li", class_="dataBody_name")
                name = name_li.get_text(strip=True) if name_li else "未知"

                role_li = row.find("li", class_="dataBody_read")
                role = role_li.get_text(strip=True) if role_li else ""

                work_li = row.find("li", class_="dataBody_down")
                work_id = work_li.get_text(strip=True) if work_li else ""

                dept_li = row.find("li", class_="dataBody_depart")
                organization = dept_li.get_text(strip=True) if dept_li else ""

                selected = True
                print(f"教师信息(Parsed): id={teacher_id}, name={name}, workId={work_id}, role={role}, dept={organization}")

                teachers.append({
                    "id": teacher_id,
                    "name": name,
                    "workId": work_id,
                    "role": role,
                    "dept": organization,
                    "organization": organization,
                    "selected": selected,
                })

            print(f"解析教师团队列表成功，共 {len(teachers)} 名教师")
            return teachers
        except Exception as e:
            print(f"获取教师列表失败: {e}")
            import traceback

            traceback.print_exc()
            return []

    def search_teacher(self, query_name: str) -> dict:
        """搜索教师。"""
        params = self.session_manager.course_params
        course_id = params.get("courseid")
        cpi = params.get("cpi")
        fid = params.get("fid", "4311")

        if not course_id:
            return {"success": False, "error": "缺少课程ID"}

        try:
            manage_url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/teacher-team-manage"
            manage_params = {
                "courseid": course_id,
                "cpi": cpi,
                "orderContentTeam": "ID",
                "orderTeam": "up",
                "role": "0",
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
                "Sec-Fetch-Site": "same-origin",
            }

            manage_resp = self.session.get(manage_url, params=manage_params, headers=manage_headers, timeout=10)
            print(f"访问教师团队管理页面状态码: {manage_resp.status_code}")

            manage_html = manage_resp.text
            if "参数被篡改" in manage_html and "nullMain" in manage_html:
                print("DEBUG: 访问教师团队管理页面返回真正的错误页面（参数被篡改）")
                print(f"错误页面内容: {manage_html[:500]}")
                return {"success": False, "error": "访问教师团队管理页面失败"}

            soup = BeautifulSoup(manage_html, "lxml")
            enc_input = soup.find("input", id="stuBankGetStuEnc")
            enc_param = ""
            if enc_input:
                enc_param = enc_input.get("value", "")
                print(f"DEBUG: 从 stuBankGetStuEnc 提取到 enc 参数: {enc_param}")
            else:
                print("DEBUG: 未找到 stuBankGetStuEnc 元素")
                return {"success": False, "error": "无法从页面中获取 enc 参数"}

            fid_param = fid
            fid_input = soup.find("input", id="queryFid")
            if fid_input:
                fid_param = fid_input.get("value", fid)
                print(f"DEBUG: 提取到 fid 参数: {fid_param}")

            ut_param = "t"
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
                "ut": ut_param,
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
                "Sec-Fetch-Site": "same-origin",
            }

            resp = self.session.get(url, params=req_params, headers=headers, timeout=10)
            print(f"搜索教师请求状态码: {resp.status_code}")
            print(f"查询参数: {req_params}")
            resp.raise_for_status()
            html = resp.text
            print(f"返回HTML长度: {len(html)}")

            soup = BeautifulSoup(html, "lxml")
            teachers = []

            teacher_rows = soup.find_all("ul", class_=lambda c: c and any("dataBody_addtea" in cls for cls in c) if isinstance(c, list) else False)
            if not teacher_rows:
                for ul in soup.find_all("ul"):
                    class_str = str(ul.get("class", []))
                    if "dataBody_addtea" in class_str:
                        teacher_rows.append(ul)

            print(f"找到教师行数: {len(teacher_rows)}")

            if not teacher_rows:
                print("DEBUG: 未找到教师行，打印HTML前1200字符:")
                print(html[:1200])
                print("DEBUG: 查找所有ul标签的class属性:")
                all_uls = soup.find_all("ul")
                for i, ul in enumerate(all_uls[:10]):
                    classes = ul.get("class", [])
                    print(f"  ul[{i}]: class={classes}")

            for idx, row in enumerate(teacher_rows):
                print(f"DEBUG: 教师行{idx + 1} HTML:")
                print(str(row)[:500])

                person_id = row.get("personid", "")
                enc = row.get("enc", "")

                name_span = row.find("span", class_="txt-w")
                name = name_span.get_text(strip=True) if name_span else "未知"

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
                    "dept": dept,
                })

            print(f"搜索教师成功，共 {len(teachers)} 名教师")
            return {
                "success": True,
                "teachers": teachers,
            }
        except Exception as e:
            print(f"搜索教师失败: {e}")
            import traceback

            traceback.print_exc()
            return {"success": False, "error": f"搜索教师失败: {str(e)}"}

    def add_team_teacher(self, course_id: str, teacher_info_list: list) -> tuple[bool, str]:
        """添加教师到教学团队。"""
        params = self.session_manager.course_params
        cpi = params.get("cpi", "")

        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/addteamteacher"
        user_data_str = json.dumps(teacher_info_list)

        req_params = {
            "courseId": course_id,
            "cpi": cpi,
            "isAssistant": "false",
            "userDataStr": user_data_str,
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

            if res_data.get("status") is True:
                msg = res_data.get("msg", "添加成功")
                count = res_data.get("addTeacherCount", 0)
                return True, f"{msg} (成功添加 {count} 人)"
            return False, res_data.get("msg", "添加失败")
        except Exception as e:
            return False, f"网络请求失败: {e}"

    def remove_team_teacher(self, course_id: str, teacher_ids: list) -> tuple[bool, str]:
        """移除教学团队中的教师。"""
        params = self.session_manager.course_params
        cpi = params.get("cpi", "")
        clazz_id = params.get("clazzid") or params.get("classId") or ""

        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/removeteamteaher"
        person_ids_str = ",".join(teacher_ids)

        req_params = {
            "courseId": course_id,
            "cpi": cpi,
            "personIds": person_ids_str,
        }

        import time

        t_param = str(int(time.time() * 1000))
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

            msg = res_data.get("msg", "")
            if "无权限设置" in msg:
                return True, "移除成功"
            if res_data.get("result") == 1 or res_data.get("status") is True:
                return True, msg or "移除成功"
            return False, msg or "移除失败"
        except Exception as e:
            return False, f"网络请求失败: {e}"
