from datetime import datetime
from PyQt6.QtCore import QThread, pyqtSignal

class CourseWorker(QThread):
    """Worker thread to fetch initial course list."""
    courses_ready = pyqtSignal(list)

    def __init__(self, crawler):
        super().__init__()
        self.crawler = crawler

    def run(self):
        try:
            courses = self.crawler.get_courses()
            self.courses_ready.emit(courses)
        except Exception as e:
            self.courses_ready.emit([])

class StatsWorker(QThread):
    """Worker thread to fetch statistics reports (attendance, etc.)."""
    stats_ready = pyqtSignal(object) # Now returns a list of dicts or error string

    def __init__(self, crawler, report_type="attendance", click_time=None, trigger_export=True):
        super().__init__()
        self.crawler = crawler
        self.report_type = report_type
        self.click_time = click_time
        self.trigger_export = trigger_export

    def run(self):
        try:
            # 使用统一的 get_stats_reports 方法获取数据
            result = self.crawler.get_stats_reports(self.report_type, trigger_export=self.trigger_export)
            
            # 如果返回的是列表（成功获取），则处理 is_new 标记
            if isinstance(result, list) and self.click_time:
                now = datetime.now()
                click_ts = int(self.click_time.timestamp())
                # For minute-only precision, we compare against the start of the current minute
                click_minute_ts = int(self.click_time.replace(second=0, microsecond=0).timestamp())
                
                for item in result:
                    try:
                        item_ts_str = item['time']
                        item_time = None
                        is_precise = False
                        
                        # Try formats
                        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%m-%d %H:%M:%S", "%m-%d %H:%M"):
                            try:
                                item_time = datetime.strptime(item_ts_str, fmt)
                                # If year is missing (e.g., "01-06 10:06"), assume current year
                                if "%Y" not in fmt:
                                    item_time = item_time.replace(year=now.year)
                                
                                # Check if seconds are provided in the raw string
                                is_precise = (item_ts_str.count(':') >= 2)
                                break
                            except: 
                                continue

                        if item_time:
                            item_val = int(item_time.timestamp())
                            # Add a 60-second grace period for clock drift
                            grace_period = 60
                            
                            if is_precise:
                                item['is_new'] = item_val >= (click_ts - grace_period)
                            else:
                                item['is_new'] = item_val >= (click_minute_ts - grace_period)
                        else:
                            item['is_new'] = False
                    except Exception as e:
                        item['is_new'] = False
            
            self.stats_ready.emit(result)
        except Exception as e:
            self.stats_ready.emit(f"Error: {e}")

