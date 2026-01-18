#!/bin/bash
# 构建脚本 - 在 Linux/WSL 中运行

set -e

echo "=== Python APK Builder ==="

# 检查是否安装了必要的工具
check_deps() {
    echo "[1/4] 检查依赖..."

    if ! command -v python3 &> /dev/null; then
        echo "错误: 未找到 python3"
        exit 1
    fi

    if ! python3 -c "import buildozer" 2>/dev/null; then
        echo "安装 buildozer..."
        pip install buildozer cython kivy
    fi

    echo "依赖检查完成"
}

# 安装系统依赖 (Ubuntu/Debian)
install_system_deps() {
    echo "[2/4] 检查系统依赖..."

    if command -v apt &> /dev/null; then
        sudo apt update
        sudo apt install -y \
            python3-pip \
            build-essential \
            git \
            zip \
            unzip \
            openjdk-17-jdk \
            autoconf \
            libtool \
            pkg-config \
            zlib1g-dev \
            libncurses5-dev \
            libncursesw5-dev \
            libtinfo5 \
            cmake \
            libffi-dev \
            libssl-dev
    fi
}

# 清理旧构建
clean() {
    echo "清理旧构建文件..."
    rm -rf .buildozer bin
}

# 构建 APK
build_debug() {
    echo "[3/4] 开始构建 Debug APK..."
    buildozer android debug
}

build_release() {
    echo "[3/4] 开始构建 Release APK..."
    buildozer android release
}

# 显示结果
show_result() {
    echo "[4/4] 构建完成!"
    echo ""
    if [ -d "bin" ]; then
        echo "APK 文件位置:"
        ls -lh bin/*.apk 2>/dev/null || echo "未找到 APK 文件"
    fi
}

# 主流程
case "${1:-debug}" in
    "debug")
        check_deps
        build_debug
        show_result
        ;;
    "release")
        check_deps
        build_release
        show_result
        ;;
    "deps")
        install_system_deps
        check_deps
        ;;
    "clean")
        clean
        ;;
    *)
        echo "用法: ./build.sh [debug|release|deps|clean]"
        echo "  debug   - 构建调试版 APK (默认)"
        echo "  release - 构建发布版 APK"
        echo "  deps    - 安装系统依赖"
        echo "  clean   - 清理构建文件"
        ;;
esac
