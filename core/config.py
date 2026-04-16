import os
import sys

# Constants and default configurations for the application
APP_TITLE = "学习通教学资源管理系统V0.5.4"

# Default Institution ID (郑州西亚斯学院)
DEFAULT_FID = "4311"

def get_base_dir():
    """获取应用资源根目录，兼容源码运行和 PyInstaller 打包运行。"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 会把打包资源解压/映射到 sys._MEIPASS
        # macOS .app 的 datas 也位于 Resources，而不是 sys.executable 所在目录
        meipass_dir = getattr(sys, '_MEIPASS', None)
        if meipass_dir:
            return meipass_dir

        # 兜底：若某些环境下 _MEIPASS 不可用，则回退到可执行文件目录
        return os.path.dirname(sys.executable)

    # Normal python environment
    # core/config.py -> core/ -> project_root/
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_user_data_dir():
    """获取用户数据存储目录，确保在不同操作系统下都有写入权限。"""
    if sys.platform == "darwin":
        path = os.path.expanduser("~/Library/Application Support/XuexitongManager")
    elif sys.platform == "win32":
        path = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "XuexitongManager")
    else:
        path = os.path.expanduser("~/.xuexitongmanager")
    
    # 确保目录存在
    os.makedirs(path, exist_ok=True)
    return path

BASE_DIR = get_base_dir()
DATA_DIR = get_user_data_dir()

# Sign-in Data Storage
SIGNIN_DATA_FILE = os.path.join(DATA_DIR, "signin_plans.json")

# Location Data Storage (签到位置配置)
LOCATION_DATA_FILE = os.path.join(DATA_DIR, "locations.json")

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

# Default Common Locations (默认常用位置配置)
# 这些位置会作为程序内置配置，用户也可以在界面中添加更多位置
DEFAULT_COMMON_LOCATIONS = [
    {
        "name": "郑州西亚斯学院-T01教学楼",
        "latitude": 34.403483,
        "longitude": 113.771373,
        "range": 500
    },
    {
        "name": "郑州西亚斯学院-T02教学楼",
        "latitude": 34.403497,
        "longitude": 113.771681,
        "range": 500
    },
    {
        "name": "郑州西亚斯学院-T03教学楼",
        "latitude": 34.401414,
        "longitude": 113.764800,
        "range": 500
    },
    {
        "name": "郑州西亚斯学院-T04教学楼",
        "latitude": 34.39779261763526,
        "longitude": 113.76521853862394,
        "range": 500
    },
    {
        "name": "郑州西亚斯学院-T05教学楼",
        "latitude": 34.404101,
        "longitude": 113.771356,
        "range": 500
    },
    {
        "name": "郑州西亚斯学院-T06教学楼",
        "latitude": 34.403461,
        "longitude": 113.770053,
        "range": 500
    },
    {
        "name": "郑州西亚斯学院-T07教学楼",
        "latitude": 34.40774,
        "longitude": 113.771182,
        "range": 500
    },
    {
        "name": "郑州西亚斯学院-T08教学楼",
        "latitude": 34.403673,
        "longitude": 113.76923,
        "range": 500
    },
    {
        "name": "郑州西亚斯学院-T09教学楼",
        "latitude": 34.403971,
        "longitude": 113.769598,
        "range": 500
    },
    {
        "name": "郑州西亚斯学院-T10教学楼",
        "latitude": 34.404104,
        "longitude": 113.770049,
        "range": 500
    },
    {
        "name": "郑州西亚斯学院-T11实验楼",
        "latitude": 34.404788,
        "longitude": 113.769583,
        "range": 500
    },
    {
        "name": "郑州西亚斯学院-T12实验教学中心",
        "latitude": 34.40497256595256,
        "longitude": 113.7715114233066,
        "range": 500
    },
    {
        "name": "郑州西亚斯学院-T13舞蹈教学楼",
        "latitude": 34.40455090951008,
        "longitude": 113.773852321233,
        "range": 500
    },
    {
        "name": "郑州西亚斯学院-T14教学楼",
        "latitude": 34.40335085404206,
        "longitude": 113.77443998901946,
        "range": 500
    },
    {
        "name": "郑州西亚斯学院-T15教学楼",
        "latitude": 34.40278778283764,
        "longitude": 113.77433979593062,
        "range": 500
    },
    {
        "name": "郑州西亚斯学院-T16中专教学楼",
        "latitude": 34.40256608795546,
        "longitude": 113.76982566835356,
        "range": 500
    },
    {
        "name": "郑州西亚斯学院-T17教学楼",
        "latitude": 34.404105402618065,
        "longitude": 113.76734736154526,
        "range": 500
    },
    {
        "name": "郑州西亚斯学院-T18教学楼",
        "latitude": 34.404618128896175,
        "longitude": 113.76698878100044,
        "range": 500
    },
    {
        "name": "郑州西亚斯学院-T19教学楼",
        "latitude": 34.40920181266354,
        "longitude": 113.76874046188557,
        "range": 500
    },
    {
        "name": "郑州西亚斯学院-T20教学楼",
        "latitude": 34.40925196237068,
        "longitude": 113.77264492395676,
        "range": 500
    },
    {
        "name": "郑州西亚斯学院-S02图书馆",
        "latitude": 34.407801,
        "longitude": 113.770445,
        "range": 500
    },
    {
        "name": "郑州西亚斯学院-P03综合体育馆",
        "latitude": 34.40572698,
        "longitude": 113.77225730,
        "range": 500
    }
]

# Default Location Template (默认位置模板配置)
DEFAULT_LOCATION_TEMPLATE = {
    "enabled": False,
    "mode": "weekly",
    "weeklySlotCount": 2,
    "oddSlotCount": 2,
    "evenSlotCount": 2,
    "weeklySlots": [],
    "oddSlots": [],
    "evenSlots": []
}
