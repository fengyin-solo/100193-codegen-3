"""出海窗口接口：窗口登记与流转、船舶占用台账、船队可用口径都从这一个服务读。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.seawindow import SeawindowService

router = APIRouter(prefix="/api/seawindow", tags=["出海窗口"])

service = SeawindowService()

STATUSES = ["待出海", "已出海", "窗口顺延", "已完成", "已取消"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按窗口编号检索"),
    status: str | None = Query(default=None, description="待出海、已出海、窗口顺延、已完成、已取消"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按窗口编号与状态过滤出海窗口列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/fleet")
def fleet() -> dict[str, Any]:
    """船队口径：船舶的占用状态由占用记录推导，台账页与看板读到的可用船数一致。"""
    return {"summary": service.fleet_summary(), "items": service.fleet()}


@router.get("/occupancies")
def occupancies() -> dict[str, Any]:
    """占用台账：占用中与已释放的记录都在，历史记录保留提交当时的船舶与名单。"""
    items = service.list_occupancies()
    return {"items": items, "total": len(items)}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出出海窗口台账：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "seawindow", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条出海窗口明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"出海窗口 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条出海窗口，缺字段或窗口编号重复时说明原因而不是静默丢弃。"""
    entry, errors = service.create_entry(payload.values)
    if errors:
        return ActionResult(ok=False, message="；".join(errors))
    return ActionResult(ok=True, message="出海窗口已登记，提交占用后作业船舶才会锁定", entry=entry)


@router.put("/{entry_id}", response_model=ActionResult)
def update_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """修改窗口的海况、时段、随船人员与作业船舶：改动落库，重新打开或刷新读到的都是最新名单。"""
    entry, message = service.update_entry(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条出海窗口执行提交占用、确认出海、海况升级、取消窗口、确认回港。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
