from __future__ import annotations
import os
import re
import yaml
from pydantic import BaseModel

# ── 模型端点（可复用的连接信息） ──

class ModelEndpoint(BaseModel):
    """一个可复用的模型连接配置。name 是唯一标识，可在 proposers/aggregator 中引用。"""
    name: str = ""
    api_type: str = "openai"
    base_url: str = ""
    api_key: str = ""
    model: str = ""


# ── Proposer / Aggregator 引用节点 ──

class ProposerRef(BaseModel):
    """proposer 引用：用哪个 endpoint、给什么标签名。"""
    endpoint: str                  # 引用 endpoints[name]
    label: str = ""                # 在聚合 prompt 中显示的名字，默认用 endpoint name
    role: str = "fast"             # fast | strong — 用于日志/分析
    weight: float = 1.0            # 该 proposer 的权重（投票策略用）


class AggregatorRef(BaseModel):
    """aggregator 引用。"""
    endpoint: str = ""
    system_prompt: str = ""


# ── 服务配置 ──

class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 18990
    api_key: str = ""


class MoaConfig(BaseModel):
    strategy: str = "simple"       # simple | vote | debate | cascade
    timeout: int = 120
    stream_timeout: int = 300      # 流式场景的超时更长
    proposer_temperature: float = 0.6   # 提案者高温 → 多样性
    aggregator_temperature: float = 0.4 # 聚合器低温 → 稳定


# ── 顶层 ──

class AppConfig(BaseModel):
    endpoints: dict[str, ModelEndpoint] = {}
    proposers: list[ProposerRef] = []
    aggregator: AggregatorRef = AggregatorRef(endpoint="")
    server: ServerConfig = ServerConfig()
    moa: MoaConfig = MoaConfig()

    # ── 便捷方法：按引用解析实际 endpoint ──

    def get_endpoint(self, ref_name: str) -> ModelEndpoint:
        if ref_name not in self.endpoints:
            raise KeyError(f"Endpoint '{ref_name}' not found in config.endpoints. Available: {list(self.endpoints.keys())}")
        return self.endpoints[ref_name]


# ── 兼容旧版 config.yaml（如果没写 endpoints 字典，直接用 proposer 内联字段）──

def _get_base_dir() -> str:
    """获取基础目录：PyInstaller 打包时用 _internal 目录，否则用脚本目录。"""
    if getattr(os.sys, 'frozen', False):
        exe_dir = os.path.dirname(os.sys.executable)
        internal = os.path.join(exe_dir, '_internal')
        if os.path.isdir(internal):
            return internal
        return exe_dir
    return os.path.dirname(os.path.abspath(__file__))


def load_config(path: str | None = None) -> AppConfig:
    if path is None:
        path = os.environ.get("MOA_CONFIG", "config.yaml")
    # 如果是相对路径，基于 base_dir 解析
    if not os.path.isabs(path):
        base = _get_base_dir()
        candidate = os.path.join(base, path)
        if os.path.exists(candidate):
            path = candidate
    with open(path, encoding="utf-8") as f:
        raw = f.read()

    def expand(m: re.Match) -> str:
        return os.environ.get(m.group(1), "")

    raw = re.sub(r"\$\{(\w+)\}", expand, raw)
    data = yaml.safe_load(raw)

    # 兼容旧格式：如果 data 里没有 endpoints，把 proposers/aggregator 的内联字段自动迁移到 endpoints
    if "endpoints" not in data:
        data = _migrate_legacy(data)

    return AppConfig(**data)


def _migrate_legacy(data: dict) -> dict:
    """将旧版 (proposers 内联 base_url/api_key/model) 转为新版 endpoints 格式。"""
    endpoints = {}
    new_proposers = []

    for i, p in enumerate(data.get("proposers", [])):
        ep_name = p.get("name", f"proposer-{i}")
        endpoints[ep_name] = {
            "name": ep_name,
            "api_type": p.get("api_type", "openai"),
            "base_url": p["base_url"],
            "api_key": p["api_key"],
            "model": p["model"],
        }
        new_proposers.append({
            "endpoint": ep_name,
            "label": p.get("name", ep_name),
        })

    data["proposers"] = new_proposers

    # aggregator
    agg = data.get("aggregator", {})
    if agg and "base_url" in agg:
        ep_name = agg.get("endpoint", "aggregator")
        endpoints[ep_name] = {
            "name": ep_name,
            "api_type": agg.get("api_type", "openai"),
            "base_url": agg["base_url"],
            "api_key": agg["api_key"],
            "model": agg["model"],
        }
        data["aggregator"] = {"endpoint": ep_name}

    data["endpoints"] = endpoints
    return data
