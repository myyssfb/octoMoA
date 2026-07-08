"""
从 SQLite 实时加载 AppConfig — 替代 app.config.load_config()。
每次 run_moa 调用时从 DB 读取，实现热重载。
"""

from app.config import AppConfig, ModelEndpoint, ProposerRef, AggregatorRef, ServerConfig, MoaConfig
from app.db import get_db


async def load_config_from_db() -> AppConfig:
    """从 SQLite 数据库加载当前配置。"""
    db = await get_db()
    try:
        # 1. endpoints
        endpoints = {}
        async with db.execute("SELECT name, api_type, base_url, api_key, model FROM endpoints") as cursor:
            async for row in cursor:
                endpoints[row["name"]] = ModelEndpoint(
                    name=row["name"],
                    api_type=row["api_type"],
                    base_url=row["base_url"],
                    api_key=row["api_key"],
                    model=row["model"],
                )

        # 2. proposers
        proposers = []
        async with db.execute("SELECT endpoint_name, label, role, weight FROM moa_proposers ORDER BY sort_order") as cursor:
            async for row in cursor:
                proposers.append(ProposerRef(
                    endpoint=row["endpoint_name"],
                    label=row["label"],
                    role=row["role"],
                    weight=row["weight"],
                ))

        # 3. moa_config
        agg = AggregatorRef()
        moa = MoaConfig()
        async with db.execute("SELECT * FROM moa_config WHERE id=1") as cursor:
            row = await cursor.fetchone()
            if row:
                agg.endpoint = row["aggregator_endpoint"]
                agg.system_prompt = row["aggregator_system_prompt"]
                moa.strategy = row["strategy"]
                moa.timeout = row["timeout"]
                moa.stream_timeout = row["stream_timeout"]
                moa.proposer_temperature = row["proposer_temperature"]
                moa.aggregator_temperature = row["aggregator_temperature"]

        # 4. server (从环境变量/默认值，不走 DB)
        server = ServerConfig()

        return AppConfig(
            endpoints=endpoints,
            proposers=proposers,
            aggregator=agg,
            server=server,
            moa=moa,
        )
    finally:
        await db.close()
