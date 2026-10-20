# 数据机器上的工作手册（决赛前，2026-10-19 起）

适用：存有 CLHLS / CHARLS 原始微观数据和正式批次 `tmp/` 的那台机器。
配套：问题与判断见 `FINAL_REVIEW_20261019.md`（下文“问题 N”均指该文件）。
决赛 12 月初；本手册按“先核对、再改文字、再零成本校准、最后花钱跑 LLM”排序。

## 0. 硬规则

1. **原始微观数据不进 git、不上公开仓库、不上 GCP 面板。** 只提交汇总分布与
   脚本。由个体记录直接重抽出的画像（任务 4.2）同样视为受限数据，不公开。
2. **冻结结果只读。** `tmp/batch/`、`tmp/model_compare/` 及所有 `.invalid-*`
   目录不改、不删、不覆盖。新产出一律写新目录（见各任务）。
3. **先写设计再跑。** 每个新实验在启动前把目标、参数、种子、验收条件写进
   脚本头部或协议文档并提交；跑完不改门槛、不挑种子。
4. **环境改动向后兼容。** 新参数默认值必须等于现值，保证旧配置重跑结果不变。
5. 完成一项，在 `FINAL_REVIEW_20261019.md` 对应复选框打勾，并写明产出路径。

## 1. 第一步：盘点与核对（约半天）

在仓库根目录执行（`PY` 为该机器的运行时 Python，参见 `run_batch.sh` 中的 `PY=`）：

```bash
EXP=examples/v2/elder_support
ls -la data/raw/clhls2021/ data/raw/harmonized/        # 原始数据
ls -la $EXP/data_pipeline/out/*.json                     # 汇总分布
ls $EXP/tmp/batch $EXP/tmp/init                          # 正式批次与画像
find data/raw -iname "*child*"                           # CHARLS 2015 Child.dta
```

### 1.1 必须核对：正式批次用的是不是校准画像

根目录 `.gitignore` 第 171 行的 `*.json` 让 `clhls2021_dist.json` 从未进 git；
该文件缺失时 `init/gen_profiles.py` **静默退回占位分布**（输出 `mode=placeholder`）。
画像生成是确定性的，可用重生成对比来判定：

```bash
for s in 1 2 3; do
  $PY $EXP/init/gen_profiles.py --num 20 --focal 6 --seed $s --out /tmp/p_s$s.json
  cmp /tmp/p_s$s.json $EXP/tmp/init/profiles_s$s.json && echo "seed $s 一致"
done
```

- 重生成时输出 `mode=calibrated(...)` 且三个 seed 都一致 → 正式批次用的是校准画像，记录结论即可。
- 不一致，或该机器上也只能得到 `placeholder` → **立即停下记录**。这会推翻论文
  “画像逐维锚定调查”的说法，须先在 `FINAL_REVIEW` 问题 6.1 增补，再决定处理。

### 1.2 修复这个隐患（提交）

- 已完成（2026-10-19）：`.gitignore` 放行 `data_pipeline/out/*.json`；`gen_profiles.py`
  缺分布文件且未传 `--placeholder` 时报错退出。
- 待做：在数据机器上提交 `clhls2021_dist.json`、`harmonized_charls.json`
  （均为汇总分布，脚本头部已注明可入 git）。
- 待做：`EVIDENCE.md` 引用的 `tests/harness_loop_result.json`、`tests/harness_loop_log.jsonl`、
  `tests/cost_report.json`、`tests/silence_diagnosis.json` 从未入库（被 `*.json` 规则排除），
  本机不存在。在数据机器上确认后提交（`.gitignore` 已放行 `tests/*.json`；`.jsonl` 若仍被
  忽略，用 `git check-ignore -v` 查明后处理）。
