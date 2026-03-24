# 学习通教学资源管理系统 (XuexitongManager)

基于 PyQt6 开发的学习通教师端辅助工具。

## 🚀 自动发布指南 (CI/CD Guide)

本项目已集成 GitHub Actions 自动化构建与发布流程（CD），支持 **Windows、macOS (Intel/ARM)、Linux** 全平台打包。

### 📌 如何触发自动打包发布？

1. **更新版本号**
   - 打开 `core/config.py`。
   - 修改 `APP_TITLE` 中的版本号（例如：`V0.1` -> `V0.2`）。
   - **核心逻辑**：GitHub 会比对此版本号与已有的 Tag，若为新版本则触发发布。

2. **编写更新日志**
   - 打开 `RELEASE_NOTES.md`。
   - 在文件最顶部添加最新版本的更新说明（格式需保持一致，以 `# 版本说明` 开头）。

3. **推送代码**
   - 执行 `git add .`、`git commit -m "Bump version to V0.x"`。
   - 执行 `git push origin main`。

### 🛠 自动化流程说明

- **检测逻辑**：系统会自动提取 `core/config.py` 中的版本号并生成 `vX.X` 的标签。
- **全平台构建**：
  - 🍎 **macOS**: 打包两个版本（Apple Silicon 与 Intel 兼容版）。
  - 🪟 **Windows**: 编译为 `.exe`。
  - 🐧 **Linux**: 编译为二进制文件。
- **发布结果**：打包完成后，GitHub 会自动创建一个新的 **Release**，并将所有平台的安装包作为附件上传。

### 🏗 手动触发
如果你只想测试构建而不发布新版本：
- 进入 GitHub 项目页面的 **Actions** 选项卡。
- 选择 **Build and Release** 工作流。
- 点击 **Run workflow** 手动触发。
