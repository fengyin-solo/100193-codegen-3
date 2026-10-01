"""出海窗口与船舶调度业务规则。

窗口台账、船舶可用池、占用历史共用同一份服务端数据，页面不保存任何本地副本：
- 随船人员调整直接改窗口记录与当前占用快照，重新打开/刷新读到的都是落库后的名单；
- 窗口取消时把「占用中」的记录置为「已释放」，船舶自动回到可用池，取消动作幂等；
- 同一窗口重复登记同一船舶占用只保留一条记录；
- 可用/占用船数一律由占用记录推导，台账与看板取的是同一个 summary；
- 已释放的占用记录只追加、不改写，历史按当时口径保留。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.store import store

WINDOW_MODULE = "seawindow_window"
VESSEL_MODULE = "seawindow_vessel"
OCCUPANCY_MODULE = "seawindow_occupancy"

REQUIRED_FIELDS = ["窗口编号", "海况等级", "预计离岸时段", "随船人员", "船舶编号"]
WINDOW_PLANNED = "计划中"
WINDOW_POSTPONED = "窗口顺延"
WINDOW_CANCELLED = "已取消"
WINDOW_STATUSES = [WINDOW_PLANNED, WINDOW_POSTPONED, WINDOW_CANCELLED]

VESSEL_AVAILABLE = "可用"
OCC_ACTIVE = "占用中"
OCC_RELEASED = "已释放"

MIN_SEA_GRADE = 1
MAX_SEA_GRADE = 9


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _norm_crew(value: Any) -> str:
    """随船人员名单统一用顿号分隔，避免「张三、李四」和「张三,李四」被当成两份名单。"""
    parts = [part for part in re.split(r"[、,，;；\s]+", str(value or "")) if part]
    return "、".join(parts)


def _next_id(rows: list[dict[str, Any]]) -> int:
    return max((int(row.get("id", 0)) for row in rows), default=0) + 1


class SeawindowService:
    # ---- 读取 ----------------------------------------------------------------

    def list_windows(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = list(store.rows(WINDOW_MODULE))
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("窗口编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_window(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(WINDOW_MODULE, entry_id)

    def list_occupancies(self, window_id: int | None = None) -> list[dict[str, Any]]:
        """历史占用记录按时间倒序返回；已释放记录是快照，调用方不得改写。"""
        rows = list(store.rows(OCCUPANCY_MODULE))
        if window_id is not None:
            rows = [row for row in rows if int(row.get("window_id", 0)) == window_id]
        return list(reversed(rows))

    def list_vessels(self) -> list[dict[str, Any]]:
        """船舶池状态由占用记录实时推导，保证台账和看板看到的可用船数一致。"""
        occupied = {int(row["vessel_id"]): row for row in self._active_occupancies()}
        result: list[dict[str, Any]] = []
        for vessel in store.rows(VESSEL_MODULE):
            row = dict(vessel)
            occ = occupied.get(int(vessel["id"]))
            row["status"] = OCC_ACTIVE if occ else VESSEL_AVAILABLE
            row["occupied_by"] = int(occ["window_id"]) if occ else None
            row["占用窗口"] = str(occ["窗口编号"]) if occ else ""
            result.append(row)
        return result

    def summary(self) -> dict[str, int]:
        """台账统计卡片和运营看板都取这里的数，口径只有一份。"""
        vessels = store.rows(VESSEL_MODULE)
        occupied_ids = {int(row["vessel_id"]) for row in self._active_occupancies()}
        windows = store.rows(WINDOW_MODULE)
        return {
            "船舶总数": len(vessels),
            "可用船舶": len(vessels) - len(occupied_ids),
            "占用船舶": len(occupied_ids),
            "窗口总数": len(windows),
            WINDOW_PLANNED: sum(1 for row in windows if row.get("status") == WINDOW_PLANNED),
            WINDOW_POSTPONED: sum(1 for row in windows if row.get("status") == WINDOW_POSTPONED),
            WINDOW_CANCELLED: sum(1 for row in windows if row.get("status") == WINDOW_CANCELLED),
        }

    # ---- 写入 ----------------------------------------------------------------

    def create_window(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
        number = str(values.get("窗口编号") or "").strip()
        period = str(values.get("预计离岸时段") or "").strip()
        crew = _norm_crew(values.get("随船人员"))
        vessel_code = str(values.get("船舶编号") or "").strip()

        missing = [
            label
            for label, value in (
                ("窗口编号", number),
                ("预计离岸时段", period),
                ("随船人员", crew),
                ("船舶编号", vessel_code),
            )
            if not value
        ]
        if str(values.get("海况等级") or "").strip() == "":
            missing.insert(1, "海况等级")
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"

        grade, message = self._parse_grade(values.get("海况等级"))
        if grade is None:
            return None, message

        windows = store.rows(WINDOW_MODULE)
        if any(str(row.get("窗口编号")) == number for row in windows):
            return None, f"窗口编号 {number} 已登记，请勿重复建窗"

        vessel = self._find_vessel(vessel_code)
        if vessel is None:
            return None, f"作业船舶 {vessel_code} 不在船舶池里，请先确认船号"
        holder = self._active_occupancy_for_vessel(int(vessel["id"]))
        if holder is not None:
            return None, f"船舶 {vessel['船舶名称']} 已被窗口 {holder['窗口编号']} 占用，无法再分配"

        entry = {
            "id": _next_id(windows),
            "窗口编号": number,
            "海况等级": grade,
            "预计离岸时段": period,
            "随船人员": crew,
            "船舶编号": vessel_code,
            "作业船舶": str(vessel["船舶名称"]),
            "顺延原因": "",
            "status": WINDOW_PLANNED,
            "pending": True,
            "abnormal": False,
        }
        windows.append(entry)
        self._occupy(entry, vessel, crew, grade)
        return entry, None

    def update_crew(
        self, window_id: int, crew_value: Any
    ) -> tuple[dict[str, Any] | None, str]:
        window = store.find(WINDOW_MODULE, window_id)
        if window is None:
            return None, f"出海窗口 {window_id} 不存在或已归档"
        if window.get("status") == WINDOW_CANCELLED:
            return None, "窗口已取消，不能再调整随船人员"
        crew = _norm_crew(crew_value)
        if not crew:
            return None, "随船人员名单不能为空"
        window["随船人员"] = crew
        # 当前占用记录代表本窗口在船人员，随窗口一起更新；已释放的历史快照不动。
        occ = self._active_occupancy_for_window(window_id)
        if occ is not None:
            occ["随船人员快照"] = crew
        return window, "随船人员名单已更新并落库"

    def postpone(
        self, window_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        window = store.find(WINDOW_MODULE, window_id)
        if window is None:
            return None, f"出海窗口 {window_id} 不存在或已归档"
        if window.get("status") == WINDOW_CANCELLED:
            return None, "窗口已取消，不能再标记顺延"
        reason = str(values.get("顺延原因") or "").strip()
        if not reason:
            return None, "海况升级顺延必须写明原因"

        grade = int(window["海况等级"])
        raw = str(values.get("海况等级") or "").strip()
        if raw:
            new_grade, message = self._parse_grade(raw)
            if new_grade is None:
                return None, message
            if new_grade <= grade:
                return None, f"海况升级需填写高于当前（{grade} 级）的等级"
            grade = new_grade

        window["海况等级"] = grade
        window["顺延原因"] = reason
        window["status"] = WINDOW_POSTPONED
        window["pending"] = True
        window["abnormal"] = True
        occ = self._active_occupancy_for_window(window_id)
        if occ is not None:
            occ["海况等级快照"] = grade
        # 顺延期间船舶继续占用，不释放回可用池。
        return window, f"窗口已标记顺延（{grade} 级海况），船舶继续占用"

    def cancel_window(self, window_id: int) -> tuple[dict[str, Any] | None, str]:
        window = store.find(WINDOW_MODULE, window_id)
        if window is None:
            return None, f"出海窗口 {window_id} 不存在或已归档"
        if window.get("status") == WINDOW_CANCELLED:
            # 幂等：已取消窗口重复提交不会再生成占用，船也不会被重新扣住。
            return window, "窗口此前已取消，占用船舶已释放，无需重复处理"
        occ = self._active_occupancy_for_window(window_id)
        if occ is not None:
            self._release(occ)
        window["status"] = WINDOW_CANCELLED
        window["pending"] = False
        message = "窗口已取消，占用船舶已释放回可用池"
        if occ is None:
            message = "窗口已取消（该窗口本就没有占用中的船舶）"
        return window, message

    def assign_vessel(
        self, window_id: int, vessel_code: Any
    ) -> tuple[dict[str, Any] | None, str]:
        """登记/更换窗口占用的作业船舶。

        同窗口同船重复提交是幂等的，只保留一条占用记录；换船时旧占用释放留痕、
        新占用另起一条，历史按当时口径保留。
        """
        window = store.find(WINDOW_MODULE, window_id)
        if window is None:
            return None, f"出海窗口 {window_id} 不存在或已归档"
        if window.get("status") == WINDOW_CANCELLED:
            return None, "窗口已取消，不能再登记船舶占用"
        code = str(vessel_code or "").strip()
        if not code:
            return None, "请选择要占用的作业船舶"
        vessel = self._find_vessel(code)
        if vessel is None:
            return None, f"作业船舶 {code} 不在船舶池里"

        current = self._active_occupancy_for_window(window_id)
        if current is not None and int(current["vessel_id"]) == int(vessel["id"]):
            return window, "该窗口已登记该船舶占用，保留唯一一条占用记录"

        holder = self._active_occupancy_for_vessel(int(vessel["id"]))
        if holder is not None and int(holder["window_id"]) != window_id:
            return None, f"船舶 {vessel['船舶名称']} 已被窗口 {holder['窗口编号']} 占用"

        if current is not None:
            self._release(current)
        self._occupy(window, vessel, str(window.get("随船人员") or ""), int(window["海况等级"]))
        window["船舶编号"] = str(vessel["船舶编号"])
        window["作业船舶"] = str(vessel["船舶名称"])
        return window, f"已登记 {vessel['船舶名称']} 的占用记录"

    # ---- 内部辅助 ------------------------------------------------------------

    def _active_occupancies(self) -> list[dict[str, Any]]:
        return [
            row
            for row in store.rows(OCCUPANCY_MODULE)
            if row.get("record_status") == OCC_ACTIVE
        ]

    def _active_occupancy_for_window(self, window_id: int) -> dict[str, Any] | None:
        for row in self._active_occupancies():
            if int(row.get("window_id", 0)) == window_id:
                return row
        return None

    def _active_occupancy_for_vessel(self, vessel_id: int) -> dict[str, Any] | None:
        for row in self._active_occupancies():
            if int(row.get("vessel_id", 0)) == vessel_id:
                return row
        return None

    def _find_vessel(self, vessel_code: str) -> dict[str, Any] | None:
        for vessel in store.rows(VESSEL_MODULE):
            if str(vessel.get("船舶编号")) == vessel_code:
                return vessel
        return None

    def _parse_grade(self, value: Any) -> tuple[int | None, str | None]:
        try:
            grade = int(str(value).strip())
        except (TypeError, ValueError):
            return None, f"海况等级需为 {MIN_SEA_GRADE}-{MAX_SEA_GRADE} 的整数"
        if not MIN_SEA_GRADE <= grade <= MAX_SEA_GRADE:
            return None, f"海况等级需在 {MIN_SEA_GRADE}-{MAX_SEA_GRADE} 级之间"
        return grade, None

    def _occupy(
        self, window: dict[str, Any], vessel: dict[str, Any], crew: str, grade: int
    ) -> dict[str, Any]:
        rows = store.rows(OCCUPANCY_MODULE)
        occ = {
            "id": _next_id(rows),
            "window_id": int(window["id"]),
            "窗口编号": str(window["窗口编号"]),
            "vessel_id": int(vessel["id"]),
            "船舶编号": str(vessel["船舶编号"]),
            "船舶名称": str(vessel["船舶名称"]),
            "随船人员快照": crew,
            "海况等级快照": grade,
            "占用时间": _now(),
            "释放时间": None,
            "record_status": OCC_ACTIVE,
            "pending": True,
            "abnormal": False,
        }
        rows.append(occ)
        return occ

    def _release(self, occ: dict[str, Any]) -> None:
        occ["record_status"] = OCC_RELEASED
        occ["释放时间"] = _now()
        occ["pending"] = False