- 待做：`EVIDENCE.md` 与论文引用的以下证据文件从未入库，代码机器上不存在，
  须在数据机器上确认并提交（`.gitignore` 已放行 `tests/*.json`）：
  `tests/harness_loop_result.json`、`tests/harness_loop_log.jsonl`、
  `tests/cost_report.json`、`tests/silence_diagnosis.json`。
  提交前确认其中不含密钥或原始微观数据。

### 1.3 记录数据版本

在 `data_pipeline/out/DATA_MANIFEST.md` 写下每份原始文件的文件名、大小、SHA256、
来源与下载日期；只写元信息，不复制数据。

## 2. 任务 A：论文文字修正（不依赖数据，可在任意机器做）

对应问题 2、6.1，以及介绍页的过时描述。中英文同步，改完运行 `tools/build_paper.sh`。

- [ ] 删除丧偶冲击的实现与校准说法：`paper/main_zh.tex` 第 75、85、215 行及英文对应处。
      护航模型理论介绍中提到丧偶可保留。
- [ ] 删除“模拟三年新发孤独梯度与 Wei 等一致”，Wei 等只作问题规模的背景引用。
- [ ] 干预参数改为“方向参照文献，数值为建模选择”（任务 4.4 完成后可再改回“对齐荟萃效应量”）。
- [ ] casework 改名（中文 29 处“个案管理”），补三种干预的选择逻辑（问题 2 的护航网络分层表）。
- [ ] `panel/index.html` 第 412 行“时机实验未开始”改为与已完成的规则层扫描一致。
- [ ] 新增参数附录表：参数、取值、来源类型（数据 / 文献 / 建模选择）、是否扫描。
      第一版按 `FINAL_REVIEW` 问题 6.2、6.3 填写，任务 3 完成后更新。

## 3. 任务 B：从原始数据补校准量（约 3–5 天）

新建 `data_pipeline/extract_dynamics.py`，输出 `data_pipeline/out/calibration_v2.json`
与同名 `.md`。样本口径与现有脚本一致：CLHLS 2021 `a51==2 & age>=65`；
Harmonized CHARLS 60+、`hhres==1`；截面用个体权重（`r4wtrespb`），纵向注明未加权。

下表中已在现有脚本使用过的变量名可直接用；其余**必须先查官方 codebook 确认**，
不要按记忆填写变量名或编码。

| 校准量 | 对应环境参数（现值） | 数据来源与变量 |
|---|---|---|
| 子女每月联系次数，按距离与是否常探望分组 | `gen_profiles.py` 中 5/3/1.8、1.5/0.8/0.4 | CHARLS 2015 Child.dta 逐子女联系 / 探望频率（查 codebook）；Harmonized `h4kcnt`、`h4kcntf`（已用）作周联系率交叉核对 |
| 邻里朋友关系数量与往来频率 | 0–4 个，权重 10/25/35/20/10；强度 N(0.5, 0.18) | CHARLS 社交活动、与朋友往来条目（查 codebook） |
| 月度患病、跌倒发生率，按年龄段 | 患病 0.10、跌倒 0.03，乘年龄系数 | CHARLS 跌倒、住院、就诊条目（查 codebook）；两年回顾期换算为月率，写明换算公式 |
| 不求助倾向 | 0.25 + 0.5×内向 | CLHLS `a58` 独居原因（已用，“不想麻烦子女” 61.4%） |
| 子女可达性：按距离的实际照料或帮助比例 | 可达性 1 / 0.7 / 0.15 | CHARLS 照料来源、子女提供帮助条目（查 codebook） |
| 子女关系初始强度 | 一律 0.8 | 按 CLHLS `f103x5` 是否常探望、`f103x6` 是否有联系（已用）分档 |
| 孤独感稳态系数 | 0.90、0.12、0.05、0.25、0.10 | 回归：孤独感（CLHLS `b38` 或 CHARLS `flonel`）对子女联系频率、关系数、自评健康的系数；连续化方式与 `_LONELY_MAP` 一致并写明 |
| 年龄分布是否加权 | `age_band` 直接用 CLHLS | 确认 CLHLS 2021 是否提供权重；若无，按 Harmonized 2018 加权年龄分布再加权（`calibration_targets.md` 已提出） |

