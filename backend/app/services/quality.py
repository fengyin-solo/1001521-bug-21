"""数据质控业务规则：状态流转、轮次管理、字段校验与统计口径都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "quality"
REQUIRED_FIELDS = ["质控编号", "质控时段", "涉及站点"]
STATUS_ORDER = ["待执行", "执行中", "已完成", "已退回"]

# 动作 -> (目标状态, 允许发起动作的当前状态)。
# 不在允许集合里的一律拒绝并说明原因，避免重复提交把任务静默推成已完成。
ACTION_TRANSITIONS = {
    "启动质控": ("执行中", {"待执行", "已退回", "已完成"}),
    "确认完成": ("已完成", {"执行中"}),
    "退回重做": ("已退回", {"执行中", "已完成"}),
}


def _today() -> str:
    return date.today().isoformat()


def _to_count(value: Any) -> int:
    """检出疑误数统一成非负整数；非法输入按 0 处理，保证列表、统计、详情口径一致。"""
    try:
        return max(int(str(value).strip()), 0)
    except (TypeError, ValueError):
        return 0


class QualityService:
    # ---- 读取 ----

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
            rows = [row for row in rows if keyword in str(row.get("质控编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        for row in rows:
            self._sync(row)
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is not None:
            self._sync(entry)
        return entry

    def stats(self) -> list[dict[str, Any]]:
        """页脚统计卡片：与列表、详情读同一份数据实时汇总，刷新后口径一致。"""
        month = _today()[:7]
        pending = 0
        rounds_this_month = 0
        abnormal_total = 0
        for row in store.rows(MODULE):
            self._sync(row)
            if row["status"] == STATUS_ORDER[0]:
                pending += 1
            for item in row["rounds"]:
                if str(item.get("启动时间", "")).startswith(month):
                    rounds_this_month += 1
                abnormal_total += _to_count(item.get("检出疑误数"))
        return [
            {"label": "待执行质控", "value": pending},
            {"label": "本月质控轮次", "value": rounds_this_month},
            {"label": "检出疑误数", "value": abnormal_total},
        ]

    # ---- 写入 ----

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: str(values.get(field)).strip() for field in REQUIRED_FIELDS})
        entry["质控规则"] = str(values.get("质控规则") or "").strip()
        entry["质控人员"] = str(values.get("质控人员") or "").strip()
        entry["质控日期"] = ""
        entry["status"] = STATUS_ORDER[0]
        entry["退回原因"] = ""
        entry["rounds"] = []
        self._sync(entry)
        rows.append(entry)
        return entry, []

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"质控任务 {entry_id} 不存在或已归档"
        if action not in ACTION_TRANSITIONS:
            return None, f"动作「{action}」不属于数据质控可执行范围"
        target, allowed = ACTION_TRANSITIONS[action]
        current = str(entry.get("status") or STATUS_ORDER[0])
        if current not in allowed:
            return None, f"质控任务当前状态为「{current}」，不允许执行「{action}」"
        ok, message = self._apply(entry, action, values)
        if not ok:
            return None, message
        entry["status"] = target
        self._sync(entry)
        return entry, message

    # ---- 状态流转 ----

    def _apply(self, entry: dict[str, Any], action: str, values: dict[str, Any]) -> tuple[bool, str]:
        if action == "启动质控":
            return self._start_round(entry, values)
        if action == "确认完成":
            return self._finish_round(entry, values)
        return self._reject_round(entry, values)

    def _start_round(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[bool, str]:
        """启动质控一律新开一轮，历史轮次保留在 rounds 里，不覆盖上一轮结果。"""
        rounds = entry.setdefault("rounds", [])
        number = len(rounds) + 1
        operator = str(values.get("质控人员") or entry.get("质控人员") or "").strip()
        rounds.append({
            "轮次": number,
            "状态": "执行中",
            "检出疑误数": 0,
            "退回原因": "",
            "质控人员": operator,
            "启动时间": _today(),
            "完成时间": "",
        })
        if operator:
            entry["质控人员"] = operator
        entry["退回原因"] = ""
        return True, f"质控任务已启动第 {number} 轮质控"

    def _finish_round(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[bool, str]:
        if not str(entry.get("质控时段") or "").strip():
            return False, "质控时段缺失，不能确认完成，请先补录质控时段"
        current = self._current_round(entry)
        if current is None:
            return False, "没有正在执行的质控轮次，不能确认完成"
        count = _to_count(values.get("检出疑误数", 0))
        operator = str(values.get("质控人员") or current.get("质控人员") or entry.get("质控人员") or "").strip()
        current["状态"] = "已完成"
        current["检出疑误数"] = count
        current["完成时间"] = _today()
        if operator:
            current["质控人员"] = operator
            entry["质控人员"] = operator
        entry["质控日期"] = _today()
        entry["退回原因"] = ""
        return True, f"第 {current['轮次']} 轮质控已确认完成，检出疑误数 {count} 条"

    def _reject_round(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[bool, str]:
        reason = str(values.get("退回原因") or "").strip()
        if not reason:
            return False, "退回重做必须填写退回原因"
        current = self._current_round(entry) or (entry.get("rounds") or [None])[-1]
        if current is not None:
            current["状态"] = "已退回"
            current["退回原因"] = reason
            current["完成时间"] = _today()
        entry["退回原因"] = reason
        label = f"第 {current['轮次']} 轮" if current else "当前"
        return True, f"{label}质控已退回：{reason}"

    # ---- 内部工具 ----

    @staticmethod
    def _current_round(entry: dict[str, Any]) -> dict[str, Any] | None:
        for item in reversed(entry.get("rounds") or []):
            if item.get("状态") == "执行中":
                return item
        return None

    @staticmethod
    def _sync(entry: dict[str, Any]) -> None:
        """从 status + rounds 派生展示字段，保证列表、统计、详情三处口径一致。"""
        rounds = entry.setdefault("rounds", [])
        status = str(entry.get("status") or STATUS_ORDER[0])
        entry["status"] = status
        entry["质控状态"] = status
        entry["当前轮次"] = len(rounds)
        entry["检出疑误数"] = sum(_to_count(item.get("检出疑误数")) for item in rounds)
        entry["pending"] = status != "已完成"
        entry["abnormal"] = status == "已退回"
        entry.setdefault("退回原因", "")