class DownloadWorker(QThread):
    """Worker thread to download files locally."""
    download_finished = pyqtSignal(bool, str) # success, message

    def __init__(self, crawler, url, save_path):
        super().__init__()
        self.crawler = crawler
        self.url = url
        self.save_path = save_path

    def run(self):
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/downloadcenter",
            }
            resp = self.crawler.session.get(self.url, headers=headers, stream=True, timeout=30)
            resp.raise_for_status()
            with open(self.save_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            self.download_finished.emit(True, f"文件已成功保存至:\n{self.save_path}")
        except Exception as e:
            self.download_finished.emit(False, f"下载失败: {e}")

class DetailsWorker(QThread):
    """Worker thread to fetch course details and navigation links."""
    details_ready = pyqtSignal(dict, object)  # details, course

    def __init__(self, crawler, course):
        super().__init__()
        self.crawler = crawler
        self.course = course

    def run(self):
        try:
            # Pass the href from the course object to ensure we visit the correct page
            details = self.crawler.get_course_details(self.course.id, url=self.course.href)
            self.details_ready.emit(details, self.course)
        except Exception as e:
            print(f"DetailsWorker error: {e}")
            self.details_ready.emit({}, self.course)

class ClassWorker(QThread):
    """Worker thread to fetch class list for a course."""
    classes_ready = pyqtSignal(list, object)  # class_list, course

    def __init__(self, crawler, course):
        super().__init__()
        self.crawler = crawler
        self.course = course

    def run(self):
        try:
            classes = self.crawler.get_class_list(self.course.id)
            self.classes_ready.emit(classes, self.course)
        except Exception as e:
            print(f"ClassWorker error: {e}")
            self.classes_ready.emit([], self.course)

class GetWeightWorker(QThread):
    """Background worker for fetching initial grade weights."""
    weights_ready = pyqtSignal(dict)

    def __init__(self, crawler):
        super().__init__()
        self.crawler = crawler

    def run(self):
        weights = self.crawler.get_grade_weights()
        self.weights_ready.emit(weights)


class WeightWorker(QThread):
    """Background worker for saving grade weights."""
    weight_saved = pyqtSignal(bool, str)

    def __init__(self, crawler, weights, class_ids=None):
        super().__init__()
        self.crawler = crawler
        self.weights = weights
        self.class_ids = class_ids

    def run(self):
        success, message = self.crawler.set_grade_weights(self.weights, self.class_ids)
        self.weight_saved.emit(success, message)


class MaterialWorker(QThread):
    """Worker thread to fetch materials without blocking the UI."""
    materials_ready = pyqtSignal(list, str)  # materials, course_name

    def __init__(self, crawler, course):
        super().__init__()
        self.crawler = crawler
        self.course = course

    def run(self):
        try:
            materials = self.crawler.get_materials(self.course.id)
            self.materials_ready.emit(materials, self.course.name)
        except Exception as e:
            print(f"MaterialWorker error: {e}")
            self.materials_ready.emit([], self.course.name)
            
class GroupWorker(QThread):
    """Worker thread to fetch group list asynchronously."""
    groups_ready = pyqtSignal(object) # list of groups or error string

    def __init__(self, crawler, course_id, class_id=None):
        super().__init__()
        self.crawler = crawler
        self.course_id = course_id
        self.class_id = class_id

    def run(self):
        try:
            result = self.crawler.get_groups(self.course_id, self.class_id)
            self.groups_ready.emit(result)
        except Exception as e:
            self.groups_ready.emit(f"Error: {e}")

class RenameWorker(QThread):
    """Worker thread to rename a group."""
    rename_finished = pyqtSignal(bool, str)

    def __init__(self, crawler, group_id, new_name):
        super().__init__()
        self.crawler = crawler
        self.group_id = group_id
        self.new_name = new_name

    def run(self):
        success, message = self.crawler.rename_group(self.group_id, self.new_name)
        self.rename_finished.emit(success, message)

class DeleteGroupWorker(QThread):
    """Worker thread to delete a group."""
    group_deleted = pyqtSignal(bool, str)

    def __init__(self, crawler, group_id):
        super().__init__()
        self.crawler = crawler
        self.group_id = group_id

    def run(self):
        success, message = self.crawler.delete_group(self.group_id)
        self.group_deleted.emit(success, message)

class AddGroupWorker(QThread):
    """Worker thread to create a new group."""
    group_added = pyqtSignal(bool, str)

    def __init__(self, crawler, course_id, class_id, name):
        super().__init__()
        self.crawler = crawler
        self.course_id = course_id
        self.class_id = class_id
        self.name = name

    def run(self):
        success, message = self.crawler.add_group(self.course_id, self.class_id, self.name)
        self.group_added.emit(success, message)


class CreateCourseWorker(QThread):
    """Worker thread to create a course."""
    course_created = pyqtSignal(bool, str)

    def __init__(self, crawler, payload):
        super().__init__()
        self.crawler = crawler
        self.payload = payload

    def run(self):
        success, message = self.crawler.create_course(**self.payload)
        self.course_created.emit(success, message)


class UpdateCourseDataWorker(QThread):
    """Worker thread to update course settings."""
    course_updated = pyqtSignal(bool, str)

    def __init__(self, crawler, payload):
        super().__init__()
        self.crawler = crawler
        self.payload = payload

    def run(self):
        # 1. 修改基本信息
        success_data, msg_data = self.crawler.update_course_data(
            course_id=str(self.payload.get("courseid")),
            cpi=str(self.payload.get("cpi")),
            course_name=self.payload.get("name"),
            teachers=self.payload.get("teacher"),
            group_id=str(self.payload.get("unit_id")),
            info_content=self.payload.get("description", ""),
            unit_fid=str(self.payload.get("unit_fid") or DEFAULT_FID),
            english_name=self.payload.get("english_name", "")  # 添加英文名称
        )
        
        # 2. 修改课程分类 (如果是单独接口)
        subject_id = str(self.payload.get("subject_id", ""))
        if success_data and subject_id:
            success_cat, msg_cat = self.crawler.update_course_classify(
                course_id=str(self.payload.get("courseid")),
                cpi=str(self.payload.get("cpi")),
                school_id=str(self.payload.get("unit_fid") or DEFAULT_FID),
                category_id=subject_id
            )
            if not success_cat:
                self.course_updated.emit(False, f"基本信息已更新，但分类更新失败: {msg_cat}")
                return
            
        self.course_updated.emit(success_data, msg_data)


class DeleteStatsWorker(QThread):
    """Worker thread to delete a stats report."""
    stats_deleted = pyqtSignal(bool, str)

    def __init__(self, crawler, report_id):
        super().__init__()
        self.crawler = crawler
        self.report_id = report_id

    def run(self):
        success, message = self.crawler.delete_stats_report(self.report_id)
        self.stats_deleted.emit(success, message)

class PublishSigninWorker(QThread):
    """Worker thread to publish a sign-in task."""
    signin_published = pyqtSignal(bool, str, str, object) # success, message, task_name, active_id

    def __init__(self, crawler, task_params):
        super().__init__()
        self.crawler = crawler
        self.params = task_params

    def run(self):
        # Extract task_name for the signal
        task_name = self.params.get('title', '未命名任务')
        
        # Call the crawler method with unpacked params
        # Note: 'title' is passed as a named arg in params, which crawler.publish_signin_task accepts via **kwargs or explicit args
        success, message, active_id = self.crawler.publish_signin_task(
            course_id=self.params.get('courseId'),
            class_id=self.params.get('classId'),
            plan_id=self.params.get('planId'),
            sign_code=self.params.get('signCode'),
            **self.params # Pass the rest as kwargs
        )
        self.signin_published.emit(success, message, task_name, active_id)

class DeleteSigninWorker(QThread):
    """Worker thread to delete a sign-in task."""
    signin_deleted = pyqtSignal(bool, str, str) # success, message, task_name

    def __init__(self, crawler, task_name, active_id=None):
        super().__init__()
        self.crawler = crawler
        self.task_name = task_name
        self.active_id = active_id

    def run(self):
        if self.active_id:
            success, message = self.crawler.delete_signin_task(self.active_id)
        else:
            # If no active_id (not published), it's just a local deletion which is always "successful" in terms of API
            success, message = True, "本地移除成功"
            
        print(f"DEBUG: DeleteSigninWorker emitting signin_deleted: {success}, {message}, {self.task_name}", flush=True)
        self.signin_deleted.emit(success, message, self.task_name)

class ClazzManageWorker(QThread):
    """Worker thread to fetch class management list."""
    classes_ready = pyqtSignal(list)

    def __init__(self, crawler, course_id, class_id):
        super().__init__()
        self.crawler = crawler
        self.course_id = course_id
        self.class_id = class_id

    def run(self):
        try:
            classes = self.crawler.get_clazz_manage_list(self.course_id, self.class_id)
            self.classes_ready.emit(classes)
        except Exception as e:
            print(f"ClazzManageWorker error: {e}")
            self.classes_ready.emit([])

class RenameClazzWorker(QThread):
    """Worker thread to rename a class."""
    rename_finished = pyqtSignal(bool, str)

    def __init__(self, crawler, clazz_id, new_name):
        super().__init__()
        self.crawler = crawler
        self.clazz_id = clazz_id
        self.new_name = new_name

    def run(self):
        success, message = self.crawler.rename_clazz(self.clazz_id, self.new_name)
        self.rename_finished.emit(success, message)

class DeleteClazzWorker(QThread):
    """Worker thread to delete a class."""
    delete_finished = pyqtSignal(bool, str)

    def __init__(self, crawler, clazz_id):
        super().__init__()
        self.crawler = crawler
        self.clazz_id = clazz_id

    def run(self):
        success, message = self.crawler.delete_clazz(self.clazz_id)
        self.delete_finished.emit(success, message)

class ParseStudentExcelWorker(QThread):
    """Worker thread to parse student Excel file."""
    parse_finished = pyqtSignal(bool, str, list)  # success, message, students_list

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            from core.excel_parser import parse_students_xls

            students = parse_students_xls(self.file_path)
            student_count = len(students)

            if student_count == 0:
                self.parse_finished.emit(False, "未找到有效学生数据，请检查Excel文件格式", [])
            else:
                message = f"成功解析出 {student_count} 名学生"
                self.parse_finished.emit(True, message, students)
        except Exception as e:
            self.parse_finished.emit(False, f"解析失败: {str(e)}", [])

class AddStudentsBatchWorker(QThread):
    """Worker thread to batch add students."""
    progress_updated = pyqtSignal(int, int, str)  # current, total, student_name
    batch_finished = pyqtSignal(int, int, list, bool, str)  # success_count, fail_count, failed_students, success, message

    def __init__(self, crawler, students, clazz_id, course_id=None):
        super().__init__()
        self.crawler = crawler
        self.students = students
        self.clazz_id = clazz_id
        self.course_id = course_id

    def run(self):
        def progress_callback(current, total, name):
            self.progress_updated.emit(current, total, name)

        success_count, fail_count, failed_students = self.crawler.add_students_batch(
            self.students, self.clazz_id, self.course_id, progress_callback
        )

        total_count = len(self.students)
        if fail_count == 0:
            message = f"成功添加 {success_count} 名学生到班级"
            success = True
        elif success_count == 0:
            message = f"添加失败，未能添加任何学生"
            success = False
        else:
            message = f"部分成功：成功添加 {success_count} 名学生，失败 {fail_count} 名"
            success = True


        self.batch_finished.emit(success_count, fail_count, failed_students, success, message)

class CourseStateWorker(QThread):
    """Worker thread to delete or archive a course."""
    finished = pyqtSignal(bool, str)

    def __init__(self, crawler, course_id, mode="delete"):
        super().__init__()
        self.crawler = crawler
        self.course_id = course_id
        self.mode = mode

    def run(self):
        if self.mode == "archive":
            success, message = self.crawler.archive_course(self.course_id)
        else:
            success, message = self.crawler.delete_course(self.course_id)
        self.finished.emit(success, message)
class FullCourseInfoWorker(QThread):
    """Worker thread to fetch all course-related data (creation data, settings, categories, etc.) at once."""
    finished = pyqtSignal(dict)

    def __init__(self, crawler, is_edit=False, initial_data=None):
        super().__init__()
        self.crawler = crawler
        self.is_edit = is_edit
        self.initial_data = initial_data or {}

    def run(self):
        try:
            result = {
                "success": True,
                "creation_data": {},
                "settings": {},
                "groups_data": {},
                "categories_data": {},
                "semesters_data": {},
                "initial_data": self.initial_data.copy()
            }
            
            # 1. 获取课程创建初始数据 (基础单位列表等)
            print("DEBUG: FullCourseInfoWorker fetching creation data...")
            result["creation_data"] = self.crawler.get_course_creation_data()
            
            course_id = self.initial_data.get("courseid") or self.initial_data.get("courseId")
            cpi = self.initial_data.get("cpi")
            
            # 补全 course_id 和 cpi (如果 initial_data 缺失)
            if not course_id or not cpi:
                params = self.crawler.session_manager.course_params or {}
                course_id = course_id or params.get("courseid") or params.get("courseId")
                cpi = cpi or params.get("cpi")
            
            # 2. 如果是编辑模式，获取服务器最新的详细设置 (名称、教师、单位名等)
            if self.is_edit and course_id and cpi:
                print(f"DEBUG: FullCourseInfoWorker fetching settings for {course_id}...")
                result["settings"] = self.crawler.get_course_setting(str(course_id), str(cpi))
                
                # 同步更新 initial_data (兼容现有 UI 逻辑)
                if result["settings"].get("success"):
                    s = result["settings"]
                    id_data = result["initial_data"]
                    if s.get("name"): id_data["name"] = s["name"]
                    if s.get("english_name"): id_data["english"] = s["english_name"]
                    if s.get("teacher"): id_data["teacher"] = s["teacher"]
                    if s.get("unit_name"): id_data["unit"] = s["unit_name"]
                    if s.get("dept_name"): id_data["dept"] = s["dept_name"]
                    if s.get("category"): id_data["category"] = s["category"]
                    if s.get("description"): id_data["desc"] = s["description"]
                    if s.get("default_cover"): id_data["cover_url"] = s["default_cover"]
                    if s.get("unit_id"): id_data["unit_id"] = s["unit_id"]
                    if s.get("dept_id"): id_data["dept_id"] = s["dept_id"]

            # 3. 预加载院系列表 (根据当前选中的单位)
            # 默认取 creation_data 里的第一个或 initial_data 里的 unit_id
            unit_fid = ""
            if self.is_edit:
                unit_fid = result["initial_data"].get("unit_id")
            
            if not unit_fid and result["creation_data"].get("units"):
                unit_fid = result["creation_data"]["units"][0].get("fid")
            
            if unit_fid:
                print(f"DEBUG: FullCourseInfoWorker fetching groups for fid={unit_fid}, cpi={cpi}...")
                target_course_id = str(course_id) if course_id else "0"
                result["groups_data"] = self.crawler.get_group_list(str(unit_fid), str(cpi), target_course_id)
            
            # 4. 获取课程分类 (调用 API)
            if course_id and unit_fid and cpi:
                print(f"DEBUG: FullCourseInfoWorker fetching categories for {course_id}...")
                result["categories_data"] = self.crawler.get_course_category_list(str(course_id), str(unit_fid), str(cpi))

            # 5. 获取学期列表
            if unit_fid:
                print(f"DEBUG: FullCourseInfoWorker fetching semesters for fid={unit_fid}...")
                target_course_id = str(course_id) if course_id else "0"
                result["semesters_data"] = self.crawler.get_semester_list(str(unit_fid), target_course_id)

            self.finished.emit(result)
        except Exception as e:
            print(f"FullCourseInfoWorker error: {e}")
            import traceback
            traceback.print_exc()
            self.finished.emit({"success": False, "error": str(e)})

class GetTeachersWorker(QThread):
    """Worker thread to fetch the list of teachers for a class."""
    teachers_ready = pyqtSignal(bool, str, list)  # success, message, teachers_list

    def __init__(self, crawler, course_id, clazz_id):
        super().__init__()
        self.crawler = crawler
        self.course_id = course_id
        self.clazz_id = clazz_id

    def run(self):
        try:
            teachers = self.crawler.get_teachers_for_clazz(self.course_id, self.clazz_id)
            # transform dict to list if needed, but get_teachers_for_clazz returns list
            if isinstance(teachers, list):
                self.teachers_ready.emit(True, "获取成功", teachers)
            else:
                self.teachers_ready.emit(False, "获取教师列表失败", [])
        except Exception as e:
            self.teachers_ready.emit(False, f"获取失败: {str(e)}", [])

class AddTeamTeacherWorker(QThread):
    """Worker thread to add teachers to the course team."""
    finished = pyqtSignal(bool, str)

    def __init__(self, crawler, course_id, teachers_data):
        super().__init__()
        self.crawler = crawler
        self.course_id = course_id
        self.teachers_data = teachers_data # List of dicts with personId and enc

    def run(self):
        try:
            success, message = self.crawler.add_team_teacher(self.course_id, self.teachers_data)
            self.finished.emit(success, message)
        except Exception as e:
            self.finished.emit(False, f"添加异常: {str(e)}")

class RemoveTeamTeacherWorker(QThread):
    """Worker thread to remove teachers from the course team."""
    finished = pyqtSignal(bool, str)

    def __init__(self, crawler, course_id, teacher_ids):
        super().__init__()
        self.crawler = crawler
        self.course_id = course_id
        self.teacher_ids = teacher_ids # List of personIds (strings)

    def run(self):
        try:
            success, message = self.crawler.remove_team_teacher(self.course_id, self.teacher_ids)
            self.finished.emit(success, message)
        except Exception as e:
            self.finished.emit(False, f"移除异常: {str(e)}")

class CloneVerifyWorker(QThread):
    """处理克隆前的校验流程（滑块、验证码请求）"""
    code_required = pyqtSignal(dict) # verify_data
    verification_done = pyqtSignal(bool, str, dict) # success, message, tokens
    
    def __init__(self, crawler, course_id, cpi, clazz_id=""):
        super().__init__()
        self.crawler = crawler
        self.course_id = course_id
        self.cpi = cpi
        self.clazz_id = clazz_id
        
    def run(self):
        try:
            # 1. 检查校验状态 (对标 need_verify)
            status = self.crawler.check_clone_verify_status(self.course_id, self.cpi)
            
            if not status.get("status"):
                 self.verification_done.emit(False, f"判断是否需要验证失败: {status.get('msg', '接口状态异常')}", {})
                 return
                 
            # 对标 Snippet 逻辑: if verify_info["verifycodeSucc"]: skip else: full flow
            if status.get("verifycodeSucc"):
                print("DEBUG: CloneVerifyWorker - already trusted, skipping verification")
                self.verification_done.emit(True, "无需校验", {
                    "copymapenc": status.get("copymapenc"),
                    "copymaptime": status.get("copymaptime")
                })
                return
                
            # 2. 需要滑块验证
            print("DEBUG: CloneVerifyWorker - verifycodeSucc is False, proceeding with full flow")
            captcha = self.crawler.get_clone_captcha(self.course_id)
            print(f"DEBUG: CloneVerifyWorker get_clone_captcha result: {captcha}")
            if not captcha.get("success"):
                self.verification_done.emit(False, "获取滑块验证码失败", {})
                return
                
            # 识别滑块
            print("DEBUG: CloneVerifyWorker downloading captcha images...")
            img_headers = {
                "Referer": "https://mooc2-gray.chaoxing.com/",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            }
            shade_bytes = self.crawler.session.get(captcha["shade_image"], headers=img_headers).content
            cutout_bytes = self.crawler.session.get(captcha["cutout_image"], headers=img_headers).content
            x_coord = self.crawler.detect_slider_displacement(shade_bytes, cutout_bytes)
            print(f"DEBUG: CloneVerifyWorker detected x_coord: {x_coord}")
            
            # 3. 提交滑块
            print(f"DEBUG: CloneVerifyWorker submitting slider captcha with token={captcha['token']}, x={x_coord}")
            validate = self.crawler.submit_clone_captcha(captcha["token"], captcha["iv"], x_coord)
            print(f"DEBUG: CloneVerifyWorker slider submission validate result: {validate}")
            if not validate:
                self.verification_done.emit(False, "滑块校验失败", {})
                return
                
            # 4. 请求验证码
            print(f"DEBUG: CloneVerifyWorker fetching verify code with validate={validate}")
            verify_data = self.crawler.fetch_clone_verify_code(self.course_id, self.cpi, validate, self.clazz_id)
            print(f"DEBUG: CloneVerifyWorker fetch_clone_verify_code result: {verify_data}")
            # 只有当明确返回 result 为 False 时才视为失败，有些接口可能直接返回 {"msg": "发送成功"} 且不包含 result 字段
            if verify_data.get("result") is False:
                 self.verification_done.emit(False, f"获取验证码失败: {verify_data.get('msg', '未知错误')}", {})
                 return
                 
            # 5. 通知 UI 需要输入验证码
            self.code_required.emit(verify_data)
            
        except Exception as e:
            self.verification_done.emit(False, f"校验过程异常: {str(e)}", {})

class CloneSubmitVerifyWorker(QThread):
    """提交验证码并获取最终 token"""
    submit_finished = pyqtSignal(bool, str, dict) # success, message, tokens
    
    def __init__(self, crawler, course_id, cpi, verify_code):
        super().__init__()
        self.crawler = crawler
        self.course_id = course_id
        self.cpi = cpi
        self.verify_code = verify_code
        
    def run(self):
        try:
            print(f"DEBUG: CloneSubmitVerifyWorker submitting code: {self.verify_code}")
            result = self.crawler.submit_clone_verify_code(self.verify_code, self.course_id, self.cpi)
            print(f"DEBUG: CloneSubmitVerifyWorker result: {result}")
            if result.get("success"):
                self.submit_finished.emit(True, "校验成功", result)
            else:
                self.submit_finished.emit(False, result.get("msg", "验证失败"), {})
        except Exception as e:
            self.submit_finished.emit(False, f"提交验证码异常: {str(e)}", {})

class CloneActionWorker(QThread):
    """执行最终的克隆操作"""
    finished = pyqtSignal(bool, str)
    
    def __init__(self, crawler, payload):
        super().__init__()
        self.crawler = crawler
        self.payload = payload
        
    def run(self):
        try:
            res = self.crawler.request_clone_course(self.payload)
            if res.get("status"):
                self.finished.emit(True, res.get("msg", "克隆成功"))
            else:
                self.finished.emit(False, res.get("msg", "克隆失败"))
        except Exception as e:
            self.finished.emit(False, f"克隆操作异常: {str(e)}")
