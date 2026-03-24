#!/bin/bash
# XuexitongManager 构建脚本 (macOS/Linux)
# 用法: ./build.sh

set -e  # 遇到错误立即退出

echo "========================================="
echo "  XuexitongManager 构建脚本"
echo "========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 检查 Python 环境
echo -e "${YELLOW}[1/5] 检查 Python 环境...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: 未找到 python3${NC}"
    exit 1
fi
python3 --version

# 安装依赖
echo -e "${YELLOW}[2/5] 检查并安装依赖...${NC}"
if [ -f "requirements.txt" ]; then
    echo "  正在从 requirements.txt 安装依赖..."
    python3 -m pip install -r requirements.txt -q
    echo "  依赖安装完成"
else
    echo "  未找到 requirements.txt，跳过依赖安装"
fi

# 清理旧的构建文件
echo -e "${YELLOW}[3/5] 清理旧的构建文件...${NC}"
rm -rf build dist
echo "  已清理 build/ 和 dist/ 目录"

# 开始打包
echo -e "${YELLOW}[4/5] 开始打包应用...${NC}"
echo "  使用配置文件: xuexitong_mac.spec"
pyinstaller --clean xuexitong_mac.spec

# 检查构建结果
echo -e "${YELLOW}[5/6] 检查构建结果...${NC}"
if [ -f "dist/XuexitongManager" ]; then
    echo -e "${GREEN}✓ 单一可执行文件构建成功!${NC}"
    echo "  位置: dist/XuexitongManager"
    echo "  大小: $(du -sh dist/XuexitongManager | cut -f1)"
    # 添加执行权限
    chmod +x dist/XuexitongManager
    echo -e "${GREEN}✓ 已添加执行权限${NC}"
elif [ -d "dist/XuexitongManager.app" ]; then
    echo -e "${GREEN}✓ macOS 应用构建成功!${NC}"
    echo "  位置: dist/XuexitongManager.app"
    echo "  大小: $(du -sh dist/XuexitongManager.app | cut -f1)"
else
    echo -e "${RED}✗ 构建失败，请检查错误信息${NC}"
    exit 1
fi

# 复制 data 文件夹到 dist 目录
echo -e "${YELLOW}[6/6] 复制 data 文件夹...${NC}"
if [ -d "data" ]; then
    cp -r data dist/
    echo -e "${GREEN}✓ 已复制 data 文件夹到 dist/data${NC}"
else
    echo -e "${YELLOW}⚠ 未找到 data 文件夹，跳过${NC}"
fi

echo ""
echo "========================================="
echo -e "${GREEN}构建完成!${NC}"
echo "========================================="
