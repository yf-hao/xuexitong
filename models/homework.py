"""作业数据模型。"""
from dataclasses import dataclass
from typing import Optional
import re


@dataclass
class Homework:
    """作业数据模型。"""
    
    homework_id: str
    title: str
    class_name: str
    time_range: str
    pending_count: int
    submitted_count: int
    unsubmitted_count: int
    course_id: str
    class_id: str
    
    @classmethod
    def from_json(cls, json_content: str) -> list['Homework']:
        """从 JSON 内容解析作业列表。"""
        import json
        homework_list = []
        
        try:
            data = json.loads(json_content)
            
            # 打印数据结构以调试
            print(f"JSON 数据类型: {type(data)}")
            if isinstance(data, dict):
                print(f"JSON 键: {list(data.keys())}")
                if 'data' in data:
                    print(f"data 字段内容: {data['data']}")
            
            # TODO: 根据 JSON 结构解析数据
            # 暂时返回空列表，等看到实际 JSON 结构后再完善
            
        except json.JSONDecodeError as e:
            print(f"JSON 解析失败: {e}")
        
        return homework_list
    
    def __str__(self) -> str:
        return f"Homework({self.title}, 待批:{self.pending_count}, 已交:{self.submitted_count})"
