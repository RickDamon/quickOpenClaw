# OpenClaw

[English](#english) | [中文](#中文)

---

# English

Quick start an OpenClaw service with Docker.

## Environment Variables

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `ACCESS_TOKEN` | Access authentication token | `your-access-token` |

### AI Model Configuration (at least one required)

#### OpenAI
| Variable | Description | Example |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | `sk-...` |
| `OPENAI_BASE_URL` | OpenAI API base URL (optional) | `https://api.openai.com/v1` |

#### Anthropic
| Variable | Description | Example |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Anthropic API key | `sk-ant-...` |
| `ANTHROPIC_BASE_URL` | Anthropic API base URL (optional) | `https://api.anthropic.com` |

#### DeepSeek
| Variable | Description | Example |
|----------|-------------|---------|
| `DEEPSEEK_API_KEY` | DeepSeek API key | `sk-...` |
| `DEEPSEEK_BASE_URL` | DeepSeek API base URL (optional) | `https://api.deepseek.com/v1` |

### Telegram Integration (optional)

| Variable | Description | Example |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather | `123456789:ABC...` |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID | `987654321` |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `DEFAULT_MODEL` | Default model to use | `openai/gpt-4o` |

## Quick Start

### 1. Build Image

```bash
docker build -t openclaw .
```

### 2. Run with OpenAI

```bash
docker run -d \
  -p 8686:8686 \
  -e ACCESS_TOKEN="your-access-token" \
  -e OPENAI_API_KEY="sk-your-openai-key" \
  --name openclaw \
  openclaw
```

### 3. Run with DeepSeek

```bash
docker run -d \
  -p 8686:8686 \
  -e ACCESS_TOKEN="your-access-token" \
  -e DEEPSEEK_API_KEY="sk-your-deepseek-key" \
  -e DEFAULT_MODEL="deepseek/deepseek-chat" \
  --name openclaw \
  openclaw
```

### 4. Run with Anthropic Claude

```bash
docker run -d \
  -p 8686:8686 \
  -e ACCESS_TOKEN="your-access-token" \
  -e ANTHROPIC_API_KEY="sk-ant-your-anthropic-key" \
  -e DEFAULT_MODEL="anthropic/claude-sonnet-4-20250514" \
  --name openclaw \
  openclaw
```

### 5. Run with Multiple Models

```bash
docker run -d \
  -p 8686:8686 \
  -e ACCESS_TOKEN="your-access-token" \
  -e OPENAI_API_KEY="sk-your-openai-key" \
  -e ANTHROPIC_API_KEY="sk-ant-your-anthropic-key" \
  -e DEEPSEEK_API_KEY="sk-your-deepseek-key" \
  --name openclaw \
  openclaw
```

### 6. Run with Telegram Integration

```bash
docker run -d \
  -p 8686:8686 \
  -e ACCESS_TOKEN="your-access-token" \
  -e OPENAI_API_KEY="sk-your-openai-key" \
  -e TELEGRAM_BOT_TOKEN="your-bot-token" \
  -e TELEGRAM_CHAT_ID="your-chat-id" \
  --name openclaw \
  openclaw
```

### 7. Access Service

Open browser: `http://localhost:8686`

First visit will redirect to the authenticated URL with token.

## Supported Models

### OpenAI
- `openai/gpt-4o` - GPT-4o
- `openai/gpt-4o-mini` - GPT-4o Mini

### Anthropic
- `anthropic/claude-sonnet-4-20250514` - Claude Sonnet 4
- `anthropic/claude-3-5-sonnet-20241022` - Claude 3.5 Sonnet

### DeepSeek
- `deepseek/deepseek-chat` - DeepSeek Chat (general conversation)
- `deepseek/deepseek-coder` - DeepSeek Coder (code-focused)
- `deepseek/deepseek-reasoner` - DeepSeek Reasoner (CoT reasoning)

## Telegram Setup

1. Create a bot via `@BotFather` in Telegram and get the bot token
2. Get your chat ID from `@userinfobot`
3. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` environment variables
4. Restart OpenClaw

Now you can control OpenClaw from your phone via Telegram!

## Project Structure

```
.
├── Dockerfile        # Docker image build file
├── openclaw.json     # OpenClaw configuration
├── start.sh          # Startup script (Docker)
├── start-local.sh    # Local startup script
├── .env              # Environment variables
└── README.md
```

---

# 中文

快速启动一个 OpenClaw 服务的 Docker 镜像。

## 环境变量配置

### 必需的环境变量

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `ACCESS_TOKEN` | 访问认证令牌 | `your-access-token` |

### AI 模型配置（至少配置一个）

#### OpenAI 配置
| 变量名 | 说明 | 示例 |
|--------|------|------|
| `OPENAI_API_KEY` | OpenAI API 密钥 | `sk-...` |
| `OPENAI_BASE_URL` | OpenAI API 基础URL（可选） | `https://api.openai.com/v1` |

#### Anthropic 配置
| 变量名 | 说明 | 示例 |
|--------|------|------|
| `ANTHROPIC_API_KEY` | Anthropic API 密钥 | `sk-ant-...` |
| `ANTHROPIC_BASE_URL` | Anthropic API 基础URL（可选） | `https://api.anthropic.com` |

#### DeepSeek 配置
| 变量名 | 说明 | 示例 |
|--------|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | `sk-...` |
| `DEEPSEEK_BASE_URL` | DeepSeek API 基础URL（可选） | `https://api.deepseek.com/v1` |

### Telegram 联动配置（可选）

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `TELEGRAM_BOT_TOKEN` | 从 @BotFather 获取的 Bot Token | `123456789:ABC...` |
| `TELEGRAM_CHAT_ID` | 你的 Telegram Chat ID | `987654321` |

### 可选配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `DEFAULT_MODEL` | 默认使用的模型 | `openai/gpt-4o` |

## 快速启动

### 1. 构建镜像

```bash
docker build -t openclaw .
```

### 2. 运行容器（使用 OpenAI）

```bash
docker run -d \
  -p 8686:8686 \
  -e ACCESS_TOKEN="your-access-token" \
  -e OPENAI_API_KEY="sk-your-openai-key" \
  --name openclaw \
  openclaw
```

### 3. 运行容器（使用 DeepSeek）

```bash
docker run -d \
  -p 8686:8686 \
  -e ACCESS_TOKEN="your-access-token" \
  -e DEEPSEEK_API_KEY="sk-your-deepseek-key" \
  -e DEFAULT_MODEL="deepseek/deepseek-chat" \
  --name openclaw \
  openclaw
```

### 4. 运行容器（使用 Anthropic Claude）

```bash
docker run -d \
  -p 8686:8686 \
  -e ACCESS_TOKEN="your-access-token" \
  -e ANTHROPIC_API_KEY="sk-ant-your-anthropic-key" \
  -e DEFAULT_MODEL="anthropic/claude-sonnet-4-20250514" \
  --name openclaw \
  openclaw
```

### 5. 运行容器（同时配置多个模型）

```bash
docker run -d \
  -p 8686:8686 \
  -e ACCESS_TOKEN="your-access-token" \
  -e OPENAI_API_KEY="sk-your-openai-key" \
  -e ANTHROPIC_API_KEY="sk-ant-your-anthropic-key" \
  -e DEEPSEEK_API_KEY="sk-your-deepseek-key" \
  --name openclaw \
  openclaw
```

### 6. 运行容器（启用 Telegram 联动）

```bash
docker run -d \
  -p 8686:8686 \
  -e ACCESS_TOKEN="your-access-token" \
  -e OPENAI_API_KEY="sk-your-openai-key" \
  -e TELEGRAM_BOT_TOKEN="your-bot-token" \
  -e TELEGRAM_CHAT_ID="your-chat-id" \
  --name openclaw \
  openclaw
```

### 7. 访问服务

浏览器打开：`http://localhost:8686`

首次访问会自动跳转到带 token 的认证地址。

## 支持的模型

### OpenAI 模型
- `openai/gpt-4o` - GPT-4o
- `openai/gpt-4o-mini` - GPT-4o Mini

### Anthropic 模型
- `anthropic/claude-sonnet-4-20250514` - Claude Sonnet 4
- `anthropic/claude-3-5-sonnet-20241022` - Claude 3.5 Sonnet

### DeepSeek 模型
- `deepseek/deepseek-chat` - DeepSeek Chat（通用对话模型）
- `deepseek/deepseek-coder` - DeepSeek Coder（代码专用模型）
- `deepseek/deepseek-reasoner` - DeepSeek Reasoner（推理模型，支持CoT）

## Telegram 联动设置

1. 在 Telegram 中搜索 `@BotFather`，创建新 Bot 并获取 Token
2. 搜索 `@userinfobot` 获取你的 Chat ID
3. 设置环境变量 `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID`
4. 重启 OpenClaw

配置完成后，你就可以通过手机 Telegram 远程控制 OpenClaw 了！

## 配置说明

配置文件 `openclaw.json` 主要包含：

- **models**: 模型提供者配置（OpenAI、Anthropic、DeepSeek）
- **agents**: Agent 默认配置（工作目录、并发数等）
- **tools**: 工具开关配置
- **gateway**: 网关配置（端口、认证模式等）
- **channels**: 社交媒体联动配置（Telegram 等）

## 目录结构

```
.
├── Dockerfile        # Docker 镜像构建文件
├── openclaw.json     # OpenClaw 配置文件
├── start.sh          # 启动脚本（Docker 用）
├── start-local.sh    # 本地启动脚本
├── .env              # 环境变量配置
└── README.md
```
