from dataclasses import dataclass
from typing import List, Optional

@dataclass
class Course:
    id: str
    name: str
    teacher: str
    image_url: Optional[str] = None
    is_finished: bool = False
    href: str = ''

@dataclass
class Material:
    id: str
    name: str
    type: str  # 'file' or 'folder'
    download_url: Optional[str] = None
    children: List['Material'] = None

    def __post_init__(self):
        if self.children is None:
            self.children = []
