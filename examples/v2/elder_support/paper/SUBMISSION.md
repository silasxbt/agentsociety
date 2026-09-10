# AISS 2026 挑战赛提交材料清单

> 维护说明：本清单是提交打包的唯一依据。批次冻结（12 有效 run）后按「冻结后流程」重刷，再打包。
> 代码已推 GitHub（silasxbt/agentsociety，2026-09-08 起团队协作用；推送前必须 grep 密钥）；提交打包仍做本地压缩产物。
> 入库边界：tmp/ 运行产物、版权文献 PDF、LaTeX 中间文件不入公开仓库。

## 一、核心材料

| # | 材料 | 路径 | 状态 |
|---|------|------|------|
| 1 | 论文（中文，主稿） | `paper/main_zh.pdf` | ✅ 可编译，7 页；数字为草稿（未冻结） |
| 2 | 论文（英文） | `paper/main_en.pdf` | ✅ 可编译，8 页，已逐页目检；图表用 `_en` 英文版 |
| 3 | 论文源码 | `paper/main_zh.tex`、`paper/main_en.tex`、`paper/refs.bib`、`paper/numbers.tex` | ✅ numbers.tex 由脚本生成 |
| 4 | 图表 + 数据 CSV | `figures/fig1–fig4.{png,csv}` + `fig*_en.png` | ✅ 中英双语（脚本可重生成，CSV 只一份） |
| 5 | 证据台账 | `EVIDENCE.md` | ✅ 自动生成 |
| 6 | 实时面板 | https://agentsociety.shangdian.me | ✅ 在线 |

## 二、可复现性包（随稿附件或链接）

- `run_batch.sh`（正式批次入口，效度门槛与归档内置）
- `tools/compare_conditions.py` → `tmp/batch/comparison.json`
- `tools/make_figures.py`、`tools/gen_paper_numbers.py`、`tools/collect_evidence.py`
- `tests/scan_timing.py`（规则层时机/剂量扫描）+ `tests/scan_timing_result.json`
- `tools/harness_loop.py` + `tests/harness_loop_log.jsonl`（闭环审计日志）
- `tools/cost_report.py` + `tests/cost_report.json`
- `tests/silence_diagnosis.json`（失效 run 根因）
- `data_pipeline/out/calibration_targets.md`、`references_verified.md`
- 归档失效 run 目录（`tmp/batch/*.invalid-*`，如体积超限则只附诊断摘要）

## 三、冻结后流程（批次到 12 有效 run 时执行）

```zsh
python3 tools/compare_conditions.py     # 重算 comparison.json（数据源）
python3 tools/cost_report.py            # 成本终版（数据源）
tools/build_paper.sh                    # 一键：图表（中英）→ numbers.tex → 双语 PDF（DraftBadge 自动消失）
python3 tools/collect_evidence.py       # EVIDENCE.md + 面板 mechanism.json
```

然后人工完成：
1. 核对 `paper/main_*.pdf` 首页草稿标记已消失；
2. §5.3 行为签名脚注换成精确数值（来源 comparison.json 行为统计）；
3. 视情况在附录补 1–2 个焦点老人叙事案例（`tools/extract_cases.py`，需可追溯 run/seed/agent/month）;
4. 填作者信息（`main_zh.tex` / `main_en.tex` 的 `\author`）；
5. 打包：`paper/*.pdf` + 上表可复现性清单 → zip。

## 四、诚实性红线（提交前逐条自检）

- [ ] 不出现显著性 / p 值 / 因果措辞（n=3 种子）
- [ ] H4 保留「探索性」标注
- [ ] 46% 存活率地板、Burt 1.63 更正、Ristolainen 亚组警告均在正文
- [ ] 思考强度「未记录」披露保留
- [ ] 成本含沉没成本口径
- [ ] 时机的 LLM 层对照仍标注为未完成（除非届时已完成）
- [ ] 不提区块链；不引用已否决的编造文献
- [ ] 任何密钥 / 令牌不入包（打包前 grep 检查）

## 五、待办

- [x] 英文版编译通过并逐页目检（图表已换英文版）
- [x] 正文补焦点老人叙事个案（§5.3，casework\_s1 · 18 号，宏驱动；timebank 侧无有效 run 个案已如实说明）
- [x] 作者信息（已填：惠栋帅、王才厚、雷明仁，中英双版）
- [ ] 批次冻结 → 冻结后流程
- [ ] §5.3 行为签名脚注换精确数值（冻结后）
- [ ] 若竞赛后续公布官方模板 / 页数限制，按其重排
