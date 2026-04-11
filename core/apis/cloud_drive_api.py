"""
云盘相关 API
"""
import json
import re


class CloudDriveAPI:
    """云盘 API 接口"""

    def get_cloud_drive_token(self):
        """
        获取云盘访问token
        
        Returns:
            str: token字符串，失败返回None
        """
        try:
            token_url = "https://i.chaoxing.com/pan/getToken"
            
            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Length": "0",
                "Origin": "https://i.chaoxing.com",
                "Pragma": "no-cache",
                "Referer": "https://i.chaoxing.com/",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest",
                "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"'
            }
            
            # POST请求获取token
            response = self.session.post(token_url, headers=headers)
            
            print(f"DEBUG get_cloud_drive_token: 状态码={response.status_code}")
            print(f"DEBUG get_cloud_drive_token: 响应={response.text[:500]}")
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") and data.get("token"):
                    return data["token"]
            
            return None
            
        except Exception as e:
            print(f"DEBUG get_cloud_drive_token: 获取token失败 - {str(e)}")
            return None

    def _extract_js_variables(self, html_text):
        """
        从HTML中提取JavaScript变量
        
        Args:
            html_text: HTML文本
        
        Returns:
            dict: 提取的变量字典
        """
        try:
            variables = {}
            
            # 提取字符串变量：const varname = "value";
            string_patterns = {
                "rootdir": r'const\s+rootdir\s*=\s*"([^"]+)"',
                "_token": r'const\s+_token\s*=\s*"([^"]+)"',
                "encstr": r'const\s+encstr\s*=\s*"([^"]+)"',
                "currentPuid": r'const\s+currentPuid\s*=\s*"([^"]+)"',
                "userFavoriteDir": r'const\s+userFavoriteDir\s*=\s*"([^"]+)"',
                "customRootId": r'const\s+customRootId\s*=\s*"([^"]+)"',
                "yunpanFidEnc": r'const\s+yunpanFidEnc\s*=\s*"([^"]+)"',
                "currentFid": r'const\s+currentFid\s*=\s*"([^"]+)"',
                "realname": r'const\s+realname\s*=\s*"([^"]+)"',
            }
            
            for var_name, pattern in string_patterns.items():
                match = re.search(pattern, html_text)
                if match:
                    variables[var_name] = match.group(1)
            
            # 提取JSON变量：const varname = JSON.parse('{"key":"value"}');
            json_match = re.search(r'const\s+viewConfigJson\s*=\s*JSON\.parse\(\'({[^}]+})\'\)', html_text)
            if json_match:
                try:
                    variables["viewConfigJson"] = json.loads(json_match.group(1))
                except:
                    pass
            
            return variables if variables else None
            
        except Exception as e:
            print(f"DEBUG _extract_js_variables: 提取失败 - {str(e)}")
            return None

    def get_file_list(self, puid, enc, parent_id, page=1, size=60, token=None):
        """
        获取云盘文件列表
        
        Args:
            puid: 用户ID
            enc: 加密字符串
            parent_id: 父目录ID
            page: 页码，默认1
            size: 每页数量，默认60
            token: 认证token（可选，如果不提供会自动获取）
        
        Returns:
            dict: 文件列表信息
        """
        try:
            # 如果没有提供token，先获取
            if not token:
                token = self.get_cloud_drive_token()
                if not token:
                    return {
                        "success": False,
                        "error": "获取token失败"
                    }
            
            list_url = "https://pan-yz.cldisk.com/opt/listres"
            
            params = {
                "puid": puid,
                "shareid": 0,
                "parentId": parent_id,
                "page": page,
                "size": size,
                "enc": enc,
                "filterType": "",
                "orderField": "default",
                "orderType": "desc"
            }
            
            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "application/x-www-form-urlencoded",
                "Pragma": "no-cache",
                "Referer": f"https://pan-yz.cldisk.com/pcuserpan/index",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Storage-Access": "active",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest",
                "p-auth-token": token,
                "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"'
            }
            
            response = self.session.get(list_url, params=params, headers=headers)
            
            print(f"DEBUG get_file_list: 状态码={response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "list": data.get("list", []),
                    "totalCount": data.get("totalCount", 0),
                    "page": page,
                    "size": size
                }
            else:
                return {
                    "success": False,
                    "error": f"请求失败，状态码: {response.status_code}"
                }
                
        except Exception as e:
            print(f"DEBUG get_file_list: 获取文件列表失败 - {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def get_cloud_drive_base_info(self):
        """
        获取云盘基础信息
        
        Returns:
            dict: 云盘基础信息，包含用户信息、存储空间等
        """
        try:
            # 第一步：获取token
            token = self.get_cloud_drive_token()
            
            if not token:
                return {
                    "success": False,
                    "error": "获取云盘token失败"
                }
            
            print(f"DEBUG get_cloud_drive_base_info: token={token[:50]}...")
            
            # 第二步：从cookie中获取uid和s参数
            uid = None
            s_param = None
            
            # 从cookie中提取UID
            for cookie in self.session.cookies:
                if cookie.name == "UID":
                    uid = cookie.value
                elif cookie.name == "s":
                    s_param = cookie.value
            
            # 如果cookie中没有s参数，使用默认值
            if not s_param:
                s_param = "8d79de2551ab8fdfc0e6d8116839bd83"
            
            if not uid:
                # 尝试从其他cookie获取
                for cookie in self.session.cookies:
                    if cookie.name == "_uid":
                        uid = cookie.value
                        break
            
            if not uid:
                return {
                    "success": False,
                    "error": "无法获取用户ID"
                }
            
            # 构建云盘URL
            cloud_url = f"https://pan-yz.cldisk.com/pcuserpan/index?s={s_param}&uid={uid}&p_auth_token={token}"
            
            print(f"DEBUG get_cloud_drive_base_info: 云盘URL={cloud_url}")
            
            # 第三步：访问云盘页面
            cloud_headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Pragma": "no-cache",
                "Referer": "https://i.chaoxing.com/",
                "Sec-Fetch-Dest": "iframe",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "cross-site",
                "Sec-Fetch-Storage-Access": "active",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"'
            }
            
            cloud_response = self.session.get(cloud_url, headers=cloud_headers)
            
            print(f"DEBUG get_cloud_drive_base_info: 云盘页面状态码={cloud_response.status_code}")
            print(f"DEBUG get_cloud_drive_base_info: 云盘页面URL={cloud_response.url}")
            
            # 提取云盘页面中的关键信息
            info = {
                "success": True,
                "token": token,
                "uid": uid,
                "s_param": s_param,
                "cloud_status": cloud_response.status_code,
                "cloud_url": cloud_url,
                "content_type": cloud_response.headers.get("Content-Type", ""),
                "text_length": len(cloud_response.text),
                "text": cloud_response.text[:5000]  # 前5000字符
            }
            
            # 提取JavaScript变量
            cloud_info = self._extract_js_variables(cloud_response.text)
            if cloud_info:
                info["cloud_info"] = cloud_info
                print(f"DEBUG get_cloud_drive_base_info: 提取到云盘信息 - {cloud_info}")
                
                # 获取文件列表
                if "rootdir" in cloud_info and "encstr" in cloud_info and "currentPuid" in cloud_info:
                    file_list_result = self.get_file_list(
                        puid=cloud_info["currentPuid"],
                        enc=cloud_info["encstr"],
                        parent_id=cloud_info["rootdir"],
                        token=token
                    )
                    
                    if file_list_result.get("success"):
                        info["file_list"] = file_list_result["list"]
                        info["file_count"] = file_list_result["totalCount"]
                        print(f"DEBUG get_cloud_drive_base_info: 获取到 {len(file_list_result['list'])} 个文件/文件夹")
            
            # 查找 JSON 数据
            json_matches = re.findall(r'window\.__INITIAL_STATE__\s*=\s*({[^;]+});', cloud_response.text)
            if json_matches:
                try:
                    initial_state = json.loads(json_matches[0])
                    info["initial_state"] = initial_state
                    print(f"DEBUG get_cloud_drive_base_info: 找到初始状态数据")
                except:
                    pass
            
            # 查找 API 端点
            api_matches = re.findall(r'["\']([^"\']*api[^"\']*file[^"\']*)["\']', cloud_response.text, re.IGNORECASE)
            if api_matches:
                info["api_endpoints"] = list(set(api_matches))[:20]  # 去重，最多20个
            
            return info
                
        except Exception as e:
            print(f"DEBUG get_cloud_drive_base_info: 请求失败 - {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def download_file(self, file_id, encrypted_id, puid, current_folder_id, token, save_path):
        """
        下载云盘文件
        
        Args:
            file_id: 文件ID
            encrypted_id: 加密ID
            puid: 用户ID
            current_folder_id: 当前文件夹ID
            token: 认证token
            save_path: 保存路径
        
        Returns:
            dict: 下载结果
        """
        try:
            # 第一步：获取下载链接
            download_url = "https://pan-yz.cldisk.com/download/downloadFileV2"
            
            params = {
                "fleid": file_id,
                "puid": puid,
                "currentFolderId": current_folder_id,
                "p_auth_token": token,
                "encryptedId": encrypted_id,
                "auditRecordIdEnc": ""
            }
            
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Pragma": "no-cache",
                "Referer": "https://pan-yz.cldisk.com/pcuserpan/index",
                "Sec-Fetch-Dest": "iframe",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Storage-Access": "active",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"'
            }
            
            # 发送请求，允许重定向
            response = self.session.get(download_url, params=params, headers=headers, allow_redirects=True, stream=True)
            
            print(f"DEBUG download_file: 最终URL={response.url}")
            print(f"DEBUG download_file: 状态码={response.status_code}")
            
            if response.status_code == 200:
                # 从URL或Content-Disposition中提取文件名
                import os
                from urllib.parse import unquote, urlparse, parse_qs
                
                # 尝试从URL参数中获取文件名
                parsed_url = urlparse(response.url)
                query_params = parse_qs(parsed_url.query)
                filename = query_params.get('fn', [None])[0]
                
                if filename:
                    filename = unquote(filename)
                else:
                    # 从Content-Disposition中提取
                    content_disp = response.headers.get('Content-Disposition', '')
                    if 'filename=' in content_disp:
                        raw_filename = content_disp.split('filename=')[1].strip('"')
                        
                        # 尝试 URL 解码
                        try:
                            filename = unquote(raw_filename)
                        except:
                            filename = raw_filename
                        
                        # 如果解码后仍然是乱码，尝试 ISO-8859-1 -> UTF-8
                        try:
                            filename = raw_filename.encode('iso-8859-1').decode('utf-8')
                        except:
                            pass
                    else:
                        filename = f"file_{file_id}"
                
                # 确保保存路径存在
                os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else '.', exist_ok=True)
                
                # 保存文件
                full_save_path = os.path.join(save_path, filename) if os.path.isdir(save_path) else save_path
                
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                
                with open(full_save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                print(f"\rDEBUG download_file: 下载进度 {progress:.1f}%", end='')
                
                print(f"\nDEBUG download_file: 文件已保存到 {full_save_path}")
                
                return {
                    "success": True,
                    "file_path": full_save_path,
                    "filename": filename,
                    "size": downloaded
                }
            else:
                return {
                    "success": False,
                    "error": f"下载失败，状态码: {response.status_code}"
                }
                
        except Exception as e:
            print(f"DEBUG download_file: 下载失败 - {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def download_folder(self, folder_id, encrypted_id, puid, token, save_path):
        """
        下载云盘文件夹（打包为ZIP）
        
        Args:
            folder_id: 文件夹ID
            encrypted_id: 加密ID
            puid: 用户ID
            token: 认证token
            save_path: 保存路径
        
        Returns:
            dict: 下载结果
        """
        try:
            import os
            from urllib.parse import unquote
            
            # 第一步：检查是否有子文件夹
            check_url = "https://pan-yz.cldisk.com/opt/getSubFoldCount"
            
            check_params = {
                "puid": puid,
                "fileInfoId": folder_id,
                "encryptedId": encrypted_id
            }
            
            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "application/x-www-form-urlencoded",
                "Pragma": "no-cache",
                "Referer": "https://pan-yz.cldisk.com/pcuserpan/index",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Storage-Access": "active",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest",
                "p-auth-token": token,
                "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"'
            }
            
            check_response = self.session.get(check_url, params=check_params, headers=headers)
            
            print(f"DEBUG download_folder: 检查子文件夹 状态码={check_response.status_code}")
            print(f"DEBUG download_folder: 检查子文件夹 响应={check_response.text}")
            
            if check_response.status_code == 200:
                check_result = check_response.json()
                if not check_result.get("result"):
                    # 有子文件夹，无法下载
                    return {
                        "success": False,
                        "error": "文件夹内包含子文件夹，请安装学习通客户端下载。"
                    }
            
            # 第二步：获取 Md5Enc
            md5_url = "https://pan-yz.cldisk.com/pcsharepan/getMd5Enc"
            
            md5_data = {
                "resids": folder_id,
                "puids": puid
            }
            
            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://pan-yz.cldisk.com",
                "Pragma": "no-cache",
                "Referer": "https://pan-yz.cldisk.com/pcuserpan/index",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Storage-Access": "active",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest",
                "p-auth-token": token,
                "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"'
            }
            
            md5_response = self.session.post(md5_url, data=md5_data, headers=headers)
            
            print(f"DEBUG download_folder: Md5Enc 状态码={md5_response.status_code}")
            print(f"DEBUG download_folder: Md5Enc 响应={md5_response.text}")
            
            if md5_response.status_code != 200:
                return {
                    "success": False,
                    "error": f"获取下载密钥失败，状态码: {md5_response.status_code}"
                }
            
            md5_result = md5_response.json()
            if not md5_result.get("result"):
                return {
                    "success": False,
                    "error": "获取下载密钥失败"
                }
            
            md5_enc = md5_result.get("Md5Enc")
            
            # 第二步：下载文件
            download_url = f"https://pan-yz.cldisk.com/opt/batchdownload_{md5_enc}"
            
            download_data = {
                "resids": folder_id,
                "puids": puid,
                "auditRecordIdEnc": "",
                "p_auth_token": token
            }
            
            download_headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://pan-yz.cldisk.com",
                "Pragma": "no-cache",
                "Referer": "https://pan-yz.cldisk.com/pcuserpan/index",
                "Sec-Fetch-Dest": "iframe",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Storage-Access": "active",
                "Upgrade-Insecure-Requests": "1",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"'
            }
            
            response = self.session.post(download_url, data=download_data, headers=download_headers, allow_redirects=True, stream=True)
            
            print(f"DEBUG download_folder: 下载状态码={response.status_code}")
            
            if response.status_code == 200:
                # 获取文件名
                content_disp = response.headers.get('Content-Disposition', '')
                filename = None
                
                # 尝试从 Content-Disposition 中提取文件名
                if 'filename=' in content_disp:
                    raw_filename = content_disp.split('filename=')[1].strip('"')
                    
                    # 尝试多种编码方式
                    # 1. 先尝试 URL 解码
                    try:
                        filename = unquote(raw_filename)
                    except:
                        pass
                    
                    # 2. 尝试 ISO-8859-1 -> UTF-8 (常见的服务器编码问题)
                    if not filename or any(ord(c) > 127 and ord(c) < 256 for c in filename):
                        try:
                            decoded = raw_filename.encode('iso-8859-1').decode('utf-8')
                            if decoded:
                                filename = decoded
                        except:
                            pass
                
                if not filename:
                    filename = f"folder_{folder_id}.zip"
                
                # 确保保存路径存在
                os.makedirs(save_path, exist_ok=True)
                
                # 完整保存路径
                full_save_path = os.path.join(save_path, filename)
                
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                
                with open(full_save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                print(f"\rDEBUG download_folder: 下载进度 {progress:.1f}%", end='')
                
                print(f"\nDEBUG download_folder: 文件夹已保存到 {full_save_path}")
                
                return {
                    "success": True,
                    "file_path": full_save_path,
                    "filename": filename,
                    "size": downloaded
                }
            else:
                return {
                    "success": False,
                    "error": f"下载失败，状态码: {response.status_code}"
                }
                
        except Exception as e:
            print(f"DEBUG download_folder: 下载失败 - {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def rename_cloud_drive_item(self, item_id, parent_id, new_name, token):
        """
        重命名云盘文件或文件夹
        
        Args:
            item_id: 文件或文件夹ID
            parent_id: 父文件夹ID
            new_name: 新名称
            token: 认证token
        
        Returns:
            dict: 重命名结果
        """
        try:
            rename_url = "https://pan-yz.cldisk.com/opt/newRootfolder"
            
            data = {
                "parentId": parent_id,
                "name": new_name,
                "selectDlid": "onlyme",
                "newfileid": item_id,
                "cx_p_token": ""
            }
            
            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://pan-yz.cldisk.com",
                "Pragma": "no-cache",
                "Referer": "https://pan-yz.cldisk.com/pcuserpan/rename",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Storage-Access": "active",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest",
                "p-auth-token": token,
                "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"'
            }
            
            response = self.session.post(rename_url, data=data, headers=headers)
            
            print(f"DEBUG rename_cloud_drive_item: 状态码={response.status_code}")
            print(f"DEBUG rename_cloud_drive_item: 响应={response.text}")
            
            if response.status_code == 200:
                result = response.json()
                # API 返回的是 "success" 字段，不是 "status"
                is_success = result.get("success", False)
                msg = result.get("msg", "")
                
                if is_success:
                    return {
                        "success": True,
                        "message": msg or "重命名成功",
                        "data": result.get("data")
                    }
                else:
                    return {
                        "success": False,
                        "error": msg or "重命名失败"
                    }
            else:
                return {
                    "success": False,
                    "error": f"请求失败，状态码: {response.status_code}"
                }
                
        except Exception as e:
            print(f"DEBUG rename_folder: 重命名失败 - {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def delete_cloud_drive_item(self, item_id, encrypted_id, puid, token):
        """
        删除云盘文件或文件夹
        
        Args:
            item_id: 文件或文件夹ID
            encrypted_id: 加密ID
            puid: 用户ID
            token: 认证token
        
        Returns:
            dict: 删除结果
        """
        try:
            delete_url = "https://pan-yz.cldisk.com/opt/delres"
            
            data = {
                "resids": item_id,
                "resourcetype": 0,
                "puids": puid,
                "encryptedids": encrypted_id
            }
            
            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://pan-yz.cldisk.com",
                "Pragma": "no-cache",
                "Referer": "https://pan-yz.cldisk.com/pcuserpan/index",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Storage-Access": "active",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest",
                "p-auth-token": token,
                "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"'
            }
            
            response = self.session.post(delete_url, data=data, headers=headers)
            
            print(f"DEBUG delete_cloud_drive_item: 状态码={response.status_code}")
            print(f"DEBUG delete_cloud_drive_item: 响应={response.text}")
            
            if response.status_code == 200:
                result = response.json()
                is_success = result.get("success", False)
                msg = result.get("msg", "")
                
                if is_success:
                    return {
                        "success": True,
                        "message": msg or "删除成功"
                    }
                else:
                    return {
                        "success": False,
                        "error": msg or "删除失败"
                    }
            else:
                return {
                    "success": False,
                    "error": f"请求失败，状态码: {response.status_code}"
                }
                
        except Exception as e:
            print(f"DEBUG delete_cloud_drive_item: 删除失败 - {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def generate_upload_url(self, puid, folder_id, _token, p_auth_token, fid="4311"):
        """
        生成上传URL
        
        Args:
            puid: 用户ID
            folder_id: 文件夹ID
            _token: URL参数token（短的）
            p_auth_token: 认证token（长的，用于header）
            fid: 固定值4311
        
        Returns:
            dict: 包含uploadUrl的结果
        """
        try:
            url = "https://pan-yz.cldisk.com/pcuserpanUpload/generateUploadUrl"
            
            params = {
                "puid": puid,
                "folderUpload": "false",
                "fldid": folder_id,
                "_token": _token,
                "fid": fid
            }
            
            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "application/x-www-form-urlencoded",
                "Pragma": "no-cache",
                "Referer": "https://pan-yz.cldisk.com/pcuserpan/index",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Storage-Access": "active",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest",
                "p-auth-token": p_auth_token,
                "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"'
            }
            
            response = self.session.get(url, params=params, headers=headers)
            
            print(f"DEBUG generate_upload_url: 状态码={response.status_code}")
            print(f"DEBUG generate_upload_url: 响应={response.text}")
            
            if response.status_code == 200:
                result = response.json()
                if result.get("result"):
                    return {
                        "success": True,
                        "upload_url": result.get("uploadUrl", "")
                    }
                else:
                    return {
                        "success": False,
                        "error": result.get("msg", "生成上传URL失败")
                    }
            else:
                return {
                    "success": False,
                    "error": f"请求失败，状态码: {response.status_code}"
                }
                
        except Exception as e:
            print(f"DEBUG generate_upload_url: 生成失败 - {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def upload_file_to_cloud(self, upload_url, file_path, token):
        """
        上传文件到云盘
        
        Args:
            upload_url: 上传URL（相对路径）
            file_path: 本地文件路径
            token: 认证token
        
        Returns:
            dict: 上传结果
        """
        try:
            import os
            from pathlib import Path
            
            # 构建完整URL
            full_url = f"https://pan-yz.cldisk.com{upload_url}"
            
            # 获取文件名
            filename = os.path.basename(file_path)
            
            # 准备文件数据
            with open(file_path, 'rb') as f:
                files = {
                    'file': (filename, f)
                }
                
                headers = {
                    "Accept": "*/*",
                    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Origin": "https://pan-yz.cldisk.com",
                    "Pragma": "no-cache",
                    "Referer": "https://pan-yz.cldisk.com/pcuserpan/index",
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-Storage-Access": "active",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                    "p-auth-token": token,
                    "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"macOS"'
                }
                
                response = self.session.post(full_url, files=files, headers=headers)
            
            print(f"DEBUG upload_file_to_cloud: 状态码={response.status_code}")
            print(f"DEBUG upload_file_to_cloud: 响应={response.text}")
            
            if response.status_code == 200:
                result = response.json()
                if result.get("result"):
                    return {
                        "success": True,
                        "message": result.get("msg", "上传成功"),
                        "data": result.get("data")
                    }
                else:
                    return {
                        "success": False,
                        "error": result.get("msg", "上传失败")
                    }
            else:
                return {
                    "success": False,
                    "error": f"请求失败，状态码: {response.status_code}"
                }
                
        except Exception as e:
            print(f"DEBUG upload_file_to_cloud: 上传失败 - {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def create_cloud_drive_folder(self, parent_id, folder_name, token):
        """
        在云盘创建新文件夹
        
        Args:
            parent_id: 父文件夹ID
            folder_name: 新文件夹名称
            token: 认证token
        
        Returns:
            dict: 创建结果
        """
        try:
            create_url = "https://pan-yz.cldisk.com/opt/newRootfolder"
            
            data = {
                "parentId": parent_id,
                "name": folder_name,
                "selectDlid": "onlyme",
                "newfileid": "0",  # 新建文件夹时为0
                "cx_p_token": ""
            }
            
            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://pan-yz.cldisk.com",
                "Pragma": "no-cache",
                "Referer": "https://pan-yz.cldisk.com/pcuserpan/index",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Storage-Access": "active",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest",
                "p-auth-token": token,
                "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"'
            }
            
            response = self.session.post(create_url, data=data, headers=headers)
            
            print(f"DEBUG create_cloud_drive_folder: 状态码={response.status_code}")
            print(f"DEBUG create_cloud_drive_folder: 响应={response.text}")
            
            if response.status_code == 200:
                result = response.json()
                is_success = result.get("success", False)
                msg = result.get("msg", "")
                
                if is_success:
                    return {
                        "success": True,
                        "message": msg or "创建成功",
                        "data": result.get("data")
                    }
                else:
                    return {
                        "success": False,
                        "error": msg or "创建失败"
                    }
            else:
                return {
                    "success": False,
                    "error": f"请求失败，状态码: {response.status_code}"
                }
                
        except Exception as e:
            print(f"DEBUG create_cloud_drive_folder: 创建失败 - {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def get_folder_list_for_move(self, parent_id, token):
        """
        获取文件夹列表（用于移动文件）
        
        Args:
            parent_id: 父文件夹ID
            token: 认证token
        
        Returns:
            dict: 包含文件夹列表的结果
        """
        try:
            url = "https://pan-yz.cldisk.com/opt/listfolder"
            
            data = {
                "parentId": parent_id
            }
            
            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://pan-yz.cldisk.com",
                "Pragma": "no-cache",
                "Referer": "https://pan-yz.cldisk.com/pcuserpan/index",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Storage-Access": "active",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest",
                "p-auth-token": token,
                "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"'
            }
            
            response = self.session.post(url, data=data, headers=headers)
            
            print(f"DEBUG get_folder_list_for_move: 状态码={response.status_code}")
            print(f"DEBUG get_folder_list_for_move: 响应={response.text[:500]}")
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    return {
                        "success": True,
                        "folders": result.get("data", [])
                    }
                else:
                    return {
                        "success": False,
                        "error": "获取文件夹列表失败"
                    }
            else:
                return {
                    "success": False,
                    "error": f"请求失败，状态码: {response.status_code}"
                }
                
        except Exception as e:
            print(f"DEBUG get_folder_list_for_move: 获取失败 - {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def move_cloud_drive_item(self, item_id, target_folder_id, puid, token):
        """
        移动文件或文件夹
        
        Args:
            item_id: 要移动的文件/文件夹ID
            target_folder_id: 目标文件夹ID
            puid: 用户ID
            token: 认证token
        
        Returns:
            dict: 移动结果
        """
        try:
            move_url = "https://pan-yz.cldisk.com/opt/moveres"
            
            # folderid 格式：文件夹ID_用户ID
            data = {
                "folderid": f"{target_folder_id}_{puid}",
                "resids": item_id
            }
            
            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ckb;q=0.6,zh-TW;q=0.5",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://pan-yz.cldisk.com",
                "Pragma": "no-cache",
                "Referer": "https://pan-yz.cldisk.com/pcuserpan/index",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Storage-Access": "active",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest",
                "p-auth-token": token,
                "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"'
            }
            
            response = self.session.post(move_url, data=data, headers=headers)
            
            print(f"DEBUG move_cloud_drive_item: 状态码={response.status_code}")
            print(f"DEBUG move_cloud_drive_item: 响应={response.text}")
            
            if response.status_code == 200:
                result = response.json()
                is_success = result.get("success", False)
                msg = result.get("msg", "")
                
                if is_success:
                    return {
                        "success": True,
                        "message": msg or "移动成功"
                    }
                else:
                    return {
                        "success": False,
                        "error": msg or "移动失败"
                    }
            else:
                return {
                    "success": False,
                    "error": f"请求失败，状态码: {response.status_code}"
                }
                
        except Exception as e:
            print(f"DEBUG move_cloud_drive_item: 移动失败 - {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
