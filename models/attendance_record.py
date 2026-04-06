"""签到记录数据模型。"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class AttendanceRecord:
    """签到记录数据模型。"""
    
    record_id: str
    uid: int
    active_id: str
    name: str
    username: str
    status: int
    status_name: str
    submit_time: str
    create_time: str
    
    # 状态映射
    STATUS_MAPPING = {
        0: "未签",
        1: "已签",
        2: "代签",
        5: "缺勤",
        7: "病假",
        8: "事假",
        9: "迟到",
        10: "早退",
    }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'AttendanceRecord':
        """从 API 返回的字典创建 AttendanceRecord 对象。"""
        status = data.get("status", 0)
        
        return cls(
            record_id=str(data.get("id", "")),
            uid=data.get("uid", 0),
            active_id=str(data.get("activeId", "")) if data.get("activeId") else "",
            name=data.get("name", "未知"),
            username=data.get("username", ""),
            status=status,
            status_name=cls.STATUS_MAPPING.get(status, f"状态{status}"),
            submit_time=data.get("submittime", "") or "",
            create_time=data.get("updatetimeStr", "") or "",
        )
    
    @property
    def is_normal(self) -> bool:
        """是否已签（正常签到）。"""
        return self.status == 1
    
    @property
    def is_unsign(self) -> bool:
        """是否未签。"""
        return self.status == 0
    
    @property
    def is_proxy(self) -> bool:
        """是否代签。"""
        return self.status == 2
    
    @property
    def is_absent(self) -> bool:
        """是否缺勤。"""
        return self.status == 5
    
    @property
    def is_leave(self) -> bool:
        """是否请假（病假或事假）。"""
        return self.status in [7, 8]
    
    @property
    def is_sick_leave(self) -> bool:
        """是否病假。"""
        return self.status == 7
    
    @property
    def is_personal_leave(self) -> bool:
        """是否事假。"""
        return self.status == 8
    
    @property
    def is_late(self) -> bool:
        """是否迟到。"""
        return self.status == 9
    
    @property
    def is_early_leave(self) -> bool:
        """是否早退。"""
        return self.status == 10
    
    def __str__(self) -> str:
        return f"AttendanceRecord({self.name}, {self.username}, {self.status_name})"


@dataclass
class AttendanceDetail:
    """签到详情数据模型。"""
    
    records: list[AttendanceRecord]
    
    @classmethod
    def from_dict(cls, data: dict) -> 'AttendanceDetail':
        """从 API 返回的字典创建 AttendanceDetail 对象。"""
        yiqian_list = data.get("yiqianList", [])
        weiqian_list = data.get("weiqianList", [])
        
        # 合并已签和未签列表
        all_records = yiqian_list + weiqian_list
        records = [AttendanceRecord.from_dict(item) for item in all_records]
        
        return cls(records=records)
    
    def get_statistics(self) -> dict:
        """获取签到统计信息。"""
        total = len(self.records)
        normal = sum(1 for r in self.records if r.is_normal)
        unsign = sum(1 for r in self.records if r.is_unsign)
        proxy = sum(1 for r in self.records if r.is_proxy)
        late = sum(1 for r in self.records if r.is_late)
        early_leave = sum(1 for r in self.records if r.is_early_leave)
        absent = sum(1 for r in self.records if r.is_absent)
        sick_leave = sum(1 for r in self.records if r.is_sick_leave)
        personal_leave = sum(1 for r in self.records if r.is_personal_leave)
        
        return {
            "总人数": total,
            "已签": normal,
            "未签": unsign,
            "代签": proxy,
            "迟到": late,
            "早退": early_leave,
            "缺勤": absent,
            "病假": sick_leave,
            "事假": personal_leave,
        }
    
    def __len__(self) -> int:
        return len(self.records)
    
    def __iter__(self):
        return iter(self.records)
