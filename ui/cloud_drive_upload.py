"""后台执行云盘文件夹上传。"""

import os

from PyQt6.QtCore import QThread, pyqtSignal


class FolderUploadThread(QThread):
    """创建远程目录树并按原目录结构上传文件。"""

    folder_created = pyqtSignal(str)
    file_started = pyqtSignal(str, int)
    file_progress = pyqtSignal(int, int)
    overall_progress = pyqtSignal(int, int)
    scan_finished = pyqtSignal(int, int)
    file_finished = pyqtSignal(dict)
    all_finished = pyqtSignal(dict)
    status_message = pyqtSignal(str)

    _FOLDER_ID_KEYS = (
        "id",
        "folderId",
        "folderID",
        "fileId",
        "fileID",
        "dlid",
        "resId",
        "resid",
    )

    def __init__(self, crawler, local_folder, cloud_info, current_folder_id):
        super().__init__()
        self.crawler = crawler
        self.local_folder = os.path.abspath(local_folder)
        self.cloud_info = dict(cloud_info or {})
        self.current_folder_id = current_folder_id
        self._is_cancelled = False

    def cancel(self):
        """请求在当前网络操作结束后停止上传。"""
        self._is_cancelled = True

    def run(self):
        summary = {
            "success": False,
            "folder_created": False,
            "folder_name": os.path.basename(os.path.normpath(self.local_folder)),
            "total_count": 0,
            "success_files": [],
            "failed_files": [],
            "cancelled": False,
        }

        try:
            directories, files = self._scan_folder()
            summary["total_count"] = len(files)
            total_bytes = sum(size for _, _, size in files)
            processed_bytes = 0
            self.scan_finished.emit(summary["total_count"], total_bytes)

            if self._is_cancelled:
                summary["cancelled"] = True
                self.all_finished.emit(summary)
                return

            root_name = summary["folder_name"]
            root_id, error = self._create_remote_folder(
                self.current_folder_id,
                root_name,
            )
            if not root_id:
                summary["failed_files"].append((root_name, error or "创建文件夹失败"))
                self.all_finished.emit(summary)
                return

            summary["folder_created"] = True
            remote_ids = {".": root_id}
            self.folder_created.emit(root_name)

            for relative_dir in directories:
                if self._is_cancelled:
                    summary["cancelled"] = True
                    break

                parent_relative = os.path.dirname(relative_dir) or "."
                parent_id = remote_ids.get(parent_relative)
                if not parent_id:
                    error = f"找不到父文件夹: {parent_relative}"
                    summary["failed_files"].append((relative_dir, error))
                    break

                folder_name = os.path.basename(relative_dir)
                folder_id, error = self._create_remote_folder(parent_id, folder_name)
                if not folder_id:
                    summary["failed_files"].append((relative_dir, error or "创建文件夹失败"))
                    break

                remote_ids[relative_dir] = folder_id
                self.folder_created.emit(relative_dir)

            if not summary["cancelled"] and not summary["failed_files"]:
                for file_path, relative_path, file_size in files:
                    if self._is_cancelled:
                        summary["cancelled"] = True
                        break

                    parent_relative = os.path.dirname(relative_path) or "."
                    parent_id = remote_ids.get(parent_relative)
                    if not parent_id:
                        summary["failed_files"].append(
                            (relative_path, f"找不到目标文件夹: {parent_relative}")
                        )
                        continue

                    result = self._upload_file(
                        file_path,
                        relative_path,
                        file_size,
                        parent_id,
                        processed_bytes,
                        total_bytes,
                    )
                    if result.get("success"):
                        summary["success_files"].append(relative_path)
                    elif result.get("cancelled"):
                        summary["cancelled"] = True
                        break
                    else:
                        summary["failed_files"].append(
                            (relative_path, result.get("error", "上传失败"))
                        )

                    processed_bytes += file_size
                    self.overall_progress.emit(processed_bytes, total_bytes)

            summary["success"] = summary["folder_created"] and not summary["failed_files"]
            summary["success"] = summary["success"] or bool(summary["success_files"])
            summary["cancelled"] = summary["cancelled"] or self._is_cancelled
            self.all_finished.emit(summary)
        except Exception as exc:
            summary["cancelled"] = self._is_cancelled
            summary["failed_files"].append((summary["folder_name"], str(exc)))
            self.all_finished.emit(summary)

    def _scan_folder(self):
        directories = []
        files = []

        for root, dir_names, file_names in os.walk(self.local_folder, followlinks=False):
            dir_names.sort()
            file_names.sort()

            relative_root = os.path.relpath(root, self.local_folder)
            if relative_root != ".":
                directories.append(relative_root)

            for file_name in file_names:
                file_path = os.path.join(root, file_name)
                if os.path.islink(file_path) or not os.path.isfile(file_path):
                    continue
                relative_path = os.path.relpath(file_path, self.local_folder)
                files.append((file_path, relative_path, os.path.getsize(file_path)))

        directories.sort(key=lambda path: (path.count(os.sep), path))
        return directories, files

    def _create_remote_folder(self, parent_id, folder_name):
        existing_folder = self._find_folder_id(parent_id, folder_name)
        if existing_folder:
            return None, f"目标目录下已存在同名文件夹: {folder_name}"

        result = self.crawler.create_cloud_drive_folder(
            parent_id=parent_id,
            folder_name=folder_name,
            token=self.cloud_info.get("token"),
        )
        if not result.get("success"):
            return None, result.get("error", "创建文件夹失败")

        folder_id = self._extract_folder_id(result.get("data"))
        if folder_id:
            return folder_id, None

        # Some server responses only report success. Resolve the new folder
        # from the parent's listing so nested uploads still have a target ID.
        folder_id = self._find_folder_id(parent_id, folder_name)
        if folder_id:
            return folder_id, None

        return None, f"创建成功，但未获取到文件夹ID: {folder_name}"

    def _find_folder_id(self, parent_id, folder_name):
        list_result = self.crawler.get_file_list(
            puid=self.cloud_info.get("currentPuid"),
            enc=self.cloud_info.get("encstr"),
            parent_id=parent_id,
            token=self.cloud_info.get("token"),
        )
        if not list_result.get("success"):
            return None

        matches = [
            item
            for item in list_result.get("list", [])
            if str(item.get("isfile", 0)) in ("0", "False")
            and item.get("name") == folder_name
        ]
        if len(matches) == 1 and matches[0].get("id") is not None:
            return str(matches[0]["id"])
        return None

    def _upload_file(
        self,
        file_path,
        relative_path,
        file_size,
        folder_id,
        processed_bytes,
        total_bytes,
    ):
        self.status_message.emit(f"正在上传: {relative_path}")
        self.file_started.emit(relative_path, file_size)

        url_result = self.crawler.generate_upload_url(
            puid=self.cloud_info.get("currentPuid"),
            folder_id=folder_id,
            _token=self.cloud_info.get("_token"),
            p_auth_token=self.cloud_info.get("token"),
        )
        if not url_result.get("success"):
            result = {
                "success": False,
                "filename": relative_path,
                "error": url_result.get("error", "生成上传URL失败"),
            }
            self.file_finished.emit(result)
            return result

        def on_progress(uploaded, total):
            if self._is_cancelled:
                return
            self.file_progress.emit(uploaded, total)
            self.overall_progress.emit(processed_bytes + uploaded, total_bytes)

        def should_cancel():
            return self._is_cancelled

        result = self.crawler.upload_file_to_cloud(
            upload_url=url_result.get("upload_url"),
            file_path=file_path,
            token=self.cloud_info.get("token"),
            progress_callback=on_progress,
            cancel_callback=should_cancel,
        )

        if result.get("success"):
            file_result = {
                "success": True,
                "filename": relative_path,
                "message": result.get("message", "上传成功"),
            }
        elif result.get("cancelled"):
            file_result = {
                "success": False,
                "cancelled": True,
                "filename": relative_path,
                "error": result.get("error", "上传已取消"),
            }
        else:
            file_result = {
                "success": False,
                "filename": relative_path,
                "error": result.get("error", "上传失败"),
            }

        self.file_finished.emit(file_result)
        return file_result

    @classmethod
    def _extract_folder_id(cls, value):
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            return str(value)
        if isinstance(value, dict):
            for key in cls._FOLDER_ID_KEYS:
                identifier = value.get(key)
                if isinstance(identifier, (str, int)) and not isinstance(identifier, bool):
                    if identifier != "":
                        return str(identifier)
                elif isinstance(identifier, (dict, list)):
                    nested_identifier = cls._extract_folder_id(identifier)
                    if nested_identifier:
                        return nested_identifier
            for nested_key in ("data", "folder", "folderInfo", "file"):
                identifier = cls._extract_folder_id(value.get(nested_key))
                if identifier:
                    return identifier
        elif isinstance(value, list):
            for item in value:
                identifier = cls._extract_folder_id(item)
                if identifier:
                    return identifier
        return None
