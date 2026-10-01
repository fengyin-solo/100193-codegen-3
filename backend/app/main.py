"""风电场机组运维平台 后端服务入口。

启动：uvicorn app.main:app --host 127.0.0.1 --port 8000
健康检查：GET /api/health
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import ROUTERS
from app.store import store

app = FastAPI(title="风电场机组运维平台", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in ROUTERS:
    app.include_router(module.router)


@app.get("/api/health")
def health() -> dict[str, object]:
    """健康检查：确认服务已经监听、示例数据已经就绪。"""
    return {"ok": True, "app": settings.app_name, "modules": len(store.module_names())}


@app.get("/api/overview")
def overview() -> dict[str, object]:
    """运营概览：把各业务模块的待处理量汇总成看板卡片。

    出海窗口调度的可用/占用船数与窗口状态直接取 SeawindowService.summary()，
    看板与窗口台账共用同一口径，不允许两边各算各的。
    """
    from app.services.seawindow import SeawindowService

    data = store.overview()
    sea = SeawindowService().summary()
    data["modules"].append({
        "name": "出海窗口调度",
        "created": sea["窗口总数"],
        "pending": sea["计划中"] + sea["窗口顺延"],
        "abnormal": sea["窗口顺延"],
    })
    data["cards"].extend([
        {"label": "可用船舶", "value": sea["可用船舶"]},
        {"label": "占用船舶", "value": sea["占用船舶"]},
    ])
    return data
