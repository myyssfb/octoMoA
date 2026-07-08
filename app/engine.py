"""
MoA 聚合引擎 — 支持流式 + 多策略 + 容错
配置格式见 config.yaml，引擎通过 AppConfig.get_endpoint() 解析引用。
"""

import json
import logging
import asyncio
from dataclasses import dataclass, field
import httpx
from app.config import AppConfig, ModelEndpoint, ProposerRef

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    endpoint_name: str = ""
    model: str = ""


# ── helpers ──

def _proposer_label(prop: ProposerRef) -> str:
    return prop.label or prop.endpoint


# ── low-level API callers ──

async def _call_openai_collect(
    client: httpx.AsyncClient,
    endpoint: ModelEndpoint,
    messages: list[dict],
    timeout: int,
    temperature: float = 0.7,
) -> tuple[str, TokenUsage]:
    """调用 OpenAI 兼容 API 非流式，收集完整回复 + token usage。"""
    headers = {
        "Authorization": f"Bearer {endpoint.api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": endpoint.model, "messages": messages, "stream": False, "temperature": temperature}
    resp = await client.post(
        f"{endpoint.base_url}/chat/completions",
        json=payload,
        headers=headers,
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    token_usage = TokenUsage(
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
        total_tokens=usage.get("total_tokens", 0),
        endpoint_name=endpoint.name,
        model=endpoint.model,
    )
    return content, token_usage


async def _call_anthropic_collect(
    client: httpx.AsyncClient,
    endpoint: ModelEndpoint,
    messages: list[dict],
    timeout: int,
    temperature: float = 0.7,
) -> tuple[str, TokenUsage]:
    """调用 Anthropic API 非流式，收集完整回复 + token usage。"""
    headers = {
        "x-api-key": endpoint.api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    # Anthropic 格式：system 单独传，messages 只含 user/assistant
    system_msg = ""
    api_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system_msg = msg["content"]
        else:
            api_messages.append(msg)

    payload = {
        "model": endpoint.model,
        "max_tokens": 4096,
        "messages": api_messages,
        "temperature": temperature,
    }
    if system_msg:
        payload["system"] = system_msg

    resp = await client.post(
        f"{endpoint.base_url}/messages",
        json=payload,
        headers=headers,
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["content"][0]["text"]
    usage = data.get("usage", {})
    token_usage = TokenUsage(
        prompt_tokens=usage.get("input_tokens", 0),
        completion_tokens=usage.get("output_tokens", 0),
        total_tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        endpoint_name=endpoint.name,
        model=endpoint.model,
    )
    return content, token_usage


async def _call_openai_stream(
    client: httpx.AsyncClient,
    endpoint: ModelEndpoint,
    messages: list[dict],
    timeout: int,
):
    """调用 OpenAI 兼容 API 流式，yield each chunk dict."""
    headers = {
        "Authorization": f"Bearer {endpoint.api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": endpoint.model, "messages": messages, "stream": True}
    resp = await client.post(
        f"{endpoint.base_url}/chat/completions",
        json=payload,
        headers=headers,
        timeout=timeout,
    )
    resp.raise_for_status()
    async for line in resp.aiter_lines():
        if line.startswith("data: "):
            s = line[6:].strip()
            if s == "[DONE]":
                break
            try:
                yield json.loads(s)
            except json.JSONDecodeError:
                continue


async def _call_anthropic_stream(
    client: httpx.AsyncClient,
    endpoint: ModelEndpoint,
    messages: list[dict],
    timeout: int,
):
    """调用 Anthropic API 流式，yield each event dict."""
    headers = {
        "x-api-key": endpoint.api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    system_msg = ""
    api_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system_msg = msg["content"]
        else:
            api_messages.append(msg)

    payload = {
        "model": endpoint.model,
        "max_tokens": 4096,
        "messages": api_messages,
        "stream": True,
    }
    if system_msg:
        payload["system"] = system_msg

    resp = await client.post(
        f"{endpoint.base_url}/messages",
        json=payload,
        headers=headers,
        timeout=timeout,
    )
    resp.raise_for_status()
    async for line in resp.aiter_lines():
        if line.startswith("data: "):
            s = line[6:].strip()
            try:
                yield json.loads(s)
            except json.JSONDecodeError:
                continue


def _get_api_caller(endpoint: ModelEndpoint):
    """根据 api_type 返回对应的调用函数"""
    if endpoint.api_type == "anthropic":
        return _call_anthropic_collect, _call_anthropic_stream
    return _call_openai_collect, _call_openai_stream


# ── proposer 并行调用 ──

async def _gather_proposers(
    client: httpx.AsyncClient,
    config: AppConfig,
    messages: list[dict],
    timeout: int,
) -> tuple[list[tuple[ProposerRef, str | Exception]], list[TokenUsage]]:
    """并行调用所有 proposers，返回 (results, token_usages)。"""
    temp = config.moa.proposer_temperature

    async def call_one(prop: ProposerRef) -> tuple[str, TokenUsage]:
        ep = config.get_endpoint(prop.endpoint)
        collect_fn, _ = _get_api_caller(ep)
        return await collect_fn(client, ep, messages, timeout, temperature=temp)

    tasks = [call_one(p) for p in config.proposers]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    results = []
    token_usages = []
    for i, raw in enumerate(raw_results):
        prop = config.proposers[i]
        if isinstance(raw, Exception):
            results.append((prop, raw))
        else:
            content, usage = raw
            results.append((prop, content))
            token_usages.append(usage)

    return results, token_usages


def _format_proposer_results(results: list[tuple[ProposerRef, str | Exception]]) -> list[str]:
    """格式化为 aggregator 用的 parts 列表。"""
    parts = []
    for prop, resp in results:
        label = _proposer_label(prop)
        if isinstance(resp, Exception):
            logger.warning("Proposer [%s] FAILED: %s", label, resp)
            parts.append(f"[{label}] ERROR: {resp}")
        else:
            logger.info("Proposer [%s] returned %d chars", label, len(resp))
            parts.append(f"[{label}]\n{resp}")
    return parts


def _valid_responses(results) -> list[tuple[ProposerRef, str]]:
    """只返回有效的响应。"""
    return [(p, r) for p, r in results if not isinstance(r, Exception)]


# ═══════════════════════════════════════════════
#  MoA 聚合策略
# ═══════════════════════════════════════════════

async def _strategy_simple(
    client: httpx.AsyncClient,
    config: AppConfig,
    messages: list[dict],
    timeout: int,
) -> tuple[str, list[TokenUsage]]:
    """默认策略：并行 proposers → 拼接 → aggregator 综合。"""
    results, token_usages = await _gather_proposers(client, config, messages, timeout)
    parts = _format_proposer_results(results)

    if not parts:
        raise RuntimeError("All proposers failed")

    user_content = (
        f"The original user query was:\n{messages[-1]['content']}\n\n"
        f"Here are responses from different models:\n\n"
        + "\n\n---\n\n".join(parts)
        + "\n\nPlease synthesize a comprehensive final answer."
    )
    agg_messages = [{"role": "system", "content": config.aggregator.system_prompt}]
    agg_messages.append({"role": "user", "content": user_content})

    agg_ep = config.get_endpoint(config.aggregator.endpoint)
    collect_fn, _ = _get_api_caller(agg_ep)
    content, agg_usage = await collect_fn(client, agg_ep, agg_messages, timeout, temperature=config.moa.aggregator_temperature)
    token_usages.append(agg_usage)
    return content, token_usages


async def _strategy_vote(
    client: httpx.AsyncClient,
    config: AppConfig,
    messages: list[dict],
    timeout: int,
) -> tuple[str, list[TokenUsage]]:
    """投票策略：proposers 独立回答 → aggregator 裁判选出最佳 → 润色。"""
    results, token_usages = await _gather_proposers(client, config, messages, timeout)
    valid = _valid_responses(results)
    if not valid:
        raise RuntimeError("All proposers failed")

    agg_ep = config.get_endpoint(config.aggregator.endpoint)

    # 裁判轮
    options = "\n\n---\n\n".join(
        f"[Option {i+1} — {_proposer_label(p)}]\n{r}"
        for i, (p, r) in enumerate(valid)
    )
    judge_msg = [
        {"role": "system", "content": "You are a judge. Pick the BEST response and explain briefly why."},
        {"role": "user", "content": f"User query: {messages[-1]['content']}\n\nResponses:\n{options}\n\nWhich is best? Return the number (1-{len(valid)}) and a brief justification."},
    ]
    collect_fn, _ = _get_api_caller(agg_ep)
    verdict, judge_usage = await collect_fn(client, agg_ep, judge_msg, timeout, temperature=config.moa.aggregator_temperature)
    token_usages.append(judge_usage)

    # 润色轮
    polish_msg = [
        {"role": "system", "content": config.aggregator.system_prompt},
        {"role": "user", "content": f"User query: {messages[-1]['content']}\n\nThe judge's verdict:\n{verdict}\n\nProduce a polished final answer."},
    ]
    content, polish_usage = await collect_fn(client, agg_ep, polish_msg, timeout, temperature=config.moa.aggregator_temperature)
    token_usages.append(polish_usage)
    return content, token_usages


async def _strategy_debate(
    client: httpx.AsyncClient,
    config: AppConfig,
    messages: list[dict],
    timeout: int,
) -> tuple[str, list[TokenUsage]]:
    """辩论策略：proposers 互看回答 → 改进一轮 → aggregator 汇总。"""
    results, token_usages = await _gather_proposers(client, config, messages, timeout)
    valid = _valid_responses(results)
    if len(valid) < 2:
        return await _strategy_simple(client, config, messages, timeout)

    # 第二轮：每个 proposer 看到所有答案后改进
    all_answers = "\n\n---\n\n".join(f"[{_proposer_label(p)}]\n{r}" for p, r in valid)
    refine_prompt = [
        {"role": "user", "content": f"Original: {messages[-1]['content']}\n\nAll responses:\n{all_answers}\n\nCritically evaluate. Identify errors, missed points, weak arguments. Then produce your own improved answer."},
    ]

    async def refine_one(prop: ProposerRef) -> tuple[str, TokenUsage]:
        ep = config.get_endpoint(prop.endpoint)
        collect_fn, _ = _get_api_caller(ep)
        return await collect_fn(client, ep, refine_prompt, timeout, temperature=config.moa.proposer_temperature)

    r2_tasks = [refine_one(p) for p, _ in valid]
    r2_results = await asyncio.gather(*r2_tasks, return_exceptions=True)

    parts = []
    for (p, _), r2 in zip(valid, r2_results):
        if isinstance(r2, Exception):
            logger.warning("Proposer [%s] round2 FAILED: %s", _proposer_label(p), r2)
        else:
            content2, usage2 = r2
            parts.append(f"[{_proposer_label(p)} — refined]\n{content2}")
            token_usages.append(usage2)

    user_content = (
        f"Original: {messages[-1]['content']}\n\n"
        f"After debate and refinement:\n\n"
        + "\n\n---\n\n".join(parts)
        + "\n\nSynthesize the final answer."
    )
    agg_messages = [{"role": "system", "content": config.aggregator.system_prompt}]
    agg_messages.append({"role": "user", "content": user_content})
    agg_ep = config.get_endpoint(config.aggregator.endpoint)
    collect_fn, _ = _get_api_caller(agg_ep)
    content, agg_usage = await collect_fn(client, agg_ep, agg_messages, timeout, temperature=config.moa.aggregator_temperature)
    token_usages.append(agg_usage)
    return content, token_usages


async def _strategy_cascade(
    client: httpx.AsyncClient,
    config: AppConfig,
    messages: list[dict],
    timeout: int,
) -> tuple[str, list[TokenUsage]]:
    """分层策略：proposers → 一次聚合 → 二次 polish（两层 aggregator）。"""
    results, token_usages = await _gather_proposers(client, config, messages, timeout)
    parts = _format_proposer_results(results)
    if not parts:
        raise RuntimeError("All proposers failed")

    agg_ep = config.get_endpoint(config.aggregator.endpoint)
    collect_fn, _ = _get_api_caller(agg_ep)

    # 第一层
    mid = [
        {"role": "system", "content": config.aggregator.system_prompt},
        {"role": "user", "content": f"Original: {messages[-1]['content']}\n\n" + "\n\n---\n\n".join(parts) + "\n\nSynthesize these into a single answer."},
    ]
    first_pass, first_usage = await collect_fn(client, agg_ep, mid, timeout, temperature=config.moa.aggregator_temperature)
    token_usages.append(first_usage)

    # 第二层 polish
    final = [
        {"role": "system", "content": config.aggregator.system_prompt},
        {"role": "user", "content": f"Original: {messages[-1]['content']}\n\nDraft answer:\n{first_pass}\n\nCritically review and produce a polished final answer."},
    ]
    content, final_usage = await collect_fn(client, agg_ep, final, timeout, temperature=config.moa.aggregator_temperature)
    token_usages.append(final_usage)
    return content, token_usages


STRATEGIES = {
    "simple": _strategy_simple,
    "vote": _strategy_vote,
    "debate": _strategy_debate,
    "cascade": _strategy_cascade,
}


# ═══════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════

async def run_moa(config: AppConfig, messages: list[dict]) -> tuple[str, list[TokenUsage]]:
    timeout = config.moa.timeout
    fn = STRATEGIES.get(config.moa.strategy)
    if fn is None:
        raise ValueError(f"Unknown strategy: {config.moa.strategy}. Choose: {list(STRATEGIES)}")
    logger.info("MoA strategy=%s, %d proposers", config.moa.strategy, len(config.proposers))
    async with httpx.AsyncClient() as client:
        return await fn(client, config, messages, timeout)


async def run_moa_stream(config: AppConfig, messages: list[dict]):
    """流式 MoA：proposers 非流式收集 → aggregator 流式输出。yields (chunk, token_usages_at_end)"""
    timeout = config.moa.timeout

    async with httpx.AsyncClient() as client:
        # 1. 并行收集所有 proposers（非流式）
        logger.info("Collecting %d proposers (non-streaming)...", len(config.proposers))
        results, token_usages = await _gather_proposers(client, config, messages, timeout)
        parts = _format_proposer_results(results)

        if not parts:
            raise RuntimeError("All proposers failed")

        # 2. aggregator 流式输出
        user_content = (
            f"The original user query was:\n{messages[-1]['content']}\n\n"
            f"Here are responses from different models:\n\n"
            + "\n\n---\n\n".join(parts)
            + "\n\nPlease synthesize a comprehensive final answer."
        )
        agg_messages = [
            {"role": "system", "content": config.aggregator.system_prompt},
            {"role": "user", "content": user_content},
        ]

        logger.info("Streaming aggregator (%s)...", config.aggregator.endpoint)
        agg_ep = config.get_endpoint(config.aggregator.endpoint)
        _, stream_fn = _get_api_caller(agg_ep)
        async for chunk in stream_fn(client, agg_ep, agg_messages, timeout):
            yield chunk, token_usages
