"""
MoA Proxy — 本地 OpenAI 兼容 API 代理。
FastAPI 入口，支持: 首次启动导入 config.yaml → SQLite → 热重载。
"""

import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.routes import router
from app.admin_api import admin
from app.db import init_db
from app.db_config import load_config_from_db


async def _config_middleware(request: Request, call_next):
    """每个请求前从 DB 加载最新配置（实现热重载）。"""
    try:
        request.app.state.config = await load_config_from_db()
    except Exception:
        pass  # 如果 DB 读失败，用之前的配置
    return await call_next(request)


def create_app() -> FastAPI:
    app = FastAPI(
        title="octoMoA",
        description="Mixture of Agents — OpenAI-compatible API proxy",
        version="0.1.0",
    )

    # 启动时初始化 DB
    @app.on_event("startup")
    async def startup():
        await init_db()
        app.state.config = await load_config_from_db()

    app.include_router(router)
    app.include_router(admin)

    # 静态文件
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # 管理面板首页
    @app.get("/")
    async def index():
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"message": "MoA Proxy is running", "docs": "/docs"}

    return app


app = create_app()


def run_server(host: str = "127.0.0.1", port: int = 18990):
    """非 reload 模式启动（桌面产品用）。"""
    import asyncio
    import uvicorn

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)

    # 使用 asyncio.run() 而非 server.run()，避免 sys.exit() 问题
    try:
        asyncio.run(server.serve())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    run_server()
