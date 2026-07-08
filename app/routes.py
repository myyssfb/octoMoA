"""
FastAPI 路由 — OpenAI 兼容 /v1/chat/completions (stream + non-stream) + /v1/models
"""

import json
import time
import logging
import traceback
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from app.config import AppConfig
from app.engine import run_moa, run_moa_stream, TokenUsage
from app.db import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1")


async def _log_request(config, messages, content, elapsed, error, token_usages: list[TokenUsage] | None = None):
    """记录请求日志到 SQLite，包括 token 消耗。"""
    try:
        db = await get_db()
        input_chars = sum(len(str(m.get("content", ""))) for m in messages[-4:])
        output_chars = len(content) if content else 0
        cursor = await db.execute(
            """INSERT INTO request_log (strategy, model_name, proposer_count, elapsed_ms,
               input_chars, output_chars, status, error_msg)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (config.moa.strategy, "moa", len(config.proposers), int(elapsed * 1000),
             input_chars, output_chars,
             "ok" if not error else "error", error or ""),
        )
        request_log_id = cursor.lastrowid

        # 记录 token 消耗
        if token_usages:
            for tu in token_usages:
                await db.execute(
                    """INSERT INTO token_log (request_log_id, endpoint_name, model, prompt_tokens, completion_tokens, total_tokens)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (request_log_id, tu.endpoint_name, tu.model, tu.prompt_tokens, tu.completion_tokens, tu.total_tokens),
                )

        await db.commit()
        await db.close()
    except Exception:
        pass  # 日志失败不应影响主流程


def verify_api_key(request: Request, config: AppConfig) -> None:
    if not config.server.api_key:
        return
    auth = request.headers.get("Authorization", "")
    expected = f"Bearer {config.server.api_key}"
    if auth != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ── OpenAI-compatible non-streaming ──

@router.post("/chat/completions")
async def chat_completions(request: Request):
    config: AppConfig = request.app.state.config
    verify_api_key(request, config)

    try:
        body = await request.json()
    except UnicodeDecodeError:
        raw = await request.body()
        try:
            body = json.loads(raw.decode("gbk"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON encoding. Use UTF-8.")

    messages = body.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="messages is required")

    stream = body.get("stream", False)

    # ── 流式 ──
    if stream:
        async def sse_generator():
            request_id = f"moa-{int(time.time())}"
            # 先发一个 chunk 告诉客户端 model 名
            init_chunk = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "moa",
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
            }
            yield f"data: {json.dumps(init_chunk, ensure_ascii=False)}\n\n"

            token_usages = []
            try:
                async for chunk, tus in run_moa_stream(config, messages):
                    token_usages = tus
                    choice = chunk.get("choices", [{}])[0]
                    delta = choice.get("delta", {})
                    finish = choice.get("finish_reason")
                    out = {
                        "id": request_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": "moa",
                        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
                    }
                    yield f"data: {json.dumps(out, ensure_ascii=False)}\n\n"

                yield "data: [DONE]\n\n"
                # 流式完成后记录日志
                await _log_request(config, messages, "", 0, None, token_usages)
            except Exception as e:
                logger.error("Stream error: %s\n%s", e, traceback.format_exc())
                await _log_request(config, messages, "", 0, str(e), token_usages)
                err = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": "moa",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "error"}],
                    "error": {"message": str(e), "type": "moa_stream_error"},
                }
                yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            sse_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ── 非流式 ──
    try:
        start = time.perf_counter()
        content, token_usages = await run_moa(config, messages)
        elapsed = time.perf_counter() - start
        await _log_request(config, messages, content, elapsed, None, token_usages)
    except Exception as e:
        logger.error("MoA failed: %s\n%s", e, traceback.format_exc())
        await _log_request(config, messages, "", 0, str(e))
        return JSONResponse(
            status_code=500,
            content={"error": {"message": str(e), "type": "moa_error"}},
        )

    proposer_labels = [p.label or p.endpoint for p in config.proposers]
    total_prompt = sum(tu.prompt_tokens for tu in token_usages)
    total_completion = sum(tu.completion_tokens for tu in token_usages)
    total_tokens = sum(tu.total_tokens for tu in token_usages)
    return {
        "id": f"moa-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "moa",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": total_prompt, "completion_tokens": total_completion, "total_tokens": total_tokens},
        "_moa_meta": {
            "elapsed_s": round(elapsed, 2),
            "proposers": proposer_labels,
            "aggregator": config.aggregator.endpoint,
            "strategy": config.moa.strategy,
        },
    }


