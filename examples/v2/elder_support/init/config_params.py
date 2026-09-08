#!/usr/bin/env python3
"""生成 ElderSupport 原型实验的 init_config.json 与 steps.yaml。

用法：
  python config_params.py --months 12 --profiles ../tmp/init/profiles.json

焦点老人使用 PersonAgent（LLM 完整推理），非焦点老人只存在于环境的规则层，
不创建 agent，不消耗 LLM。每个 step = 1 个模拟月（tick = 30 天）。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
TMP_INIT_DIR = EXP_DIR / "tmp" / "init"

MONTH_TICK_SEC = 30 * 24 * 3600  # 1 step = 1 个模拟月


def _profile_block(e: dict) -> str:
    children_desc = (
        "、".join(
            f"{c['name']}（住{ {'local': '本小区附近', 'same_city': '同城', 'other_province': '外地'}[c['distance']] }）"
            for c in e["children"]
        )
        or "没有子女"
    )
    ties_desc = "、".join(t["name"] for t in e["ties"]) or "平时几乎没有来往的邻居朋友"
    persona = "性格外向，爱串门聊天" if e["extroversion"] > 0.6 else (
        "性格内向要强，不爱麻烦别人" if e["extroversion"] < 0.4 else "性格随和"
    )
    return (
        f"你是{e['name']}，{e['age']}岁，{e['gender']}性，独自居住。{persona}。"
        f"子女情况：{children_desc}。相熟的邻居朋友：{ties_desc}。\n"
        "每个仿真步是你生活中的一个月。每个月你要：\n"
        "1. 先用 observe_my_life 看看自己这个月的处境（健康、发生的事、和亲友的关系）；\n"
        "2. 像一个真实的中国独居老人那样，决定这个月做哪几件事（给子女打电话、找邻居走动、"
        "遇到困难求助、参加社区活动，或者就宅在家）；一般做 1-3 件事即可；\n"
        "3. 每个决定都要在 reason 参数里说真实的心里话：包括顾虑（怕麻烦人、拉不下面子、"
        "怕欠人情）和期待。遇到困难时，你可以求助，也可以硬扛着不求助——按你的性格来。\n"
        "始终保持角色，按自己的身体状况、性格和人情世故来行动，不要过度乐观或过度活跃。\n"
        "【语言要求】reason 必须全部用简体中文口语写，像老人自己说话那样。"
        "禁止出现任何英文单词或句子，禁止中英混写。"
    )


def questionnaire_step(month: int, target_ids: list[int]) -> dict:
    return {
        "type": "questionnaire",
        "questionnaire_id": f"elder_support_survey_m{month}",
        "title": f"第{month}个月生活状况问卷",
        "description": "",
        "target_agent_ids": target_ids,
        "questions": [
            {
                "id": "loneliness",
                "prompt": (
                    "过去一个月，您感到孤独吗？请选择最符合的一项。"
                    "（1=从不孤独 2=偶尔 3=有时 4=经常 5=总是孤独）"
                ),
                "response_type": "choice",
                "choices": ["1", "2", "3", "4", "5"],
            },
            {
                "id": "help_source",
                "prompt": "如果您突然生病需要人帮忙，您第一个会找谁？",
                "response_type": "choice",
                "choices": ["子女", "邻居或朋友", "居委会/社区", "硬扛着不找人", "不知道找谁"],
            },
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--survey-every", type=int, default=3)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--decay-rate", type=float, default=0.06)
    ap.add_argument(
        "--profiles", default=str(TMP_INIT_DIR / "profiles.json")
    )
    ap.add_argument("--start-t", default="2026-01-01T08:00:00")
    ap.add_argument(
        "--intervention", default="none",
        choices=["none", "casework", "timebank", "platform"],
    )
    ap.add_argument("--iv-start", type=int, default=7)
    ap.add_argument("--iv-end", type=int, default=18)
    args = ap.parse_args()

    profiles_path = Path(args.profiles).resolve()
    elders = json.loads(profiles_path.read_text(encoding="utf-8"))
    focal = [e for e in elders if e.get("focal")]
    focal_ids = [e["id"] for e in focal]

    agents = [
        {
            "agent_id": e["id"],
            "agent_type": "PersonAgent",
            "kwargs": {
                "id": e["id"],
                "profile": _profile_block(e),
                "max_react_turns": 8,
                # 不激活 built-in@daily-guidance：该技能声明适用于"小时及以下"
                # 时间尺度，且其 pre_step hook 每步注入通勤/位置日程。本实验
                # 1 step = 1 个模拟月，激活后老人会把 react turns 耗在环境不
                # 支持的"通勤/位置变更"上而不调用决策工具——baseline12 实测
                # 由此产生 28.2% 的 agent-月完全静默。详见 README 的"已知坑"。
            },
        }
        for e in focal
    ]

    init_cfg = {
        "env_modules": [
            {
                "module_type": "ElderSupportEnv",
                "kwargs": {
                    "elders": elders,
                    "seed": args.seed,
                    "decay_rate": args.decay_rate,
                    **(
                        {
                            "intervention": {
                                "type": args.intervention,
                                "start_month": args.iv_start,
                                "end_month": args.iv_end,
                                "params": {},
                            }
                        }
                        if args.intervention != "none"
                        else {}
                    ),
                },
            }
        ],
        "agents": agents,
    }

    steps: list[dict] = []
    for m in range(1, args.months + 1):
        steps.append({"type": "run", "num_steps": 1, "tick": MONTH_TICK_SEC})
        if args.survey_every > 0 and m % args.survey_every == 0:
            steps.append(questionnaire_step(m, focal_ids))
    # 结尾补一个 run，让最后一个月的行动被结算进指标
    steps.append({"type": "run", "num_steps": 1, "tick": MONTH_TICK_SEC})

    steps_yaml = {"start_t": args.start_t, "steps": steps}

    TMP_INIT_DIR.mkdir(parents=True, exist_ok=True)
    out_cfg = TMP_INIT_DIR / "init_config.json"
    out_steps = TMP_INIT_DIR / "steps.yaml"
    out_cfg.write_text(json.dumps(init_cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    out_steps.write_text(
        yaml.safe_dump(steps_yaml, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    print(f"Wrote {out_cfg}")
    print(f"Wrote {out_steps}")
    print(
        f"elders={len(elders)} focal={len(focal_ids)} months={args.months} "
        f"seed={args.seed} focal_ids={focal_ids}"
    )


if __name__ == "__main__":
    main()
