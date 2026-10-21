#!/usr/bin/env python3
"""论文架构图：分层（LLM 焦点层 / 规则层）、环境路由、数据锚定与科学性纪律回路。

输出：figures/fig0_architecture.png（中文）、figures/fig0_architecture_en.png（英文）
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

plt.rcParams["font.sans-serif"] = ["PingFang SC", "Hiragino Sans GB", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
OUT = Path(__file__).resolve().parents[1] / "figures"

TEXT = {
    "zh": {
        "survey": "调查数据\nCLHLS 2021 · CHARLS",
        "profiles": "画像生成\n边际分布锚定",
        "focal": "LLM 焦点层\n6 名老人（PersonAgent）\n记忆 · 推理 · 理由",
        "rules": "规则层\n14 名老人\n按联系频率自动接触",
        "router": "环境路由\n一句话 → 代码生成 → 工具\n只读 / 可写；注册表能力清单",
        "env": "ElderSupportEnv\n关系账本 · 衰减 · 月度事件\n干预：社工探访 /\n时间银行 / 数字平台",
        "trace": "全程留痕\nmetrics · decisions · trace",
        "gate": "科学性纪律\n预注册 · 效度门槛 · 根因分类\n成本核算 · 结果来源对照",
        "loop": "提案--评估回路（harness）\n干预排期搜索 · 动力学校准（训练 / 留出）",
        "ask": "ask_env\n（一句话）",
        "tools": "工具调用",
        "auto": "规则接触",
        "dyn": "动力学参数",
        "fit": "调查靶标",
        "title": "",
    },
    "en": {
        "survey": "Survey data\nCLHLS 2021 · CHARLS",
        "profiles": "Profile generator\nmarginals anchored",
        "focal": "LLM focal layer\n6 elders (PersonAgent)\nmemory · reasoning",
        "rules": "Rules layer\n14 elders\ncontacts from frequencies",
        "router": "Environment router\nsentence → codegen → tools\nread-only / write\nregistry catalog",
        "env": "ElderSupportEnv\ntie ledger · decay · events\ninterventions:\ncasework / timebank / platform",
        "trace": "Full trace\nmetrics · decisions · trace",
        "gate": "Scientific discipline\npreregistration · gates\nroot causes · costs\nresult-source ledger",
        "loop": "Propose--evaluate loop (harness)\nschedule search · dynamics calibration (train / hold-out)",
        "ask": "ask_env",
        "tools": "tool calls",
        "auto": "rules",
        "dyn": "dynamics params",
        "fit": "survey targets",
        "title": "",
    },
}

COLORS = {"data": "#e8eef7", "llm": "#fde7d4", "rule": "#e3f1e3", "env": "#f2f2f2", "disc": "#efe6f7"}


SCALE = {"v": 1.0}


def box(ax, x, y, w, h, text, color, fs=8.5):
    fs *= SCALE["v"]
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                fc=color, ec="#555", lw=0.9))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, linespacing=1.35)


def arrow(ax, p, q, label="", fs=7.5, off=(0, 0.12)):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=11, lw=1.0, color="#333"))
    if label:
        ax.text((p[0] + q[0]) / 2 + off[0], (p[1] + q[1]) / 2 + off[1], label,
                ha="center", va="center", fontsize=fs, color="#333")


def draw(lang: str) -> Path:
    t = TEXT[lang]
    SCALE["v"] = 1.0 if lang == "zh" else 0.92
    fig, ax = plt.subplots(figsize=(11, 5.2))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 5.2)
    ax.axis("off")
    box(ax, 0.1, 3.9, 1.9, 0.9, t["survey"], COLORS["data"])
    box(ax, 0.1, 2.5, 1.9, 0.9, t["profiles"], COLORS["data"])
    box(ax, 2.6, 3.6, 2.4, 1.2, t["focal"], COLORS["llm"])
    box(ax, 2.6, 1.0, 2.4, 1.1, t["rules"], COLORS["rule"])
    box(ax, 5.6, 3.6, 2.4, 1.2, t["router"], COLORS["llm"])
    box(ax, 5.6, 1.0, 2.4, 1.6, t["env"], COLORS["env"], fs=8)
    box(ax, 8.6, 2.0, 2.3, 0.9, t["trace"], COLORS["env"])
    box(ax, 8.6, 3.5, 2.3, 1.3, t["gate"], COLORS["disc"], fs=8)
    box(ax, 2.6, 0.05, 8.3, 0.7, t["loop"], COLORS["disc"])
    arrow(ax, (1.05, 3.9), (1.05, 3.4))
    arrow(ax, (2.0, 2.95), (2.6, 4.0))
    arrow(ax, (2.0, 2.95), (2.6, 1.7))
    arrow(ax, (5.0, 4.2), (5.6, 4.2), t["ask"], off=(0, -0.42))
    arrow(ax, (6.8, 3.6), (6.8, 2.6), t["tools"], off=(0.45, 0))
    arrow(ax, (5.0, 1.55), (5.6, 1.55), t["auto"], off=(0, 0.2))
    arrow(ax, (8.0, 1.8), (8.6, 2.4))
    arrow(ax, (9.75, 2.9), (9.75, 3.5))
    arrow(ax, (9.75, 2.0), (9.75, 0.75))
    arrow(ax, (1.05, 2.5), (2.6, 0.4), t["fit"], off=(-0.45, -0.1))
    arrow(ax, (7.2, 0.75), (7.2, 1.0), "", off=(0, 0))
    ax.text(7.75, 0.88, t["dyn"], ha="left", va="center", fontsize=7.5, color="#333")
    out = OUT / ("fig0_architecture.png" if lang == "zh" else "fig0_architecture_en.png")
    fig.savefig(out, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return out


if __name__ == "__main__":
    for lang in ("zh", "en"):
        print(draw(lang))
