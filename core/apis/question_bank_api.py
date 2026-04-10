from core.utils.latex_utils import latex_to_unicode, apply_latex_unicode_map, is_simple_unicode

class QuestionBankAPI:
    """题库目录与题目相关接口。"""
    
    def upload_image_bytes(self, image_bytes: bytes, filename: str = "image.png") -> str:
        """
        上传图片字节数据到超星服务器
        
        Args:
            image_bytes: 图片的字节数据
            filename: 文件名
            
        Returns:
            上传成功返回图片URL，失败返回None
        """
        import tempfile
        import os
        
        tmp_path = None
        try:
            # 保存为临时文件
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(image_bytes)
                tmp_path = tmp.name
            
            # 调用 upload_cover_image（来自 CourseManageAPI）
            upload_result = self.upload_cover_image(tmp_path)
            
            if upload_result.get("success"):
                url = upload_result.get("url", "")
                print(f"DEBUG upload_image_bytes: 上传成功，URL={url}")
                return url
            else:
                print(f"DEBUG upload_image_bytes: 上传失败 - {upload_result}")
                return None
        except Exception as e:
            print(f"DEBUG upload_image_bytes: 异常 - {str(e)}")
            return None
        finally:
            # 清理临时文件
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
    
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
    
    def _parse_question_folders_and_questions_html(self, html_content: str, course_id: str) -> dict:
        """从 HTML 内容同时解析文件夹和题目列表"""
        from bs4 import BeautifulSoup
        import re
        
        soup = BeautifulSoup(html_content, "lxml")
        folders = []
        questions = []
        
        # 解析文件夹
        folder_items = soup.find_all("li", class_="list-folder")
        for item in folder_items:
            try:
                folder_id = item.get("id", "")
                if not folder_id:
                    continue
                
                dirname_span = item.find("span", class_="dirname")
                name = dirname_span.get_text(strip=True) if dirname_span else "未命名"
                
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
                    "course_id": item.get("courseid", course_id),
                    "is_share": item.get("isshare", "0") == "1",
                    "creator_id": item.get("createrid", ""),
                    "user_id": item.get("userid", ""),
                    "parent_id": None,
                    "children": []
                }
                
                folders.append(folder_data)
                
            except Exception as e:
                print(f"DEBUG: 解析文件夹项失败: {e}")
                continue
        
        # 解析题目
        question_items = soup.find_all("li", class_="TiMu")
        for item in question_items:
            try:
                question_id = item.get("id", "")
                if not question_id:
                    continue
                
                # 题干
                choose_name_span = item.find("span", class_="choose-name")
                content = choose_name_span.get("title", "") if choose_name_span else ""
                
                # 题型
                type_span = item.find("span", class_="overHidden1")
                question_type = type_span.get("title", "") if type_span else "未知"
                
                # 难度
                hard_span = item.find("span", class_="hard")
                difficulty_text = hard_span.get_text(strip=True) if hard_span else "0.5 (中)"
                difficulty_match = re.search(r'([\d.]+)', difficulty_text)
                difficulty = float(difficulty_match.group(1)) if difficulty_match else 0.5
                
                # 使用量
                dose_span = item.find("span", class_="dose")
                usage_count = int(dose_span.get_text(strip=True)) if dose_span else 0
                
                # 正确率
                accuracy_span = item.find("span", class_="accuracy")
                accuracy_text = accuracy_span.get_text(strip=True) if accuracy_span else "-"
                accuracy_match = re.search(r'([\d.]+)', accuracy_text)
                accuracy = float(accuracy_match.group(1)) if accuracy_match else None
                
                # 作者
                auth_span = item.find("span", class_="auth-name")
                author = auth_span.get_text(strip=True) if auth_span else ""
                
                # 创建时间
                time_span = item.find("span", class_="time")
                create_time = time_span.get_text(strip=True) if time_span else ""
                
                # 原始题型ID
                origin_type = item.get("originType", "0")
                
                question_data = {
                    "id": question_id,
                    "content": content,
                    "question_type": question_type,
                    "difficulty": difficulty,
                    "usage_count": usage_count,
                    "accuracy": accuracy,
                    "author": author,
                    "create_time": create_time,
                    "course_id": item.get("courseid", course_id),
                    "origin_type": origin_type
                }
                
                questions.append(question_data)
                
            except Exception as e:
                print(f"DEBUG: 解析题目项失败: {e}")
                continue
        
        print(f"解析完成: {len(folders)} 个文件夹, {len(questions)} 道题目")
        return {"folders": folders, "questions": questions}
    
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
            "pageSize": "100",  # 系统最大支持 100
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
            all_folders = []
            all_questions = []
            page_num = 1
            
            # 循环加载所有页
            while True:
                # 更新页码
                data["pageNum"] = str(page_num)
                
                resp = self.session.post(url, data=data, headers=headers, timeout=15)
                resp.raise_for_status()
                
                # 尝试解析 JSON 响应
                html_content = ""
                try:
                    result = resp.json()
                    if isinstance(result, dict):
                        html_content = result.get("html", "") or result.get("data", "")
                    elif isinstance(result, list):
                        # 如果是列表，按原逻辑处理（仅第一页）
                        if page_num == 1:
                            return {
                                "folders": self._parse_question_folders_json(result, course_id),
                                "questions": []
                            }
                        else:
                            break
                except:
                    html_content = resp.text
                
                if html_content:
                    # 解析 HTML，同时提取文件夹和题目
                    page_result = self._parse_question_folders_and_questions_html(html_content, course_id)
                    
                    # 第一页时获取文件夹列表
                    if page_num == 1:
                        all_folders = page_result.get("folders", [])
                    
                    # 累加题目
                    page_questions = page_result.get("questions", [])
                    all_questions.extend(page_questions)
                    
                    # 如果当前页题目少于 100，说明已经加载完所有题目
                    if len(page_questions) < 100:
                        break
                    
                    # 继续加载下一页
                    page_num += 1
                else:
                    break
            
            return {"folders": all_folders, "questions": all_questions}
            
        except Exception as e:
            print(f"获取子文件夹和题目失败: {e}")
            return {"folders": [], "questions": []}

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

    def add_question(self, folder_id: str, question_data: dict, course_id: str = None, base_dir: str = None) -> dict:
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
                
                # 检查是否包含中文字符，如果包含则跳过渲染（matplotlib 不支持中文）
                has_chinese = bool(re2.search(r'[\u4e00-\u9fff]', expr_render))
                if has_chinese:
                    print(f"DEBUG render_math_expr: 包含中文字符，跳过渲染，返回文本")
                    # 将 LaTeX 命令转换为 Unicode 符号后返回
                    expr_text = expr_render
                    # LaTeX 命令转换为 Unicode 符号（用于保留为文本显示）
                    expr_text = expr_text.replace(r"\{", "{")
                    expr_text = expr_text.replace(r"\}", "}")
                    expr_text = expr_text.replace(r"\text", "")
                    return None, 0, 0, expr_text
                
                # ===== 方案1: 尝试使用 CodeCogs API（在线），超时5秒 =====
                # 检测是否包含复杂命令（矩阵、积分、求和、大括号等）
                has_matrix = bool(re2.search(r'\\begin\{(pmatrix|matrix|bmatrix|vmatrix|Vmatrix)\}', expr_render))
                has_complex_commands = bool(re2.search(
                    r'\\int|\\sum|\\prod|\\Big|\\bigg|\\Bigg|\\big|\\oint|\\iint|\\iiint|\\lim|\\sup|\\inf|\\max|\\min',
                    expr_render
                ))
                
                def try_codecogs_api(latex_expr):
                    """使用 CodeCogs 在线 API 渲染 LaTeX，超时5秒"""
                    try:
                        import urllib.parse
                        import urllib.request
                        import socket
                        
                        # 准备 LaTeX 表达式
                        latex_code = latex_expr.strip()
                        # 移除 $$ 标记（如果有）
                        if latex_code.startswith('$$'):
                            latex_code = latex_code[2:]
                        if latex_code.endswith('$$'):
                            latex_code = latex_code[:-2]
                        latex_code = latex_code.strip()
                        
                        # 清理换行符和多余空格（保留 LaTeX 的 \\ 和 \quad 等）
                        # 将普通换行符替换为空格
                        latex_code_clean = re2.sub(r'\n\s*', ' ', latex_code)
                        # 清理多余空格
                        latex_code_clean = re2.sub(r'\s+', ' ', latex_code_clean)
                        
                        print(f"DEBUG render_math_expr: 尝试 CodeCogs API（超时20秒）...")
                        
                        # URL 编码
                        encoded_latex = urllib.parse.quote(latex_code_clean)
                        
                        # CodeCogs API URL
                        api_url = f"https://latex.codecogs.com/png.latex?{encoded_latex}"
                        
                        # 设置超时为20秒
                        socket.setdefaulttimeout(20)
                        
                        # 下载图片
                        req = urllib.request.Request(
                            api_url,
                            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                        )
                        response = urllib.request.urlopen(req, timeout=20)
                        img_data = response.read()
                        
                        print(f"DEBUG render_math_expr: CodeCogs API 成功，图片大小={len(img_data)} bytes")
                        
                        if img_data and len(img_data) > 100:  # 确保下载了有效图片
                            # 获取图片尺寸
                            from PIL import Image
                            import io
                            img = Image.open(io.BytesIO(img_data))
                            img_w, img_h = img.size
                            
                            # 上传图片
                            upload_url = self.upload_image_bytes(img_data, f"codecogs_{hash(latex_expr)}.png")
                            if upload_url:
                                print(f"DEBUG render_math_expr: CodeCogs 图片上传成功")
                                # 生成文本格式
                                expr_text = latex_expr
                                def matrix_to_text(m):
                                    content = m.group(2).replace('\\\\', ';').replace('&', ',')
                                    return f"({content})"
                                expr_text = re2.sub(r'\\begin\{(pmatrix|bmatrix|vmatrix|Vmatrix|matrix)\}(.*?)\\end\{\1\}',
                                                   matrix_to_text,
                                                   expr_text, flags=re2.DOTALL)
                                expr_text = expr_text.replace('$$', '').replace('$', '').strip()
                                return upload_url, img_w, img_h, expr_text
                        
                        return None
                    except Exception as e:
                        print(f"DEBUG render_math_expr: CodeCogs API 超时或失败: {str(e)}，切换到 matplotlib")
                        return None
                
                # 对于复杂命令，优先尝试 CodeCogs API
                if has_matrix or has_complex_commands:
                    if has_matrix:
                        print(f"DEBUG render_math_expr: 包含矩阵环境，优先使用 CodeCogs API")
                    else:
                        print(f"DEBUG render_math_expr: 包含复杂命令（积分/求和/大括号等），优先使用 CodeCogs API")
                    
                    # 尝试 CodeCogs API
                    result = try_codecogs_api(expr_render)
                    if result:
                        return result
                    
                    # CodeCogs API 失败后的 fallback 处理
                    if has_matrix:
                        # 矩阵：使用 matplotlib table 绘制（离线）
                        print(f"DEBUG render_math_expr: CodeCogs API 失败，使用 matplotlib table 绘制矩阵")
                        
                        import matplotlib.pyplot as plt
                        
                        def draw_matrix_with_matplotlib(expr_with_matrix):
                            """使用matplotlib绘制矩阵"""
                            import numpy as np
                            
                            # 查找所有矩阵
                            matrices = []
                            pattern = r'\\begin\{(pmatrix|bmatrix|vmatrix|Vmatrix|matrix)\}(.*?)\\end\{\1\}'
                            
                            def parse_matrix_content(content):
                                """解析矩阵内容为二维数组"""
                                # 分割行
                                rows = content.split('\\\\')
                                matrix_data = []
                                for row in rows:
                                    # 分割列
                                    cells = row.split('&')
                                    matrix_data.append([c.strip() for c in cells])
                                return matrix_data
                            
                            # 提取所有矩阵
                            for match in re2.finditer(pattern, expr_with_matrix, re2.DOTALL):
                                env_type = match.group(1)
                                content = match.group(2)
                                matrix_data = parse_matrix_content(content)
                                matrices.append({
                                    'type': env_type,
                                    'data': matrix_data,
                                    'full_match': match.group(0)
                                })
                            
                            if not matrices:
                                return None
                            
                            # 绘制所有矩阵
                            fig, ax = plt.subplots(figsize=(8, 4), dpi=150)
                            ax.set_xlim(0, 10)
                            ax.set_ylim(0, 5)
                            ax.axis('off')
                            
                            x_offset = 0.5
                            for matrix_info in matrices:
                                matrix_type = matrix_info['type']
                                matrix_data = matrix_info['data']
                                
                                # 计算矩阵尺寸
                                n_rows = len(matrix_data)
                                n_cols = max(len(row) for row in matrix_data) if matrix_data else 0
                                
                                # 单元格大小
                                cell_width = 0.8
                                cell_height = 0.5
                                
                                # 矩阵起始位置
                                matrix_x = x_offset
                                matrix_y = 4.0
                                
                                # 绘制表格
                                table_data = []
                                for i, row in enumerate(matrix_data):
                                    row_data = []
                                    for j, cell in enumerate(row):
                                        row_data.append(cell)
                                    # 填充空列
                                    while len(row_data) < n_cols:
                                        row_data.append('')
                                    table_data.append(row_data)
                                
                                table = ax.table(
                                    cellText=table_data,
                                    loc='upper left',
                                    bbox=[matrix_x + 0.3, matrix_y - n_rows * cell_height, 
                                          n_cols * cell_width, n_rows * cell_height],
                                    cellLoc='center',
                                    edges=''
                                )
                                
                                # 设置表格样式
                                table.auto_set_font_size(False)
                                table.set_fontsize(14)
                                for key, cell in table.get_celld().items():
                                    cell.set_edgecolor('none')
                                    cell.set_facecolor('none')
                                    cell.set_text_props(color='black')
                                
                                # 绘制括号
                                total_height = n_rows * cell_height
                                bracket_x = matrix_x + 0.1
                                bracket_y = matrix_y - total_height
                                
                                if matrix_type == 'pmatrix':
                                    # 圆括号
                                    ax.text(bracket_x, matrix_y - total_height/2, '(', 
                                           fontsize=30, ha='center', va='center', 
                                           fontweight='bold', color='black',
                                           transform=ax.transData)
                                    ax.text(matrix_x + 0.3 + n_cols * cell_width + 0.15, 
                                           matrix_y - total_height/2, ')',
                                           fontsize=30, ha='center', va='center',
                                           fontweight='bold', color='black',
                                           transform=ax.transData)
                                elif matrix_type == 'bmatrix':
                                    # 方括号
                                    ax.text(bracket_x, matrix_y - total_height/2, '[',
                                           fontsize=30, ha='center', va='center',
                                           fontweight='bold', color='black',
                                           transform=ax.transData)
                                    ax.text(matrix_x + 0.3 + n_cols * cell_width + 0.15,
                                           matrix_y - total_height/2, ']',
                                           fontsize=30, ha='center', va='center',
                                           fontweight='bold', color='black',
                                           transform=ax.transData)
                                elif matrix_type in ['vmatrix', 'Vmatrix']:
                                    # 竖线
                                    lines_count = 2 if matrix_type == 'Vmatrix' else 1
                                    for idx in range(lines_count):
                                        offset = idx * 0.05
                                        ax.plot([bracket_x + offset, bracket_x + offset],
                                               [bracket_y, matrix_y],
                                               color='black', linewidth=2, transform=ax.transData)
                                        ax.plot([matrix_x + 0.3 + n_cols * cell_width + 0.15 - offset,
                                               matrix_x + 0.3 + n_cols * cell_width + 0.15 - offset],
                                               [bracket_y, matrix_y],
                                               color='black', linewidth=2, transform=ax.transData)
                                
                                # 更新x偏移
                                x_offset = matrix_x + 0.3 + n_cols * cell_width + 0.6
                            
                            plt.tight_layout()
                            return fig
                        
                        # 绘制矩阵
                        fig = draw_matrix_with_matplotlib(expr_render)
                        if fig:
                            # 保存图片
                            import io
                            buf = io.BytesIO()
                            fig.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                                       facecolor='white', edgecolor='none')
                            buf.seek(0)
                            plt.close(fig)
                            
                            # 获取图片尺寸
                            from PIL import Image
                            img = Image.open(buf)
                            img_w, img_h = img.size
                            
                            # 上传图片
                            upload_url = self.upload_image_bytes(buf.getvalue(), f"matrix_{hash(expr_render)}.png")
                            if upload_url:
                                print(f"DEBUG render_math_expr: matplotlib table 渲染成功")
                                # 生成文本格式
                                expr_text = expr_render
                                def matrix_to_text_2(m):
                                    content = m.group(2).replace('\\\\', ';').replace('&', ',')
                                    return f"matrix({content})"
                                expr_text = re2.sub(r'\\begin\{(pmatrix|bmatrix|vmatrix|Vmatrix|matrix)\}(.*?)\\end\{\1\}', 
                                                  matrix_to_text_2, 
                                                  expr_text, flags=re2.DOTALL)
                                expr_text = expr_text.replace('$$', '').replace('$', '').strip()
                                return upload_url, img_w, img_h, expr_text
                        
                        # 如果绘制失败，fallback到文本格式
                        print(f"DEBUG render_math_expr: 矩阵绘制失败，使用文本格式")
                        expr_text = expr_render
                        def matrix_to_text_3(m):
                            content = m.group(2).replace('\\\\', ';').replace('&', ',')
                            return f"({content})"
                        expr_text = re2.sub(r'\\begin\{(pmatrix|bmatrix|vmatrix|Vmatrix|matrix)\}(.*?)\\end\{\1\}',
                                           matrix_to_text_3,
                                           expr_text, flags=re2.DOTALL)
                        expr_text = expr_text.replace('$$', '').replace('$', '').strip()
                        return None, 0, 0, expr_text
                    else:
                        # 其他复杂命令：继续用后面的 matplotlib mathtext 流程
                        print(f"DEBUG render_math_expr: CodeCogs API 失败，尝试 matplotlib mathtext")
                        # 不返回，继续执行后面的 mathtext 渲染逻辑
                
                # 检查是否包含上标 ^ 或下标 _，如果有则需要渲染
                has_superscript = '^' in expr_render
                has_subscript = '_' in expr_render
                if has_superscript or has_subscript:
                    print(f"DEBUG render_math_expr: 检测到上标或下标，需要渲染")
                else:
                    # 检查是否只包含普通字符（不需要渲染为图片）
                    # 普通字符：字母、数字、括号、基本运算符（不含 ^ 和 _）
                    # 注意：排除 < 和 >，因为它们会被 HTML 转义，应该渲染成图片或转换为数学尖括号
                    plain_chars_pattern = r'^[a-zA-Z0-9\s\(\)\[\]\{\}+\-=,.\'\';:\!]+$'
                    if re2.match(plain_chars_pattern, expr_render):
                        print(f"DEBUG render_math_expr: 只包含普通字符，返回文本: {expr_render}")
                        return None, 0, 0, expr_render
                
                # LaTeX 命令转换为 Unicode 符号（用于保留为文本显示）
                # 使用工具函数处理下标、上标、尖括号、花括号
                print(f"DEBUG render_math_expr: 原始表达式: {repr(expr_render)}")
                expr_text = latex_to_unicode(expr_render)
                print(f"DEBUG render_math_expr: latex_to_unicode后: {repr(expr_text)}")
                # 处理 LaTeX 空格命令（\ 后跟空格或 ; 或 : 或 ,）
                expr_text = re2.sub(r'\\[,;: ]', ' ', expr_text)  # \, \; \: \  → 空格
                print(f"DEBUG render_math_expr: 处理空格命令后: {repr(expr_text)}")
                # 其他 LaTeX 命令转换（使用映射表）
                expr_text = apply_latex_unicode_map(expr_text)
                print(f"DEBUG render_math_expr: apply_latex_unicode_map后: {repr(expr_text)}")
                # 其他转换
                expr_text = expr_text.replace("~", " ")  # 不间断空格转普通空格
                expr_text = expr_text.replace("...", "…")  # 省略号
                expr_text = expr_text.replace(r"&", "")  # 移除对齐符 &
                
                # 再次检查：如果转换后只包含简单 Unicode 符号，可以跳过渲染
                print(f"DEBUG render_math_expr: LaTeX转Unicode后: {repr(expr_text)}")
                is_simple = is_simple_unicode(expr_text)
                print(f"DEBUG render_math_expr: is_simple_unicode返回: {is_simple}")
                if is_simple:
                    print(f"DEBUG render_math_expr: 转换后只包含简单Unicode符号，返回文本: {expr_text}")
                    return None, 0, 0, expr_text
                
                # 预处理：替换不支持的命令为 matplotlib 支持的命令（用于渲染）
                
                # Unicode 符号转换为 LaTeX 命令（后面加空格避免粘连）
                # 尖括号（数学）
                expr_render = expr_render.replace("⟨", r"\langle ")  # 左尖括号
                expr_render = expr_render.replace("⟩", r"\rangle ")  # 右尖括号
                # 处理 LaTeX 空格命令（matplotlib mathtext 不支持 \, \; \: \ 空格）
                # 替换为标准空格
                expr_render = re2.sub(r'\\[,;: ]', ' ', expr_render)
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
                expr_render = expr_render.replace("⊈", r"\nsubseteq ")  # 不是子集或等于
                expr_render = expr_render.replace("⊉", r"\nsupseteq ")  # 不是超集或等于
                expr_render = expr_render.replace("⊄", r"\nsubset ")  # 不是真子集
                expr_render = expr_render.replace("⊅", r"\nsupset ")  # 不是真超集
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
                
                # 矩阵环境预处理：将 pmatrix 转换为 matplotlib 支持的格式
                # matplotlib mathtext 不支持 pmatrix，需要转换为 \left( \begin{matrix} ... \end{matrix} \right)
                expr_render = re2.sub(r'\\begin\{pmatrix\}', r'\\left( \\begin{matrix} ', expr_render)
                expr_render = re2.sub(r'\\end\{pmatrix\}', r' \\end{matrix} \\right)', expr_render)
                # bmatrix: 方括号矩阵
                expr_render = re2.sub(r'\\begin\{bmatrix\}', r'\\left[ \\begin{matrix} ', expr_render)
                expr_render = re2.sub(r'\\end\{bmatrix\}', r' \\end{matrix} \\right]', expr_render)
                # vmatrix: 竖线矩阵（行列式）
                expr_render = re2.sub(r'\\begin\{vmatrix\}', r'\\left| \\begin{matrix} ', expr_render)
                expr_render = re2.sub(r'\\end\{vmatrix\}', r' \\end{matrix} \\right|', expr_render)
                # Vmatrix: 双竖线矩阵
                expr_render = re2.sub(r'\\begin\{Vmatrix\}', r'\\left\\| \\begin{matrix} ', expr_render)
                expr_render = re2.sub(r'\\end\{Vmatrix\}', r' \\end{matrix} \\right\\|', expr_render)
                
                # 检测是否是多行公式（仅在 align 环境中拆分）
                # 注意：矩阵环境（pmatrix, matrix, bmatrix等）中的 \\ 不能拆分
                is_multiline = False
                if re2.search(r"\\begin\{align\}|\\begin\{aligned\}", expr_render):
                    is_multiline = True
                elif re2.search(r"\\\\", expr_render):
                    # 如果包含 \\，检查是否在矩阵环境中
                    if re2.search(r"\\begin\{(pmatrix|matrix|bmatrix|vmatrix|Vmatrix)\}", expr_render):
                        # 矩阵环境，不拆分
                        is_multiline = False
                        print(f"DEBUG render_math_expr: 检测到矩阵环境，不拆分")
                    else:
                        # 其他情况，拆分
                        is_multiline = True
                
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
                base_height_per_line = 24  # 每行基础高度
                target_height = actual_line_count * base_height_per_line
                
                # 检测是否包含高符号（积分、求和、根号、分数等）
                has_tall_symbols = bool(re2.search(r'\\int|\\sum|\\prod|\\sqrt|\\frac|\^|\_', expr_render))
                
                if has_tall_symbols:
                    # 如果包含高符号，不强制缩放高度，保持原始高度
                    # 但如果太高（超过36px），则适当缩放
                    if im.height > 36:
                        scale = 36 / im.height
                        new_w = int(im.width * scale)
                        im = im.resize((new_w, 36), Image.LANCZOS)
                        print(f"DEBUG render_math_expr: 高公式缩放从 {img_w}x{img_h} 到 {new_w}x36")
                    else:
                        print(f"DEBUG render_math_expr: 高公式保持原尺寸 {img_w}x{img_h}")
                else:
                    # 普通公式：缩放到目标高度
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
            # 仅当含有 $ 或 \[ 或 \( 时才尝试解析，避免无关文本的正则开销
            if not text or not re.search(r"\$|\\\[|\\\(", text):
                return text, {}
            # 改进正则：支持 $$, $, \[...\], \(...\) 四种格式
            pattern = re.compile(r"\$\$\s*(.+?)\s*\$\$|\$\s*(.+?)\s*\$|\\\[\s*(.+?)\s*\\\]|\\\(\s*(.+?)\s*\\\)", re.DOTALL)
            replacements = {}
            new_text = text
            for idx, m in enumerate(pattern.finditer(text)):
                expr = m.group(1) or m.group(2) or m.group(3) or m.group(4) or ""
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
                        # 图片上传成功，只缓存图片信息，不缓存plain_text
                        self._math_img_cache[expr] = (url, w, h, None)
                    elif plain_text:
                        self._math_img_cache[expr] = ("text", 0, 0, plain_text)  # 缓存纯文本
                        
                if url:
                    # 图片模式：替换为图片标签（优先使用图片）
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
                elif plain_text:
                    # 纯文本模式：直接替换为转换后的文本（去掉 $ 符号）
                    placeholder = f"__MATH_TEXT_{len(replacements)}__"
                    replacements[placeholder] = plain_text
                    new_text = new_text.replace(m.group(0), placeholder, 1)
                # 如果既没有plain_text也没有url，保留原样（不替换）
            return new_text, replacements
        
        def replace_local_images(text: str, base_dir: str = None):
            """
            处理本地图片引用，上传到超星服务器并替换URL
            
            Args:
                text: 包含图片引用的文本
                base_dir: 图片相对路径的基准目录，默认为当前工作目录
                
            Returns:
                (处理后的文本, 替换字典)
            """
            import os
            import re
            
            if not text:
                return text, {}
            
            # 匹配 Markdown 图片语法：![alt](path)
            pattern = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
            replacements = {}
            new_text = text
            
            for match in pattern.finditer(text):
                alt_text = match.group(1)
                img_path = match.group(2)
                
                # 提取缩放比例或像素尺寸
                scale_percent = None
                target_height_px = None
                alt_text_clean = alt_text
                
                # 优先匹配百分比格式：图片(30%)
                scale_match = re.search(r'\((\d+(?:\.\d+)?)\s*%\)', alt_text)
                if scale_match:
                    scale_percent = float(scale_match.group(1))
                    alt_text_clean = alt_text[:scale_match.start()].strip() + alt_text[scale_match.end():].strip()
                    print(f"DEBUG: 检测到缩放比例: {scale_percent}%")
                else:
                    # 尝试匹配像素尺寸格式：图片(150px)
                    px_match = re.search(r'\((\d+(?:\.\d+)?)\s*px\)', alt_text, re.IGNORECASE)
                    if px_match:
                        target_height_px = float(px_match.group(1))
                        alt_text_clean = alt_text[:px_match.start()].strip() + alt_text[px_match.end():].strip()
                        print(f"DEBUG: 检测到像素高度: {target_height_px}px")
                
                # 跳过网络URL
                if img_path.startswith(('http://', 'https://', 'ftp://')):
                    continue
                
                print(f"DEBUG: 发现本地图片引用: {img_path}")
                
                # 查找图片文件
                if base_dir and not os.path.isabs(img_path):
                    full_path = os.path.join(base_dir, img_path)
                else:
                    full_path = img_path
                
                # 如果文件不存在，尝试几种常见位置
                if not os.path.exists(full_path):
                    # 尝试当前工作目录
                    alt_path = os.path.join(os.getcwd(), img_path)
                    if os.path.exists(alt_path):
                        full_path = alt_path
                    else:
                        print(f"DEBUG: 图片文件不存在: {full_path}")
                        continue
                
                # 检查文件扩展名
                ext = os.path.splitext(full_path)[1].lower()
                if ext not in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp']:
                    print(f"DEBUG: 不支持的图片格式: {ext}")
                    continue
                
                try:
                    # 读取图片文件
                    with open(full_path, 'rb') as f:
                        img_bytes = f.read()
                    
                    print(f"DEBUG: 读取图片成功，大小={len(img_bytes)} bytes")
                    
                    # 上传图片
                    upload_url = self.upload_image_bytes(img_bytes, os.path.basename(full_path))
                    
                    if upload_url:
                        print(f"DEBUG: 图片上传成功: {upload_url}")
                        # 替换为超星URL
                        placeholder = f"__LOCAL_IMG_{len(replacements)}__"
                        
                        # 应用缩放比例或像素高度
                        if scale_percent is not None:
                            img_html = f'<img src="{upload_url}" alt="{alt_text_clean}" style="width:{scale_percent}%; height:auto;" />'
                        elif target_height_px is not None:
                            img_html = f'<img src="{upload_url}" alt="{alt_text_clean}" style="height:{target_height_px}px; width:auto; max-width:100%;" />'
                        else:
                            img_html = f'<img src="{upload_url}" alt="{alt_text_clean}" style="max-width:100%; height:auto;" />'
                        
                        replacements[placeholder] = img_html
                        new_text = new_text.replace(match.group(0), placeholder, 1)
                    else:
                        print(f"DEBUG: 图片上传失败")
                        
                except Exception as e:
                    print(f"DEBUG: 处理图片失败: {str(e)}")
                    continue
            
            return new_text, replacements

        # 全局预处理：统一公式定界符格式
        # \( \) → $ $，\[ \] → $$ $$
        content = content.replace(r"\[", "$$").replace(r"\]", "$$")
        content = content.replace(r"\(", "$").replace(r"\)", "$")
        analysis = analysis.replace(r"\[", "$$").replace(r"\]", "$$")
        analysis = analysis.replace(r"\(", "$").replace(r"\)", "$")
        for opt in options:
            val = opt.get("value", "")
            opt["value"] = val.replace(r"\[", "$$").replace(r"\]", "$$")
            opt["value"] = opt["value"].replace(r"\(", "$").replace(r"\)", "$")

        content, content_repl = replace_math(content)
        analysis, analysis_repl = replace_math(analysis)
        
        # 处理本地图片引用
        content, content_img_repl = replace_local_images(content, base_dir)
        analysis, analysis_img_repl = replace_local_images(analysis, base_dir)
        # 合并替换字典
        content_repl.update(content_img_repl)
        analysis_repl.update(analysis_img_repl)

        processed_options = []
        for opt in options:
            val = opt.get("value", "")
            val_new, val_repl = replace_math(val)
            val_new, val_img_repl = replace_local_images(val_new, base_dir)
            val_repl.update(val_img_repl)
            processed_options.append({"key": opt.get("key", ""), "value": val_new, "repl": val_repl})

        # 全局替换 LaTeX 转义的花括号（公式外的 \{ \} 也要处理）
        content = content.replace(r"\{", "{").replace(r"\}", "}")
        analysis = analysis.replace(r"\{", "{").replace(r"\}", "}")
        for opt in processed_options:
            opt["value"] = opt["value"].replace(r"\{", "{").replace(r"\}", "}")

        # 将内容转为 HTML 格式：每行包裹 <p>，空格/制表符转为 &nbsp; 保留缩进
        # 支持 Markdown 代码块转换为 <pre><code> 格式
        # 支持占位符替换（如公式图片 <img>），在转义后执行 replacements
        def to_html(text, replacements=None):
            import html
            import re as re3
            if text is None:
                return ""

            # 预处理：检测并转换 Markdown 代码块
            # 匹配 ```lang\ncode\n``` 格式
            code_block_pattern = re3.compile(r'```(\w*)\n(.*?)\n```', re3.DOTALL)

            # 使用占位符保护代码块
            code_blocks = {}
            placeholder_counter = [0]

            def replace_code_block(match):
                lang = match.group(1) or ""  # 语言标识
                code = match.group(2)  # 代码内容

                # 转义 HTML 特殊字符
                code_escaped = html.escape(code)

                # 处理缩进和换行
                # 制表符 -> 4个空格
                code_escaped = code_escaped.replace("\t", "&nbsp;&nbsp;&nbsp;&nbsp;")
                # 空格 -> &nbsp;
                code_escaped = code_escaped.replace(" ", "&nbsp;")
                # 换行符 -> <br/>
                code_escaped = code_escaped.replace("\n", "<br/>")

                # 生成 HTML 代码块
                if lang:
                    code_html = f'<pre class="hover"><code lang="{lang}" class="language-{lang}">{code_escaped}<br/></code></pre>'
                else:
                    code_html = f'<pre class="hover"><code>{code_escaped}<br/></code></pre>'

                # 使用占位符
                placeholder = f"__CODE_BLOCK_{placeholder_counter[0]}__"
                placeholder_counter[0] += 1
                code_blocks[placeholder] = code_html
                return placeholder

            # 替换代码块为占位符
            text_with_placeholders = code_block_pattern.sub(replace_code_block, str(text))

            # 处理普通文本行
            lines = text_with_placeholders.splitlines() or [""]
            html_lines = []
            for line in lines:
                # 先转义 HTML
                escaped = html.escape(line)
                # 转换 Markdown 粗体 **text** -> <strong>text</strong>
                escaped = re3.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', escaped)
                # 转换着重号 `text` -> <span style="text-emphasis: dot;">text</span>
                escaped = re3.sub(r'`([^`]+)`', r'<span style="text-emphasis: dot;">\1</span>', escaped)
                escaped = escaped.replace("\t", "&nbsp;&nbsp;&nbsp;&nbsp;")
                if escaped == "":
                    escaped = "&nbsp;"  # 空行占位
                html_lines.append(f"<p>{escaped}</p>")
            html_str = "".join(html_lines)

            # 恢复代码块
            for placeholder, code_html in code_blocks.items():
                # 代码块不需要 <p> 包裹，直接替换
                html_str = html_str.replace(f"<p>{placeholder}</p>", code_html)

            # 应用其他替换（如公式图片）
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
    
    def get_question_detail(self, question_id: str, folder_id: str, course_id: str = None) -> dict:
        """
        获取题目详情
        
        Args:
            question_id: 题目 ID
            folder_id: 文件夹 ID
            course_id: 课程 ID
        
        Returns:
            题目详情数据
        """
        params = self.session_manager.course_params
        
        if not course_id:
            course_id = params.get("courseid", "")
        
        cpi = params.get("cpi", "")
        
        url = f"https://mooc2-gray.chaoxing.com/mooc2-ans/qbank/view-question"
        
        params_dict = {
            "courseid": course_id,
            "cpi": cpi,
            "dirId": folder_id,
            "questionId": question_id,
            "curCourseId": course_id,
            "qbanksystem": "0",
            "isMap": "false",
            "microTopicId": "0"
        }
        
        headers = {
            "Accept": "text/html, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/qbank/questionlist?courseid={course_id}&cpi={cpi}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        }
        
        try:
            resp = self.session.get(url, params=params_dict, headers=headers, timeout=15)
            resp.raise_for_status()
            
            html_content = resp.text
            
            # 解析 HTML
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, "lxml")
            
            # 提取题干
            stem_div = soup.find("div", class_="stem_con")
            
            # 提取题型信息（从题干中移除）
            type_span = stem_div.find("span", class_="colorShallow") if stem_div else None
            question_type_info = type_span.get_text(strip=True) if type_span else ""
            
            # 移除题型信息 span 后再获取纯题干内容
            if stem_div and type_span:
                type_span.decompose()
            stem = stem_div.decode_contents() if stem_div else ""
            
            # 提取选项
            options = []
            answer_divs = soup.find_all("div", class_="answer_p")
            for div in answer_divs:
                option_label = div.find("span", class_="fl")
                option_content = div.find("div", class_="fl")
                
                if option_label and option_content:
                    label = option_label.get_text(strip=True)
                    content = option_content.decode_contents()
                    options.append({
                        "label": label,
                        "content": content
                    })
            
            # 提取答案
            answer_div = soup.find("div", class_="answer_tit")
            answer = ""
            if answer_div:
                answer_p = answer_div.find("p")
                answer = answer_p.get_text(strip=True) if answer_p else ""
            
            # 提取解析
            analysis_div = soup.find("div", class_="p_764")
            analysis = analysis_div.decode_contents() if analysis_div else ""
            
            # 提取难度
            difficulty_p = soup.find("p", class_="p_764")
            difficulty = difficulty_p.get_text(strip=True) if difficulty_p else ""
            
            return {
                "success": True,
                "stem": stem,
                "question_type_info": question_type_info,
                "options": options,
                "answer": answer,
                "analysis": analysis,
                "difficulty": difficulty
            }
            
        except Exception as e:
            print(f"获取题目详情失败: {e}")
            return {
                "success": False,
                "msg": str(e)
            }
