#!/bin/bash

set -e

# 加载环境变量
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# 创建配置目录
mkdir -p ~/.openclaw

# 复制配置文件
cp openclaw.json ~/.openclaw/openclaw.json

echo "Starting OpenClaw with DeepSeek..."
echo "Access Token: $ACCESS_TOKEN"
echo "Default Model: $DEFAULT_MODEL"
echo "DeepSeek API Key: ${DEEPSEEK_API_KEY:0:10}..."

# 检查 openclaw 是否已安装
if ! command -v openclaw &> /dev/null; then
    echo "Installing openclaw globally..."
    npm install -g openclaw@latest
fi

# 启动 openclaw
echo "Starting OpenClaw gateway on port 18789..."
openclaw gateway --allow-unconfigured