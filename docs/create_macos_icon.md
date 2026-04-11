# 创建 macOS 操作系统的 App 图标文件 icons

> 作者：小弟调调  
> 发布日期：2022-11-08  
> 来源：[腾讯云开发者社区](https://cloud.tencent.com/developer/article/2154591)

本文介绍如何在 macOS 中创建 `.icns` 格式的 App 图标文件。

## 步骤

### 1. 准备原始图片

准备一张 1024×1024 像素的 PNG 图片，命名为 `icon.png`

### 2. 创建 .iconset 文件夹

```bash
mkdir icons.iconset
```

### 3. 生成多种尺寸的 PNG 图片

使用 `sips` 命令生成不同尺寸的图片：

```bash
sips -z 16 16     icon.png --out icons.iconset/icon_16x16.png
sips -z 32 32     icon.png --out icons.iconset/icon_16x16@2x.png
sips -z 32 32     icon.png --out icons.iconset/icon_32x32.png
sips -z 64 64     icon.png --out icons.iconset/icon_32x32@2x.png
sips -z 128 128   icon.png --out icons.iconset/icon_128x128.png
sips -z 256 256   icon.png --out icons.iconset/icon_128x128@2x.png
sips -z 256 256   icon.png --out icons.iconset/icon_256x256.png
sips -z 512 512   icon.png --out icons.iconset/icon_256x256@2x.png
sips -z 512 512   icon.png --out icons.iconset/icon_512x512.png
sips -z 1024 1024 icon.png --out icons.iconset/icon_512x512@2x.png
```

### 4. 生成 icns 文件

```bash
iconutil -c icns icons.iconset -o icon.icns
```

## 一键脚本

可以将以上步骤整合为一个脚本：

```bash
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
```

## 项目应用

在本项目中，将生成的 `icon.icns` 文件放入 `assets/` 目录即可。

相关配置文件：
- `xuexitong_mac.spec` 中已配置 `icon='assets/icon.icns'`
