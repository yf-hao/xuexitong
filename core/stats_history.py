import json
from pathlib import Path

import os
from .config import DATA_DIR

class StatsHistory:
    def __init__(self, filepath=None):
        if filepath is None:
            filepath = os.path.join(DATA_DIR, "stats_history.json")
        self.filepath = Path(filepath)
        self.ensure_file()

    def ensure_file(self):
        if not self.filepath.parent.exists():
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
        if not self.filepath.exists():
            self.save_data({})
            
    def load_data(self):
        try:
            if not self.filepath.exists():
                return {}
            with open(self.filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def save_data(self, data):
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving stats history: {e}")

    def get_info(self, report_id):
        if not report_id:
            return None
        data = self.load_data()
        return data.get(str(report_id))

    def get_name(self, report_id):
        info = self.get_info(report_id)
        if isinstance(info, dict):
            return info.get('name')
        return info # Backward compatibility for string values

    def save_info(self, report_id, name, time_str=None):
        if not report_id:
            return
        data = self.load_data()
        entry = {'name': name}
        if time_str:
            entry['time'] = time_str
        data[str(report_id)] = entry
        self.save_data(data)

    def delete_info(self, report_id):
        if not report_id:
            return
        data = self.load_data()
        if str(report_id) in data:
            del data[str(report_id)]
            self.save_data(data)
