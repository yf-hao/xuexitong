# 🚀 自动打包发布手册 (CI/CD Guide)

本项目已集成 GitHub Actions 自动化构建与发布流程（CD）。只需简单操作，即可自动完成 Windows、macOS (Intel/ARM) 及 Linux 的打包。

---

## 🛠 如何触发发布 (How to Trigger)

### 1. 修改版本号
打开 `core/config.py`，修改 `APP_TITLE` 中的版本号：
```python
APP_TITLE = "学习通教学资源管理系统V0.2"  # 将 V0.x 修改为新版本号
```

### 2. 更新日志 (可选但建议)
在 `RELEASE_NOTES.md` 的最上方添加最新的更新内容。GitHub 会自动提取这一部分作为 Release 的说明。

### 3. 推送代码
将修改后的代码推送到 GitHub 的 `main` 分支：
```bash
git add .
git commit -m "Bump version to v0.2"
git push origin main
```

---

## 📦 工作流执行过程 (What Happens Next)

当你推送到 `main` 分支后，GitHub Actions 会执行以下步骤：

1.  **版本校验**：自动比对 `core/config.py` 中的版本号。如果发现标签库中不存在对应的 `vX.X` 标签，则触发构建。
2.  **并行构建**：
    *   🍎 **macOS (Apple Silicon)**: 原生 ARM 架构打包。
    *   🍎 **macOS (Intel)**: 交叉编译为 Intel 架构。
    *   🪟 **Windows**: 打包为 `.exe`。
    *   🐧 **Linux**: 打包为可执行文件及资源。
3.  **自动发布**：
    *   自动创建 GitHub Release 页面。
    *   自动上传各平台的压缩包（`.tar.gz` 和 `.zip`）。
    *   自动提取 `RELEASE_NOTES.md` 中的内容填入发布文档。

---

## ⚙️ 手动触发 (Manual Trigger)

如果你需要手动测试打包流程，可以在 GitHub 仓库页面：
1. 点击 **Actions** 选项卡。
2. 选中左侧的 **Build and Release**。
3. 点击右侧的 **Run workflow** -> **Run workflow**。

---

## 📂 产物说明 (Artifacts)
构建成功后，你可以在 GitHub 的 **Releases** 页面下载：
- `XuexitongManager-windows.zip` (Windows)
- `XuexitongManager-macos-arm.tar.gz` (Mac M1/M2/M3/M4)
- `XuexitongManager-macos-intel.tar.gz` (Mac Intel)
- `XuexitongManager-linux.tar.gz` (Linux)
