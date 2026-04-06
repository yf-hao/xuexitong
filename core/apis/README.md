# API Mixins

`core/apis/` 目录按业务域拆分 `XuexitongCrawler` 的能力。

- `auth_api.py`: 登录与退出登录
- `captcha_api.py`: 滑块验证码辅助能力
- `course_api.py`: 课程列表、课程详情、课程创建与课程基础修改
- `class_api.py`: 班级与学生相关接口
- `stats_api.py`: 统计报表与成绩权重
- `group_api.py`: 分组与签到
- `teacher_api.py`: 教学团队
- `course_manage_api.py`: 课程创建页、课程设置、封面与分类
- `question_bank_api.py`: 题库目录与题目
- `material_api.py`: 课程资料

`core/crawler.py` 仅负责聚合这些 mixin，并维护共享 `session_manager`、`session`、`_details_cache` 等基础状态。
