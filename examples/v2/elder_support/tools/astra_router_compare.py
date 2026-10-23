#!/usr/bin/env python3
"""gpt-6-astra seed 1：路由修复前后同模型对照（只读，描述性）。

输入（均为 gitignore 的本地副本，只含 metrics/decisions）：
- tmp/model_compare/gpt-6-astra/{none,casework}_s1   旧路由
- tmp/astra_router_v1/{none,casework,timebank,platform}_s1   新路由（2026-10-20 修复后）
输出：
- tests/astra_router_compare.json   聚合结果（不含微观数据）
- paper/numbers.tex 中 ASTRA-ROUTER 标记块（\\Ar... 宏）

只做旧/新路由下 Astra 同模型对照，不与 Sol 批次混合。窗口同 compare_conditions：
干预期 7–18，撤出后 19–24。DONE 标记不作要求（新 cohort 用 chain.log 作完成凭证）。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXP / "tools"))
from compare_conditions import validate  # noqa: E402

OLD = EXP / "tmp" / "model_compare" / "gpt-6-astra"
NEW = EXP / "tmp" / "astra_router_v1"
CONDS = {"none": "None", "casework": "Cw", "timebank": "Tb", "platform": "Pf"}
BEGIN, END = "% BEGIN ASTRA-ROUTER (tools/astra_router_compare.py)", "% END ASTRA-ROUTER"


def arm(run_dir: Path) -> dict | None:
    if not (run_dir / "env/ElderSupportEnv/state/metrics.jsonl").is_file():
        return None
    v = validate(run_dir)
    ms = v["metrics"]

    def avg(lo: int, hi: int) -> float:
        xs = [m["isolation_rate"] for m in ms if lo <= m["month"] <= hi]
        return sum(xs) / len(xs)

    iv, post = avg(7, 18), avg(19, 24)
    return {
        "silence_rate": v["silence_rate"],
        "valid": v["silence_rate"] <= 0.10 and v["months"] == 24,
        "months": v["months"],
        "iso_iv": round(iv, 6),
        "iso_post": round(post, 6),
        "iso_rebound": round(post - iv, 6),
    }


def paired(arms: dict) -> dict | None:
    if not (arms.get("none") and arms.get("casework")):
        return None
    return {k: round(arms["casework"][k] - arms["none"][k], 6) for k in ("iso_iv", "iso_post", "iso_rebound")}


def pp(x: float) -> str:
    return f"{x * 100:+.1f}"


def main() -> int:
    result = {}
    for tag, base in (("old", OLD), ("new", NEW)):
        arms = {c: arm(base / f"{c}_s1") for c in CONDS}
        result[tag] = {"arms": {c: a for c, a in arms.items() if a}, "paired_casework_minus_none": paired(arms)}
    if len(result["new"]["arms"]) != 4 or not result["old"]["paired_casework_minus_none"]:
        raise SystemExit("缺少旧路由 none/casework 或新路由四条件数据")
    result["note"] = "gpt-6-astra seed 1，路由修复前后同模型描述性对照；不与 Sol 混合"
    (EXP / "tests" / "astra_router_compare.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

    lines = [BEGIN]
    for tag, t in (("old", "Old"), ("new", "New")):
        for c, a in result[tag]["arms"].items():
            k = CONDS[c]
            lines += [
                f"\\newcommand{{\\Ar{t}Sil{k}}}{{{a['silence_rate'] * 100:.1f}}}",
                f"\\newcommand{{\\Ar{t}Iv{k}}}{{{a['iso_iv'] * 100:.1f}}}",
                f"\\newcommand{{\\Ar{t}Post{k}}}{{{a['iso_post'] * 100:.1f}}}",
                f"\\newcommand{{\\Ar{t}Reb{k}}}{{{pp(a['iso_rebound'])}}}",
            ]
        p = result[tag]["paired_casework_minus_none"]
        lines += [
            f"\\newcommand{{\\Ar{t}PIv}}{{{pp(p['iso_iv'])}}}",
            f"\\newcommand{{\\Ar{t}PPost}}{{{pp(p['iso_post'])}}}",
            f"\\newcommand{{\\Ar{t}PReb}}{{{pp(p['iso_rebound'])}}}",
        ]
    lines.append(END)
    block = "\n".join(lines)
    nt = EXP / "paper" / "numbers.tex"
    text = nt.read_text()
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)
    text = pattern.sub(lambda _: block, text) if pattern.search(text) else text.rstrip("\n") + "\n" + block + "\n"
    nt.write_text(text)
    print(json.dumps({t: result[t]["paired_casework_minus_none"] for t in ("old", "new")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
