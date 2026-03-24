import sys
import os

# Add project root to sys.path to allow imports from 'core'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.login_handler import ChaoxingLogin
import json

def test():
    phone = "YOUR_PHONE_NUMBER"
    password = "YOUR_PASSWORD"
    
    print(f"Testing login for {phone}...")
    try:
        # Disable environment proxies if they are causing issues
        session_config = {
            'trust_env': False
        }
        
        chaoxing = ChaoxingLogin(phone, password)
        # Apply session config to avoid ProxyError if needed
        chaoxing.session.trust_env = False
        
        chaoxing.get_login_page()
        resp_json, cookies = chaoxing.login()
        
        print("\nLogin Response JSON:")
        print(json.dumps(resp_json, indent=4, ensure_ascii=False))
        
        print("\nCookies fetched:")
        for name, value in cookies.items():
            print(f"{name} = {value}")
            
        if resp_json.get("status") == True or resp_json.get("result") == 1:
            print("\n[SUCCESS] Login successful!")
        else:
            print("\n[FAILED] Login failed. Check the response above.")
            
    except Exception as e:
        print(f"\n[ERROR] An error occurred during login: {e}")

if __name__ == "__main__":
    test()
