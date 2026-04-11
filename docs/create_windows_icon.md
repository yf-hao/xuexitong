# 创建 Windows 操作系统的 App 图标文件 ico

本文介绍如何创建 `.ico` 格式的 Windows App 图标文件。

## 方法一：使用 ImageMagick（推荐）

### 安装 ImageMagick

**macOS:**
```bash
brew install imagemagick
```

**Linux:**
```bash
sudo apt-get install imagemagick
```

**Windows:**
从 [ImageMagick 官网](https://imagemagick.org/script/download.php) 下载安装。

### 转换命令

```bash
convert icon.png -resize 256x256 icon.ico
```

或者生成包含多种尺寸的 ico 文件：
```bash
convert icon.png -define icon:auto-resize=256,128,64,48,32,16 icon.ico
```

## 方法二：使用 Python 脚本

### 安装依赖

```bash
pip install Pillow
```

### Python 脚本

```python
from PIL import Image

# 打开原始图片
img = Image.open('icon.png')

# 定义多种尺寸
sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

# 保存为 ico 文件
img.save('icon.ico', format='ICO', sizes=sizes)
print("图标文件已生成: icon.ico")
```

## 方法三：使用在线工具

无需安装软件，直接上传 PNG 图片转换：

- [ConvertICO](https://convertio.co/zh/png-ico/)
- [ICO Convert](https://icoconvert.com/)
- [Online-Convert](https://image.online-convert.com/convert-to-ico)

## 一键脚本

将以下脚本保存为 `create_icon_win.py`：

```python
#!/usr/bin/env python3
"""
创建 Windows ico 图标文件
使用方法: python create_icon_win.py icon.png
"""

import sys
from PIL import Image

def create_ico(input_file):
    """从 PNG 创建 ico 文件"""
    try:
        img = Image.open(input_file)
        
        # 确保是 RGBA 模式
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        # 定义多种尺寸
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        
        # 保存为 ico
        img.save('icon.ico', format='ICO', sizes=sizes)
        print(f"✓ Windows 图标已生成: icon.ico")
        
    except Exception as e:
        print(f"✗ 错误: {e}")
        sys.exit(1)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("使用方法: python create_icon_win.py <input.png>")
        sys.exit(1)
    
    create_ico(sys.argv[1])
```

## 项目应用

在本项目中，将生成的 `icon.ico` 文件放入 `assets/` 目录即可。

相关配置文件：
- `xuexitong_win.spec` 中已配置 `icon='assets/icon.ico'`