**靶标划分（写入脚本头部后再拟合，不得事后调换）：**

- 训练靶标：末期截面孤独“经常及以上”约 15%、“有时及以上”约 40%；三年孤独发生率 27.2%。
- 留出靶标：三年孤独持续率 53.3%；2018 加权截面周联系率；`a58` 不求助比例。
- 回归速度（`_end_of_month` 中的 0.5）用训练靶标拟合，留出靶标只看不调。

验收：`calibration_v2.json` 每个量都带样本量、是否加权、变量名与编码说明；
`.md` 中写明与现值的差异。

## 4. 任务 C：规则层改造与零成本实验（约 1 周）

### 4.1 参数外置

**环境部分已完成（2026-10-19/20，本机）**：
- `elder_support_env.py` 的常数已移入 `DEFAULT_DYNAMICS` / `INTERVENTION_DEFAULTS`，
  `config_params.py` 支持 `--dynamics`、`--iv-params`（JSON 文件或字符串）。
  默认值的结果由 `tests/regress_dynamics.py` 锁定（20/20 一致）。
- 规则层扫描已支持 `--profiles placeholder|calibrated`（也可设环境变量
  `ELDER_PROFILES`），覆盖 `scan_timing.py`、`scan_decay_outcomes.py`、
  `scan_post_persist.py`、`measure_tie_survival.py`、`scan_tie_survival_floor.py`、
  `tools/harness_loop.py`。默认 `placeholder`，结果与已入库文件逐位一致；
  `calibrated` 结果写入加 `_calibrated` 后缀的新文件，harness 读取同来源的网格。

数据机器上要做的：

```bash
for s in tests/scan_timing.py tests/scan_decay_outcomes.py tests/scan_post_persist.py \
         tests/scan_tie_survival_floor.py; do
  $PY $EXP/$s --profiles calibrated
done
# harness 需要 LLM 网关，且须在 scan_timing --profiles calibrated 之后运行
$PY $EXP/tools/harness_loop.py --profiles calibrated
```

尚未做：`init/gen_profiles.py` 内的画像常数（子女联系频率、邻里关系数与强度等）仍写在
代码里，校准时一并外置。

验收：
- `tests/regress_dynamics.py` 仍为 20/20 一致；旧扫描用默认参数重跑与已入库结果一致。
- 新增 `init/dynamics_v2.json`，取值来自 `calibration_v2.json`，经 `--dynamics` 传入。

### 4.2 画像消融（问题 1）

`gen_profiles.py` 增加 `--mode calibrated|placeholder|resample`。`resample` 从 CLHLS
独居子样本按权重抽取真实受访者记录，保留联合分布。抽出的画像不公开（硬规则 1）。

实验：`tests/scan_profile_ablation.py`，三种画像模式 × 20 种子，统一用 `dynamics_v2`，
比较输出侧对第 3 节训练靶标与留出靶标的命中误差。
输出 `tests/profile_ablation_result.json`，并附画像保真表（逐 seed 各维度相对靶标的偏差）。

### 4.3 自动校准（问题 4 目的 B）

把 `tools/harness_loop.py` 的提案对象从“干预配置”扩展为“动力学参数”：
- 目标：最小化训练靶标误差；每轮同时报告留出靶标误差，但不进入目标函数。
- 空间：第 3 节中无法直接由数据确定的参数（深谈概率、回归速度等），范围预注册。
- 验收：留出误差不随训练误差下降而上升；全轮次落盘。最终选定参数存为
  `init/dynamics_v2_tuned.json`。

### 4.4 干预强度与等投入对照（问题 2、6.1）

