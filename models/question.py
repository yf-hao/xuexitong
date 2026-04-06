"""题目数据模型。"""
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Question:
    """题目数据模型"""
    id: str  # 题目ID
    content: str  # 题干内容
    question_type: str  # 题型（单选题、多选题等）
    difficulty: str  # 难度（如 "0.5 (中)"）
    usage_count: int  # 使用量
    accuracy: Optional[float]  # 正确率（百分比），None表示暂无数据
    author: str  # 创建者
    create_time: str  # 创建时间
    
    # 详细信息
    options: Optional[List[str]] = None  # 选项列表
    answer: Optional[str] = None  # 答案
    topics: Optional[List[str]] = None  # 知识点列表
    
    # 创建作业所需的字段
    course_id: Optional[str] = None  # 课程ID
    origin_type: Optional[str] = None  # 题目类型（原始值）
    course_question_type_id: Optional[str] = None  # 课程题目类型ID
    
    @staticmethod
    def parse_accuracy(accuracy_str: str) -> Optional[float]:
        """解析正确率字符串"""
        if not accuracy_str or accuracy_str.strip() == "-":
            return None
        
        # 提取数字（如 "94.92%" -> 94.92）
        import re
        match = re.search(r'(\d+\.?\d*)', accuracy_str)
        if match:
            return float(match.group(1))
        return None
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "content": self.content,
            "question_type": self.question_type,
            "difficulty": self.difficulty,
            "usage_count": self.usage_count,
            "accuracy": self.accuracy,
            "author": self.author,
            "create_time": self.create_time,
            "options": self.options,
            "answer": self.answer,
            "topics": self.topics,
            "course_id": self.course_id,
            "origin_type": self.origin_type,
            "course_question_type_id": self.course_question_type_id
        }