@router.get("/models")
async def list_models(request: Request):
    config: AppConfig = request.app.state.config
    verify_api_key(request, config)
    return {
        "object": "list",
        "data": [{"id": "moa", "object": "model", "created": 0, "owned_by": "moa-proxy"}],
    }


@router.get("/health")
async def health():
    return {"status": "ok"}


# ── Anthropic-compatible /v1/messages ──

def _anthropic_to_internal(body: dict) -> tuple[list[dict], bool]:
    """将 Anthropic 请求格式转换为内部 messages 格式。"""
    messages = body.get("messages", [])
    system = body.get("system")
    if system:
        messages = [{"role": "system", "content": system}] + messages
    stream = body.get("stream", False)
    return messages, stream


def _make_anthropic_response(content: str, token_usages: list[TokenUsage], elapsed: float, config: AppConfig) -> dict:
    """将 MoA 结果包装为 Anthropic 响应格式。"""
    total_input = sum(tu.prompt_tokens for tu in token_usages)
    total_output = sum(tu.completion_tokens for tu in token_usages)
    return {
        "id": f"msg_{int(time.time())}",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": content}],
        "model": "moa",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": total_input, "output_tokens": total_output},
    }


def _anthropic_sse(event: str, data: dict) -> str:
    """格式化一条 Anthropic SSE 事件。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/messages")
async def anthropic_messages(request: Request):
    config: AppConfig = request.app.state.config
    verify_api_key(request, config)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    messages, stream = _anthropic_to_internal(body)
    if not messages:
        raise HTTPException(status_code=400, detail="messages is required")

    # ── 流式 ──
    if stream:
        async def anthropic_sse_generator():
            msg_id = f"msg_{int(time.time())}"
            # message_start
            yield _anthropic_sse("message_start", {
                "type": "message_start",
                "message": {
                    "id": msg_id, "type": "message", "role": "assistant",
                    "content": [], "model": "moa", "stop_reason": None,
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                },
            })
            # content_block_start
            yield _anthropic_sse("content_block_start", {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            })

            token_usages = []
            try:
                async for chunk, tus in run_moa_stream(config, messages):
                    token_usages = tus
                    choice = chunk.get("choices", [{}])[0]
                    delta = choice.get("delta", {})
                    text = delta.get("content", "")
                    if text:
                        yield _anthropic_sse("content_block_delta", {
                            "type": "content_block_delta",
                            "index": 0,
                            "delta": {"type": "text_delta", "text": text},
                        })

                # content_block_stop
                yield _anthropic_sse("content_block_stop", {"type": "content_block_stop", "index": 0})
                # message_delta
                total_input = sum(tu.prompt_tokens for tu in token_usages)
                total_output = sum(tu.completion_tokens for tu in token_usages)
                yield _anthropic_sse("message_delta", {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": total_output},
                })
                # message_stop
                yield _anthropic_sse("message_stop", {"type": "message_stop"})

                await _log_request(config, messages, "", 0, None, token_usages)
            except Exception as e:
                logger.error("Anthropic stream error: %s\n%s", e, traceback.format_exc())
                await _log_request(config, messages, "", 0, str(e), token_usages)
                yield _anthropic_sse("error", {
                    "type": "error",
                    "error": {"type": "moa_stream_error", "message": str(e)},
                })

        return StreamingResponse(
            anthropic_sse_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    # ── 非流式 ──
    try:
        start = time.perf_counter()
        content, token_usages = await run_moa(config, messages)
        elapsed = time.perf_counter() - start
        await _log_request(config, messages, content, elapsed, None, token_usages)
    except Exception as e:
        logger.error("Anthropic MoA failed: %s\n%s", e, traceback.format_exc())
        await _log_request(config, messages, "", 0, str(e))
        return JSONResponse(
            status_code=500,
            content={"type": "error", "error": {"type": "moa_error", "message": str(e)}},
        )

    return _make_anthropic_response(content, token_usages, elapsed, config)
