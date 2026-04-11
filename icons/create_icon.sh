#!/bin/bash

# 创建图标脚本
# 使用方法: ./create_icon.sh icon.png

INPUT_FILE=$1

if [ -z "$INPUT_FILE" ]; then
    echo "请提供原始图片文件路径"
    echo "使用方法: ./create_icon.sh icon.png"
    exit 1
fi

# 创建临时目录
mkdir -p icons.iconset

# 生成各种尺寸
sips -z 16 16     "$INPUT_FILE" --out icons.iconset/icon_16x16.png
sips -z 32 32     "$INPUT_FILE" --out icons.iconset/icon_16x16@2x.png
sips -z 32 32     "$INPUT_FILE" --out icons.iconset/icon_32x32.png
sips -z 64 64     "$INPUT_FILE" --out icons.iconset/icon_32x32@2x.png
sips -z 128 128   "$INPUT_FILE" --out icons.iconset/icon_128x128.png
sips -z 256 256   "$INPUT_FILE" --out icons.iconset/icon_128x128@2x.png
sips -z 256 256   "$INPUT_FILE" --out icons.iconset/icon_256x256.png
sips -z 512 512   "$INPUT_FILE" --out icons.iconset/icon_256x256@2x.png
sips -z 512 512   "$INPUT_FILE" --out icons.iconset/icon_512x512.png
sips -z 1024 1024 "$INPUT_FILE" --out icons.iconset/icon_512x512@2x.png

# 生成 icns
iconutil -c icns icons.iconset -o icon.icns

# 清理临时目录
rm -rf icons.iconset

echo "图标文件已生成: icon.icns"