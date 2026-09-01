"""独居老人社会支持网络环境（原型版）。

混合分层仿真：
- 规模层：非焦点老人由环境内置规则驱动（子女联系、邻里互动、求助），不消耗 LLM。
- 焦点层：焦点老人是 PersonAgent，通过本环境的工具自主决策（打电话、串门、求助、
  参加活动），每个决策附带理由，写入 ``state/decisions.jsonl`` 供定性分析。

核心机制：
- 关系账本（不依赖 embedding）：每位老人对每个支持来源记录 类型/强度/最近联系/
  情感与工具性支持次数。
- 关系强度随不联系逐月衰减；关键节点流失（邻居搬走等）触发级联。
- 深度孤立操作化定义：连续 3 个模拟月无情感性支持接触，且当月工具性支持为 0。

每个仿真 step 视为 1 个模拟月。宏观指标写入 replay 表与 ``state/metrics.jsonl``。
"""

from __future__ import annotations

import json
import random
from datetime import datetime
from typing import Any, ClassVar, Dict, List, Optional

from agentsociety2.env import EnvBase, tool
from agentsociety2.storage import ColumnDef
from agentsociety2.storage.workspace_state import atomic_write_text

_STATE_REL = "state/ENV_STATE.json"
_METRICS_REL = "state/metrics.jsonl"
_DECISIONS_REL = "state/decisions.jsonl"

# 深度孤立判定阈值：连续无情感性支持的月数
DEEP_ISOLATION_MONTHS = 3

# 子女距离 -> (探望概率系数, 工具性帮助可达性)
_DISTANCE_FACTOR = {
    "local": (1.0, 1.0),
    "same_city": (0.6, 0.7),
    "other_province": (0.2, 0.15),
}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


