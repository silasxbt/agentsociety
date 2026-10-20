# 跨模型敏感性补充实验（2026-10-19）

状态：实施准备中；尚未启动付费调用。

2026-10-19 用户更新：新增总数仍为 8；先运行 Astra medium 的 none_s1
一场，结束后停下检查实际计费，不自动继续。此次先于 platform_s2 补跑。
用户明确不设金额上限。单场内部 API 重试最多 6 次，整场不自动重跑。

## 样本与顺序

1. 保留论文冻结时的 11 个有效主实验以及全部失败记录。单独补跑一次
   `platform_s2`，使用原始配置、`gpt-5.6-sol`、原提供商；不追加推理强度。
   若不合格，暂停后续批次并报告，不能反复抽样直至合格。
2. 在主批次补齐并验证后，新开 `astra6_medium_20261019`：
   `none/casework/timebank/platform × seed 1/2`，共 8 次。
   模型 `gpt-6-astra`，`reasoning_effort=medium`，同一提供商。
3. 每个实验复制对应主实验的 init_config.json、steps.yaml，保存 SHA256；
   不重新生成角色、网络、干预参数。20 人、6 个 focal LLM、24 个月，
   干预窗口 7–18，撤离窗口 19–24。历史 Astra pilot 不并入此批。
4. 原始数据和旧目录只读。新数据独立存储；有效性不合格也保留，禁止覆盖。
   基础设施中断与科学失败分开记录，恢复必须显式登记，不自动重试整场实验。

## 要回答的问题与数据

- H1/H2：逐 seed 比较干预期与撤离期的 isolation_rate、avg_loneliness，
  同时报告 deep_isolation_rate、avg_active_ties。
- H3：逐月保留 decisions 全量 action/detail、help_requests/help_success，
  分析求助途径、结对和志愿匹配，而非仅看最终均值。
- H4：撤离期均值减干预期均值；逐 seed 给出反弹量，以及 casework 与
  timebank 的差异。机制部分由规则编码，不宣称为模型自发发现。
- 同 seed、同条件、同配置跨模型配对；先算各模型相对 none 的差，
  再算 Astra 差值减 Sol 差值。给出所有原始点，不以月份充当独立样本。
- 单独分层 focal/rule；focal_act 仅为排除静默后的诊断，不能替代主分析。

## 完整性与请求审计

沿用主批次 gate：月份完整 0–24、指标合法、静默率 ≤10%、
LLM completion 错误率 ≤5%，保留原 gate 状态。额外用配置中的固定
focal 名单检查全部 agent-month，防止完全静默的 agent 从分母消失。
严格解析原始 JSONL，损坏行不得静默忽略。INVALID 不进入有效汇总。

每次实际请求需记录请求模型、reasoning_effort、响应模型（若上游返回）、
尝试序号、耗时、错误类型、usage（含 reasoning/cached token 若返回）。
不记录密钥或额外复制提示词。manifest 记录配置及代码哈希、提供商、
开始/结束时间、调用参数；请求级审计缺失不能宣称已验证 medium。
usage 缺失只能标缺失，不能用估算冒充实际账单。

## 执行门槛与资源

当前约 1GB VM，一次只运行一个实验，避免与在线服务争用；先检查内存、
磁盘和 Ray 配置。开跑前恢复同提供商凭证，完成真实 medium 小请求验证，
确认费用预算/停止阈值与请求审计。不能借用其他网站的密钥。

## 结论边界

每条件只有 2 个新增 seed，属于描述性敏感性检验，不检验显著性或证明等价。
主模型原推理强度未记录，因此比较是“模型与推理配置的联合敏感性”，
另有运行日期和网关后端变化的混杂。失败率、静默率和有效样本数与结果
并列报告；不补跑无效样本来改变分母。方向不一致或证据不足也应入论文。

## 工具

`tools/cross_model_cohort.py prepare --baseline-dir ... --output-dir ...`
只准备 8 份独立配置与 manifest，不发起 API 调用；已有目标拒绝覆盖。
`report --baseline-dir ... --cohort-dir ... --output ...`
只读原始数据，输出逐 seed 指标、有效性、行为记录和配对差中之差。
此工具不替代启动器、请求审计或 focal/rule 状态重放；这些执行门槛
未验收前不得启动批次。
