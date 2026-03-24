import sys
import os

# Add the project root to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from core.crawler import XuexitongCrawler
import json

def fetch_specific_class_id():
    crawler = XuexitongCrawler()
    
    # Use the test credentials
    phone = "YOUR_PHONE_NUMBER"
    password = "YOUR_PASSWORD"
    
    print(f"正在登录账号: {phone}...")
    if crawler.login_by_password(phone, password):
        print("登录成功！")
        
        course_id = "254062535"
        print(f"正在获取课程 {course_id} 的详情...")
        
        # Manually inject a clazzid to trigger mooc2 fetch in get_course_details
        crawler.session_manager.course_params['clazzid'] = "125959676"
        
        details = crawler.get_course_details(course_id)
        
        print("\n当前 Session 中的最新参数:")
        print(json.dumps(crawler.session_manager.course_params, indent=2))
        
        classes = crawler.get_class_list(course_id)
        
        if not classes:
            print("未找到任何班级信息。")
        else:
            print("\n成功获取班级列表:")
            for c in classes:
                print(f"班级ID: {c['id']}, 名称: {c['name']}")
    else:
        print("登录失败，请检查账号密码。")

if __name__ == "__main__":
    fetch_specific_class_id()