- 投入量对照：三种干预按每月服务人次对齐（以 casework 的 16 人次为准，或取三者最小值），
  输出 `tests/equal_dose_result.json`。
- 效应量对齐：在规则层计算各干预在干预窗末孤独感的标准化均差（对 none，20 种子），
  调整干预参数使其落在荟萃分析给出的区间内。荟萃 d 值以
  `data_pipeline/literature/` 中原文为准，在脚本头部注明页码与表号。

### 4.5 时机与成文实务规则对照（问题 4 目的 A）

- 环境加入干预启动滞后与覆盖爬坡（参数外置，默认 0 保持兼容）。
- 把民政部门特殊困难老年人探访关爱的风险分级与探访频次、社工机构开案标准，
  编码为策略 `practice_rule`；另设简单基线 `age_only`（只按年龄排序）。
- 在 `dynamics_v2_tuned` 下比较 harness 推荐策略、`practice_rule`、`age_only`：
  “先介入谁、何时介入”的一致率与全时程孤立率、孤独感差异。
- 输出 `tests/practice_rule_compare.json`。成文规则的原文出处与条款号写入脚本头部。

## 5. 任务 D：新环境上的 LLM 实验（花钱，约 2–3 周墙钟）

前置条件：任务 C 全部验收，`dynamics_v2_tuned.json` 冻结并提交。

1. **预注册**（问题 5）：`CROSS_MODEL_PROTOCOL_V2.md` 已在本机起草（2026-10-20）。
   设计、收敛判据、静默处理、输出目录见该文件。开跑前只改勘误，不得改判据。
2. **工程**（本机已完成，数据机器上验收）：
   - `run_astra_single.py` 支持 `--model/--reasoning-effort/--provider/--run-dir`；
     anthropic 审计 `/messages` 的 thinking / output_config。
   - `AGENTSOCIETY_LLM_ALLOW_REASONING_ALIAS=1` 已写入
     `packages/agentsociety2/.../panel_settings.py`，仅 openai 线生效。
   - `cross_model_cohort.py prepare/report` 支持任意模型、种子与 `--extra-cohort`。
   数据机器上：Opus 先发一条真实 medium 小请求，确认审计与计费后再开跑。
3. **资源**：e2-micro（1GB）串行太慢，换 4–8 核、约 16GB 机器同时跑 3–4 场；
   先小规模试并发，确认网关不致静默。费用估算每场约 \$100–130，以账单为准。
4. **分析**：`cross_model_cohort.py report --extra-cohort opus_medium=... --seeds 1,2,3`；
   结论按 `tab:prescribed` 逐条标注各模型下是否一致。

## 6. 任务 E：论文重构（与任务 D 并行开始，D 出数后定稿）

主线改为：调查锚定的模型 → harness 自动校准、留出靶标验证 → harness 搜索介入策略
→ 与成文实务规则比较 → 三模型下哪些结论成立。

- 架构介绍压缩到约一页；第一阶段 Sol 结果作为“校准前版本”保留在附录或稳健性节。
- 正文加入 1–2 个焦点老人模拟案例，附 run、seed、agent、month 与日志位置（问题 3）。
- 全部数字由 `tools/gen_paper_numbers.py` 生成；`tools/collect_evidence.py` 重跑更新
  `EVIDENCE.md`；网站 PDF 与终稿一致。

## 7. 建议时间线

| 时间 | 内容 |
|---|---|
| 10 月第 4 周 | 第 1 节盘点与核对；任务 A 文字修正；任务 B 开始 |
| 10 月底–11 月第 1 周 | 任务 B 完成；任务 C |
| 11 月第 2–4 周 | 任务 D（LLM 实验）；任务 E 并行 |
| 11 月底 | 冻结数据、定稿论文、离线演示材料 |
| 12 月初 | 决赛 |

若任务 D 赶不及：先保证每模型 seed 1 的四条件，其余 seed 作为后续工作如实写出，
不以未完成的实验写结论。
