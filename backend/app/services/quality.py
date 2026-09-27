"""数据质控业务规则：状态流转、轮次台账与统计口径都收在这里。

关键约定：
- 退回重做必须填写退回原因，任务停在「已退回」，原因随轮次保留；
- 每次启动质控都新开一轮，历史轮次不覆盖，检出疑误数按轮次累计；
- 确认完成只允许从「执行中」进入，重复提交、质控时段缺失都会被拦下；
- 列表、页脚统计、详情页三处的检出疑误数都从同一份轮次台账推导。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "quality"
REQUIRED_FIELDS = ["质控编号", "质控时段", "涉及站点"]
STATUS_ORDER = ["待执行", "执行中", "已完成", "已退回"]
# 动作 -> (允许的前置状态, 目标状态)
ACTION_RULES: dict[str, tuple[set[str], str]] = {
    "启动质控": ({"待执行", "已退回"}, "执行中"),
    "确认完成": ({"执行中"}, "已完成"),
    "退回重做": ({"执行中", "已完成"}, "已退回"),
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_count(value: Any) -> int | None:
    """把检出疑误数解析成非负整数；解析不了返回 None 由调用方报错。"""
    try:
        count = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return count if count >= 0 else None


class QualityService:
    # ---------- 读取 ----------

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        period: str | None = None,
        site: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        for row in rows:
            self._sync(row)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("质控编号", ""))]
        if period:
            rows = [row for row in rows if period in str(row.get("质控时段", ""))]
        if site:
            rows = [row for row in rows if site in str(row.get("涉及站点", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is not None:
            self._sync(entry)
        return entry

    def stats(self) -> dict[str, int]:
        """页脚/卡片统计：与列表、详情共用同一份轮次台账，保证三处口径一致。"""
        rows = store.rows(MODULE)
        month_prefix = datetime.now().strftime("%Y-%m")
        rounds = [r for row in rows for r in self._rounds(row)]
        return {
            "待执行质控": sum(1 for row in rows if row.get("status") == "待执行"),
            "本月质控轮次": sum(
                1 for r in rounds if str(r.get("启动时间", "")).startswith(month_prefix)
            ),
            "检出疑误数": sum(int(r["检出疑误数"]) for r in rounds if r.get("检出疑误数") is not None),
        }

    # ---------- 写入 ----------

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        for field in ("质控规则", "质控人员", "质控日期"):
            if values.get(field) is not None:
                entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["rounds"] = []
        self._sync(entry)
        rows.append(entry)
        store.save()
        return entry, []

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"质控任务 {entry_id} 不存在或已归档"
        self._sync(entry)
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于数据质控可执行范围"
        allowed_from, target = ACTION_RULES[action]
        current = str(entry.get("status") or "")
        if current == target:
            return None, f"质控任务已处于「{target}」，请勿重复提交"
        if current not in allowed_from:
            return None, f"当前状态为「{current}」，不能执行「{action}」"

        handler = {
            "启动质控": self._start,
            "确认完成": self._finish,
            "退回重做": self._reject,
        }[action]
        error = handler(entry, values)
        if error:
            return None, error
        entry["status"] = target
        self._sync(entry)
        store.save()
        return entry, f"质控任务已{action}（第 {entry['当前轮次']} 轮）"

    # ---------- 动作实现 ----------

    def _start(self, entry: dict[str, Any], values: dict[str, Any]) -> str | None:
        """启动质控：新开一轮，历史轮次保留不覆盖。"""
        if not str(entry.get("质控时段") or "").strip():
            return "质控时段缺失，无法启动质控，请先补齐质控时段"
        rounds = self._rounds(entry)
        rounds.append({
            "轮次": len(rounds) + 1,
            "状态": "执行中",
            "启动时间": _now(),
            "完成时间": None,
            "检出疑误数": None,
            "退回原因": None,
            "质控人员": str(values.get("质控人员") or entry.get("质控人员") or "").strip(),
        })
        return None

    def _finish(self, entry: dict[str, Any], values: dict[str, Any]) -> str | None:
        """确认完成：校验时段与疑误数，把当前轮次闭环。"""
        if not str(entry.get("质控时段") or "").strip():
            return "质控时段缺失，不能确认完成，请先补齐质控时段"
        count = _parse_count(values.get("检出疑误数", 0))
        if count is None:
            return "检出疑误数必须是非负整数"
        current = self._current_round(entry)
        if current is None:
            return "没有正在执行的质控轮次，请先启动质控"
        current["状态"] = "已完成"
        current["完成时间"] = _now()
        current["检出疑误数"] = count
        operator = str(values.get("质控人员") or "").strip()
        if operator:
            current["质控人员"] = operator
            entry["质控人员"] = operator
        entry["质控日期"] = current["完成时间"][:10]
        return None

    def _reject(self, entry: dict[str, Any], values: dict[str, Any]) -> str | None:
        """退回重做：必须给出退回原因，原因写进轮次台账，任务停在已退回。"""
        reason = str(values.get("退回原因") or "").strip()
        if not reason:
            return "退回重做必须填写退回原因"
        round_no = values.get("轮次")
        target_round = None
        for item in reversed(self._rounds(entry)):
            if round_no is not None and int(item.get("轮次", 0)) != _parse_count(round_no):
                continue
            if item.get("状态") in ("执行中", "已完成"):
                target_round = item
                break
        if target_round is None:
            return "没有可退回的质控轮次"
        target_round["状态"] = "已退回"
        target_round["退回原因"] = reason
        target_round["完成时间"] = _now()
        return None

    # ---------- 轮次台账与派生字段 ----------

    @staticmethod
    def _rounds(entry: dict[str, Any]) -> list[dict[str, Any]]:
        return entry.setdefault("rounds", [])

    def _current_round(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        for item in reversed(self._rounds(entry)):
            if item.get("状态") == "执行中":
                return item
        return None

    def _sync(self, entry: dict[str, Any]) -> None:
        """从轮次台账推导列表/详情共用的展示字段，保证各处口径一致。"""
        rounds = self._rounds(entry)
        entry["当前轮次"] = len(rounds)
        entry["检出疑误数"] = sum(
            int(r["检出疑误数"]) for r in rounds if r.get("检出疑误数") is not None
        )
        reasons = [str(r["退回原因"]) for r in rounds if r.get("退回原因")]
        entry["退回原因"] = reasons[-1] if reasons else ""
        entry["质控状态"] = entry.get("status", STATUS_ORDER[0])
        entry["pending"] = entry.get("status") in ("待执行", "执行中", "已退回")
        entry["abnormal"] = entry.get("status") == "已退回"
