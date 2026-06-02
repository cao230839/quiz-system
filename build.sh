#!/usr/bin/env bash
# 安装系统依赖
apt-get update && apt-get install -y \
    poppler-utils \
    libmagic1 \
    gcc \
    python3-dev

# 安装 Python 依赖
pip install -r requirements.txt