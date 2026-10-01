"""出海窗口与船舶调度接口：窗口登记、随船人员变更、海况顺延、取消释放、船舶占用。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.seawindow import SeawindowService

router = APIRouter(prefix="/api/seawindow", tags=["出海窗口调度"])

service = SeawindowService()

LIST_FIELDS = [
    "窗口编号", "海况等级", "预计离岸时段", "随船人员", "船舶编号", "作业船舶", "顺延原因",
]
WINDOW_STATUSES = ["计划中", "窗口顺延", "已取消"]
ACTIONS = ["更新人员", "海况升级顺延", "取消窗口", "登记船舶占用"]


@router.get("/summary")
def summary() -> dict[str, int]:
    """台账与看板共用的统计：可用/占用船数、各状态窗口数，一处计算两处展示。"""
    return service.summary()


@router.get("/vessels")
def list_vessels() -> dict[str, Any]:
    items = service.list_vessels()
    return {"items": items, "total": len(items)}


@router.get("/occupancies")
def list_occupancies(
    window_id: int | None = Query(default=None, description="只看某个窗口的占用历史"),
) -> dict[str, Any]:
    """占用历史：已释放记录按当时口径保留，供台账追溯。"""
    items = service.list_occupancies(window_id=window_id)
    return {"items": items, "total": len(items)}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按窗口编号检索"),
    status: str | None = Query(default=None, description="计划中、窗口顺延、已取消"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按窗口编号与状态过滤出海窗口列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_windows(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出台账：窗口、船舶池与占用历史一并导出，历史占用保留当时快照。"""
    windows, total = service.list_windows(page=1, size=10000)
    return {
        "module": "seawindow",
        "total": total,
        "summary": service.summary(),
        "items": windows,
        "vessels": service.list_vessels(),
        "occupancies": service.list_occupancies(),
    }


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条出海窗口明细；不存在时给出可读的错误说明。"""
    entry = service.get_window(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"出海窗口 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记出海窗口：海况等级、预计离岸时段、随船人员、作业船舶缺一不可。"""
    entry, message = service.create_window(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message or "出海窗口登记失败")
    return ActionResult(ok=True, message="出海窗口已登记，船舶占用已同步", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """更新人员 / 海况升级顺延 / 取消窗口 / 登记船舶占用；非法动作与冲突都会被拦下并说明原因。"""
    values = payload.values
    action = str(values.get("action") or "").strip()
    if action == "更新人员":
        entry, message = service.update_crew(entry_id, values.get("随船人员"))
    elif action == "海况升级顺延":
        entry, message = service.postpone(entry_id, values)
    elif action == "取消窗口":
        entry, message = service.cancel_window(entry_id)
    elif action == "登记船舶占用":
        entry, message = service.assign_vessel(entry_id, values.get("船舶编号"))
    else:
        return ActionResult(ok=False, message=f"动作「{action}」不属于出海窗口可执行范围")
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
