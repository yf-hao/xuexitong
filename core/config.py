import os
import sys

# Constants and default configurations for the application
APP_TITLE = "学习通教学资源管理系统V0.2.0"

# Default Institution ID (郑州西亚斯学院)
DEFAULT_FID = "4311"

def get_base_dir():
    """Get the base directory for the application.  """
    if getattr(sys, 'frozen', False):
        # If the application is run as a bundle (PyInstaller)
        # sys.executable points to the executable file
        return os.path.dirname(sys.executable)
    else:
        # Normal python environment
        # core/config.py -> core/ -> project_root/
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BASE_DIR = get_base_dir()
DATA_DIR = os.path.join(BASE_DIR, "data")

# Sign-in Data Storage
SIGNIN_DATA_FILE = os.path.join(DATA_DIR, "signin_plans.json")

# Statistics Types Configuration
# 统计类型配置：定义不同统计功能的参数和显示信息
STATS_TYPES = {
    "attendance": {
        "seltables": "12",           # API 参数：考勤数据的表格选择参数
        "name": "考勤",              # 显示名称
        "icon": "📊",                # UI 图标
        "display_suffix": "签到表",  # 新记录的显示后缀（替换"统计一键导出"）
        "button_label": "📊 考勤"     # 按钮文字
    },
    "quiz": {
        "seltables": "8",            # API 参数：测验数据的表格选择参数
        "name": "测验",              # 显示名称
        "icon": "📝",                # UI 图标
        "display_suffix": "测验成绩表",  # 新记录的显示后缀
        "button_label": "📝 测验"     # 按钮文字
    },
    "homework": {
        "seltables": "7",            # API 参数：作业数据的表格选择参数（示例，需验证）
        "name": "作业",              # 显示名称
        "icon": "✍️",                # UI 图标
        "display_suffix": "作业成绩表",  # 新记录的显示后缀
        "button_label": "✍️ 作业"     # 按钮文字
    },
    "final_score": {
        "seltables": "13",            # API 参数：综合成绩数据的表格选择参数
        "name": "综合成绩",           # 显示名称
        "icon": "🎓",                # UI 图标
        "display_suffix": "综合成绩表",  # 新记录的显示后缀
        "button_label": "🎓 综合成绩"  # 按钮文字
    },
    # 未来可以轻松添加更多统计类型，例如：
    # "discussion": {
    #     "seltables": "XX",
    #     "name": "讨论",
    #     "icon": "💬",
    #     "display_suffix": "讨论统计表",
    #     "button_label": "💬 讨论"
    # },
}
