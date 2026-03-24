from datetime import datetime, timedelta
import sys
import os

# Mocking the logic in main_window.py to test renaming behavior

def parse_dt(ts):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    return None

def test_logic(click_time_str, record_time_str, record_name):
    click_time = datetime.strptime(click_time_str, "%Y-%m-%d %H:%M:%S")
    item_time = parse_dt(record_time_str)
    
    is_new = bool(item_time and item_time >= click_time)
    
    display_name = record_name.replace("统计一键导出", "签到表") if is_new else record_name
    
    print(f"Click Time:  {click_time}")
    print(f"Record Time: {record_time_str} (Parsed: {item_time})")
    print(f"Original:    {record_name}")
    print(f"Is New:      {is_new}")
    print(f"Display:     {display_name}")
    print("-" * 30)
    return is_new

print("Checking Seconds Precision...")
# Scenario 1: Record generated after click (same minute, different seconds)
test_logic("2026-01-20 09:16:10", "2026-01-20 09:16:15", "9班-统计一键导出")

# Scenario 2: Record generated before click (same minute)
test_logic("2026-01-20 09:16:10", "2026-01-20 09:16:05", "9班-统计一键导出")

# Scenario 3: Record generated at exact same time
test_logic("2026-01-20 09:16:10", "2026-01-20 09:16:10", "9班-统计一键导出")

print("\nChecking Minute Precision (Server doesn't provide seconds)...")
# Scenario 4: Record generated in same minute but click has seconds
# If server says 09:16, it is treated as 09:16:00
test_logic("2026-01-20 09:16:10", "2026-01-20 09:16", "9班-统计一键导出")
