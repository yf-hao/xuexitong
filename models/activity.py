"""活动数据模型。"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Activity:
    """活动数据模型（签到、投票、通知等）。"""
    
    active_id: str
    title: str
    activity_type: int
    type_name: str
    create_time: str
    start_time: Optional[str]
    end_time: Optional[str]
    status: str
    status_name: str
    class_id: int
    group_name: str
    
    # 活动类型映射
    TYPE_MAPPING = {
        2: "签到",
        4: "投票",
        45: "通知",
    }
    
    # 状态映射
    STATUS_MAPPING = {
        "0": "未开始",
        "1": "进行中",
        "2": "已结束",
    }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Activity':
        """从 API 返回的字典创建 Activity 对象。"""
        activity_type = data.get("activeType", 0)
        status = data.get("status", "0")
        
        return cls(
            active_id=str(data.get("activeId", "")),
            title=data.get("title", "未知"),
            activity_type=activity_type,
            type_name=cls.TYPE_MAPPING.get(activity_type, f"类型{activity_type}"),
            create_time=data.get("createTime", ""),
            start_time=data.get("startTime"),
            end_time=data.get("endTime"),
            status=status,
            status_name=cls.STATUS_MAPPING.get(status, f"状态{status}"),
            class_id=data.get("classId", 0),
            group_name=data.get("groupName", ""),
        )
    
    @property
    def time_range(self) -> str:
        """获取活动时间范围描述。"""
        if self.start_time and self.end_time:
            return f"{self.start_time} ~ {self.end_time}"
        elif self.start_time:
            return f"{self.start_time} ~"
        else:
            return "未设置"
    
    @property
    def is_active(self) -> bool:
        """活动是否正在进行。"""
        return self.status == "1"
    
    @property
    def is_ended(self) -> bool:
        """活动是否已结束。"""
        return self.status == "2"
    
    @property
    def is_pending(self) -> bool:
        """活动是否未开始。"""
        return self.status == "0"
    
    def __str__(self) -> str:
        return f"Activity({self.title}, {self.type_name}, {self.status_name})"


@dataclass
class ActivityList:
    """活动列表数据模型。"""
    
    activities: list[Activity]
    archived: int
    group_list: list[dict]
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ActivityList':
        """从 API 返回的字典创建 ActivityList 对象。"""
        active_list = data.get("activeList", [])
        activities = [Activity.from_dict(item) for item in active_list]
        
        return cls(
            activities=activities,
            archived=data.get("archived", 0),
            group_list=data.get("groupList", []),
        )
    
    def filter_by_type(self, activity_type: int) -> list[Activity]:
        """按类型筛选活动。"""
        return [a for a in self.activities if a.activity_type == activity_type]
    
    def filter_by_status(self, status: str) -> list[Activity]:
        """按状态筛选活动。"""
        return [a for a in self.activities if a.status == status]
    
    def get_active_activities(self) -> list[Activity]:
        """获取正在进行的活动。"""
        return self.filter_by_status("1")
    
    def get_ended_activities(self) -> list[Activity]:
        """获取已结束的活动。"""
        return self.filter_by_status("2")
    
    def get_pending_activities(self) -> list[Activity]:
        """获取未开始的活动。"""
        return self.filter_by_status("0")
    
    def __len__(self) -> int:
        return len(self.activities)
    
    def __iter__(self):
        return iter(self.activities)
