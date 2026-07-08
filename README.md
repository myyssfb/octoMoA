# octoMoA

> **EN**: Local Mixture of Agents proxy — turn multiple AI models into one smarter endpoint.
>
> **CN**: 本地多模型聚合代理 —— 多个 AI 模型协作，一个端点搞定。

---

## EN

### What is octoMoA?

octoMoA is a local proxy server that implements **Mixture of Agents (MoA)** — a technique where multiple AI models answer the same question in parallel, then a designated aggregator model synthesizes the best response. It runs as a **Windows desktop app** with a system tray icon and an admin web UI.

**Any client that speaks OpenAI or Anthropic API can use it** — Claude Code, Cursor, Trae, Continue, or plain curl.

### Features

- **Dual-protocol inbound**: OpenAI `/v1/chat/completions` + Anthropic `/v1/messages`, auto-detected
- **4 aggregation strategies**: simple, vote, debate, cascade
- **Multi-backend**: configure endpoints as OpenAI or Anthropic type (DeepSeek, Mimo, Claude, etc.)
- **Hot-reload config**: change settings via admin panel, no restart needed
- **Model benchmarking**: auto-test all endpoints + MoA combinations
- **Desktop GUI**: PySide6 dashboard with endpoint management, orchestration config, and evaluation tabs
- **System tray**: minimize to tray, server runs in background
- **NSIS installer**: one-click Windows installation

### Quick Start

#### Option 1: Installer (recommended)

