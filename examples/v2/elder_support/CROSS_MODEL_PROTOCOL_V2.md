# 跨模型敏感性预注册 v2（校准后环境）

状态：**草稿，尚未启动付费调用。** 2026-10-20 本机起草。
旧协议 `CROSS_MODEL_PROTOCOL.md`（Astra medium × 4 × 2，韩国节点 none_s1）
冻结只读，不并入本批。

前置：任务 C 验收、`dynamics_v2_tuned.json` 冻结。未校准前不得开跑；
现有 Sol 11 个有效 run 作为“校准前版本”保留。

## 1. 要回答的问题

在同一套校准后的环境与同一批画像上：

1. 三种干预相对 none 的配对差（干预期孤立率、撤出后反弹）在三个模型上
   **方向是否一致**。
2. 跨模型差异是否小于同模型跨种子差异（见第 4 节收敛判据）。
3. 行为层（静默率、求助签名、高请求低成功、撤出后是否主动维系时间银行结对）
   是否随模型变化；宏观结局多为规则预设，跨模型一致本身信息量有限。
4. LLM 层介入时机（预防 / 预警 / 危机）是否改变焦点层结局方向。

一致与不一致都照实报告，不补跑无效样本来改变分母。

## 2. 设计

| 模型 | 条件 × 种子 | 新跑场数 | provider / 推理 | 说明 |
|---|---|---|---|---|
| gpt-5.6-sol | 4 × 3 | 12（校准后环境必须重跑） | openai / 不追加 effort | 旧 11 场不可直接比 |
| gpt-6-astra | 4 × 3 | 12 | openai / medium + `ALLOW_REASONING_ALIAS=1` | 韩国 none_s1 不并入 |
| Claude Opus 5.5 | 4 × 3 | 12 | anthropic / medium | 网关小请求通过后再开跑 |

共 36 场主分析。画像、干预窗（7–18）、撤出（19–24）、20 人 / 6 焦点、24 月
与主批次相同，配置从校准后的 `tmp/init/` 复制并记 SHA256。

另加 **LLM 层时机对照**（在 36 场完成且主分析有效后再开，可裁）：

- 条件：casework、timebank（platform 总效应弱，时机不敏感，规则层已见）
- 启动月：3（预防）、7（预警，与主分析重叠故复用）、12（危机）
- 时长固定 12 月；每模型 seed 1
- 新跑：2 条件 × 2 新启动月 × 3 模型 = 12 场（start=7 复用主分析）

输出目录：`tmp/v2_calibrated/<model_slug>/<cond>_s<seed>/`
时机：`tmp/v2_calibrated/<model_slug>/timing_start<N>_<cond>_s1/`
旧 `tmp/batch`、`tmp/model_compare`、`.invalid-*` 只读。

`model_slug`：`gpt-5.6-sol` / `gpt-6-astra` / `claude-opus-5-5`。

## 3. 静默与效度门槛

沿用主批次门槛，run 有效当且仅当：

- 完成 24 月，月度指标 0–24 完整、指标有限；
- 决策记录非空；6 名焦点老人合计静默率 **≤10%**（严格大于 0.10 判无效）；
- LLM completion 错误率 **≤5%**；
- 另用配置中的固定焦点名单检查全部 agent-month，完全静默的 agent 不得从分母消失；
- 请求审计存在：记录请求模型、provider、reasoning_effort（或 anthropic 的
  thinking / output_config）、响应模型、usage、错误类型。缺审计不得宣称已验证推理强度。

**预注册的补充报告（不改门槛）：**

- 每模型报告 none 臂的基线静默率（10% 门槛按 Sol 设定，对更沉默的模型偏严，
  对照臂更易判无效，必须并列写出）。
- 主结局仍用全焦点 agent-月；另做“剔除静默月”的焦点层分析，不得替代主分析。
- INVALID 归档留存，不删除、不覆盖、不反复抽样直至合格。

## 4. 收敛判据（开跑前写定）

对每个干预条件、每个结局键（isolation_rate 的 iv / post / rebound，
avg_loneliness 同口径）：

1. **方向一致**：三模型各自相对 none 的配对差符号相同。
2. **跨模型差小于跨种子差**：三模型配对差的极差，小于该条件在三模型合并后
   跨种子配对差的标准差（n=有效 seed；不足 2 个有效 seed 则判“无法评估”）。
3. **规定 vs 涌现**：对照论文表 `tab:prescribed` 逐条标注该条在各模型下
   是否仍成立。标为“规定”的条目跨模型一致不作为模型稳健性证据。

两条都满足 → 该条结论记为“跨模型收敛”。
仅方向一致 → “方向稳健、量级未收敛”。
方向不一致或无法评估 → 照实写入限制，不以多数模型为准。

不做显著性检验，不宣称模型等价。比较的是“模型 + 推理配置 + 运行日期”
的联合敏感性。

## 5. 执行

准备（不调用 API）：

```bash
$PY $EXP/tools/cross_model_cohort.py prepare \
  --baseline-dir $EXP/tmp/v2_calibrated/source_profiles \
  --output-dir $EXP/tmp/v2_calibrated/gpt-6-astra \
  --model gpt-6-astra --reasoning-effort medium --provider openai \
  --cohort astra_medium_v2 --seeds 1,2,3

$PY $EXP/tools/cross_model_cohort.py prepare \
  --baseline-dir $EXP/tmp/v2_calibrated/source_profiles \
  --output-dir $EXP/tmp/v2_calibrated/claude-opus-5-5 \
  --model claude-opus-5-5 --reasoning-effort medium --provider anthropic \
  --cohort opus_medium_v2 --seeds 1,2,3
```

单场（禁止队列续跑、禁止整场自动重试）：

```bash
$PY $EXP/tools/run_astra_single.py \
  --run-dir $EXP/tmp/v2_calibrated/gpt-6-astra/none_s1 \
  --model gpt-6-astra --reasoning-effort medium --provider openai

$PY $EXP/tools/run_astra_single.py \
  --run-dir $EXP/tmp/v2_calibrated/claude-opus-5-5/none_s1 \
  --model claude-opus-5-5 --reasoning-effort medium --provider anthropic
```

Opus 开跑前必须：同一网关发一条真实 medium 小请求，审计记录 thinking /
output_config，并与提供商账单核对金额（token 数不得冒充扣费）。

报告：

```bash
$PY $EXP/tools/cross_model_cohort.py report \
  --baseline-dir $EXP/tmp/v2_calibrated/gpt-5.6-sol \
  --cohort-dir $EXP/tmp/v2_calibrated/gpt-6-astra \
  --extra-cohort opus_medium=$EXP/tmp/v2_calibrated/claude-opus-5-5 \
  --seeds 1,2,3 \
  --output $EXP/tmp/v2_calibrated/cross_model_report.json
```

## 6. 资源与裁剪

Astra 一场在 1GB VM 上约 22 小时。36 场串行需一个月以上。
建议 4–8 核、约 16GB，同时跑 3–4 场；先用 none_s1 试并发，确认网关不致静默。
费用按每场约 \$100–130 粗估，36 场约 \$3.6k–4.7k，**以账单为准**。

若赶不及决赛：先保证每模型 seed 1 的四条件（12 场），时机对照与其余 seed
列为后续工作，不以未完成的实验写结论。

## 7. 结论边界

- 不把校准前 Sol 11 场与校准后三模型混在一张主表。
- 不把规则层时机扫描的延迟成本写成 LLM 层发现。
- usage 缺失只能标缺失，不能用估算冒充账单。
- 本文件改动须在开跑前完成；开跑后只允许勘误（日期、路径），不得改判据。
