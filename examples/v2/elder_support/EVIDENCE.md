# 证据与进展台账（自动生成，勿手改）

生成时间：2026-09-10T02:59:13.273980+00:00。来源：本文件由 tools/collect_evidence.py 聚合，每节标注原始文件；重跑脚本即更新。

## 1. 正式批次（主结果，LLM 行为层）
- 有效 11 / 无效 1 / 进行中 0（目标 12 有效）
- 结论冻结前不报告显著性、因果或稳定排序；来源 tmp/batch/comparison.json

## 2. 介入时机与剂量（规则层机制扫描，20 种子）
- 干预期内孤立率几乎不随启动时机变化：本模型中干预即时起效，延迟的代价全部来自未被保护的等待月份
- casework/timebank 延迟成本约每月 +0.15/+0.18pp（全时程孤立率）；platform 总效应弱故时机不敏感
- casework 撤出反弹 (+0.08~0.09) 不随时长 6→12 缓解，为依赖型支持；timebank 反弹 +0.02，为存量型
- 限制：规则层（无 LLM），绝对水平不可与正式批次直接比较，仅比较方向与量级；启动越晚撤出后观察窗越短，反弹比较须连同 post_window_len 报告；dur18 无撤出后窗口，反弹为 NaN
- 来源 tests/scan_timing_result.json、scan_timing_report.md

## 3. Harness 自主闭环（自动化科研演示）
- 设计师 gpt-5.6-sol；目标 min overall_isolation_rate (months 1-24, 20 seeds)；约束 duration ≤ 12（资源帽）
- 闭环 5 轮复现网格平台区（最优 0.0770 与网格 0.0774 差异在种子 SD 内），流程闭环成立且无夸大发现
- 护栏：目标/空间/迭代数预注册；LLM 仅提案，评估为确定性规则层；全部轮次落盘
- 来源 tests/harness_loop_result.json、tests/harness_loop_log.jsonl

## 4. 真实成本说明（含失败的钱）
- 累计估算 $943.7：有效 run $528.69 / 无效沉没 $405.95 / 进行中 $9.06；沉没占比 43.0%
- 口径：调用数为 trace 实测（llm.completion span，共 22 个 run 目录含归档）；token/调用与单价为文档化假设，见 tests/cost_report.json assumptions
- 叙事要点：多智能体 LLM 实验的真实成本必须计入质量门槛淘汰的 run；本项目沉没成本主要来自网关 502 风暴与行为性静默两类失效（见下节）

## 5. 静默失效诊断（无效 run 根因）
- infra_gateway：platform_s3, platform_s2 → 重跑 pass 将 AGENTSOCIETY_LLM_MAX_RETRIES 6→10（仅基础设施参数，非协议变更，写入台账）
- behavioral_inaction：casework_s2, none_s2 → 无基础设施可修；按预注册门槛重跑。若 casework_s2 复跑仍因干预窗内行为性静默超标，按预注册规则排除并在限制节报告该张力（门槛可能混同『故障静默』与『依赖性合法不行动』），另做包含该 run 的敏感性分析，不改门槛
- 详细证据链见 tests/silence_diagnosis.json（含逐 run 的错误时段、静默月分布）

## 6. 图表资产（tools/make_figures.py 自动生成，配套同名 CSV）
- figures/fig1_trajectory_isolation.png
- figures/fig1_trajectory_isolation_en.png
- figures/fig2_trajectory_loneliness.png
- figures/fig2_trajectory_loneliness_en.png
- figures/fig3_scatter_iv_isolation.png
- figures/fig3_scatter_iv_isolation_en.png
- figures/fig4_paired_rebound.png
- figures/fig4_paired_rebound_en.png
- 冻结前均标注（未冻结）；批次收口后重跑脚本即为终版

## 7. 实践叙事口径（用于论文讨论节）
- 轮候时间本身是干预设计变量：机制层估计每延迟一月，两年平均孤立率上升约 0.15–0.18pp
- casework 需配退出计划：撤出反弹不随时长缓解，提示逐步减量或向互惠型网络转介
- 弱干预（platform 类）谈时机无意义：先保证强度，再优化时机
- 以上均为模型机制结论，不宣称真实人群因果效应

## 8. 待办与边界
- 主批次重跑至 12 有效后冻结 H1–H4；三模型对比（MODEL_COMPARE.md）只进稳健性
- 时机结论的 LLM 行为层抽验视规则层效应量再决定是否花钱
