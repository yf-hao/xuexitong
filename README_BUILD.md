# XuexitongManager 打包说明

## 快速开始

### macOS / Linux
```bash
# 1. 赋予脚本执行权限
chmod +x build.sh

# 2. 运行构建脚本
./build.sh
```

生成的应用位于：
- macOS: `dist/XuexitongManager.app`
- Linux: `dist/XuexitongManager`

### Windows
```cmd
# 双击运行或在命令行执行
build.bat
```

生成的应用位于：`dist\XuexitongManager.exe`

---

## 手动打包（不使用脚本）

### 安装 PyInstaller
```bash
pip install pyinstaller
```

### 使用 spec 文件打包
```bash
# 清理旧文件
rm -rf build dist  # Linux/macOS
# 或
rmdir /s /q build dist  # Windows

# 执行打包
pyinstaller --clean xuexitong.spec
```

---

## 配置文件说明

### `xuexitong.spec`
PyInstaller 高级配置文件，包含：
- **hiddenimports**: 隐式导入的模块列表
- **excludes**: 排除不需要的大型库（减小体积）
- **datas**: 资源文件配置
- **console**: 设为 `False` 隐藏控制台窗口

### 自定义配置

#### 添加应用图标
1. 准备一个 `.ico` 文件（Windows）或 `.icns` 文件（macOS）
2. 在 `xuexitong.spec` 中修改：
   ```python
   icon='path/to/icon.ico'  # Windows
   # 或
   icon='path/to/icon.icns'  # macOS
   ```

#### 添加资源文件
在 `datas` 列表中添加：
```python
datas=[
    ('resources/images', 'resources/images'),
    ('config.json', '.'),
],
```

#### 减小文件大小
1. 在 `excludes` 中添加不需要的库
2. 使用 UPX 压缩（已默认启用）
3. 考虑使用文件夹模式而非单文件模式

---

## 常见问题

### 1. 打包后运行报错
**解决方法**：
- 修改 `xuexitong.spec` 中 `console=True` 查看错误
- 检查 `hiddenimports` 是否包含所有动态导入的模块

### 2. 文件过大
**解决方法**：
- 移除不需要的库（在 `excludes` 中添加）
- 考虑使用虚拟环境仅安装必需的包
- 使用文件夹模式：修改 spec 文件，将单文件打包改为多文件

### 3. macOS 提示"已损坏"
**解决方法**：
```bash
# 移除隔离属性
xattr -cr dist/XuexitongManager.app

# 或签名应用（需要开发者账号）
codesign --force --deep --sign - dist/XuexitongManager.app
```

### 4. Windows Defender 误报
**解决方法**：
- 正常现象，可添加白名单
- 或进行代码签名（需要证书）

---

## 分发建议

### macOS
- 压缩成 `.zip` 或创建 `.dmg` 安装包
- 建议进行代码签名和公证（需要苹果开发者账号）

### Windows
- 可使用 NSIS 或 Inno Setup 创建安装程序
- 建议进行代码签名（需要证书）

### Linux
- 打包成 `.AppImage` 或 `.deb`/`.rpm` 包
- 或直接分发二进制文件

---

## 版本信息

- PyInstaller: >= 5.0
- Python: >= 3.8
- PyQt6: >= 6.0

---

## 许可证

请确保分发的应用符合所有依赖库的许可证要求。
