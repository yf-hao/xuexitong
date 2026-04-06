import re

from bs4 import BeautifulSoup


class StatsAPI:
    """统计报表与成绩权重相关接口。"""

    def _get_stats_reports(self, seltables: str, report_name: str = "统计", trigger_export: bool = True) -> any:
        """
        Generic method to fetch stats reports (attendance, quiz, homework, etc.).

        Args:
            seltables: The seltables parameter for the export API (e.g., "12" for attendance, "8" for quiz)
            report_name: Name of the report type for logging (e.g., "考勤", "测验")
            trigger_export: Whether to trigger a new export request before fetching the list

        Returns:
            List of report dictionaries or error message string
        """
        params = self.session_manager.course_params
        if not params:
            return "错误：未找到课程参数，请先选择课程。"

        export_url = "https://stat2-ans.chaoxing.com/stat2/teach-data/export"
        export_params = {
            "clazzid": params.get("clazzid"),
            "courseid": params.get("courseid"),
            "cpi": params.get("cpi"),
            "ut": "t",
            "pEnc": "",
            "seltables": seltables,
            "type": "1",
            "exportType": "0",
            "fr": "stat2",
        }
        export_headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://stat2-ans.chaoxing.com/teach-data/index?courseid={params.get('courseid')}&clazzid={params.get('clazzid')}&cpi={params.get('cpi')}&ut=t",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        try:
            if trigger_export:
                print(f"正在触发{report_name}数据预导出 (Export)...")
                self.session.get(export_url, params=export_params, headers=export_headers, timeout=10)
            else:
                print(f"跳过触发{report_name}预导出，执行增量刷新...")
        except Exception as e:
            print(f"预导出请求失败(忽略): {e}")

        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/downloadcenter"
        headers = {
            "Referer": f"https://stat2-ans.chaoxing.com/teach-data/index?courseid={params.get('courseid')}&clazzid={params.get('clazzid')}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        all_items = []
        page_num = 1
        max_pages = 1

        try:
            while page_num <= max_pages:
                query_params = {
                    "courseId": params.get("courseid"),
                    "pageNum": str(page_num),
                    "cpi": params.get("cpi"),
                    "order": "down",
                }

                print(f"正在获取{report_name}下载列表 (第 {page_num} 页): {url}")
                resp = self.session.get(url, params=query_params, headers=headers, timeout=10)
                resp.raise_for_status()

                soup = BeautifulSoup(resp.text, "lxml")
                rows = soup.select("ul.dataBody_td")

                if not rows:
                    print(f"第 {page_num} 页无数据，已获取所有页面")
                    break

                page_items = []
                for row in rows:
                    lis = row.find_all("li")
                    if len(lis) >= 3:
                        name_tag = lis[0].select_one("span.nameText")
                        name = name_tag.get_text(strip=True) if name_tag else "未知名称"
                        time = lis[1].get_text(strip=True)
                        status = lis[2].get_text(strip=True)

                        link_tag = lis[3].select_one("a.download_ic") if len(lis) > 3 else None
                        download_url = link_tag.get("href") if link_tag else None

                        report_id = row.attrs.get("data") or row.get("id")
                        if not report_id:
                            del_tag = lis[3].select_one("a[onclick*='delete'], a[onclick*='remove'], a[onclick*='del'], a.delete_ic, a.btn-delete, a.deleteOrCancel") if len(lis) > 3 else None
                            if del_tag:
                                onclick = del_tag.get("onclick", "")
                                id_match = re.search(r"['\"](\d+)['\"]", onclick) or re.search(r"\((\d+)\)", onclick)
                                if id_match:
                                    report_id = id_match.group(1)
                                if not report_id:
                                    report_id = del_tag.attrs.get("data-id") or del_tag.get("id") or del_tag.attrs.get("data")

                        if not report_id and download_url:
                            id_match = re.search(r"[?&]\bid=(\d+)", download_url) or re.search(r"[?&]\bresId=(\d+)", download_url)
                            if id_match:
                                report_id = id_match.group(1)

                        if not report_id or report_id == "14632912":
                            if report_id == "14632912":
                                report_id = None

                        page_items.append({
                            "name": name,
                            "time": time,
                            "status": status,
                            "url": download_url,
                            "id": report_id,
                        })

                if page_items:
                    all_items.extend(page_items)
                    print(f"第 {page_num} 页获取到 {len(page_items)} 条记录")
                    page_num += 1
                else:
                    print(f"第 {page_num} 页解析结果为空，停止分页")
                    break

            if not all_items:
                return "💡 提示: 未发现有效的导出记录，可能正在生成中，请稍后刷新。"

            print(f"共获取 {len(all_items)} 条{report_name}记录")
            return all_items
        except Exception as e:
            return f"获取下载列表具体错误: {e}"

    def delete_stats_report(self, report_id: str) -> tuple[bool, str]:
        """Delete a stats report item from the download center."""
        params = self.session_manager.course_params
        if not params:
            return False, "未找到课程参数"

        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/deleteDownloadCenter"
        query_params = {
            "courseId": params.get("courseid"),
            "id": report_id,
            "cpi": params.get("cpi"),
        }

        headers = {
            "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/downloadcenter?courseId={params.get('courseid')}&cpi={params.get('cpi')}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
        }

        try:
            resp = self.session.get(url, params=query_params, headers=headers, timeout=10)
            resp.raise_for_status()
            try:
                result = resp.json()
                if result.get("result") == 1 or result.get("status") is True:
                    return True, "删除成功"
                return False, f"删除失败: {result.get('msg', '未知错误')}"
            except Exception:
                if "1" in resp.text:
                    return True, "删除成功"
                return False, f"服务器返回: {resp.text[:100]}"
        except Exception as e:
            return False, f"删除请求失败: {e}"

    def get_stats_reports(self, stats_type: str, trigger_export: bool = True) -> any:
        """通用的统计报告获取方法（配置驱动）。"""
        from core.config import STATS_TYPES

        config = STATS_TYPES.get(stats_type)
        if not config:
            available_types = ", ".join(STATS_TYPES.keys())
            return f"❌ 未知的统计类型: {stats_type}。可用类型: {available_types}"

        return self._get_stats_reports(
            seltables=config["seltables"],
            report_name=config["name"],
            trigger_export=trigger_export,
        )

    def get_attendance_reports(self) -> any:
        """获取考勤报告。"""
        return self.get_stats_reports("attendance")

    def get_quiz_reports(self) -> any:
        """获取测验报告。"""
        return self.get_stats_reports("quiz")

    def get_homework_reports(self) -> any:
        """获取作业报告。"""
        return self.get_stats_reports("homework")

    def get_grade_weights(self) -> dict:
        """Fetch current grade weights from Xuexitong."""
        params = self.session_manager.course_params
        if not params:
            print("Crawler: No course params found for weights")
            return {}

        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/scoreweightdata"
        query_params = {
            "courseId": params.get("courseid"),
            "clazzId": params.get("clazzid"),
            "cpi": params.get("cpi"),
        }

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/course-manage?courseid={params.get('courseid')}&clazzid={params.get('clazzid')}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Upgrade-Insecure-Requests": "1",
        }

        try:
            resp = self.session.get(url, params=query_params, headers=headers, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            mapping = {
                "video": "章节任务点",
                "ceyan": "章节测验",
                "work": "作业",
                "test": "考试",
                "aiEvaluate": "AI实践",
                "pbl": "分组任务(PBL)",
                "attend": "签到",
                "active": "课程积分",
                "bbs": "讨论",
            }

            weights = {}
            print(f"\n--- 权重同步调试 (班级ID: {params.get('clazzid')}) ---")
            for field, display_name in mapping.items():
                inputs = soup.find_all("input", {"name": field})
                val = 0
                for inp in inputs:
                    v_str = inp.get("value")
                    if v_str and v_str.strip():
                        try:
                            val = int(float(v_str))
                            break
                        except Exception:
                            continue

                weights[display_name] = val
                print(f"  > {display_name} ({field}): {val}%")
            print("--- 同步结束 ---\n")
            return weights
        except Exception as e:
            print(f"Error fetching weights: {e}")
            return {}

    def set_grade_weights(self, weights: dict, class_ids: list = None) -> tuple[bool, str]:
        """Set course grade weights."""
        params = self.session_manager.course_params
        if not params:
            return False, "未找到课程参数"

        current_clazzid = params.get("clazzid")
        if class_ids:
            unique_ids = []
            if current_clazzid in class_ids:
                unique_ids.append(current_clazzid)
            for cid in class_ids:
                if cid != current_clazzid:
                    unique_ids.append(cid)
            class_id_str = ",".join(str(cid) for cid in unique_ids) + ","
        else:
            class_id_str = f"{current_clazzid},"

        url = "https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/setWeights"
        data = {
            "offlineName": "",
            "courseId": params.get("courseid"),
            "clazzId": current_clazzid,
            "cpi": params.get("cpi"),
            "video": weights.get("章节任务点", 0),
            "ceyan": weights.get("章节测验", 0),
            "work": weights.get("作业", 0),
            "test": weights.get("考试", 0),
            "aiEvaluateType": "0",
            "aiEvaluate": weights.get("AI实践", 0),
            "pbl": weights.get("分组任务(PBL)", 0),
            "attend": weights.get("签到", 0),
            "attendStatisticType": "0",
            "active": weights.get("课程积分", 0),
            "activeLimit": "300",
            "bbs": weights.get("讨论", 0),
            "bbsStatisticType": "0",
            "visitTime": "0",
            "visitTimeLimit": "",
            "readTime": "0",
            "readTimeLimit": "",
            "liveTime": "0",
            "liveStatisticType": "1",
            "liveViewingRate": "",
            "liveTimeLimit": "",
            "interactiveQuestion": "0",
            "chaoxingClassTime": "0",
            "chaoxingClassType": "0",
            "chaoxingClassLimit": "",
            "chaoxingClassRate": "",
            "offline": "0",
            "attendAttendance": "0",
            "bbsLimit": "2.0",
            "bbsReplyLimit": "2.0",
            "bbsPraiseLimit": "1.0",
            "cleanCustomScoreVal": "0",
            "customWeightJson": "[]",
            "classIdStr": class_id_str,
        }

        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Referer": f"https://mooc2-gray.chaoxing.com/mooc2-ans/tcm/course-manage?courseid={params.get('courseid')}&clazzid={current_clazzid}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        try:
            resp = self.session.post(url, data=data, headers=headers, timeout=10)
            resp.raise_for_status()
            res_json = resp.json()
            if res_json.get("result") == 1 or res_json.get("status") is True:
                target_desc = "所有班级" if class_ids and len(class_ids) > 1 else "当前班级"
                return True, f"权重设置已成功保存至{target_desc}！"
            return False, res_json.get("msg", "保存失败，服务器返回异常")
        except Exception as e:
            return False, f"网络请求失败: {e}"
