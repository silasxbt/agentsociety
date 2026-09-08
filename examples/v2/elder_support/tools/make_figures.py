#!/usr/bin/env python3
"""论文图表统一生成：从 tmp/batch/comparison.json 出静态图 + 配套 CSV。

- fig1 主结局轨迹：跨条件月度孤立率（均值粗线 + 每 seed 细线 + 干预窗阴影）
- fig2 次结局轨迹：平均孤独感（同上）
- fig3 seed-level 散点：干预期孤立率按条件（配对结构可见）
- fig4 H4 配对差：撤出反弹相对同 seed none 的差值（点 = seed）

原则：每张图都有同名 CSV（原始数据版本）；图上标注有效 run 数；
有效 run < 12 时标题带（未冻结）。重跑脚本即全量重生成，勿手改输出。

双语：中文图用原文件名（供 main_zh.tex），英文图加 _en 后缀（供 main_en.tex）；
CSV 数据无语言之分，只写一份。

用法：<venv-python> tools/make_figures.py
输出：figures/fig1_trajectory_isolation[_en].png、fig1_trajectory_isolation.csv 等
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams["font.sans-serif"] = ["PingFang SC", "Hiragino Sans GB",
                                    "Arial Unicode MS", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

EXP = Path(__file__).resolve().parents[1]
OUT = EXP / "figures"
IV_START, IV_END = 7, 18
COLORS = {"none": "#4C72B0", "casework": "#DD5C42", "timebank": "#2E9E6B",
          "platform": "#DBA400"}
CONDS = ["none", "casework", "timebank", "platform"]

# 全部呈现文案集中于此；新增图表请两种语言同时补全
TEXTS = {
    "zh": {
        "labels": {"none": "基线", "casework": "个案管理",
                   "timebank": "时间银行", "platform": "数字平台"},
        "iv_window": f"干预窗 {IV_START}–{IV_END} 月",
        "xlabel_month": "模拟月份",
        "traj_title": "{ylabel}月度轨迹 · {tag}",
        "ylabel_iso": "孤立率",
        "ylabel_lon": "平均孤独感",
        "scatter_xlabel": "seed（条件横向错位以防重叠）",
        "scatter_ylabel": "干预期平均孤立率",
        "scatter_title": "干预期孤立率 · seed-level · {tag}",
        "panel_iv": "干预期孤立率配对差",
        "panel_reb": "撤出反弹配对差（H4，探索性）",
        "pairs_n": "(配对n={n})",
        "paired_ylabel": "差值（条件 - 同seed基线）",
        "paired_suptitle": "同 seed 配对对比 · {tag}",
        "tag": "有效 run n={n}", "tag_draft": "（未冻结）",
        "legend_n": "（n={n}）",
    },
    "en": {
        "labels": {"none": "Baseline", "casework": "Casework",
                   "timebank": "Timebank", "platform": "Platform"},
        "iv_window": f"Intervention window, months {IV_START}–{IV_END}",
        "xlabel_month": "Simulation month",
        "traj_title": "Monthly trajectory: {ylabel} · {tag}",
        "ylabel_iso": "Isolation rate",
        "ylabel_lon": "Mean loneliness",
        "scatter_xlabel": "seed (conditions jittered horizontally)",
        "scatter_ylabel": "Mean isolation rate, intervention window",
        "scatter_title": "In-window isolation rate · seed level · {tag}",
        "panel_iv": "Paired diff.: in-window isolation",
        "panel_reb": "Paired diff.: withdrawal rebound (H4, exploratory)",
        "pairs_n": "(pairs n={n})",
        "paired_ylabel": "Difference (condition − same-seed baseline)",
        "paired_suptitle": "Same-seed paired contrasts · {tag}",
        "tag": "valid runs n={n}", "tag_draft": " (not frozen)",
        "legend_n": " (n={n})",
    },
}


def load() -> dict:
    return json.loads((EXP / "tmp" / "batch" / "comparison.json")
                      .read_text(encoding="utf-8"))


def tag_of(comp: dict, t: dict) -> str:
    n = comp.get("valid_runs", 0)
    return t["tag"].format(n=n) + (t["tag_draft"] if n < 12 else "")


def suffix(lang: str) -> str:
    return "" if lang == "zh" else f"_{lang}"


def traj_fig(comp: dict, metric: str, ylabel_key: str, fname: str,
             lang: str) -> None:
    t = TEXTS[lang]
    ylabel = t[ylabel_key]
    traj = comp["trajectories"][metric]
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=200)
    ax.axvspan(IV_START, IV_END, color="#000", alpha=0.06,
               label=t["iv_window"])
    csv_rows = []
    for cond in CONDS:
        rows = traj.get(cond) or []
        if not rows:
            continue
        months = [r["month"] for r in rows]
        # seed 细线
        seeds = sorted({sv["seed"] for r in rows for sv in r["seed_values"]})
        for sd in seeds:
            ys = [next((sv["value"] for sv in r["seed_values"]
                        if sv["seed"] == sd), None) for r in rows]
            ax.plot(months, ys, color=COLORS[cond], alpha=0.25, lw=0.8)
        ax.plot(months, [r["mean"] for r in rows], color=COLORS[cond], lw=2,
                label=t["labels"][cond] + t["legend_n"].format(n=rows[0]["n"]))
        for r in rows:
            csv_rows.append({"condition": cond, "month": r["month"],
                             "mean": r["mean"], "sd": r["sd"], "n": r["n"],
                             **{f"seed{sv['seed']}": sv["value"]
                                for sv in r["seed_values"]}})
    ax.set_xlabel(t["xlabel_month"])
    ax.set_ylabel(ylabel)
    ax.set_xlim(0, 24)
    ax.set_title(t["traj_title"].format(ylabel=ylabel, tag=tag_of(comp, t)),
                 fontsize=11)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(OUT / f"{fname}{suffix(lang)}.png")
    plt.close(fig)
    if lang != "zh":
        return
    keys = sorted({k for r in csv_rows for k in r})
    with (OUT / f"{fname}.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(csv_rows)


def scatter_fig(comp: dict, lang: str) -> None:
    t = TEXTS[lang]
    fig, ax = plt.subplots(figsize=(6.5, 4.5), dpi=200)
    offs = {"none": -0.18, "casework": -0.06, "timebank": 0.06, "platform": 0.18}
    marks = {"none": "o", "casework": "s", "timebank": "^", "platform": "D"}
    csv_rows = []
    for cond in CONDS:
        rows = (comp["conditions"].get(cond) or {}).get("seeds") or []
        for r in rows:
            ax.scatter(r["seed"] + offs[cond], r["iso_iv"], color=COLORS[cond],
                       marker=marks[cond], s=48, zorder=3)
            csv_rows.append({"condition": cond, "seed": r["seed"],
                             "iso_iv": r["iso_iv"], "run": r["run"]})
        if rows:
            ax.scatter([], [], color=COLORS[cond], marker=marks[cond],
                       label=t["labels"][cond])
    ax.set_xlabel(t["scatter_xlabel"])
    ax.set_ylabel(t["scatter_ylabel"])
    ax.set_xticks([1, 2, 3])
    ax.set_title(t["scatter_title"].format(tag=tag_of(comp, t)), fontsize=11)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / f"fig3_scatter_iv_isolation{suffix(lang)}.png")
    plt.close(fig)
    if lang != "zh":
        return
    with (OUT / "fig3_scatter_iv_isolation.csv").open("w", newline="",
                                                      encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["condition", "seed", "iso_iv", "run"])
        w.writeheader()
        w.writerows(csv_rows)


def paired_fig(comp: dict, lang: str) -> None:
    t = TEXTS[lang]
    paired = comp.get("paired_contrasts_vs_none") or {}
    panels = [("iso_iv", t["panel_iv"]), ("iso_rebound", t["panel_reb"])]
    fig, axes = plt.subplots(1, 2, figsize=(9, 4.2), dpi=200, sharex=True)
    csv_rows = []
    for ax, (metric, title) in zip(axes, panels):
        xs, names = [], []
        for i, cond in enumerate([c for c in CONDS if c != "none"]):
            p = (paired.get(cond) or {}).get(metric) or {}
            for pr in p.get("pairs") or []:
                ax.scatter(i, pr["difference_vs_none"], color=COLORS[cond],
                           s=48, zorder=3)
                csv_rows.append({"metric": metric, "condition": cond,
                                 "seed": pr["seed"],
                                 "diff_vs_none": pr["difference_vs_none"]})
            if p.get("mean_difference") is not None:
                ax.hlines(p["mean_difference"], i - 0.2, i + 0.2,
                          color=COLORS[cond], lw=2)
            xs.append(i)
            names.append(t["labels"][cond] + "\n"
                         + t["pairs_n"].format(n=p.get("n", 0)))
        ax.axhline(0, color="#999", lw=0.8, ls="--")
        ax.set_xticks(xs)
        ax.set_xticklabels(names, fontsize=8)
        ax.set_title(title, fontsize=10)
    axes[0].set_ylabel(t["paired_ylabel"])
    fig.suptitle(t["paired_suptitle"].format(tag=tag_of(comp, t)), fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / f"fig4_paired_rebound{suffix(lang)}.png")
    plt.close(fig)
    if lang != "zh":
        return
    with (OUT / "fig4_paired_rebound.csv").open("w", newline="",
                                                encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["metric", "condition", "seed",
                                          "diff_vs_none"])
        w.writeheader()
        w.writerows(csv_rows)


def main() -> int:
    OUT.mkdir(exist_ok=True)
    comp = load()
    for lang in ("zh", "en"):
        traj_fig(comp, "isolation_rate", "ylabel_iso",
                 "fig1_trajectory_isolation", lang)
        traj_fig(comp, "avg_loneliness", "ylabel_lon",
                 "fig2_trajectory_loneliness", lang)
        scatter_fig(comp, lang)
        paired_fig(comp, lang)
    print(f"图表已写入 {OUT}（{tag_of(comp, TEXTS['zh'])}，中英各一套）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
