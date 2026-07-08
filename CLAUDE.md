# CLAUDE.md

## 项目概述

MoA Proxy — 本地 OpenAI 兼容 API 代理，通过 Mixture of Agents 聚合多个 LLM 模型的结果，对外暴露统一端点。

配合 cc-switch 本地代理使用，使编程工具（Claude Code、Cursor、Codex）可以透明地使用 MoA 聚合后的模型。

## 技术栈

- Python 3.12+（uv 管理依赖）
- FastAPI + httpx
- 外部依赖：cc-switch（本地代理）

## 开发命令

```bash
# 安装依赖
uv sync

# 启动服务
uv run uvicorn app.main:app --reload --port 18990
```

## 架构

```
编程工具 → cc-switch → MoA Proxy → 多个 LLM API
                          ↓
                    Proposer Models (并行)
                          ↓
                    Aggregator Model (汇总)
                          ↓
                    返回最终响应
```
