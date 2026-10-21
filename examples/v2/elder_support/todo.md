# 决赛准备进度与待办（2026-10-19）

决赛：12 月初（具体日期与材料截止待定）。决赛提出的六个问题、分类与依据见
`FINAL_REVIEW_20261019.md`；需要原始微观数据的工作按 `DATA_MACHINE_RUNBOOK.md`
在数据机器上做。本文只记录进度。

## 一、今天完成的工作

提交 `c2dbcd92`…`7bdfd38e` 在分支 `elder-support/finals-prep-20261019`，经
[PR #19](https://github.com/silasxbt/agentsociety/pull/19) 合入 `main`（`main` 受保护，不能直推）。时间顺序如下。

1. **六个问题的审查与计划**（`c2dbcd92`）
   - 六个问题逐条分类（2/2/5/3/2/2），写明依据与下一步，赛道建议投
     “智能体与计算社会科学”。
   - 数据机器工作手册：画像核验、动态靶标提取、参数外置与自动校准、跨模型重跑、
     论文重构的步骤与时间线。
2. **修正论文中代码不支持的说法**（`c2dbcd92`，中英文 tex 同步）
   - 删除丧偶事件与 +27pp 靶标：代码没有丧偶事件，老人都独居、未建模配偶。
   - 删除“三年新发孤独梯度与 Wei 等一致”：没有脚本算过这个数，独居/非独居对比
     在只含独居老人的模型里也算不出来。
   - 干预参数从“依据 Masi 荟萃与 RCT”改为“方向参照文献、数值为建模选择”。
   - 年龄未做再加权、画像偏老（80 岁以上占 69.4%），如实写明。
   - 规则层接触频率是假设而非调查校准；输出侧唯一的外部检验（Burt）未通过。
3. **问题 2：三种干预的选择逻辑**（`c328e852`）
   - 第 3.3 节新增“选择逻辑”：按护航模型比较补哪一层关系、靠哪种关系逻辑维持，
     分别对应 Cantor 1979、Gouldner 1960、Granovetter 1973（三篇经 Crossref 核实，
     已加入 `refs.bib` 与 `references_verified.md`）。
   - casework 改名为“风险导向的社工外展探访”（简称社工探访），说明没有实现
     个案管理的需求评估、服务计划、跟进与结案。
   - 新增表 `tab:mechanism`（需求、代码中的服务行动、关系机制、撤出后条件、
     实现程度），以及“参数性质说明”“投入量不对等”两段和局限 (9)。
   - 面板 `panel/index.html` 条件名与提示文案同步。
4. **画像来源问题**（`6f9b753d`）
   - 发现所有规则层扫描（时机、剂量、harness、衰减率、post_persist、关系存活曲线）
     都用占位画像 `gen_elder`，论文第 3.4 节与局限 (10) 已披露。
   - `gen_profiles.py` 找不到 `clhls2021_dist.json` 时原本会静默改用占位分布，
     现在改为报错退出；`.gitignore` 放行 `data_pipeline/out/*.json`，汇总分布可入库。
5. **环境参数外置**（`6ece260f`、`7bdfd38e`）
   - 先建回归基准：4 条件 × 5 种子 × 24 月，逐月指标与期末状态取哈希。
   - `elder_support_env.py` 中全部机制常数移入 `DEFAULT_DYNAMICS`，干预内部常数移入
     `INTERVENTION_DEFAULTS`，取值不变；未知键报错；`dynamics` 写入状态文件，
     旧状态文件按默认值恢复。
   - `config_params.py` 新增 `--dynamics` 与 `--iv-params`；不传时输出与改动前逐字节一致。
   - 验证：回归 20/20 一致；新增单测 5 项通过。
   - `.gitignore` 放行 `tests/*.json`。

## 二、剩余工作

### 本机可做（不需要原始数据）

- [ ] **论文附录参数表**：中文版已由另一位编辑者在 `main_zh.tex` 附录加了
      “参数表与依据”（`app:params` / `tab:params`），**截至推送时未提交**，
      工作区里还有两处正文引用改为指向 `app:params`。确认后与英文版一并完成、提交。
- [x] 规则层扫描脚本加 `--profiles placeholder|calibrated`（默认占位，输出文件名区分），
      数据机器上用校准画像重跑。
- [x] `tools/run_astra_single.py` 改为模型名、推理强度、provider 可配置；Claude 臂于 2026-10-21 取消，跨模型只做 sol 与 astra。
- [x] 起草 `CROSS_MODEL_PROTOCOL_V2.md`：收敛判据、静默处理、2 模型 × 4 条件 × 3 种子，
      以及 LLM 层时机对照。
- [ ] `EVIDENCE.md` 引用的 `tests/harness_loop_result.json`、`harness_loop_log.jsonl`、
      `cost_report.json`、`silence_diagnosis.json` 从未入库、本机也没有，
      须在数据机器上找回并提交。
- [ ] 线上介绍页问答（“时机实验尚未完成”“harness 不会自动改配置”）在 GCP 部署副本
      `/srv/agentsociety-panel/app`，不在本仓库，需在那边改。
- [ ] 问题 3：从焦点老人决策日志提取 1–2 条完整模拟案例（需要 `tmp/batch`，在数据机器上做）。

### 数据机器上做（详见 `DATA_MACHINE_RUNBOOK.md`）

- [ ] 核实正式批次是否用了校准画像：重新生成画像，与 `tmp/init/profiles_s*.json`
      逐字节比对（手册 1.1）。
- [ ] 提交 `clhls2021_dist.json`、`harmonized_charls.json` 等汇总分布。
- [ ] 提取动态靶标，分训练集与留出集（手册任务 B）。
- [ ] 规则层：校准 vs 占位画像消融、等服务人次对照、按 6.2 表数据校准、
      干预强度对齐荟萃效应量（手册任务 C）。
- [ ] 新环境上三个模型统一重跑 LLM 层（手册任务 D）。
- [ ] 成文实务规则（民政探访关爱分级、机构开案标准）编码为策略，与仿真推荐策略、
      “只按年龄排序”基线比较（问题 4 目的 A）。
- [ ] 用 `tools/build_paper.sh` 重建 PDF（本机无 TeX，也没有 `tmp/`，`numbers.tex` 无法再生成）。
- [ ] 论文重构：主线改为“调查锚定 → 自动校准与留出验证 → 策略搜索 → 与成文实务规则比较”。

### 待确认

- 决赛具体日期与材料截止。
- CLHLS/CHARLS 原始微观数据的位置：本机全盘未找到；待查 GCP VM、移动硬盘或网盘，
  必要时重新申请。

## 三、今天新增或改动的文件

| 文件 | 作用 |
|---|---|
| `FINAL_REVIEW_20261019.md`（新） | 六个问题的分类、依据、下一步与总体顺序，完成一项勾选一项 |
| `DATA_MACHINE_RUNBOOK.md`（新） | 在有原始数据的机器上的操作手册：硬规则、盘点核验、任务 A–E、时间线 |
| `todo.md`（新，本文） | 当天进度、剩余工作、文件索引 |
| `tests/regress_dynamics.py`（新） | 环境动力学回归：默认参数下结果须与基准逐位一致；`--write` 重写基准 |
| `tests/regress_dynamics_golden.json`（新） | 回归基准哈希（20 个 run），由参数外置前的代码生成 |
| `tests/test_env_dynamics.py`（新） | 参数外置单测：覆盖生效、未知键报错、旧状态恢复、参数随状态保存 |
| `custom/envs/elder_support_env.py`（改） | `DEFAULT_DYNAMICS`、`INTERVENTION_DEFAULTS` 与 `dynamics` 构造参数 |
| `init/config_params.py`（改） | 新增 `--dynamics`、`--iv-params` |
| `init/gen_profiles.py`（改） | 缺校准分布时报错，不再静默降级 |
| `paper/main_zh.tex`、`paper/main_en.tex`（改） | 第 3.2–3.4、5.1 节、相关工作、预注册说明、局限 (4)(6)(9)(10)，表 `tab:mechanism` |
| `paper/refs.bib`（改） | 新增 Cantor 1979、Gouldner 1960、Granovetter 1973 |
| `data_pipeline/out/references_verified.md`（改） | 三篇新文献的核实记录；Antonucci support bank 未采用的原因 |
| `panel/index.html`（改） | 条件名改为“社工探访”，提示文案补投入量与 `post_persist` 说明 |
| 根目录 `.gitignore`（改） | 放行 `data_pipeline/out/*.json` 与 `tests/*.json` |

路径均相对 `examples/v2/elder_support/`，`custom/envs/` 与 `.gitignore` 相对仓库根目录。

本次推送不包含的未提交改动（非本次工作）：`main_zh.tex` 中另一位编辑者的参数表；
`CROSS_MODEL_PROTOCOL.md`、`MIGRATION_KR_20261019.md`、`tools/run_astra_single.py`、
`tools/cross_model_cohort.py`、`tools/check_ray_host.py` 及两个对应测试；
仓库其他目录（rumor_spreader、benchmark、community）的改动。
