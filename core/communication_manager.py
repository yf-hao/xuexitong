"""沟通状态管理器。"""
import json
import os
from pathlib import Path
from typing import Dict


from .config import DATA_DIR

class CommunicationManager:
    """管理学生沟通状态的持久化存储。"""
    
    def __init__(self, data_dir: str = None):
        """
        初始化沟通管理器。
        
        Args:
            data_dir: 数据存储目录（默认为配置中的 DATA_DIR）
        """
        if data_dir is None:
            data_dir = DATA_DIR
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.data_file = self.data_dir / "communication_status.json"
        self.data: Dict[str, Dict[str, bool]] = {}
        self._load()
    
    def _load(self):
        """从文件加载沟通状态数据。"""
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
                print(f"已加载沟通状态数据，共 {len(self.data)} 个班级")
            except Exception as e:
                print(f"加载沟通状态数据失败: {e}")
                self.data = {}
        else:
            self.data = {}
    
    def _save(self):
        """保存沟通状态数据到文件。"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            print(f"已保存沟通状态数据")
        except Exception as e:
            print(f"保存沟通状态数据失败: {e}")
    
    def _get_key(self, course_id: str, class_id: str) -> str:
        """生成存储键。"""
        return f"{course_id}_{class_id}"
    
    def get_status(self, course_id: str, class_id: str, person_id: int) -> bool:
        """
        获取学生的沟通状态。
        
        Args:
            course_id: 课程 ID
            class_id: 班级 ID
            person_id: 学生 ID
        
        Returns:
            沟通状态（True: 已沟通, False: 未沟通）
        """
        key = self._get_key(course_id, class_id)
        if key not in self.data:
            return False
        
        person_id_str = str(person_id)
        return self.data[key].get(person_id_str, False)
    
    def set_status(self, course_id: str, class_id: str, person_id: int, status: bool):
        """
        设置学生的沟通状态。
        
        Args:
            course_id: 课程 ID
            class_id: 班级 ID
            person_id: 学生 ID
            status: 沟通状态（True: 已沟通, False: 未沟通）
        """
        key = self._get_key(course_id, class_id)
        if key not in self.data:
            self.data[key] = {}
        
        person_id_str = str(person_id)
        self.data[key][person_id_str] = status
        self._save()
    
    def toggle_status(self, course_id: str, class_id: str, person_id: int) -> bool:
        """
        切换学生的沟通状态。
        
        Args:
            course_id: 课程 ID
            class_id: 班级 ID
            person_id: 学生 ID
        
        Returns:
            切换后的状态
        """
        current = self.get_status(course_id, class_id, person_id)
        new_status = not current
        self.set_status(course_id, class_id, person_id, new_status)
        return new_status
    
    def get_all_status(self, course_id: str, class_id: str) -> Dict[str, bool]:
        """
        获取某个班级所有学生的沟通状态。
        
        Args:
            course_id: 课程 ID
            class_id: 班级 ID
        
        Returns:
            学生沟通状态字典 {person_id: status}
        """
        key = self._get_key(course_id, class_id)
        return self.data.get(key, {})
