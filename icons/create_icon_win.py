#!/usr/bin/env python3
"""
创建 Windows ico 图标文件
使用方法: python create_icon_win.py icon.png
"""

import sys
from PIL import Image

def create_ico(input_file, output_file='icon.ico'):
    """从 PNG 创建 ico 文件"""
    try:
        img = Image.open(input_file)
        
        # 确保是 RGBA 模式
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        # 定义多种尺寸
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        
        # 保存为 ico
        img.save(output_file, format='ICO', sizes=sizes)
        print(f"✓ Windows 图标已生成: {output_file}")
        
    except Exception as e:
        print(f"✗ 错误: {e}")
        sys.exit(1)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("使用方法: python create_icon_win.py <input.png> [output.ico]")
        print("示例: python create_icon_win.py icon.png icon.ico")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'icon.ico'
    
    create_ico(input_file, output_file)
