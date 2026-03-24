import sys
import os
import re

# Add the project root to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from core.crawler import XuexitongCrawler

def debug_enc_discovery():
    crawler = XuexitongCrawler()
    phone = "YOUR_PHONE_NUMBER"
    password = "YOUR_PASSWORD"
    
    if crawler.login_by_password(phone, password):
        course_id = "254062535"
        
        # 1. Get initial details to find navigation
        print("--- 步骤 1: 获取课程详情 ---")
        details = crawler.get_course_details(course_id)
        
        # 2. Extract stats link
        stats_url = None
        for link in details.get('nav_links', []):
            if "统计" in link['title']:
                stats_url = link['url']
                break
        
        print(f"找到统计链接: {stats_url}")
        
        # 3. Visit stats link and capture redirect/enc
        if stats_url:
            print(f"--- 步骤 2: 访问统计链接 ---")
            headers = {
                "Referer": f"https://mooc1-gray.chaoxing.com/course/isNewCourse?courseId={course_id}",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }
            resp = crawler.session.get(stats_url, headers=headers, allow_redirects=True)
            print(f"统计页最终 URL: {resp.url}")
            print(f"统计页内容预览 (前 2000 字节):")
            print(resp.text[:2000])
            
            # Look for any link with "attendance" or "downloadcenter"
            links = re.findall(r'href="([^"]+)"', resp.text)
            for l in links:
                if "attendance" in l or "download" in l:
                    print(f"发现有趣链接: {l}")

if __name__ == "__main__":
    debug_enc_discovery()