Download `octoMoA-Setup-1.0.0.exe` from [Releases](https://github.com/myyssfb/octoMoA/releases) and run it.

#### Option 2: From source

```bash
# Clone
git clone https://github.com/myyssfb/octoMoA.git
cd octoMoA

# Install dependencies
uv sync

# Run
uv run python app/desktop.py
```

### Configuration

1. Open the admin panel at `http://127.0.0.1:18990` (or use the desktop GUI)
2. Go to **Endpoints** — add your model providers:
   - DeepSeek: type `anthropic`, base URL `https://api.deepseek.com/anthropic`
   - Mimo: type `openai`, base URL `https://token-plan-cn.xiaomimimo.com/v1`
   - Claude: type `anthropic`, base URL `https://api.anthropic.com`
3. Go to **Orchestration** — select proposers, aggregator, and strategy
4. Start using it!

### Usage with Claude Code

```bash
# Set environment variables
export ANTHROPIC_BASE_URL=http://127.0.0.1:18990
export ANTHROPIC_API_KEY=any-value

# Use model "moa"
claude --model moa
```

### Usage with curl

```bash
# OpenAI format
curl http://127.0.0.1:18990/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"moa","messages":[{"role":"user","content":"hello"}]}'

# Anthropic format
curl http://127.0.0.1:18990/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model":"moa","max_tokens":100,"messages":[{"role":"user","content":"hello"}]}'
```

### Architecture

```
Client (OpenAI / Anthropic format)
  │
  ▼
┌─────────────────────────────┐
│  routes.py                  │  ← auto-detect protocol
│  /v1/chat/completions       │
│  /v1/messages               │
└─────────┬───────────────────┘
          │
          ▼
┌─────────────────────────────┐
│  engine.py                  │  ← MoA orchestration
│  strategy: simple|vote|     │
│  debate|cascade             │
│                             │
│  ┌─────┐ ┌─────┐ ┌─────┐  │
│  │ LLM │ │ LLM │ │ LLM │  │  ← parallel proposers
│  └──┬──┘ └──┬──┘ └──┬──┘  │
│     └───────┼───────┘      │
│             ▼              │
│      ┌───────────┐         │
│      │ Aggregator│         │  ← synthesize final answer
│      └───────────┘         │
└─────────────────────────────┘
```

### Tech Stack

- Python 3.12, FastAPI, httpx, aiosqlite
- PySide6 (desktop GUI)
- PyInstaller + NSIS (packaging)

---

## CN

### octoMoA 是什么？

octoMoA 是一个本地代理服务器，实现了 **MoA（Mixture of Agents）** 技术 —— 多个 AI 模型同时回答同一个问题，再由一个聚合模型综合出最佳答案。它以 **Windows 桌面应用** 形式运行，带系统托盘图标和管理面板。

**任何支持 OpenAI 或 Anthropic API 的客户端都能直接使用** —— Claude Code、Cursor、Trae、Continue 或 curl。

### 功能特性

- **双协议入站**：OpenAI `/v1/chat/completions` + Anthropic `/v1/messages`，自动识别
- **4 种聚合策略**：simple（简单合并）、vote（投票选优）、debate（辩论改进）、cascade（分层精炼）
- **多后端支持**：端点可配置为 OpenAI 或 Anthropic 类型（DeepSeek、Mimo、Claude 等）
- **热重载配置**：通过管理面板修改设置，无需重启
- **模型评测**：自动测试所有端点 + MoA 组合的得分
- **桌面 GUI**：PySide6 仪表盘，含端点管理、编排配置、模型评测
- **系统托盘**：最小化到托盘，服务后台运行
- **NSIS 安装包**：一键安装

### 快速开始

#### 方式一：安装包（推荐）

从 [Releases](https://github.com/myyssfb/octoMoA/releases) 下载 `octoMoA-Setup-1.0.0.exe`，双击安装。

#### 方式二：源码运行

```bash
# 克隆
git clone https://github.com/myyssfb/octoMoA.git
cd octoMoA

# 安装依赖
uv sync

# 运行
uv run python app/desktop.py
```

### 配置指南

1. 打开管理面板 `http://127.0.0.1:18990`（或使用桌面 GUI）
2. 进入 **端点管理** —— 添加模型提供商：
   - DeepSeek：类型选 `anthropic`，Base URL 填 `https://api.deepseek.com/anthropic`
   - Mimo：类型选 `openai`，Base URL 填 `https://token-plan-cn.xiaomimimo.com/v1`
   - Claude：类型选 `anthropic`，Base URL 填 `https://api.anthropic.com`
3. 进入 **编排配置** —— 选择提案者、聚合器和策略
4. 开始使用！

### 在 Claude Code 中使用

```bash
# 设置环境变量
export ANTHROPIC_BASE_URL=http://127.0.0.1:18990
export ANTHROPIC_API_KEY=任意值

# 使用 moa 模型
claude --model moa
```

### 用 curl 调用

```bash
# OpenAI 格式
curl http://127.0.0.1:18990/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"moa","messages":[{"role":"user","content":"你好"}]}'

# Anthropic 格式
curl http://127.0.0.1:18990/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model":"moa","max_tokens":100,"messages":[{"role":"user","content":"你好"}]}'
```

### 系统架构

```
客户端（OpenAI / Anthropic 格式）
  │
  ▼
┌─────────────────────────────┐
│  routes.py                  │  ← 自动识别协议
│  /v1/chat/completions       │
│  /v1/messages               │
└─────────┬───────────────────┘
          │
          ▼
┌─────────────────────────────┐
│  engine.py                  │  ← MoA 编排
│  策略: simple|vote|         │
│  debate|cascade             │
│                             │
│  ┌─────┐ ┌─────┐ ┌─────┐  │
│  │ LLM │ │ LLM │ │ LLM │  │  ← 并行提案者
│  └──┬──┘ └──┬──┘ └──┬──┘  │
│     └───────┼───────┘      │
│             ▼              │
│      ┌───────────┐         │
│      │  聚合器   │         │  ← 综合最终答案
│      └───────────┘         │
└─────────────────────────────┘
```

### 技术栈

- Python 3.12、FastAPI、httpx、aiosqlite
- PySide6（桌面 GUI）
- PyInstaller + NSIS（打包分发）

### License

MIT
