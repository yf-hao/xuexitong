class QuestionBankAPI:
    """题库目录与题目相关接口。"""

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
                # 先处理 \langle 和 \rangle（LaTeX 尖括号命令）
                expr_text = expr_render.replace(r"\langle", "⟨")  # 左尖括号
                expr_text = expr_text.replace(r"\rangle", "⟩")  # 右尖括号
                # 再处理普通尖括号（转换为数学尖括号，避免 HTML 转义）
                expr_text = expr_text.replace("<", "⟨")  # < → ⟨
                expr_text = expr_text.replace(">", "⟩")  # > → ⟩
                expr_text = expr_text.replace(r"\iff", "⟺")  # 当且仅当
                expr_text = expr_text.replace(r"\implies", "⇒")  # 蕴含
                expr_text = expr_text.replace(r"\land", "∧")  # 逻辑与
                expr_text = expr_text.replace(r"\lor", "∨")  # 逻辑或
                expr_text = expr_text.replace(r"\lnot", "¬")  # 逻辑非
                expr_text = expr_text.replace(r"\neg", "¬")  # 逻辑非
                expr_text = expr_text.replace(r"\forall", "∀")  # 全称量词
                expr_text = expr_text.replace(r"\exists", "∃")  # 存在量词
                # 注意：先替换长的命令，再替换短的命令
                expr_text = expr_text.replace(r"\leftrightarrow", "↔")  # 双向箭头
                expr_text = expr_text.replace(r"\rightarrow", "→")  # 箭头
                expr_text = expr_text.replace(r"\to", "→")  # 箭头
                expr_text = expr_text.replace(r"\leq", "≤")  # 小于等于
                expr_text = expr_text.replace(r"\geq", "≥")  # 大于等于
                expr_text = expr_text.replace(r"\neq", "≠")  # 不等于
                # 注意：先替换长的命令，再替换短的命令
                # \not\xxx 形式（先处理，因为更长）
                expr_text = expr_text.replace(r"\not\subseteq", "⊈")  # 不是子集或等于
                expr_text = expr_text.replace(r"\not\supseteq", "⊉")  # 不是超集或等于
                expr_text = expr_text.replace(r"\not\subset", "⊄")  # 不是真子集
                expr_text = expr_text.replace(r"\not\supset", "⊅")  # 不是真超集
                expr_text = expr_text.replace(r"\not\in", "∉")  # 不属于
                expr_text = expr_text.replace(r"\not=", "≠")  # 不等于
                # \nxxx 形式
                expr_text = expr_text.replace(r"\nsubseteq", "⊈")  # 不是子集或等于
                expr_text = expr_text.replace(r"\nsupseteq", "⊉")  # 不是超集或等于
                expr_text = expr_text.replace(r"\nsubset", "⊄")  # 不是真子集
                expr_text = expr_text.replace(r"\nsupset", "⊅")  # 不是真超集
                expr_text = expr_text.replace(r"\notin", "∉")  # 不属于
                # 基本符号
                expr_text = expr_text.replace(r"\subseteq", "⊆")  # 子集或等于
                expr_text = expr_text.replace(r"\supseteq", "⊇")  # 超集或等于
                expr_text = expr_text.replace(r"\subset", "⊂")  # 真子集
                expr_text = expr_text.replace(r"\supset", "⊃")  # 真超集
                expr_text = expr_text.replace(r"\in", "∈")  # 属于
                expr_text = expr_text.replace(r"\cup", "∪")  # 并集
                expr_text = expr_text.replace(r"\cap", "∩")  # 交集
                expr_text = expr_text.replace("~", " ")  # 不间断空格转普通空格
                expr_text = expr_text.replace(r"\emptyset", "∅")  # 空集
                expr_text = expr_text.replace(r"\empty", "∅")  # 空集
                expr_text = expr_text.replace(r"\wedge", "∧")  # 逻辑与
                expr_text = expr_text.replace(r"\vee", "∨")  # 逻辑或
                expr_text = expr_text.replace("...", "…")  # 省略号
                expr_text = expr_text.replace(r"\ldots", "…")  # 省略号
                expr_text = expr_text.replace(r"&", "")  # 移除对齐符 &
                expr_text = expr_text.replace(r"\lrarr", "↔")  # 双向箭头
                # 花括号转义（\{ 和 \} 表示字面的花括号）
                expr_text = expr_text.replace(r"\{", "{")  # 左花括号
                expr_text = expr_text.replace(r"\}", "}")  # 右花括号
                
                # 再次检查：如果转换后只包含普通字符和简单Unicode符号，可以跳过渲染
                # 注意：∉ 是组合字符，某些环境可能显示异常，需要渲染成图片
                # 注意：^ 和 _ 是上标下标，需要渲染成图片
                # 包含基本字符和大部分符号的模式（排除 ∉、^ 和 _）
                # | 用于集合描述法（如 {x | x > 0}）
                # ⟨ ⟩ 是数学尖括号（由 < > 转换而来）
                simple_pattern = r'^[a-zA-Z0-9\s\(\)\[\]\{\}|+\-=,.\'\';:\!¬∀∃∧∨→↔⇒⟺∈⊂⊃⊆⊇∪∩∅≤≥≠≈≡±×÷∞…⊈⊉⊄⊅⟨⟩]+$'
                print(f"DEBUG render_math_expr: LaTeX转Unicode后: {expr_text}")
                # 检查是否包含 ∉（组合字符），如果有则必须渲染
                if '∉' in expr_text:
                    print(f"DEBUG render_math_expr: 包含组合字符∉，需要渲染")
                elif re2.match(simple_pattern, expr_text):
                    print(f"DEBUG render_math_expr: 转换后只包含简单Unicode符号，返回文本: {expr_text}")
                    return None, 0, 0, expr_text
                
                # 预处理：替换不支持的命令为 matplotlib 支持的命令（用于渲染）
                
                # Unicode 符号转换为 LaTeX 命令（后面加空格避免粘连）
                # 尖括号（数学）
                expr_render = expr_render.replace("⟨", r"\langle ")  # 左尖括号
                expr_render = expr_render.replace("⟩", r"\rangle ")  # 右尖括号
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

        processed_options = []
        for opt in options:
            val = opt.get("value", "")
            val_new, val_repl = replace_math(val)
            processed_options.append({"key": opt.get("key", ""), "value": val_new, "repl": val_repl})

        # 全局替换 LaTeX 转义的花括号（公式外的 \{ \} 也要处理）
        content = content.replace(r"\{", "{").replace(r"\}", "}")
        analysis = analysis.replace(r"\{", "{").replace(r"\}", "}")
        for opt in processed_options:
            opt["value"] = opt["value"].replace(r"\{", "{").replace(r"\}", "}")

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
