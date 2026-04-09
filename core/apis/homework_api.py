"""作业相关 API。"""
from typing import List, Dict
import json
import re
from models.student_work_stats import StudentWorkStats
from models.question import Question


class HomeworkAPI:
    """作业相关 API 接口。"""
    
    def get_question_bank_courses(self, course_id: str, class_id: str) -> List[Dict[str, str]]:
        """
        获取题库课程列表。
        
        Args:
            course_id: 当前课程 ID
            class_id: 班级 ID
        
        Returns:
            课程列表 [{"id": "xxx", "name": "xxx"}, ...]
        """
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/work/qtbank"
        
        params = {
            "built": 1,
            "courseid": course_id,
            "clazzid": class_id,
            "workid": "",
            "cpi": self.session_manager.course_params.get("cpi", ""),
            "mooc": 1,
            "title": "新建作业",
            "grading": 0,
            "questionGroup": 0,
            "pid": 0,
            "fromChapter": 0,
            "from": ""
        }
        
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Pragma': 'no-cache',
            'Referer': f'https://mooc2-gray.chaoxing.com/mooc2-ans/work/goToWorkEditor?courseid={course_id}&clazzid={class_id}&directoryid=0&mooc=1&workid=&built=1&from=',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
        }
        
        try:
            response = self.session.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            response.encoding = 'utf-8'
            
            # 解析 HTML
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            courses = []
            course_list = soup.find('ul', class_='course-list')
            if course_list:
                for li in course_list.find_all('li', class_='operate-option'):
                    checkbox = li.find('input', class_='courseItem')
                    name_span = li.find('span', class_='infos')
                    
                    if checkbox and name_span:
                        course_id_value = checkbox.get('value', '').strip()
                        course_name = name_span.get_text(strip=True)
                        
                        if course_id_value and course_name:
                            courses.append({
                                'id': course_id_value,
                                'name': course_name
                            })
            
            return courses
            
        except Exception as e:
            print(f"获取题库课程列表失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def get_question_bank_check_list(self, course_id: str, class_id: str, course_ids: str = "", dir_id: str = "") -> Dict:
        """
        获取题库筛选条件统计数据。
        
        Args:
            course_id: 当前课程 ID
            class_id: 班级 ID
            course_ids: 选中的课程ID列表(逗号分隔)
            dir_id: 文件夹ID（空字符串表示根目录）
        
        Returns:
            {
                "typeNumArr": [{"key": "0", "doc_count": 97}, ...],
                "topicNumArr": [...],
                "allTopicList": [...],
                ...
            }
        """
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/qbank/update-check-list"
        
        params = {
            "cpi": self.session_manager.course_params.get("cpi", ""),
            "courseid": course_id,
            "courseIds": course_ids,
            "dirId": dir_id
        }
        
        headers = {
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Pragma': 'no-cache',
            'Referer': f'https://mooc2-gray.chaoxing.com/mooc2-ans/work/qtbank?built=1&courseid={course_id}&clazzid={class_id}',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest',
            'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
        }
        
        try:
            response = self.session.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status'):
                return data
            else:
                print(f"获取筛选条件失败: {data.get('msg', '未知错误')}")
                return {}
                
        except Exception as e:
            print(f"获取筛选条件统计数据失败: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def get_student_work_stats(self, course_id: str, class_id: str, page: int = 1, page_size: int = 200) -> List[StudentWorkStats]:
        """
        获取学生作业统计情况。
        
        Args:
            course_id: 课程 ID
            class_id: 班级 ID
            page: 页码
            page_size: 每页数量
        
        Returns:
            学生作业统计列表
        """
        url = "https://stat2-ans.chaoxing.com/stat2/work-stastics/student-works"
        
        params = {
            "clazzid": class_id,
            "courseid": course_id,
            "cpi": self.session_manager.course_params.get("cpi", ""),
            "ut": "t",
            "pEnc": "",
            "page": page,
            "pageSize": page_size,
            "order": 1
        }
        
        # 添加必要的请求头
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
        }
        
        try:
            response = self.session.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            
            # 解析 JSON 内容
            stats_list = StudentWorkStats.from_json(response.text)
            
            return stats_list
            
        except Exception as e:
            print(f"获取学生作业统计失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def search_questions(
        self,
        course_id: str,
        class_id: str,
        course_ids: str = "",
        question_types: List[str] = None,
        difficulties: List[str] = None,
        topic_ids: List[str] = None,
        keyword: str = "",
        page: int = 1,
        page_size: int = 30,
        dir_id: str = "",
        dir_course_id: str = ""
    ) -> Dict:
        """
        搜索题库题目。
        
        Args:
            course_id: 当前课程 ID（主课程）
            class_id: 班级 ID
            course_ids: 选中的课程ID列表(逗号分隔)
            question_types: 题型列表 ["type-typeId", ...]，如 ["0-0", "6-104209993"]
            difficulties: 难度列表 ["0", "1", "2"]
            topic_ids: 知识点ID列表
            keyword: 搜索关键词
            page: 页码
            page_size: 每页数量
            dir_id: 文件夹ID（空字符串表示根目录）
            dir_course_id: 文件夹所属课程ID（空字符串表示使用主课程ID）
        
        Returns:
            {
                "questions": [...],
                "folders": [...],
                "total": 总数,
                ...
            }
        """
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/qbank/search"
        
        # 构建 qTypes 参数
        q_types_str = ""
        if question_types is not None:
            # 不是全选，构建题型列表
            # question_types 格式为 ["type-typeId", ...]，如 ["0-0", "6-104209993"]
            q_types = []
            for type_str in question_types:
                if '-' in type_str:
                    type_id, type_id_value = type_str.split('-', 1)
                    q_types.append({"type": type_id, "typeId": type_id_value})
                else:
                    # 兼容旧格式
                    q_types.append({"type": type_str, "typeId": "0"})
            q_types_str = json.dumps(q_types, ensure_ascii=False) if q_types else ""
        # 如果 question_types 是 None，表示全选，qTypes 为空字符串
        
        # 构建 eTypes 参数
        e_types_str = ""
        if difficulties is not None:
            # 不是全选
            e_types_str = ",".join(difficulties) if difficulties else ""
        # 如果 difficulties 是 None，表示全选，eTypes 为空字符串
        
        # 构建 topicIds 参数
        topic_ids_str = ""
        if topic_ids is not None:
            # 不是全选
            topic_ids_str = ",".join(topic_ids) + "," if topic_ids else ""
        # 如果 topic_ids 是 None，表示全选，topicIds 为空字符串
        
        # 构建表单数据
        form_data = {
            "courseid": course_id,
            "clazzid": class_id,
            "cpi": self.session_manager.course_params.get("cpi", ""),
            "dirId": dir_id,
            "dirCourseId": dir_course_id if dir_course_id else course_id,  # 文件夹所属课程ID
            "courseIds": dir_course_id if dir_course_id else (course_ids or course_id),  # 搜索的课程ID
            "qTypes": q_types_str,
            "eTypes": e_types_str,
            "sw": keyword,
            "orderType": "",
            "orderByType": "",
            "orderByRight": "",
            "pageNum": page,
            "pageSize": page_size,
            "topicIds": topic_ids_str,
            "labelIds": "",
            "courseTargetIds": "",
            "rightPercentFrom": "",
            "rightPercentTo": "",
            "fetchQue": "true",
            "needHtml": "true"
        }
        
        headers = {
            'Accept': 'text/html, */*; q=0.01',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Cache-Control': 'no-cache',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Pragma': 'no-cache',
            'Referer': f'https://mooc2-gray.chaoxing.com/mooc2-ans/work/qtbank?built=1&courseid={course_id}&clazzid={class_id}',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest',
            'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
        }
        
        try:
            # 调试输出
            print(f"\n=== 搜索题目 ===")
            print(f"dir_id: {dir_id}")
            print(f"dir_course_id: {dir_course_id}")
            print(f"course_ids: {course_ids}")
            
            response = self.session.post(url, data=form_data, headers=headers, timeout=15)
            response.raise_for_status()
            response.encoding = 'utf-8'
            
            # 解析 HTML 响应
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 提取 qBankId（从隐藏的input或script中）
            q_bank_id = ""
            
            # 方法1：从隐藏input中提取
            q_bank_input = soup.find('input', {'name': 'qBankId'})
            if q_bank_input:
                q_bank_id = q_bank_input.get('value', '')
            
            # 方法2：从script中提取（如果没有从input找到）
            if not q_bank_id:
                scripts = soup.find_all('script')
                for script in scripts:
                    if script.string and 'qBankId' in script.string:
                        # 使用正则提取 qBankId
                        match = re.search(r'qBankId["\']?\s*[:=]\s*["\']?([^"\',;\s]+)', script.string)
                        if match:
                            q_bank_id = match.group(1)
                            break
            
            print(f"q_bank_id: {q_bank_id}")
            
            # 提取总数
            total = 0
            sum_span = soup.find('span', id='sumNum')
            if sum_span:
                text = sum_span.get_text()
                match = re.search(r'共\s*(\d+)\s*题', text)
                if match:
                    total = int(match.group(1))
            
            # 解析题目列表
            questions = []
            folders = []
            
            # 查找所有列表项（包括题目和文件夹）
            list_items = soup.find_all('li', class_='list')
            
            print(f"找到 {len(list_items)} 个列表项")
            
            for item in list_items:
                try:
                    data_type = item.get('data-type', '')
                    
                    if data_type == 'folder':
                        # 解析文件夹
                        folder = self._parse_folder_item(item)
                        if folder:
                            folders.append(folder)
                            print(f"文件夹: {folder['name']}")
                    elif 'questions' in item.get('class', []):
                        # 解析题目
                        question = self._parse_question_item(item)
                        if question:
                            questions.append(question)
                except Exception as e:
                    print(f"解析列表项失败: {e}")
                    continue
            
            print(f"解析结果: {len(folders)} 个文件夹, {len(questions)} 道题目")
            
            return {
                "questions": questions,
                "folders": folders,
                "total": total,
                "q_bank_id": q_bank_id
            }
            
        except Exception as e:
            print(f"搜索题目失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "questions": [],
                "total": 0,
                "error": str(e)
            }
    
    def _parse_folder_item(self, item) -> dict:
        """解析文件夹HTML元素"""
        # 文件夹ID
        folder_id = item.get('id', '')
        
        # 文件夹名称
        folder_name = ""
        dirname_span = item.find('span', class_='dirname')
        if dirname_span:
            folder_name = dirname_span.get_text(strip=True)
        
        # 题目数量
        question_num = 0
        num_span = item.find('span', class_='question-num')
        if num_span:
            text = num_span.get_text()
            match = re.search(r'共\s*(\d+)\s*题', text)
            if match:
                question_num = int(match.group(1))
        
        # 创建者
        author = ""
        author_span = item.find('span', class_='auth-name')
        if author_span:
            author = author_span.get_text(strip=True)
        
        # 创建时间
        create_time = ""
        time_span = item.find('span', class_='time')
        if time_span:
            create_time = time_span.get_text(strip=True)
        
        # 课程ID
        course_id = item.get('courseid', '')
        
        return {
            "id": folder_id,
            "name": folder_name,
            "question_count": question_num,
            "author": author,
            "create_time": create_time,
            "course_id": course_id,
            "type": "folder"
        }
    
    def _parse_question_item(self, item) -> Question:
        """解析单个题目HTML元素"""
        # 题目ID
        question_id = item.get('id', '')
        
        # 提取创建作业所需的字段
        course_id = item.get('courseid', '')
        origin_type = item.get('origintype', '')
        course_question_type_id = item.get('coursequestionyypeid', '')
        
        # 题干
        content = ""
        name_span = item.find('span', class_='choose-name')
        if name_span:
            content = name_span.get('title', '') or name_span.get_text(strip=True)
        
        # 题型
        question_type = ""
        type_span = item.find('span', class_='choose')
        if type_span:
            question_type = type_span.get('title', '') or type_span.get_text(strip=True)
        
        # 难度
        difficulty = ""
        hard_span = item.find('span', class_='hard')
        if hard_span:
            difficulty = hard_span.get_text(strip=True)
        
        # 使用量
        usage_count = 0
        dose_span = item.find('span', class_='dose')
        if dose_span:
            try:
                usage_count = int(dose_span.get_text(strip=True))
            except:
                usage_count = 0
        
        # 正确率
        accuracy = None
        accuracy_span = item.find('span', class_='accuracy')
        if accuracy_span:
            accuracy_str = accuracy_span.get_text(strip=True)
            accuracy = Question.parse_accuracy(accuracy_str)
        
        # 创建者
        author = ""
        author_span = item.find('span', class_='auth-name')
        if author_span:
            author = author_span.get_text(strip=True)
        
        # 创建时间
        create_time = ""
        time_span = item.find('span', class_='time')
        if time_span:
            create_time = time_span.get_text(strip=True)
        
        # 详细信息（选项、答案、知识点）
        options = []
        answer = ""
        topics = []
        
        details_div = item.find('div', class_='questions-details')
        if details_div:
            # 选项
            option_ul = details_div.find('ul', class_='option')
            if option_ul:
                for li in option_ul.find_all('li'):
                    option_text = li.get_text(strip=True)
                    if option_text:
                        options.append(option_text)
            
            # 答案
            answer_div = details_div.find('div', class_='question-box')
            if answer_div:
                answer = answer_div.get_text(strip=True)
            
            # 知识点
            topic_div = details_div.find('div', class_='topic-list')
            if topic_div:
                topic_items = topic_div.find_all('span', class_='item')
                for topic_item in topic_items:
                    topic_name = topic_item.get_text(strip=True)
                    if topic_name:
                        topics.append(topic_name)
        
        return Question(
            id=question_id,
            content=content,
            question_type=question_type,
            difficulty=difficulty,
            usage_count=usage_count,
            accuracy=accuracy,
            author=author,
            create_time=create_time,
            options=options if options else None,
            answer=answer,
            topics=topics if topics else None,
            course_id=course_id,
            origin_type=origin_type,
            course_question_type_id=course_question_type_id
        )
    
    def create_homework(
        self,
        course_id: str,
        class_id: str,
        title: str,
        questions: List[Dict[str, str]],
        q_bank_id: str = "",
        directory_id: int = 0
    ) -> Dict:
        """
        创建作业。
        
        Args:
            course_id: 课程 ID
            class_id: 班级 ID
            title: 作业标题
            questions: 题目列表 [{"id": "xxx", "courseId": "xxx", "type": "x", "courseQuestionTypeId": "x"}, ...]
            q_bank_id: 题库ID（可选）
            directory_id: 目录ID（文件夹ID，0表示根目录）
        
        Returns:
            {
                "status": True/False,
                "workid": "xxx",  # 作业ID
                "msg": "xxx"
            }
        """
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/work/completeChooseQues"
        
        # 构建题目参数
        question_params = []
        for q in questions:
            question_params.append({
                "qBankId": q.get("id"),  # 题目ID
                "courseId": q.get("course_id"),
                "type": q.get("origin_type"),
                "courseQuestionTypeId": q.get("course_question_type_id")
            })
        
        # 调试输出
        print(f"\n=== 创建作业参数 ===")
        print(f"course_id: {course_id}")
        print(f"class_id: {class_id}")
        print(f"questions count: {len(question_params)}")
        print(f"questions: {json.dumps(question_params, ensure_ascii=False, indent=2)}")
        
        form_data = {
            "courseid": course_id,
            "clazzid": class_id,
            "cpi": self.session_manager.course_params.get("cpi", ""),
            "workid": "",
            "questions": json.dumps(question_params, ensure_ascii=False),  # 参数名是 questions，不是 ques
            "title": title,
            "grading": 0,
            "directoryid": directory_id,  # 使用传入的文件夹ID
            "questionGroup": 0,
            "workLibraryType": 0,
            "evaluationQuesNum": 0
        }
        
        print(f"\n=== 表单数据 ===")
        for key, value in form_data.items():
            if key == "questions":
                print(f"{key}: {value[:200]}...")  # 只显示前200个字符
            else:
                print(f"{key}: {value}")
        
        headers = {
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Cache-Control': 'no-cache',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Pragma': 'no-cache',
            'Referer': f'https://mooc2-gray.chaoxing.com/mooc2-ans/work/qtbank?built=1&courseid={course_id}&clazzid={class_id}',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest',
            'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
        }
        
        try:
            response = self.session.post(url, data=form_data, headers=headers, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            print(f"\n=== 创建作业结果 ===")
            print(f"status: {data.get('status')}")
            print(f"workid: {data.get('workid')}")
            print(f"msg: {data.get('msg')}")
            
            return data
            
        except Exception as e:
            print(f"创建作业失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": False,
                "msg": str(e)
            }
    
    def save_work(
        self,
        course_id: str,
        class_id: str,
        work_id: str,
        title: str,
        work_status: int = 0,
        grading: int = 0,
        directory_id: int = 0,
        question_group: int = 0
    ) -> Dict:
        """
        保存作业。
        
        Args:
            course_id: 课程 ID
            class_id: 班级 ID
            work_id: 作业 ID
            title: 作业标题
            work_status: 作业状态（0=草稿）
            grading: 评分方式（0=默认）
            directory_id: 目录ID（0=根目录）
            question_group: 题目组（0=默认）
        
        Returns:
            {
                "status": True/False,
                "msg": "xxx"
            }
        """
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/work/save-work"
        
        params = {
            "courseid": course_id,
            "clazzid": class_id,
            "cpi": self.session_manager.course_params.get("cpi", ""),
            "workid": work_id,
            "title": title,
            "grading": grading,
            "directoryid": directory_id,
            "workStatus": work_status,
            "questionGroup": question_group
        }
        
        headers = {
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Pragma': 'no-cache',
            'Referer': f'https://mooc2-gray.chaoxing.com/mooc2-ans/work/qtbank?built=1&courseid={course_id}&clazzid={class_id}',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest',
            'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
        }
        
        try:
            response = self.session.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            print(f"\n=== 保存作业结果 ===")
            print(f"status: {data.get('status')}")
            print(f"msg: {data.get('msg')}")
            
            return data
            
        except Exception as e:
            print(f"保存作业失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": False,
                "msg": str(e)
            }
    
    def get_homework_library(self, course_id: str, class_id: str, directory_id: int = 0) -> Dict:
        """
        获取作业库列表。
        
        Args:
            course_id: 课程 ID
            class_id: 班级 ID
            directory_id: 文件夹ID（0表示根目录）
        
        Returns:
            {
                "folders": [{"id": "xxx", "name": "xxx", "count": 5, "author": "xxx", "time": "xxx"}, ...],
                "works": [{"id": "xxx", "title": "xxx", "question_num": 2, "score": 100, "author": "xxx", "time": "xxx"}, ...],
                "error": None 或错误信息
            }
        """
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/work/library"
        
        params = {
            "courseid": course_id,
            "directoryid": directory_id,
            "cpi": self.session_manager.course_params.get("cpi", ""),
            "from": "",
            "topicid": 0,
            "backurl": ""
        }
        
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5',
            'Connection': 'keep-alive',
            'Referer': f'https://mooc2-gray.chaoxing.com/mooc2-ans/work/list?courseid={course_id}&clazzid={class_id}',
            'Sec-Fetch-Dest': 'iframe',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
        }
        
        try:
            response = self.session.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            
            html_content = response.text
            
            # 解析HTML
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            folders = []
            works = []
            
            # 查找所有数据项
            data_list = soup.find_all('ul', class_='dataBody_td')
            
            for item in data_list:
                item_type = item.get('type', '0')  # type="0" 是文件夹, type="1" 是作业
                item_id = item.get('data', '')
                
                if item_type == '0':
                    # 文件夹
                    name_elem = item.find('a', class_='rename_title')
                    count_elem = item.find('span', class_='work_count')
                    
                    name = name_elem.get('title', '') if name_elem else ''
                    count_text = count_elem.text if count_elem else ''
                    count = int(re.search(r'共\s*(\d+)\s*份', count_text).group(1)) if count_text and re.search(r'共\s*(\d+)\s*份', count_text) else 0
                    
                    # 获取作者和时间
                    author_elem = item.find('li', class_='dataBody_read')
                    time_elem = item.find('li', class_='dataBody_time')
                    
                    author = author_elem.text.strip() if author_elem else ''
                    time_text = time_elem.contents[0].strip() if time_elem and time_elem.contents else ''
                    
                    folders.append({
                        'id': item_id,
                        'name': name,
                        'count': count,
                        'author': author,
                        'time': time_text
                    })
                    
                elif item_type == '1':
                    # 作业
                    name_elem = item.find('li', class_='dataBody_name').find('a')
                    
                    title = name_elem.get('title', '') if name_elem else ''
                    
                    # 获取题量和分值
                    question_num_elem = item.find('li', class_='dataHead_questionNum')
                    score_elem = item.find('li', class_='dataHead_score')
                    
                    question_num = int(question_num_elem.text.strip()) if question_num_elem else 0
                    score = int(score_elem.text.strip()) if score_elem else 0
                    
                    # 获取作者和时间
                    author_elem = item.find('li', class_='dataBody_read')
                    time_elem = item.find('li', class_='dataBody_time')
                    
                    author = author_elem.text.strip() if author_elem else ''
                    time_text = time_elem.contents[0].strip() if time_elem and time_elem.contents else ''
                    
                    works.append({
                        'id': item_id,
                        'title': title,
                        'question_num': question_num,
                        'score': score,
                        'author': author,
                        'time': time_text
                    })
            
            return {
                'folders': folders,
                'works': works,
                'error': None
            }
            
        except Exception as e:
            print(f"获取作业库失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'folders': [],
                'works': [],
                'error': str(e)
            }
    
    def get_folder_list(self, course_id: str, parent_id: int = 0) -> List[Dict]:
        """
        获取文件夹列表。
        
        Args:
            course_id: 课程 ID
            parent_id: 父文件夹ID，0表示根目录
        
        Returns:
            文件夹列表 [{"id": xxx, "name": "xxx", "children": false}, ...]
        """
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/work/library/getfolderlist"
        
        params = {
            "pid": parent_id,
            "courseid": course_id,
            "cpi": self.session_manager.course_params.get("cpi", "")
        }
        
        headers = {
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Connection': 'keep-alive',
            'Referer': f'https://mooc2-gray.chaoxing.com/mooc2-ans/work/library?courseid={course_id}',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest',
        }
        
        try:
            response = self.session.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            print(f"\n=== 获取文件夹列表 ===")
            print(f"父文件夹ID: {parent_id}")
            print(f"文件夹数量: {len(data)}")
            
            return data
            
        except Exception as e:
            print(f"获取文件夹列表失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def move_work_to_folder(self, work_id: str, folder_id: int, course_id: str, class_id: str) -> Dict:
        """
        移动作业到文件夹。
        
        Args:
            work_id: 作业ID
            folder_id: 目标文件夹ID（0表示根目录）
            course_id: 课程ID
            class_id: 班级ID（参数未使用，保留用于兼容）
        
        Returns:
            {"status": True/False, "msg": "xxx"}
        """
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/work/library/move"
        
        params = {
            "courseid": course_id,
            "cpi": self.session_manager.course_params.get("cpi", ""),
            "pid": folder_id,  # 目标文件夹ID
            "type": 1,  # 类型：1=作业
            "id": work_id  # 要移动的作业ID
        }
        
        headers = {
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Pragma': 'no-cache',
            'Referer': f'https://mooc2-gray.chaoxing.com/mooc2-ans/work/library?courseid={course_id}',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest',
        }
        
        try:
            response = self.session.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            print(f"\n=== 移动作业结果 ===")
            print(f"作业ID: {work_id}")
            print(f"目标文件夹ID: {folder_id}")
            print(f"结果: {data}")
            
            return data
            
        except Exception as e:
            print(f"移动作业失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": False,
                "msg": str(e)
            }
    
    def copy_work(self, work_id: str, directory_id: int, course_id: str) -> Dict:
        """
        复制作业。
        
        Args:
            work_id: 作业ID
            directory_id: 目标文件夹ID（当前文件夹，复制到同一目录）
            course_id: 课程ID
        
        Returns:
            {"status": True/False, "msg": "xxx"}
        """
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/work/library/copy"
        
        params = {
            "courseid": course_id,
            "directoryid": directory_id,
            "workid": work_id,
            "cpi": self.session_manager.course_params.get("cpi", "")
        }
        
        headers = {
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Pragma': 'no-cache',
            'Referer': f'https://mooc2-gray.chaoxing.com/mooc2-ans/work/library?courseid={course_id}&directoryid={directory_id}',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest',
        }
        
        try:
            response = self.session.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            print(f"\n=== 复制作业结果 ===")
            print(f"作业ID: {work_id}")
            print(f"目标文件夹ID: {directory_id}")
            print(f"结果: {data}")
            
            return data
            
        except Exception as e:
            print(f"复制作业失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": False,
                "msg": str(e)
            }
    
    def delete_work(self, work_id: str, course_id: str) -> Dict:
        """
        删除作业（移到回收站）。
        
        Args:
            work_id: 作业ID
            course_id: 课程ID
        
        Returns:
            {"status": True/False, "msg": "xxx"}
        """
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/work/library/work-update"
        
        params = {
            "courseid": course_id,
            "workid": work_id,
            "cpi": self.session_manager.course_params.get("cpi", ""),
            "status": 2  # 状态：2表示删除
        }
        
        headers = {
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Pragma': 'no-cache',
            'Referer': f'https://mooc2-gray.chaoxing.com/mooc2-ans/work/library?courseid={course_id}',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest',
        }
        
        try:
            response = self.session.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            print(f"\n=== 删除作业结果 ===")
            print(f"作业ID: {work_id}")
            print(f"结果: {data}")
            
            return data
            
        except Exception as e:
            print(f"删除作业失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": False,
                "msg": str(e)
            }
    
    def create_folder(self, folder_name: str, course_id: str, parent_id: int = 0) -> Dict:
        """
        创建文件夹。

        Args:
            folder_name: 文件夹名称
            course_id: 课程ID
            parent_id: 父文件夹ID（0表示根目录）

        Returns:
            {"status": True/False, "msg": "xxx", "id": 文件夹ID}
        """
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/work/library/addfolder"

        params = {
            "courseid": course_id,
            "directoryid": parent_id,
            "title": folder_name,
            "cpi": self.session_manager.course_params.get("cpi", "")
        }

        headers = {
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Pragma': 'no-cache',
            'Referer': f'https://mooc2-gray.chaoxing.com/mooc2-ans/work/library?courseid={course_id}',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest',
        }

        try:
            response = self.session.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()

            data = response.json()

            print(f"\n=== 创建文件夹结果 ===")
            print(f"文件夹名称: {folder_name}")
            print(f"父文件夹ID: {parent_id}")
            print(f"结果: {data}")

            return data

        except Exception as e:
            print(f"创建文件夹失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": False,
                "msg": str(e)
            }

    def rename_folder(self, folder_id: str, new_name: str, course_id: str) -> Dict:
        """
        重命名文件夹。

        Args:
            folder_id: 文件夹ID
            new_name: 新名称
            course_id: 课程ID

        Returns:
            {"status": True/False, "msg": "xxx"}
        """
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/work/library/rename"

        params = {
            "courseid": course_id,
            "directoryid": folder_id,
            "title": new_name,
            "cpi": self.session_manager.course_params.get("cpi", "")
        }

        headers = {
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Pragma': 'no-cache',
            'Referer': f'https://mooc2-gray.chaoxing.com/mooc2-ans/work/library?courseid={course_id}',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest',
        }

        try:
            response = self.session.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()

            data = response.json()

            print(f"\n=== 重命名文件夹结果 ===")
            print(f"文件夹ID: {folder_id}")
            print(f"新名称: {new_name}")
            print(f"结果: {data}")

            return data

        except Exception as e:
            print(f"重命名文件夹失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": False,
                "msg": str(e)
            }

    def move_folder(self, folder_id: str, target_folder_id: int, course_id: str) -> Dict:
        """
        移动文件夹。

        Args:
            folder_id: 要移动的文件夹ID
            target_folder_id: 目标文件夹ID（0表示根目录）
            course_id: 课程ID

        Returns:
            {"status": True/False, "msg": "xxx"}
        """
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/work/library/move"

        params = {
            "courseid": course_id,
            "cpi": self.session_manager.course_params.get("cpi", ""),
            "pid": target_folder_id,
            "type": 0,  # 类型：0=文件夹
            "id": folder_id
        }

        headers = {
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Pragma': 'no-cache',
            'Referer': f'https://mooc2-gray.chaoxing.com/mooc2-ans/work/library?courseid={course_id}',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest',
        }

        try:
            response = self.session.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()

            data = response.json()

            print(f"\n=== 移动文件夹结果 ===")
            print(f"文件夹ID: {folder_id}")
            print(f"目标文件夹ID: {target_folder_id}")
            print(f"结果: {data}")

            return data

        except Exception as e:
            print(f"移动文件夹失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": False,
                "msg": str(e)
            }

    def delete_folder(self, folder_id: str, course_id: str) -> Dict:
        """
        删除文件夹。

        Args:
            folder_id: 文件夹ID
            course_id: 课程ID

        Returns:
            {"status": True/False, "msg": "xxx"}
        """
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/work/library/folder-update"

        params = {
            "courseid": course_id,
            "directoryid": folder_id,
            "cpi": self.session_manager.course_params.get("cpi", ""),
            "status": 2  # 状态：2表示删除
        }

        headers = {
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Pragma': 'no-cache',
            'Referer': f'https://mooc2-gray.chaoxing.com/mooc2-ans/work/library?courseid={course_id}',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest',
        }

        try:
            response = self.session.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()

            data = response.json()

            print(f"\n=== 删除文件夹结果 ===")
            print(f"文件夹ID: {folder_id}")
            print(f"结果: {data}")

            return data

        except Exception as e:
            print(f"删除文件夹失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": False,
                "msg": str(e)
            }

    def rename_work(self, work_id: str, new_title: str, course_id: str, class_id: str, directory_id: int = 0) -> Dict:
        """
        重命名作业（通过保存接口）。
        
        Args:
            work_id: 作业ID
            new_title: 新标题
            course_id: 课程ID
            class_id: 班级ID
            directory_id: 文件夹ID
        
        Returns:
            {"status": True/False, "msg": "xxx"}
        """
        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/work/save-work"
        
        params = {
            "courseid": course_id,
            "clazzid": class_id,
            "cpi": self.session_manager.course_params.get("cpi", ""),
            "workid": work_id,
            "title": new_title,
            "grading": 0,
            "directoryid": directory_id,
            "workStatus": 0,
            "questionGroup": 0
        }
        
        headers = {
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Pragma': 'no-cache',
            'Referer': f'https://mooc2-gray.chaoxing.com/mooc2-ans/work/library?courseid={course_id}',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest',
        }
        
        try:
            response = self.session.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            print(f"\n=== 重命名作业结果 ===")
            print(f"作业ID: {work_id}")
            print(f"新标题: {new_title}")
            print(f"结果: {data}")
            
            return data
            
        except Exception as e:
            print(f"重命名作业失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": False,
                "msg": str(e)
            }