class ElderSupportEnv(EnvBase):
    """独居老人支持网络环境：关系账本 + 月度事件 + 规则层老人。"""

    _env_state_columns: ClassVar[list[ColumnDef]] = [
        ColumnDef("isolation_rate", "REAL"),
        ColumnDef("deep_isolation_rate", "REAL"),
        ColumnDef("avg_loneliness", "REAL"),
        ColumnDef("avg_active_ties", "REAL"),
        ColumnDef("events_count", "INTEGER"),
        ColumnDef("help_requests", "INTEGER"),
        ColumnDef("help_success", "INTEGER"),
    ]
    _agent_state_columns: ClassVar[list[ColumnDef]] = [
        ColumnDef("loneliness", "REAL"),
        ColumnDef("active_ties", "INTEGER"),
        ColumnDef("months_no_emotional", "INTEGER"),
        ColumnDef("deep_isolation", "INTEGER"),
        ColumnDef("health", "REAL"),
        ColumnDef("events", "TEXT"),
    ]

    def __init__(
        self,
        elders: Optional[List[Dict[str, Any]]] = None,
        seed: int = 42,
        decay_rate: float = 0.06,
        event_rates: Optional[Dict[str, float]] = None,
        intervention: Optional[Dict[str, Any]] = None,
    ):
        """初始化环境。

        :param elders: 老人画像列表。每项字段：
            ``id``（焦点老人为 agent_id，规则层老人为负数或任意不冲突整数）、
            ``name``、``age``、``gender``、``health``（0-1）、
            ``extroversion``（0-1 外向性）、``focal``（是否 LLM 焦点老人）、
            ``children``（列表：``name``/``distance``（local|same_city|other_province）/
            ``contact_per_month``）、``ties``（初始邻里朋友：``name``/``kind``/``strength``）。
        :param seed: 随机种子（保证同种子可复现）。
        :param decay_rate: 关系强度月衰减率（当月无联系时）。
        :param event_rates: 月度事件基准概率，键：``illness``/``fall``/``neighbor_move``。
        """
        super().__init__()
        self._seed = int(seed)
        self._rng = random.Random(self._seed)
        self._decay_rate = float(decay_rate)
        self._event_rates = {
            "illness": 0.10,
            "fall": 0.03,
            "neighbor_move": 0.02,
            **(event_rates or {}),
        }
        self._month = 0
        self._started = False  # tick 0 只记初始快照，不做月末结算
        self._elders: Dict[int, Dict[str, Any]] = {}
        for e in elders or []:
            self._elders[int(e["id"])] = self._init_elder(e)
        # 环境级月度计数
        self._counters = {"events": 0, "help_requests": 0, "help_success": 0}
        self._decision_buffer: List[dict] = []
        # 干预配置：{"type": none|casework|timebank|platform,
        #           "start_month": int, "end_month": int, "params": {...}}
        self._intervention: Dict[str, Any] = intervention or {"type": "none"}
        self._timebank_credits: Dict[int, float] = {}
        self._timebank_pairs: List[List[int]] = []

    # ------------------------------------------------------------------
    # 初始化与状态
    # ------------------------------------------------------------------

    def _init_elder(self, e: Dict[str, Any]) -> Dict[str, Any]:
        ties: Dict[str, Dict[str, Any]] = {}
        for c in e.get("children", []):
            ties[str(c["name"])] = {
                "kind": "family",
                "distance": c.get("distance", "other_province"),
                "contact_per_month": float(c.get("contact_per_month", 2.0)),
                "strength": 0.8,
                "last_contact_month": 0,
                "emotional_count": 0,
                "instrumental_count": 0,
            }
        for tie in e.get("ties", []):
            ties[str(tie["name"])] = {
                "kind": tie.get("kind", "neighbor"),
                "distance": "local",
                "contact_per_month": 0.0,
                "strength": float(tie.get("strength", 0.5)),
                "last_contact_month": 0,
                "emotional_count": 0,
                "instrumental_count": 0,
            }
        return {
            "id": int(e["id"]),
            "name": str(e.get("name", f"老人{e['id']}")),
            "age": int(e.get("age", 75)),
            "gender": str(e.get("gender", "女")),
            "health": float(e.get("health", 0.7)),
            "extroversion": float(e.get("extroversion", 0.5)),
            "focal": bool(e.get("focal", False)),
            "ties": ties,
            "loneliness": _clamp(float(e.get("loneliness", 0.3))),
            "months_no_emotional": 0,
            "deep_isolation": False,
            "month_events": [],  # 本月发生的生活事件
            "month_emotional": 0,  # 本月获得的情感性支持次数
            "month_instrumental": 0,  # 本月获得的工具性支持次数
        }

    @classmethod
    def description(cls) -> str:
        return "独居老人社会支持网络环境：关系账本、月度生活事件、规则层老人与焦点老人工具。"

    @classmethod
    def init_description(cls) -> str:
        return """ElderSupportEnv: 独居老人社会支持网络环境

每个仿真 step = 1 个模拟月。环境维护每位老人的关系账本（支持来源、强度、
最近联系、情感/工具性支持次数），逐月生成生活事件（患病、跌倒、邻居搬走），
关系强度当月无联系则衰减。非焦点老人由内置规则驱动；焦点老人（PersonAgent）
用工具自主决策。

构造参数（kwargs）：
- elders: list[dict]，老人画像。字段：id(int)、name(str)、age(int)、gender(str)、
  health(0-1)、extroversion(0-1)、focal(bool)、
  children(list: name/distance[local|same_city|other_province]/contact_per_month)、
  ties(list: name/kind[neighbor|friend]/strength)
- seed: int 随机种子（默认 42）
- decay_rate: float 关系月衰减率（默认 0.06）
- event_rates: dict 月度事件概率（illness/fall/neighbor_move）
- intervention: dict 干预配置 {"type": none|casework|timebank|platform,
  "start_month": int, "end_month": int, "params": {...}}。
  casework=社工个案管理（n_workers/caseload）；timebank=时间银行互助
  （max_per_helper/post_persist）；platform=数字平台志愿匹配（coverage）

焦点老人可用工具：observe_my_life（观察自身处境）、call_family（给子女打电话）、
visit_neighbor（找邻居朋友走动）、seek_help（求助）、join_activity（参加社区活动）、
stay_home（宅家并说明原因）。统计工具：community_report。
"""

    async def to_workspace(self, workspace_path=None) -> None:
        if workspace_path is not None:
            self._bind_workspace(workspace_path)
        if self._workspace_root is None:
            raise RuntimeError("Env module workspace is not bound")
        atomic_write_text(
            self._workspace_root / _STATE_REL,
            json.dumps(
                {
                    "seed": self._seed,
                    "rng_state": self._rng.getstate(),
                    "decay_rate": self._decay_rate,
                    "event_rates": self._event_rates,
                    "month": self._month,
                    "started": self._started,
                    "elders": {str(k): v for k, v in self._elders.items()},
                    "counters": self._counters,
                    "intervention": self._intervention,
                    "timebank_credits": {str(k): v for k, v in self._timebank_credits.items()},
                    "timebank_pairs": self._timebank_pairs,
                },
                ensure_ascii=False,
                indent=2,
                default=list,
            ),
        )

    async def restore(self, workspace_path) -> bool:
        self._bind_workspace(workspace_path)
        state_path = self._workspace_root / _STATE_REL
        if not state_path.is_file():
            return False
        data = json.loads(state_path.read_text(encoding="utf-8"))
        self._seed = int(data["seed"])
        self._decay_rate = float(data["decay_rate"])
        self._event_rates = dict(data["event_rates"])
        self._month = int(data["month"])
        self._started = bool(data.get("started", True))
        self._elders = {int(k): v for k, v in data["elders"].items()}
        self._counters = dict(data["counters"])
        self._intervention = dict(data.get("intervention", {"type": "none"}))
        self._timebank_credits = {
            int(k): v for k, v in data.get("timebank_credits", {}).items()
        }
        self._timebank_pairs = [list(p) for p in data.get("timebank_pairs", [])]
        self._rng = random.Random(self._seed)
        try:
            st = data.get("rng_state")
            if st:
                self._rng.setstate((st[0], tuple(st[1]), st[2]))
        except Exception:
            pass  # 随机态恢复失败时退回种子重置，不阻断 resume
        return True

    # ------------------------------------------------------------------
    # 内部机制
    # ------------------------------------------------------------------

    def _elder(self, agent_id: int) -> Dict[str, Any]:
        e = self._elders.get(int(agent_id))
        if e is None:
            raise ValueError(f"未知老人 agent_id={agent_id}")
        return e

    def _log_decision(self, agent_id: int, action: str, detail: dict) -> None:
        self._decision_buffer.append(
            {
                "month": self._month,
                "agent_id": int(agent_id),
                "action": action,
                **detail,
            }
        )

    def _flush_jsonl(self, rel: str, rows: List[dict]) -> None:
        if self._workspace_root is None or not rows:
            return
        path = self._workspace_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def _touch_tie(
        self,
        elder: Dict[str, Any],
        name: str,
        *,
        emotional: bool = False,
        instrumental: bool = False,
        delta: float = 0.05,
    ) -> None:
        tie = elder["ties"].get(name)
        if tie is None:
            return
        tie["last_contact_month"] = self._month
        tie["strength"] = _clamp(tie["strength"] + delta)
        if emotional:
            tie["emotional_count"] += 1
            elder["month_emotional"] += 1
        if instrumental:
            tie["instrumental_count"] += 1
            elder["month_instrumental"] += 1

    def _deep_talk(self, tie: Dict[str, Any], *, in_person: bool) -> bool:
        """一次联系是否构成有效的情感性支持（说上心里话）。

        日常寒暄不等于情感支持：概率随关系强度上升，见面走动高于电话。
        """
        base = 0.25 if in_person else 0.10
        return self._rng.random() < base + 0.35 * tie["strength"]

    def _try_help(self, elder: Dict[str, Any], name: str, help_type: str) -> bool:
        """按关系强度与可达性判定求助是否成功，并更新账本。"""
        tie = elder["ties"].get(name)
        self._counters["help_requests"] += 1
        if tie is None:
            return False
        reach = 1.0
        if tie["kind"] == "family":
            reach = _DISTANCE_FACTOR.get(tie["distance"], (0.2, 0.15))[1]
        p = _clamp(0.15 + 0.8 * tie["strength"] * reach)
        ok = self._rng.random() < p
        if ok:
            self._counters["help_success"] += 1
            self._touch_tie(
                elder,
                name,
                emotional=(help_type == "emotional"),
                instrumental=(help_type != "emotional"),
                delta=0.08,
            )
            elder["loneliness"] = _clamp(elder["loneliness"] - 0.06)
        else:
            tie["strength"] = _clamp(tie["strength"] - 0.05)
            elder["loneliness"] = _clamp(elder["loneliness"] + 0.05)
        return ok

    def _gen_events(self, elder: Dict[str, Any]) -> List[str]:
        events: List[str] = []
        age_factor = 1.0 + max(0, elder["age"] - 70) * 0.03
        if self._rng.random() < self._event_rates["illness"] * (
            2.0 - elder["health"]
        ) * age_factor * 0.6:
            events.append("患病（本月身体不适，需要买药或就医）")
            elder["health"] = _clamp(elder["health"] - 0.05, 0.05)
        if self._rng.random() < self._event_rates["fall"] * age_factor:
            events.append("跌倒（行动不便，日常起居需要人搭把手）")
            elder["health"] = _clamp(elder["health"] - 0.08, 0.05)
        if self._rng.random() < self._event_rates["neighbor_move"]:
            neighbors = [
                n for n, t in elder["ties"].items() if t["kind"] in ("neighbor", "friend")
            ]
            if neighbors:
                gone = self._rng.choice(neighbors)
                del elder["ties"][gone]
                events.append(f"邻居/朋友「{gone}」搬走了，从此断了来往")
        return events

    def _rule_layer_month(self, elder: Dict[str, Any]) -> None:
        """规则层老人的月度行为：子女联系、邻里互动、遇事求助。"""
        # 子女按频率联系（泊松近似：逐次伯努利）；通话不必然构成情感支持
        for name, tie in list(elder["ties"].items()):
            if tie["kind"] != "family":
                continue
            n_contact = 0
            expect = tie["contact_per_month"] * (0.5 + 0.5 * tie["strength"])
            while expect > 0:
                if self._rng.random() < min(1.0, expect):
                    n_contact += 1
                expect -= 1.0
            for _ in range(n_contact):
                self._touch_tie(
                    elder, name,
                    emotional=self._deep_talk(tie, in_person=False),
                    delta=0.02,
                )
        # 邻里互动：外向性 × 强度；见面走动更容易说上心里话
        for name, tie in list(elder["ties"].items()):
            if tie["kind"] == "family":
                continue
            if self._rng.random() < elder["extroversion"] * (0.2 + 0.45 * tie["strength"]):
                self._touch_tie(
                    elder, name,
                    emotional=self._deep_talk(tie, in_person=True),
                    delta=0.03,
                )
        # 遇事求助：从最强的关系开始，最多两次
        if elder["month_events"]:
            candidates = sorted(
                elder["ties"].items(), key=lambda kv: kv[1]["strength"], reverse=True
            )
            # 内向者可能干脆不求助（面子/怕麻烦，规则层的简化近似）
            if self._rng.random() < 0.25 + 0.5 * (1 - elder["extroversion"]):
                candidates = []
            for name, _tie in candidates[:2]:
                if self._try_help(elder, name, "instrumental"):
                    break

    def _end_of_month(self, elder: Dict[str, Any]) -> None:
        """月末结算：衰减、孤独感稳态回归、深度孤立判定。"""
        for name, tie in list(elder["ties"].items()):
            if tie["last_contact_month"] < self._month:
                tie["strength"] = _clamp(tie["strength"] * (1 - self._decay_rate))
                if tie["strength"] < 0.05:
                    del elder["ties"][name]
        if elder["month_emotional"] > 0:
            elder["months_no_emotional"] = 0
        else:
            elder["months_no_emotional"] += 1
        # 孤独感向稳态水平回归：稳态由情感支持量、关系数量、健康与性格决定。
        # 联系多则稳态低，孤立则稳态高——不会单调塌缩，也不会无界上升。
        target = _clamp(
            0.90
            - 0.12 * min(elder["month_emotional"], 4)
            - 0.05 * min(len(elder["ties"]), 5)
            - 0.25 * elder["health"]
            + 0.10 * (1 - elder["extroversion"])
        )
        elder["loneliness"] = _clamp(
            elder["loneliness"] + 0.5 * (target - elder["loneliness"])
        )
        elder["deep_isolation"] = (
            elder["months_no_emotional"] >= DEEP_ISOLATION_MONTHS
            and elder["month_instrumental"] == 0
        )

    # ------------------------------------------------------------------
    # 干预机制（配置驱动，确定性调度，同种子可复现）
    # ------------------------------------------------------------------

    def _intervention_active(self) -> bool:
        iv = self._intervention
        if iv.get("type", "none") == "none":
            return False
        return iv.get("start_month", 1) <= self._month <= iv.get("end_month", 10**9)

    def _risk_rank(self) -> List[Dict[str, Any]]:
        """按孤立风险从高到低排序（社工评估逻辑的简化版）。"""

        def score(e: Dict[str, Any]) -> float:
            return (
                2.0 * e["months_no_emotional"]
                + 1.5 * (1 - e["health"])
                + 1.0 * max(0, 3 - len(e["ties"]))
                + 0.8 * len(e["month_events"])
                + e["loneliness"]
            )

        return sorted(self._elders.values(), key=score, reverse=True)

    def _make_tie(self, elder, name, kind, strength=0.3) -> None:
        if name not in elder["ties"]:
            elder["ties"][name] = {
                "kind": kind, "distance": "local", "contact_per_month": 0.0,
                "strength": strength, "last_contact_month": self._month,
                "emotional_count": 0, "instrumental_count": 0,
            }

    def _log_intervention(self, action: str, detail: dict) -> None:
        self._decision_buffer.append(
            {"month": self._month, "agent_id": -1, "action": action, **detail}
        )

    def _apply_intervention(self) -> None:
        if not self._intervention_active():
            return
        iv_type = self._intervention["type"]
        params = self._intervention.get("params", {})
        if iv_type == "casework":
            self._iv_casework(params)
        elif iv_type == "timebank":
            self._iv_timebank(params)
        elif iv_type == "platform":
            self._iv_platform(params)

    def _iv_casework(self, params: dict) -> None:
        """专业社工个案管理：风险评估 → 高风险者每月探访 + 家庭联结。"""
        n_workers = int(params.get("n_workers", 2))
        caseload = int(params.get("caseload", 8))
        capacity = n_workers * caseload
        for i, e in enumerate(self._risk_rank()[:capacity]):
            worker = f"社工小{'王李张刘'[i % n_workers % 4]}"
            self._make_tie(e, worker, "social_worker", 0.4)
            # 专业会谈：情感支持概率高
            self._touch_tie(e, worker, emotional=(self._rng.random() < 0.8), delta=0.05)
            e["month_events"].append(f"{worker}本月上门探访了一次")
            # 联结服务：概率性修复最强家庭纽带
            fam = [n for n, t in e["ties"].items() if t["kind"] == "family"]
            if fam and self._rng.random() < 0.5:
                target = max(fam, key=lambda n: e["ties"][n]["strength"])
                self._touch_tie(e, target, emotional=(self._rng.random() < 0.4),
                                delta=0.05)
                self._log_intervention(
                    "casework_link", {"elder": e["id"], "family": target}
                )
            self._log_intervention("casework_visit", {"elder": e["id"], "worker": worker})
        # 干预后风险重排在下月自然发生；工具性支持走正常求助渠道（社工是强可达 tie）

    def _iv_timebank(self, params: dict) -> None:
        """时间银行互助：低龄健康老人结对高风险老人，服务换积分，双向受益。

        结对关系一旦建立即持续（写入双方关系账本），这是撤出后可持续性的机制来源。
        """
        max_per_helper = int(params.get("max_per_helper", 2))
        # 每月重算可服务者；结对只增不减（关系存续）
        helpers = [
            e for e in self._elders.values()
            if e["health"] >= 0.6 and e["age"] <= 78
        ]
        paired_recipients = {p[1] for p in self._timebank_pairs}
        load = {h["id"]: 0 for h in helpers}
        for hid, rid in self._timebank_pairs:
            if hid in load:
                load[hid] += 1
        # 新结对：高风险且未被结对的老人
        for e in self._risk_rank():
            if e["id"] in paired_recipients or e["id"] in load:
                continue
            avail = [h for h in helpers if load.get(h["id"], 99) < max_per_helper]
            if not avail:
                break
            h = self._rng.choice(avail)
            self._timebank_pairs.append([h["id"], e["id"]])
            load[h["id"]] += 1
            paired_recipients.add(e["id"])
            self._log_intervention("timebank_match", {"helper": h["id"], "elder": e["id"]})
        # 每月互动：上门陪伴/搭手，帮扶者赚积分且自身也获益（互惠）
        for hid, rid in self._timebank_pairs:
            h, r = self._elders.get(hid), self._elders.get(rid)
            if h is None or r is None:
                continue
            if self._rng.random() < 0.85:  # 偶有当月未成行
                hname, rname = f"互助伙伴{h['name']}", f"互助对象{r['name']}"
                self._make_tie(r, hname, "timebank", 0.35)
                self._make_tie(h, rname, "timebank", 0.35)
                self._touch_tie(r, hname, emotional=(self._rng.random() < 0.6),
                                instrumental=(self._rng.random() < 0.5), delta=0.06)
                self._touch_tie(h, rname, emotional=(self._rng.random() < 0.4),
                                delta=0.04)
                self._timebank_credits[hid] = self._timebank_credits.get(hid, 0) + 1
                r["month_events"].append(f"{hname}本月来陪伴帮忙")

    def _timebank_afterglow(self) -> None:
        """时间银行撤出后：不再新结对、不再计积分，但已建立的人际结对
        （非机构服务，而是真实互惠关系）以较低概率延续互动。
        延续概率是 H4 的关键机制假设，报告中做敏感性分析。"""
        post_p = float(
            self._intervention.get("params", {}).get("post_persist", 0.5)
        )
        for hid, rid in self._timebank_pairs:
            h, r = self._elders.get(hid), self._elders.get(rid)
            if h is None or r is None:
                continue
            if self._rng.random() < post_p:
                hname, rname = f"互助伙伴{h['name']}", f"互助对象{r['name']}"
                if hname in r["ties"]:
                    self._touch_tie(r, hname, emotional=(self._rng.random() < 0.5),
                                    delta=0.03)
                if rname in h["ties"]:
                    self._touch_tie(h, rname, emotional=(self._rng.random() < 0.3),
                                    delta=0.02)

    def _iv_platform(self, params: dict) -> None:
        """数字平台志愿匹配：响应式、覆盖广，但志愿者轮换、关系浅。"""
        coverage = float(params.get("coverage", 0.6))
        for e in self._elders.values():
            need = bool(e["month_events"]) or e["months_no_emotional"] >= 2
            if not need or self._rng.random() > coverage:
                continue
            vol = f"志愿者{self._rng.choice('甲乙丙丁戊己庚辛')}"
            self._make_tie(e, vol, "volunteer", 0.2)
            tie = e["ties"][vol]
            tie["strength"] = min(tie["strength"], 0.35)  # 轮换制，关系难深
            self._touch_tie(e, vol, emotional=(self._rng.random() < 0.3),
                            instrumental=bool(e["month_events"]), delta=0.03)
            e["month_events"].append(f"{vol}通过社区平台上门服务了一次")
            self._log_intervention("platform_serve", {"elder": e["id"], "volunteer": vol})

    # ------------------------------------------------------------------
    # 焦点老人工具
    # ------------------------------------------------------------------

    @tool(readonly=True, kind="observe")
    async def observe_my_life(self, agent_id: int) -> dict:
        """观察自己当前的生活处境：健康、本月发生的事、和亲友邻里的关系情况。"""
        e = self._elder(agent_id)
        ties_view = []
        for name, tie in sorted(
            e["ties"].items(), key=lambda kv: kv[1]["strength"], reverse=True
        ):
            months_ago = self._month - tie["last_contact_month"]
            ties_view.append(
                {
                    "name": name,
                    "kind": tie["kind"],
                    "distance": tie["distance"],
                    "closeness": round(tie["strength"], 2),
                    "months_since_last_contact": months_ago,
                }
            )
        return {
            "month": self._month,
            "my_profile": {
                "name": e["name"],
                "age": e["age"],
                "gender": e["gender"],
                "health": round(e["health"], 2),
            },
            "this_month_events": e["month_events"] or ["本月无特别事件"],
            "loneliness_feeling": round(e["loneliness"], 2),
            "months_without_heart_to_heart_talk": e["months_no_emotional"],
            "my_relationships": ties_view,
        }

    @tool(readonly=False)
    async def call_family(self, agent_id: int, child_name: str, reason: str) -> dict:
        """给子女打电话聊天。child_name 是子女姓名，reason 是想打这通电话的原因。"""
        e = self._elder(agent_id)
        if child_name not in e["ties"]:
            return {"ok": False, "message": f"联系人里没有「{child_name}」"}
        tie = e["ties"][child_name]
        deep = self._deep_talk(tie, in_person=False)
        self._touch_tie(e, child_name, emotional=deep, delta=0.04)
        self._log_decision(
            agent_id, "call_family",
            {"target": child_name, "reason": reason, "deep_talk": deep},
        )
        if deep:
            return {"ok": True, "message": f"和{child_name}通了电话，说了不少心里话，心里舒坦了"}
        return {"ok": True, "message": f"和{child_name}通了电话，对方在忙，只匆匆聊了几句家常"}

    @tool(readonly=False)
    async def visit_neighbor(self, agent_id: int, neighbor_name: str, reason: str) -> dict:
        """去找邻居或朋友走动聊天。neighbor_name 是对方姓名，reason 是想走动的原因。"""
        e = self._elder(agent_id)
        if neighbor_name not in e["ties"]:
            return {"ok": False, "message": f"认识的人里没有「{neighbor_name}」"}
        tie = e["ties"][neighbor_name]
        deep = self._deep_talk(tie, in_person=True)
        self._touch_tie(e, neighbor_name, emotional=deep, delta=0.05)
        self._log_decision(
            agent_id, "visit_neighbor",
            {"target": neighbor_name, "reason": reason, "deep_talk": deep},
        )
        if deep:
            return {"ok": True, "message": f"和{neighbor_name}坐着聊了半天知心话，关系更熟络了"}
        return {"ok": True, "message": f"去{neighbor_name}家坐了坐，寒暄了几句"}

    @tool(readonly=False)
    async def seek_help(
        self, agent_id: int, target_name: str, help_type: str, reason: str
    ) -> dict:
        """遇到困难时向某人求助。help_type 取 instrumental（跑腿买药等实际帮忙）或
        emotional（找人说说心里话）。reason 说明为什么找这个人、犹豫过什么。"""
        e = self._elder(agent_id)
        if target_name not in e["ties"]:
            self._log_decision(
                agent_id,
                "seek_help",
                {"target": target_name, "help_type": help_type, "reason": reason,
                 "outcome": "no_such_tie"},
            )
            return {"ok": False, "message": f"联系人里没有「{target_name}」"}
        ok = self._try_help(e, target_name, help_type)
        self._log_decision(
            agent_id,
            "seek_help",
            {"target": target_name, "help_type": help_type, "reason": reason,
             "outcome": "success" if ok else "declined"},
        )
        if ok:
            return {"ok": True, "message": f"{target_name}帮了忙，这件事解决了"}
        return {"ok": False, "message": f"{target_name}这次没能帮上（在忙或不方便）"}

    @tool(readonly=False)
    async def join_activity(self, agent_id: int, activity: str, reason: str) -> dict:
        """参加社区活动（如广场舞、棋牌、义诊），有机会结识新邻居。"""
        e = self._elder(agent_id)
        e["loneliness"] = _clamp(e["loneliness"] - 0.04)
        e["month_emotional"] += 1
        made_friend = self._rng.random() < 0.35 + 0.4 * e["extroversion"]
        new_name = None
        if made_friend:
            new_name = f"活动认识的{self._rng.choice(['张阿姨', '刘叔', '王婶', '陈伯', '李姐'])}"
            if new_name not in e["ties"]:
                e["ties"][new_name] = {
                    "kind": "friend",
                    "distance": "local",
                    "contact_per_month": 0.0,
                    "strength": 0.25,
                    "last_contact_month": self._month,
                    "emotional_count": 1,
                    "instrumental_count": 0,
                }
        self._log_decision(
            agent_id,
            "join_activity",
            {"activity": activity, "reason": reason, "new_tie": new_name},
        )
        msg = f"参加了「{activity}」，心情好了些"
        if new_name:
            msg += f"，还认识了{new_name}"
        return {"ok": True, "message": msg}

    @tool(readonly=False)
    async def stay_home(self, agent_id: int, reason: str) -> dict:
        """这个月选择基本宅在家里不主动联系人，reason 说明原因（如身体累、怕麻烦人）。"""
        self._log_decision(agent_id, "stay_home", {"reason": reason})
        return {"ok": True, "message": "这个月基本待在家里"}

    @tool(readonly=True, kind="statistics")
    async def community_report(self) -> dict:
        """社区整体统计：孤立率、深度孤立率、平均孤独感、平均活跃关系数。"""
        return self._community_metrics()

    def _community_metrics(self) -> dict:
        n = len(self._elders) or 1
        lonely = sum(e["loneliness"] for e in self._elders.values()) / n
        active = sum(len(e["ties"]) for e in self._elders.values()) / n
        no_emo = sum(1 for e in self._elders.values() if e["months_no_emotional"] >= 1)
        deep = sum(1 for e in self._elders.values() if e["deep_isolation"])
        return {
            "month": self._month,
            "num_elders": len(self._elders),
            "isolation_rate": round(no_emo / n, 4),
            "deep_isolation_rate": round(deep / n, 4),
            "avg_loneliness": round(lonely, 4),
            "avg_active_ties": round(active, 4),
        }

    # ------------------------------------------------------------------
    # 仿真步进
    # ------------------------------------------------------------------

    async def step(self, tick: int, t: datetime):
        """一个 step = 一个模拟月。

        顺序：月末结算上一月（衰减/孤立判定）→ 进入新月 → 生成事件 →
        规则层老人行动 → 写指标。焦点老人在本 step 与下一 step 之间由
        PersonAgent 调用工具行动，其效果计入下一次结算。
        """
        self.t = t
        # tick 0 只记初始快照；之后每次调用先结算当前月
        if self._started:
            for e in self._elders.values():
                self._end_of_month(e)
        self._started = True

        metrics = self._community_metrics()
        agent_rows = [
            {
                "agent_id": aid,
                "loneliness": round(e["loneliness"], 4),
                "active_ties": len(e["ties"]),
                "months_no_emotional": e["months_no_emotional"],
                "deep_isolation": int(e["deep_isolation"]),
                "health": round(e["health"], 4),
                "events": "；".join(e["month_events"]),
            }
            for aid, e in self._elders.items()
        ]
        await self._write_env_state(
            tick,
            t,
            isolation_rate=metrics["isolation_rate"],
            deep_isolation_rate=metrics["deep_isolation_rate"],
            avg_loneliness=metrics["avg_loneliness"],
            avg_active_ties=metrics["avg_active_ties"],
            events_count=self._counters["events"],
            help_requests=self._counters["help_requests"],
            help_success=self._counters["help_success"],
        )
        await self._write_agent_state_batch(tick, t, agent_rows)
        self._flush_jsonl(
            _METRICS_REL,
            [{**metrics, "tick": tick, "t": t.isoformat(), **self._counters}],
        )
        self._flush_jsonl(_DECISIONS_REL, self._decision_buffer)
        self._decision_buffer = []
        self._counters = {"events": 0, "help_requests": 0, "help_success": 0}

        # 进入新月
        self._month += 1
        for e in self._elders.values():
            e["month_events"] = self._gen_events(e)
            self._counters["events"] += len(e["month_events"])
            e["month_emotional"] = 0
            e["month_instrumental"] = 0
        # 干预（若在窗口内）；时间银行撤出后已结对关系以较低概率延续
        if self._intervention_active():
            self._apply_intervention()
        elif (
            self._intervention.get("type") == "timebank"
            and self._month > self._intervention.get("end_month", 10**9)
        ):
            self._timebank_afterglow()
        # 规则层老人行动
        for e in self._elders.values():
            if not e["focal"]:
                self._rule_layer_month(e)
