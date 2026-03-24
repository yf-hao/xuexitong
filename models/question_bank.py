"""
题库数据模型
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class QuestionFolder:
    """题库文件夹"""
    id: str                    # 文件夹 ID
    name: str                  # 文件夹名称
    count: int = 0             # 题目数量
    course_id: str = ""        # 课程 ID
    is_share: bool = False     # 是否公开
    creator_id: str = ""       # 创建者 ID
    user_id: str = ""          # 用户 ID
    parent_id: Optional[str] = None  # 父文件夹 ID
    children: List['QuestionFolder'] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "count": self.count,
            "course_id": self.course_id,
            "is_share": self.is_share,
            "creator_id": self.creator_id,
            "user_id": self.user_id,
            "parent_id": self.parent_id,
            "children": [c.to_dict() for c in self.children]
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'QuestionFolder':
        """从字典创建"""
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            count=data.get("count", 0),
            course_id=data.get("course_id", ""),
            is_share=data.get("is_share", False),
            creator_id=data.get("creator_id", ""),
            user_id=data.get("user_id", ""),
            parent_id=data.get("parent_id"),
            children=[cls.from_dict(c) for c in data.get("children", [])]
        )


@dataclass
class Question:
    """题目"""
    id: str                    # 题目 ID
    title: str                 # 题目标题/内容
    type: str = ""             # 题目类型：单选、多选、判断、填空等
    folder_id: str = ""        # 所属文件夹 ID
    options: List[dict] = field(default_factory=list)  # 选项列表
    answer: str = ""           # 正确答案
    analysis: str = ""         # 解析
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "title": self.title,
            "type": self.type,
            "folder_id": self.folder_id,
            "options": self.options,
            "answer": self.answer,
            "analysis": self.analysis
        }
