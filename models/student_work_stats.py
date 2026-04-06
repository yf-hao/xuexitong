"""学生作业统计数据模型。"""
from dataclasses import dataclass
from typing import List
import json


@dataclass
class StudentWorkStats:
    """学生作业统计数据模型。"""
    
    person_id: int
    user_name: str
    alias_name: str
    complete_num: int
    work_submitted: int
    work_marked: int
    avg_score: float
    min_score: float
    max_score: float
    
    @property
    def pending_count(self) -> int:
        """待批作业数（已提交但未批改）。"""
        return self.work_submitted - self.work_marked
    
    @property
    def unsubmitted_count(self) -> int:
        """未提交作业数。"""
        return self.complete_num - self.work_submitted
    
    @property
    def real_avg_score(self) -> float:
        """真实平均分（未交作业按0分计算）。"""
        if self.complete_num == 0:
            return 0.0
        # 真实平均分 = (已提交作业总分) / 总作业数
        # 已提交作业总分 = avg × work_submitted
        total_score = self.avg_score * self.work_submitted
        return total_score / self.complete_num
    
    @classmethod
    def from_json(cls, json_content: str) -> List['StudentWorkStats']:
        """从 JSON 内容解析学生作业统计。"""
        stats_list = []
        
        try:
            data = json.loads(json_content)
            
            if not isinstance(data, dict) or 'data' not in data:
                print(f"JSON 数据格式错误")
                return stats_list
            
            for item in data['data']:
                try:
                    stats = cls(
                        person_id=item.get('personId', 0),
                        user_name=item.get('userName', ''),
                        alias_name=item.get('aliasName', ''),
                        complete_num=item.get('completeNum', 0),
                        work_submitted=item.get('workSubmited', 0),
                        work_marked=item.get('workMarked', 0),
                        avg_score=float(item.get('avg', 0)),
                        min_score=float(item.get('min', 0)),
                        max_score=float(item.get('max', 0))
                    )
                    stats_list.append(stats)
                except Exception as e:
                    print(f"解析学生数据失败: {e}, item: {item}")
                    continue
            
            print(f"解析到 {len(stats_list)} 个学生作业统计")
            
        except json.JSONDecodeError as e:
            print(f"JSON 解析失败: {e}")
        
        return stats_list
    
    def __str__(self) -> str:
        return f"StudentWorkStats({self.user_name}, 提交:{self.work_submitted}/{self.complete_num}, 平均分:{self.avg_score})"
