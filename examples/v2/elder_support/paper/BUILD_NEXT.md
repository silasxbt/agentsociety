# 论文编译与最终版清单（更新于 2026-10-22）

## 当前正本

- `paper/main_zh.tex` / `main_en.tex`；PDF 各 15 页，2026-10-22 用 Tectonic 编译。
- 无未定义引用；中文无 overfull，英文干预机制表约 9pt 轻微 overfull。
- 当前 PDF 已部署到 `https://agentsociety.shangdian.me/downloads/main_zh.pdf` 与 `main_en.pdf`。
- 面板文案暂不更新（用户决定）。

## 已纳入当前稿

- 社工实务主线；三种干预统一为社工探访 / 互助结对 / 志愿匹配。
- 分层架构图、环境路由与路由事故。
- 画像消融、动力学校准（训练/留出）、校准后复跑、逐种子保真。
- harness 排期回路重跑（占位与校准画像），证据文件已入库。
- 中英文完整参数表、结果来源对照、核心结论与创新、局限后置、评审关切附录。

## 最终版依赖

1. ✅ 2026-10-23 完成（见 `tools/astra_router_compare.py`）。原：等新路由 Astra seed 1 四条件完成；只做旧/新路由下 Astra 同模型对照，不与旧路由 Sol 混合。
2. ✅ 更新第 `sec:robust` 节、对应表格/图和 `numbers.tex`。
3. ✅（附录 `app:router`）把 `ROUTER_INCIDENT_20261021.md` 时间线压缩进附录。
4. ✅ 英文稿 tectonic 编译无 Overfull（2026-10-23）。
5. ✅ 2026-10-23 全量复核：在韩国机完整 `tmp/batch` 上重生成 `cost_report`、`model_compare_report`、`layer_decomposition`、`behavior_signature`，本机重生成 `tie_survival_result` 与全部图表。图表逐字节不变；`numbers.tex` 除成本 5 个宏外全部逐位一致。
   2026-10-23 起论文不再报告金额，只报 trace 实测调用次数（`tests/llm_calls_ledger.json`，含新路由 Astra 5,307 次）；冻结的 45,901 次按冻结值保留，现存 trace 只能复算 43,945 次，差额是已删除的无效归档。原命令：
```bash
cd examples/v2/elder_support
tools/build_paper.sh all
```

6. ✅（tectonic，无错误/未定义引用；`numbers.tex` 只新增 `\Ar*` 宏块）验收：无硬错误、无未定义引用；`numbers.tex` 变化逐条可解释；抽查摘要、架构图、核心结论、评审表、参数表。
7. 备份并更新面板 PDF；面板文案仍不动，除非用户另行授权。

## 冻结口径

- 主批次是旧路由、校准画像、校准前默认动力学；事后校准不回写主批次数字。
- 老人行为层不主张涌现；方法层发现是多模型对照暴露路由缺陷。
- harness 是受护栏的提案--评估回路，不写成自我演进。
- 论文结论均为模型情景推演，不宣称真实人群因果效应。
