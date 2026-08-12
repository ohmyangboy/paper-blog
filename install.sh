#!/bin/bash
set -euo pipefail

# 这个脚本只服务源码开发；普通用户应通过 Homebrew 安装，避免污染全局 Python。
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "Paper 源码开发入口："
echo "  python3 \"$ROOT_DIR/paper.py\" --version"
echo "  python3 -m unittest discover -s \"$ROOT_DIR/tests\" -v"
echo ""
echo "面向用户的安装方式：brew install ohmyangboy/tap/paper"
