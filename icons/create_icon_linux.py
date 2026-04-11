#!/usr/bin/env python3
"""
创建 Linux PNG 图标文件（多种尺寸）
使用方法: python create_icon_linux.py icon.png
"""

import sys
import os
from PIL import Image

def create_linux_icons(input_file, output_dir='linux_icons'):
    """从 PNG 创建多种尺寸的 Linux 图标"""
    try:
        img = Image.open(input_file)
        
        # 确保是 RGBA 模式
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 定义常用尺寸
        sizes = [16, 22, 24, 32, 48, 64, 128, 256, 512]
        
        for size in sizes:
            resized = img.resize((size, size), Image.LANCZOS)
            output_path = os.path.join(output_dir, f'icon_{size}x{size}.png')
            resized.save(output_path)
            print(f"✓ 已生成: {output_path}")
        
        # 复制一个 512x512 作为主图标
        main_icon = os.path.join(output_dir, 'icon.png')
        img.resize((512, 512), Image.LANCZOS).save(main_icon)
        print(f"✓ 主图标: {main_icon}")
        
    except Exception as e:
        print(f"✗ 错误: {e}")
        sys.exit(1)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("使用方法: python create_icon_linux.py <input.png> [output_dir]")
        print("示例: python create_icon_linux.py icon.png linux_icons")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else 'linux_icons'
    
    create_linux_icons(input_file, output_dir)
