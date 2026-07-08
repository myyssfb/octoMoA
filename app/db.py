"""
SQLite 数据库初始化 + 连接管理。
数据库文件: %APPDATA%/octoMoA/moa.db (Windows) 或 ~/.moa-proxy/moa.db
"""

import os
import logging
import aiosqlite

logger = logging.getLogger(__name__)

_db_path: str | None = None


def get_db_path() -> str:
    global _db_path
    if _db_path:
        return _db_path
    if os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        _db_path = os.path.join(base, "octoMoA", "moa.db")
    else:
        base = os.path.expanduser("~/.moa-proxy")
        _db_path = os.path.join(base, "moa.db")
    os.makedirs(os.path.dirname(_db_path), exist_ok=True)
    return _db_path


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(get_db_path())
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db() -> None:
    """创建表结构 + 从 config.yaml 导入初始数据（如果是首次运行）。"""
    db = await get_db()
    try:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS endpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                api_type TEXT NOT NULL DEFAULT 'openai',
                base_url TEXT NOT NULL,
                api_key TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS moa_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),  -- 单行配置
                aggregator_endpoint TEXT NOT NULL DEFAULT '',
                aggregator_system_prompt TEXT NOT NULL DEFAULT '',
                strategy TEXT NOT NULL DEFAULT 'simple',
                timeout INTEGER NOT NULL DEFAULT 120,
                stream_timeout INTEGER NOT NULL DEFAULT 300,
                proposer_temperature REAL NOT NULL DEFAULT 0.6,
                aggregator_temperature REAL NOT NULL DEFAULT 0.4,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS moa_proposers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint_name TEXT NOT NULL REFERENCES endpoints(name) ON DELETE CASCADE,
                label TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'strong',
                weight REAL NOT NULL DEFAULT 1.0,
                sort_order INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS request_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT,
                strategy TEXT,
                model_name TEXT,
                proposer_count INTEGER,
                elapsed_ms INTEGER,
                input_chars INTEGER,
                output_chars INTEGER,
                status TEXT,         -- ok | error
                error_msg TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_request_log_created ON request_log(created_at);

            CREATE TABLE IF NOT EXISTS token_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_log_id INTEGER REFERENCES request_log(id),
                endpoint_name TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_tokens INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_token_log_created ON token_log(created_at);
            CREATE INDEX IF NOT EXISTS idx_token_log_endpoint ON token_log(endpoint_name);

            CREATE TABLE IF NOT EXISTS moa_presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT DEFAULT '',
                config_json TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)
        await db.commit()

        # 检查是否为空库 → 从 config.yaml 导入
        row = await db.execute("SELECT COUNT(*) as cnt FROM endpoints")
        count = (await row.fetchone())["cnt"]
        if count == 0:
            logger.info("Empty DB, importing from config.yaml...")
            await _import_from_yaml(db)

    finally:
        await db.close()


async def _import_from_yaml(db: aiosqlite.Connection) -> None:
    """从 config.yaml 导入初始数据到 SQLite。"""
    try:
        from app.config import load_config
    except Exception:
        logger.warning("Cannot import from config.yaml, skipping")
        return

    cfg = load_config()

    # 导入 endpoints
    for name, ep in cfg.endpoints.items():
        await db.execute(
            "INSERT INTO endpoints (name, api_type, base_url, api_key, model) VALUES (?, ?, ?, ?, ?)",
            (name, ep.api_type, ep.base_url, ep.api_key, ep.model),
        )

    # 导入 proposers
    for i, p in enumerate(cfg.proposers):
        await db.execute(
            "INSERT INTO moa_proposers (endpoint_name, label, role, weight, sort_order) VALUES (?, ?, ?, ?, ?)",
            (p.endpoint, p.label or p.endpoint, p.role, p.weight, i),
        )

    # 导入 config
    agg = cfg.aggregator
    moa = cfg.moa
    await db.execute(
        """INSERT OR REPLACE INTO moa_config (id, aggregator_endpoint, aggregator_system_prompt, strategy, timeout, stream_timeout)
           VALUES (1, ?, ?, ?, ?, ?)""",
        (agg.endpoint, agg.system_prompt, moa.strategy, moa.timeout, moa.stream_timeout),
    )

    await db.commit()
    logger.info("Imported config from config.yaml to SQLite")
