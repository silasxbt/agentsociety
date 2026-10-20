# 论文编译与下一版方向（2026-10-20）

## 当前版本（本提交）

- 正本：本仓库 `paper/main_zh.tex`、`main_en.tex`。GCP 两台机器上的 tex/PDF 是 10-12 前的旧副本，不要在那边改。
- 本版改动：
  - harness 统一称“提案–评估闭环”：只在固定规则下搜索干预排期，不改模型参数，
    不跨轮自动带入教训；新增局限 (11) 写明自校准是后续工作。
  - 中文附录“参数表与依据”（`app:params` / `tab:params`），正文两处引用指向它。
  - 第 12 场 platform_s2 改判为行为型静默（见 `MODEL_COMPARE.md` 10-20 复核）。
  - 裁判/运动员分离：H1/H2 改为“与参数规定的在场效应同向”、删 Masi 对应；孤独感写明是稳态公式
    （无事件项），ℓ≥0.6 标为手定切点；求助成功率改为“规定”，只留请求对象与次数为涌现；
    删“静默集中于干预窗”；摘要与 H4 改用撤出后水平；新增局限 (11)–(13)：帮扶者年龄上限 ×
    画像年龄、风险分配与评价同变量、诊断量与静默门槛偏倚；总结只列三项实验给出的结果。
- 尚未编译：本机与 GCP 均无 TeX。

## 编译当前版本（有 TeX Live 且有 `tmp/` 的数据机器）

```bash
cd examples/v2/elder_support
tools/build_paper.sh all
```

脚本会刷新图表与 `numbers.tex` 后 xelatex→bibtex→xelatex×2。验收：

1. 日志无 `^!` 硬错误、无未定义引用；`grep -c "??" *.log` 为 0。
2. `git diff paper/numbers.tex`：数字变化须能逐条解释，否则先查原因再用。
3. `\LoopIters`、`\LoopBestDesc`、`\LoopBestScore` 依赖
   `tests/harness_loop_result.json`；该文件和 `harness_loop_log.jsonl`、
   `cost_report.json`、`silence_diagnosis.json` 一并找回提交。找不回则从正文撤掉这几个数，
   只保留闭环设计描述。
4. 英文版附录参数表尚缺，须对照中文版补齐后再编译。
5. PDF 同步到面板：`/srv/agentsociety-panel/app/paper/`（silasvps）。

## 下一版方向（数据机器跑完 DATA_MACHINE_RUNBOOK 任务后）

按结果分别改写，不预写结论：

| 产出 | 论文改动 |
|---|---|
| 1.1 画像比对一致 | 第 3.4 节写“LLM 层画像经逐字节复核为校准画像”；不一致则降级该说法 |
| 规则层 `--profiles calibrated` 重跑 | 若排序不变：删局限 (10)，改写为“结论对画像来源稳健”；若变化：以校准版为准重写第 6 节 |
| Burt 按群体半衰期口径重算（家庭 3.42 年 / 非家庭 1.63 年） | 第 `sec:honest` 节改为通过或给出偏差方向 |
| 训练/留出靶标校准（任务 B） | 第 3.4 节“动力学未通过外部检验”改为留出靶标结果 |
| harness 改为提案动力学参数并在留出数据上成立 | 才可把自校准作为结果单列；此前保持局限 (11) |

主线目标：调查锚定 → 校准与留出验证 → 策略搜索 → 与成文实务规则比较 → 三模型下哪些结论成立。
