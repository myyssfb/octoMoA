"""
管理 API: /admin/api/endpoints, /admin/api/config, /admin/api/stats, /admin/api/requests
"""

import time
from fastapi import APIRouter, HTTPException, Request
from app.db import get_db

admin = APIRouter(prefix="/admin/api")


# ── Endpoints CRUD ──

@admin.get("/endpoints")
async def list_endpoints():
    db = await get_db()
    try:
        rows = []
        async with db.execute("SELECT * FROM endpoints ORDER BY name") as cursor:
            async for row in cursor:
                rows.append(dict(row))
        return rows
    finally:
        await db.close()


@admin.post("/endpoints")
async def create_endpoint(data: dict):
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO endpoints (name, api_type, base_url, api_key, model) VALUES (?, ?, ?, ?, ?)",
            (data["name"], data.get("api_type", "openai"), data["base_url"], data.get("api_key", ""), data["model"]),
        )
        await db.commit()
        return {"ok": True, "name": data["name"]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await db.close()


@admin.put("/endpoints/{name}")
async def update_endpoint(name: str, data: dict):
    db = await get_db()
    try:
        await db.execute(
            """UPDATE endpoints SET api_type=?, base_url=?, api_key=?, model=?, updated_at=datetime('now')
               WHERE name=?""",
            (data.get("api_type", "openai"), data.get("base_url", ""), data.get("api_key", ""), data.get("model", ""), name),
        )
        if db.total_changes == 0:
            raise HTTPException(status_code=404, detail=f"Endpoint '{name}' not found")
        await db.commit()
        return {"ok": True, "name": name}
    finally:
        await db.close()


@admin.delete("/endpoints/{name}")
async def delete_endpoint(name: str):
    db = await get_db()
    try:
        await db.execute("DELETE FROM endpoints WHERE name=?", (name,))
        if db.total_changes == 0:
            raise HTTPException(status_code=404, detail=f"Endpoint '{name}' not found")
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


@admin.post("/endpoints/{name}/test")
async def test_endpoint(name: str, data: dict | None = None):
    """测试端点连通性。发一条短请求确认可用。"""
    import httpx
    db = await get_db()
    try:
        row = await db.execute("SELECT * FROM endpoints WHERE name=?", (name,))
        ep = await row.fetchone()
        if not ep:
            raise HTTPException(status_code=404, detail=f"Endpoint '{name}' not found")
        ep = dict(ep)

        t0 = time.perf_counter()
        async with httpx.AsyncClient() as client:
            if ep["api_type"] == "anthropic":
                headers = {
                    "x-api-key": ep["api_key"],
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                }
                payload = {"model": ep["model"], "messages": [{"role": "user", "content": "hi"}], "max_tokens": 10}
                resp = await client.post(f"{ep['base_url']}/messages", json=payload, headers=headers, timeout=15)
            else:
                headers = {
                    "Authorization": f"Bearer {ep['api_key']}",
                    "Content-Type": "application/json",
                }
                payload = {"model": ep["model"], "messages": [{"role": "user", "content": "hi"}], "max_tokens": 10, "stream": False}
                resp = await client.post(f"{ep['base_url']}/chat/completions", json=payload, headers=headers, timeout=15)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        return {
            "ok": resp.status_code == 200,
            "status_code": resp.status_code,
            "elapsed_ms": elapsed_ms,
            "detail": resp.text[:200] if resp.status_code != 200 else "OK",
        }
    except Exception as e:
        return {"ok": False, "status_code": 0, "elapsed_ms": 0, "detail": str(e)}
    finally:
        await db.close()


# ── Config ──

@admin.get("/config")
async def get_config():
    db = await get_db()
    try:
        cfg = {}
        async with db.execute("SELECT * FROM moa_config WHERE id=1") as cursor:
            row = await cursor.fetchone()
            if row:
                cfg = dict(row)

        proposers = []
        async with db.execute("SELECT * FROM moa_proposers ORDER BY sort_order") as cursor:
            async for row in cursor:
                proposers.append(dict(row))

        # 端点池
        endpoints = []
        async with db.execute("SELECT name, api_type, model FROM endpoints ORDER BY name") as cursor:
            async for row in cursor:
                endpoints.append(dict(row))

        cfg["proposers"] = proposers
        cfg["available_endpoints"] = endpoints
        return cfg
    finally:
        await db.close()


@admin.put("/config")
async def update_config(data: dict):
    """一次性更新 moa_config + moa_proposers。"""
    db = await get_db()
    try:
        # 更新 moa_config
        await db.execute(
            """INSERT OR REPLACE INTO moa_config (id, aggregator_endpoint, aggregator_system_prompt, strategy, timeout, stream_timeout, proposer_temperature, aggregator_temperature, updated_at)
               VALUES (1, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (
                data.get("aggregator_endpoint", ""),
                data.get("aggregator_system_prompt", ""),
                data.get("strategy", "simple"),
                data.get("timeout", 120),
                data.get("stream_timeout", 300),
                data.get("proposer_temperature", 0.6),
                data.get("aggregator_temperature", 0.4),
            ),
        )

        # 重建 proposers 列表
        await db.execute("DELETE FROM moa_proposers")
        for i, p in enumerate(data.get("proposers", [])):
            await db.execute(
                "INSERT INTO moa_proposers (endpoint_name, label, role, weight, sort_order) VALUES (?, ?, ?, ?, ?)",
                (p["endpoint"], p.get("label", p["endpoint"]), p.get("role", "strong"), p.get("weight", 1.0), i),
            )

        await db.commit()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await db.close()


@admin.post("/config/reload")
async def reload_config():
    """通知引擎重载配置（热重载是通过每次请求时读 DB 实现的，这里只做确认）。"""
    return {"ok": True, "message": "Config reloaded from DB (already live)"}


# ── Presets（配置预设）──

@admin.get("/presets")
async def list_presets():
    """获取所有预设配置"""
    db = await get_db()
    try:
        rows = []
        async with db.execute("SELECT * FROM moa_presets ORDER BY is_active DESC, name") as cursor:
            async for row in cursor:
                rows.append(dict(row))
        return rows
    finally:
        await db.close()


@admin.post("/presets")
async def create_preset(request: Request):
    """保存当前配置为预设"""
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not data.get("name"):
        raise HTTPException(status_code=400, detail="name is required")

    db = await get_db()
    try:
        # 获取当前配置
        cfg = {}
        async with db.execute("SELECT * FROM moa_config WHERE id=1") as cursor:
            row = await cursor.fetchone()
            if row:
                cfg = dict(row)

        proposers = []
        async with db.execute("SELECT * FROM moa_proposers ORDER BY sort_order") as cursor:
            async for row in cursor:
                proposers.append(dict(row))

        config_json = {
            "aggregator_endpoint": cfg.get("aggregator_endpoint", ""),
            "aggregator_system_prompt": cfg.get("aggregator_system_prompt", ""),
            "strategy": cfg.get("strategy", "simple"),
            "timeout": cfg.get("timeout", 120),
            "stream_timeout": cfg.get("stream_timeout", 300),
            "proposer_temperature": cfg.get("proposer_temperature", 0.6),
            "aggregator_temperature": cfg.get("aggregator_temperature", 0.4),
            "proposers": proposers,
        }

        import json
        await db.execute(
            "INSERT INTO moa_presets (name, description, config_json) VALUES (?, ?, ?)",
            (data["name"], data.get("description", ""), json.dumps(config_json, ensure_ascii=False)),
        )
        await db.commit()
        return {"ok": True, "name": data["name"]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await db.close()


@admin.post("/presets/{preset_id}/activate")
async def activate_preset(preset_id: int):
    """激活预设：将预设配置写入当前配置"""
    db = await get_db()
    try:
        # 获取预设
        row = await db.execute("SELECT * FROM moa_presets WHERE id=?", (preset_id,))
        preset = await row.fetchone()
        if not preset:
            raise HTTPException(status_code=404, detail="Preset not found")

        import json
        config = json.loads(preset["config_json"])

        # 更新 moa_config（包括温度设置）
        await db.execute(
            """UPDATE moa_config SET aggregator_endpoint=?, aggregator_system_prompt=?,
               strategy=?, timeout=?, stream_timeout=?, proposer_temperature=?, aggregator_temperature=?,
               updated_at=datetime('now') WHERE id=1""",
            (config["aggregator_endpoint"], config["aggregator_system_prompt"],
             config["strategy"], config["timeout"], config["stream_timeout"],
             config.get("proposer_temperature", 0.6), config.get("aggregator_temperature", 0.4)),
        )

        # 重建 proposers
        await db.execute("DELETE FROM moa_proposers")
        for i, p in enumerate(config.get("proposers", [])):
            await db.execute(
                "INSERT INTO moa_proposers (endpoint_name, label, role, weight, sort_order) VALUES (?, ?, ?, ?, ?)",
                (p["endpoint_name"], p.get("label", p["endpoint_name"]), p.get("role", "strong"), p.get("weight", 1.0), i),
            )

        # 标记为活跃
        await db.execute("UPDATE moa_presets SET is_active=0")
        await db.execute("UPDATE moa_presets SET is_active=1 WHERE id=?", (preset_id,))

        await db.commit()
        return {"ok": True, "message": f"已激活预设: {preset['name']}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await db.close()


@admin.delete("/presets/{preset_id}")
async def delete_preset(preset_id: int):
    """删除预设"""
    db = await get_db()
    try:
        await db.execute("DELETE FROM moa_presets WHERE id=?", (preset_id,))
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


# ── Stats ──

@admin.get("/stats")
async def get_stats():
    db = await get_db()
    try:
        # 总览
        total = await db.execute("SELECT COUNT(*) as cnt FROM request_log")
        total = (await total.fetchone())["cnt"]

        ok = await db.execute("SELECT COUNT(*) as cnt FROM request_log WHERE status='ok'")
        ok = (await ok.fetchone())["cnt"]

        avg_latency = await db.execute("SELECT AVG(elapsed_ms) as avg FROM request_log WHERE status='ok'")
        avg_latency = (await avg_latency.fetchone())["avg"] or 0

        # 最近 24h 按小时聚合
        hourly = []
        async with db.execute("""
            SELECT strftime('%H', created_at) as hour, COUNT(*) as cnt, AVG(elapsed_ms) as avg_ms
            FROM request_log
            WHERE created_at > datetime('now', '-24 hours')
            GROUP BY strftime('%H', created_at)
            ORDER BY hour
        """) as cursor:
            async for row in cursor:
                hourly.append(dict(row))

        # 按策略统计
        by_strategy = []
        async with db.execute("""
            SELECT strategy, COUNT(*) as cnt, AVG(elapsed_ms) as avg_ms
            FROM request_log
            WHERE created_at > datetime('now', '-7 days')
            GROUP BY strategy
        """) as cursor:
            async for row in cursor:
                by_strategy.append(dict(row))

        return {
            "total_requests": total,
            "ok_requests": ok,
            "avg_latency_ms": round(avg_latency, 1),
            "hourly": hourly,
            "by_strategy": by_strategy,
        }
    finally:
        await db.close()


@admin.get("/requests")
async def list_requests(limit: int = 50):
    db = await get_db()
    try:
        rows = []
        async with db.execute(
            "SELECT * FROM request_log ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cursor:
            async for row in cursor:
                rows.append(dict(row))
        return rows
    finally:
        await db.close()


# ── Token 统计 ──

@admin.get("/token-stats")
async def get_token_stats():
    db = await get_db()
    try:
        # 按 endpoint 分组
        by_endpoint = []
        async with db.execute("""
            SELECT endpoint_name, model,
                   SUM(prompt_tokens) as total_prompt,
                   SUM(completion_tokens) as total_completion,
                   SUM(total_tokens) as total,
                   COUNT(*) as call_count
            FROM token_log
            GROUP BY endpoint_name
            ORDER BY total DESC
        """) as cursor:
            async for row in cursor:
                by_endpoint.append(dict(row))

        # 按天分组（最近 7 天）
        by_day = []
        async with db.execute("""
            SELECT date(created_at) as day,
                   SUM(prompt_tokens) as prompt,
                   SUM(completion_tokens) as completion,
                   SUM(total_tokens) as total
            FROM token_log
            WHERE created_at > datetime('now', '-7 days')
            GROUP BY date(created_at)
            ORDER BY day
        """) as cursor:
            async for row in cursor:
                by_day.append(dict(row))

        # 总计
        total_row = await db.execute("SELECT SUM(total_tokens) as grand_total FROM token_log")
        grand_total = (await total_row.fetchone())["grand_total"] or 0

        return {
            "grand_total": grand_total,
            "by_endpoint": by_endpoint,
            "by_day": by_day,
        }
    finally:
        await db.close()


# ── 模型评测 ──

# 全局评测状态存储
_benchmark_runs: dict[str, dict] = {}


@admin.post("/benchmark")
async def start_benchmark(data: dict | None = None):
    """启动模型评测。返回 run_id 供轮询。"""
    import asyncio
    import uuid

    run_id = str(uuid.uuid4())[:8]
    _benchmark_runs[run_id] = {"status": "running", "progress": 0, "results": [], "total": 0}

    async def run_benchmark():
        from app.benchmark import BENCHMARK_QUESTIONS, score_answer
        from app.engine import _get_api_caller, TokenUsage, run_moa

        db = await get_db()
        try:
            # 获取所有 endpoints
            endpoints = []
            async with db.execute("SELECT * FROM endpoints WHERE api_key != '' ORDER BY name") as cursor:
                async for row in cursor:
                    endpoints.append(dict(row))

            # 获取当前 MoA 配置
            from app.db_config import load_config_from_db
            config = await load_config_from_db()

            questions = BENCHMARK_QUESTIONS
            total_tasks = len(endpoints) * len(questions) + len(questions)  # 单模型 + MoA
            _benchmark_runs[run_id]["total"] = total_tasks

            import httpx
            async with httpx.AsyncClient() as client:
                progress = 0

                # 1. 单独测试每个 endpoint
                for ep_data in endpoints:
                    from app.config import ModelEndpoint
                    ep = ModelEndpoint(
                        name=ep_data["name"], api_type=ep_data["api_type"],
                        base_url=ep_data["base_url"], api_key=ep_data["api_key"],
                        model=ep_data["model"],
                    )
                    for q in questions:
                        try:
                            messages = [{"role": "user", "content": q["prompt"]}]
                            t0 = time.perf_counter()
                            collect_fn, _ = _get_api_caller(ep)
                            content, usage = await collect_fn(client, ep, messages, 60)
                            elapsed = time.perf_counter() - t0
                            score = score_answer(q, content)
                            _benchmark_runs[run_id]["results"].append({
                                "name": ep.name,
                                "model": ep.model,
                                "type": "single",
                                "question_id": q["id"],
                                "question": q["category"],
                                "content_preview": content[:200],
                                "score": score,
                                "latency_s": round(elapsed, 2),
                                "prompt_tokens": usage.prompt_tokens,
                                "completion_tokens": usage.completion_tokens,
                            })
                        except Exception as e:
                            _benchmark_runs[run_id]["results"].append({
                                "name": ep.name, "model": ep.model, "type": "single",
                                "question_id": q["id"], "question": q["category"],
                                "content_preview": f"ERROR: {e}", "score": 0,
                                "latency_s": 0, "prompt_tokens": 0, "completion_tokens": 0,
                            })
                        progress += 1
                        _benchmark_runs[run_id]["progress"] = progress

                # 2. MoA 组合测试
                for q in questions:
                    try:
                        messages = [{"role": "user", "content": q["prompt"]}]
                        t0 = time.perf_counter()
                        content, usages = await run_moa(config, messages)
                        elapsed = time.perf_counter() - t0
                        score = score_answer(q, content)
                        total_prompt = sum(u.prompt_tokens for u in usages)
                        total_completion = sum(u.completion_tokens for u in usages)
                        _benchmark_runs[run_id]["results"].append({
                            "name": "MoA",
                            "model": config.moa.strategy,
                            "type": "moa",
                            "question_id": q["id"],
                            "question": q["category"],
                            "content_preview": content[:200],
                            "score": score,
                            "latency_s": round(elapsed, 2),
                            "prompt_tokens": total_prompt,
                            "completion_tokens": total_completion,
                        })
                    except Exception as e:
                        _benchmark_runs[run_id]["results"].append({
                            "name": "MoA", "model": config.moa.strategy, "type": "moa",
                            "question_id": q["id"], "question": q["category"],
                            "content_preview": f"ERROR: {e}", "score": 0,
                            "latency_s": 0, "prompt_tokens": 0, "completion_tokens": 0,
                        })
                    progress += 1
                    _benchmark_runs[run_id]["progress"] = progress

            _benchmark_runs[run_id]["status"] = "done"
        except Exception as e:
            _benchmark_runs[run_id]["status"] = "error"
            _benchmark_runs[run_id]["error"] = str(e)
        finally:
            await db.close()

    asyncio.create_task(run_benchmark())
    return {"run_id": run_id, "status": "started"}


@admin.get("/benchmark/{run_id}")
async def get_benchmark(run_id: str):
    """查询评测进度和结果。"""
    if run_id not in _benchmark_runs:
        raise HTTPException(status_code=404, detail="Benchmark run not found")
    run = _benchmark_runs[run_id]

    # 如果完成，计算排名
    ranking = []
    if run["status"] == "done" and run["results"]:
        from collections import defaultdict
        scores = defaultdict(lambda: {"total_score": 0, "count": 0, "total_latency": 0, "total_tokens": 0})
        for r in run["results"]:
            key = f"{r['name']} ({r['model']})"
            scores[key]["total_score"] += r["score"]
            scores[key]["count"] += 1
            scores[key]["total_latency"] += r["latency_s"]
            scores[key]["total_tokens"] += r["prompt_tokens"] + r["completion_tokens"]
            scores[key]["type"] = r["type"]

        for name, s in scores.items():
            avg_score = s["total_score"] / s["count"] if s["count"] > 0 else 0
            avg_latency = s["total_latency"] / s["count"] if s["count"] > 0 else 0
            ranking.append({
                "name": name,
                "type": s["type"],
                "avg_score": round(avg_score, 1),
                "avg_latency_s": round(avg_latency, 2),
                "total_tokens": s["total_tokens"],
            })
        ranking.sort(key=lambda x: (-x["avg_score"], x["avg_latency_s"]))

    return {
        "status": run["status"],
        "progress": run["progress"],
        "total": run["total"],
        "results": run["results"],
        "ranking": ranking,
    }
