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

## 二、当前状态（2026-10-22）

### 已完成

- [x] 中英文参数附录、论文新题目与三种干预名称统一（社工探访 / 互助结对 / 志愿匹配）。
- [x] 主批次画像逐字节核对：seed 1--3 均为校准画像；CLHLS/CHARLS 汇总分布入库。
- [x] 画像消融：校准 / 普通随机 / CLHLS 记录重抽，各 20 种子；逐种子保真表入库。
- [x] 动力学校准：72 个预注册候选，B1--B3 训练、B4 留出；留出误差 43.1pp → 4.6pp，V1/V2 通过。
- [x] 校准后重跑消融：调查锚定画像输出误差 4.3/4.2pp，普通随机 7.3pp。
- [x] 校准画像重跑时机、衰减、post_persist 扫描，方向与历史结果一致。
- [x] harness 按原预注册重跑并恢复证据文件：占位画像最优 casework start=4 dur=12（7.70%，4 轮提前停止）；校准画像同一最优（8.08%）。
- [x] 路由事故查明并修复：旧只读路由把“本次不能写”说成“没有联系功能”；测试 5 项通过；论文撤回模型行为解读。
- [x] 架构图、路由小节、Astra System Card 引用、事故记录、结果来源对照表。
- [x] 论文重写：社工实务主线、核心结论与创新、局限后置、评审五维度与六问附录对照表。
- [x] 中文/英文 PDF 编译（各 15 页），无未定义引用；PDF 已在 2026-10-22 部署到面板下载。
- [x] Claude 模型臂取消；跨模型计划只保留 Sol / Astra。

### 进行中

- [x] 新路由 Astra seed 1 四条件全部完成（2026-10-22，静默率 0–0.7%，LLM 错误率 0）。新路由结果只与旧路由 Astra seed 1 比较，不与旧路由 Sol 混合。

### 剩余工作

- [x] 路由修复前后对照表（`tools/astra_router_compare.py` → `tests/astra_router_compare.json`、`\Ar*` 宏），`sec:robust` 中英文改写，事故时间线入附录，PDF 重编（2026-10-23）。对照图未做，表已足够。
- [ ] 把事故时间线压缩后加入论文附录（当前完整记录在 `ROUTER_INCIDENT_20261021.md`）。
- [ ] 英文干预机制表仍有约 9pt 轻微溢出，排版收尾时修复。
- [ ] 最终数据冻结后重新运行图表/数字生成、编译中英文 PDF，并更新面板下载。
- [ ] 线上面板文案仍是旧干预名称；按用户要求暂不更新。

### 不再做 / 降级

- Claude Opus / Fable 实验已取消；不再运行。
- 不把 harness 写成“自我演进”；只写提案--评估回路及训练/留出校准。
- 不主张老人行为层“涌现”；只保留方法层发现（多模型对照暴露路由缺陷）。
- 成文实务规则策略对照、等服务人次、对齐荟萃效应量未进入当前论文主线，列为后续工作。

## 三、关键产出索引（2026-10-22）

| 产出 | 文件 |
|---|---|
| 决赛计划 | `PLAN_FINALS_20261021.md` |
| 数据机器手册 | `DATA_MACHINE_RUNBOOK.md` |
| 路由事故 | `ROUTER_INCIDENT_20261021.md` |
| 画像消融设计/结果 | `tests/scan_profile_ablation.py`、`profile_ablation_result*.json`、`profile_ablation_report.md` |
| 逐种子保真 | `tests/profile_fidelity_by_seed.csv` / `.md` |
| 动力学校准 | `tools/calibrate_dynamics.py`、`tests/calibrate_dynamics_*`、`init/dynamics_v2_tuned.json` |
| harness 重跑 | `tests/harness_loop_result*.json`、`harness_loop_log*.jsonl` |
| 校准画像扫描 | `tests/*_calibrated.json` |
| 正本与 PDF | `paper/main_zh.tex` / `main_en.tex` / `main_zh.pdf` / `main_en.pdf` |
