"""出海窗口与船舶调度业务规则：窗口流转、船舶占用与释放的口径都收在这里。

设计要点（对应台账一致性要求）：
- 窗口、船舶、占用记录都只存在 store 里，页面改任何一处都必须落库后再读，
  重新打开或刷新看到的才是同一份数据。
- 船舶「占用中」不存字段，而是从占用中的占用记录推导；窗口台账和看板都读
  fleet_summary，可用船数天然一致。
- 占用记录按窗口编号幂等：同一窗口重复提交只留一条；窗口取消或回港后记录
  标记为已释放并保留当时的船舶、人员名单快照，不删不改。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "seawindow"
VESSEL_MODULE = "vessel"
OCCUPANCY_MODULE = "occupancy"

REQUIRED_FIELDS = ["窗口编号", "作业场站", "海况等级", "预计离岸时段"]
STATUS_ORDER = ["待出海", "已出海", "窗口顺延", "已完成", "已取消"]
TERMINAL_STATUSES = ["已完成", "已取消"]
ACTIONS = ["提交占用", "确认出海", "海况升级", "取消窗口", "确认回港"]
EDITABLE_FIELDS = ["海况等级", "预计离岸时段", "随船人员", "作业船舶"]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _as_list(value: Any) -> list[str]:
    """随船人员、作业船舶既接受数组，也接受顿号/逗号分隔的字符串。"""
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").replace("，", "、").replace(",", "、")
    return [item.strip() for item in text.split("、") if item.strip()]


class SeawindowService:
    # ---------- 查询 ----------

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("窗口编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def list_occupancies(self) -> list[dict[str, Any]]:
        """占用台账：新的在前，已释放的历史记录原样保留。"""
        return sorted(store.rows(OCCUPANCY_MODULE), key=lambda row: int(row.get("id", 0)), reverse=True)

    # ---------- 船舶池（占用状态由占用记录推导，不落第二份数据） ----------

    def _active_occupancies(self) -> list[dict[str, Any]]:
        return [row for row in store.rows(OCCUPANCY_MODULE) if row.get("status") == "占用中"]

    def _occupied_vessel_map(self) -> dict[str, str]:
        """船舶编号 -> 占用它的窗口编号，只统计占用中的记录。"""
        mapping: dict[str, str] = {}
        for record in self._active_occupancies():
            for code in _as_list(record.get("作业船舶")):
                mapping[code] = str(record.get("窗口编号", ""))
        return mapping

    def fleet(self) -> list[dict[str, Any]]:
        occupied = self._occupied_vessel_map()
        fleet_rows: list[dict[str, Any]] = []
        for row in store.rows(VESSEL_MODULE):
            code = str(row.get("船舶编号", ""))
            if row.get("status") == "维保中":
                current, window = "维保中", ""
            elif code in occupied:
                current, window = "占用中", occupied[code]
            else:
                current, window = "可用", ""
            fleet_rows.append({**row, "当前状态": current, "占用窗口": window})
        return fleet_rows

    def fleet_summary(self) -> dict[str, int]:
        fleet_rows = self.fleet()
        return {
            "船舶总数": len(fleet_rows),
            "可用": sum(1 for row in fleet_rows if row["当前状态"] == "可用"),
            "占用中": sum(1 for row in fleet_rows if row["当前状态"] == "占用中"),
            "维保中": sum(1 for row in fleet_rows if row["当前状态"] == "维保中"),
        }

    # ---------- 占用记录 ----------

    def _active_occupancy_for(self, window_code: str) -> dict[str, Any] | None:
        for record in self._active_occupancies():
            if record.get("窗口编号") == window_code:
                return record
        return None

    def _check_vessels(self, vessel_codes: list[str], *, holder: str = "") -> list[str]:
        """返回不可用的船舶及原因；holder 是允许重复持有的窗口（自己占的不算冲突）。"""
        known = {str(row.get("船舶编号", "")): row for row in store.rows(VESSEL_MODULE)}
        occupied = self._occupied_vessel_map()
        problems: list[str] = []
        for code in vessel_codes:
            vessel = known.get(code)
            if vessel is None:
                problems.append(f"{code} 不在船舶台账里")
            elif vessel.get("status") == "维保中":
                problems.append(f"{code} 维保中")
            elif code in occupied and occupied[code] != holder:
                problems.append(f"{code} 正被窗口 {occupied[code]} 占用")
        return problems

    def _submit_occupancy(self, window: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """为窗口锁定船舶；同一窗口重复提交只留一条占用记录。"""
        window_code = str(window.get("窗口编号", ""))
        if window.get("status") in TERMINAL_STATUSES:
            return None, f"窗口 {window_code} {window.get('status')}，不能再提交占用"
        existing = self._active_occupancy_for(window_code)
        if existing is not None:
            return existing, f"窗口 {window_code} 已存在占用记录 {existing.get('占用编号')}，未重复提交"
        vessel_codes = _as_list(window.get("作业船舶"))
        if not vessel_codes:
            return None, f"窗口 {window_code} 未登记作业船舶，先在台账里补登船舶再提交占用"
        problems = self._check_vessels(vessel_codes)
        if problems:
            return None, "船舶不可用：" + "；".join(problems)
        rows = store.rows(OCCUPANCY_MODULE)
        record = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "status": "占用中",
            "pending": True,
            "abnormal": False,
            "占用编号": f"OCC-{len(rows) + 1:04d}",
            "窗口编号": window_code,
            "作业船舶": vessel_codes,
            "随船人员": _as_list(window.get("随船人员")),
            "预计离岸时段": str(window.get("预计离岸时段", "")),
            "提交时间": _now(),
            "释放时间": "",
            "释放原因": "",
        }
        rows.append(record)
        return record, f"占用已提交：{record['占用编号']}，{len(vessel_codes)} 艘船舶锁定"

    def _release_occupancy(self, window_code: str, reason: str) -> dict[str, Any] | None:
        """释放窗口的占用：记录转已释放并写原因，船舶自动回到可用池。

        只改状态与释放信息，提交时的船舶、人员名单快照原样保留。
        """
        record = self._active_occupancy_for(window_code)
        if record is None:
            return None
        record["status"] = "已释放"
        record["pending"] = False
        record["释放时间"] = _now()
        record["释放原因"] = reason
        return record

    # ---------- 窗口登记与修改 ----------

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        errors = [f"缺少必填字段：{field}" for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if errors:
            return None, errors
        code = str(values.get("窗口编号", "")).strip()
        if any(row.get("窗口编号") == code for row in store.rows(MODULE)):
            return None, [f"窗口编号 {code} 已存在，请勿重复登记"]
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: str(values.get(field, "")).strip() for field in REQUIRED_FIELDS})
        entry["随船人员"] = _as_list(values.get("随船人员"))
        entry["作业船舶"] = _as_list(values.get("作业船舶"))
        entry["顺延原因"] = ""
        entry["取消原因"] = ""
        entry["登记时间"] = _now()
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def update_entry(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """修改窗口的海况、时段、随船人员与作业船舶，落库后各端读到的才是同一份。

        窗口有占用中的记录时，船舶与人员名单同步到占用记录上（仍是一条记录，
        不产生新占用）；已完结的窗口不允许再改，名单以历史记录为准。
        """
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"出海窗口 {entry_id} 不存在或已归档"
        if entry.get("status") in TERMINAL_STATUSES:
            return None, f"窗口 {entry.get('窗口编号')} {entry.get('status')}，名单以历史记录为准，不能再改"
        updates = {field: values[field] for field in EDITABLE_FIELDS if field in values}
        if not updates:
            return None, "没有需要修改的字段"
        window_code = str(entry.get("窗口编号", ""))
        occupancy = self._active_occupancy_for(window_code)
        if "作业船舶" in updates:
            vessel_codes = _as_list(updates["作业船舶"])
            if occupancy is not None:
                problems = self._check_vessels(vessel_codes, holder=window_code)
                if problems:
                    return None, "船舶不可用：" + "；".join(problems)
            entry["作业船舶"] = vessel_codes
            if occupancy is not None:
                occupancy["作业船舶"] = vessel_codes
        if "随船人员" in updates:
            entry["随船人员"] = _as_list(updates["随船人员"])
            if occupancy is not None:
                occupancy["随船人员"] = entry["随船人员"]
        for field in ("海况等级", "预计离岸时段"):
            if field in updates:
                text = str(updates[field] or "").strip()
                if not text:
                    return None, f"{field}不能为空"
                entry[field] = text
        return entry, f"窗口 {window_code} 已更新，重新打开或刷新看到的都是这份名单"

    # ---------- 窗口动作 ----------

    def run_action(self, entry_id: int, action: str, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"出海窗口 {entry_id} 不存在或已归档"
        if action not in ACTIONS:
            return None, f"动作「{action}」不属于出海窗口可执行范围"
        handler = {
            "提交占用": self._act_submit,
            "确认出海": self._act_depart,
            "海况升级": self._act_postpone,
            "取消窗口": self._act_cancel,
            "确认回港": self._act_return,
        }[action]
        return handler(entry, values)

    def _act_submit(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        record, message = self._submit_occupancy(entry)
        if record is None:
            return None, message
        return entry, message

    def _act_depart(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        if entry.get("status") not in ("待出海", "窗口顺延"):
            return None, f"窗口当前状态为「{entry.get('status')}」，不能确认出海"
        window_code = str(entry.get("窗口编号", ""))
        if self._active_occupancy_for(window_code) is None:
            return None, f"窗口 {window_code} 尚未提交占用，先锁定作业船舶再确认出海"
        entry["status"] = "已出海"
        entry["pending"] = True
        return entry, f"窗口 {window_code} 已确认出海"

    def _act_postpone(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        if entry.get("status") not in ("待出海", "窗口顺延"):
            return None, f"窗口当前状态为「{entry.get('status')}」，不能标记顺延"
        reason = str(values.get("顺延原因") or values.get("原因") or "").strip()
        if not reason:
            return None, "海况升级必须写明顺延原因，窗口才能标记为窗口顺延"
        level = str(values.get("海况等级") or "").strip()
        if level:
            entry["海况等级"] = level
        slot = str(values.get("预计离岸时段") or "").strip()
        if slot:
            entry["预计离岸时段"] = slot
        entry["status"] = "窗口顺延"
        entry["顺延原因"] = reason
        entry["abnormal"] = True
        return entry, f"窗口 {entry.get('窗口编号')} 已标记窗口顺延：{reason}"

    def _act_cancel(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        status = str(entry.get("status", ""))
        if status == "已取消":
            return None, f"窗口 {entry.get('窗口编号')} 已取消，请勿重复操作"
        if status in ("已出海", "已完成"):
            return None, f"窗口当前状态为「{status}」，不能取消；如在海上作业请确认回港"
        reason = str(values.get("取消原因") or values.get("原因") or "").strip() or "计划调整"
        window_code = str(entry.get("窗口编号", ""))
        released = self._release_occupancy(window_code, f"窗口取消：{reason}")
        entry["status"] = "已取消"
        entry["pending"] = False
        entry["取消原因"] = reason
        if released is not None:
            return entry, f"窗口 {window_code} 已取消，占用 {released.get('占用编号')} 已释放，船舶回到可用池"
        return entry, f"窗口 {window_code} 已取消"

    def _act_return(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        if entry.get("status") != "已出海":
            return None, f"窗口当前状态为「{entry.get('status')}」，不能确认回港"
        window_code = str(entry.get("窗口编号", ""))
        released = self._release_occupancy(window_code, "作业完成回港")
        entry["status"] = "已完成"
        entry["pending"] = False
        if released is not None:
            return entry, f"窗口 {window_code} 已回港，占用 {released.get('占用编号')} 已释放，船舶回到可用池"
        return entry, f"窗口 {window_code} 已回港"
