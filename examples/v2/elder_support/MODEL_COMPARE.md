# 三模型敏感性对比计划（探索性，不进主结果）

## 目的
检验主结论是否依赖具体 LLM：gpt-5.6-sol（主批次）vs gpt-6-astra vs claude-fable-5-1。
这是模型敏感性分析，不是主实验；结果只用于"结论稳健性"一节，不参与 H1–H4 冻结。

## 最小设计（把新增成本压到最低）
- 范围：2 条件（none + casework）× seed 1 × 仅 2 个新模型 = **4 个新 run**。
- sol 臂零成本：直接复用主批次已验证有效的 `tmp/batch/none_s1`、`casework_s1`。
- 选 casework：当前 H4 反弹信号最强的条件；保留 none 才能算同种子配对差。
- 其余一切与主批次一致：20 老人、6 焦点、24 个月、干预 7–18、decay 0.06、
  timeout 180s、retries 6，复用主批次 run 目录里的同一份 init_config.json / steps.yaml。

## 输出隔离
tmp/model_compare/<model-slug>/<condition>_s1/
绝不写入 tmp/batch/；主批次数据不动。每个 run 启动前写 manifest.json
（模型、API base、生成参数、配置哈希、时间戳；不含任何密钥）。

## 已知不可对齐项（如实报告，不静默适配）
- gpt-6-astra 不支持 reasoning_effort=none（最低 low）；claude-fable-5-1 自适应思考
  始终开启；sol 主批次未显式设置 effort。三者思考深度无法完全对齐，
  manifest 记录实际值，论文中作为设计差异说明。
- astra 不支持 temperature/top_p；本项目本来就未设置，无影响。
- tokenflux 网关上这两个模型 ID 是否可用尚未核实：启动前先 GET /v1/models 探测，
  探测不到就停，不花钱。

## 成本与时间预估（按官方 $10/$50 每 MTok，网关价可能不同）
每 run ≈ 2000–2200 次 completion ≈ $100–130；4 run ≈ $400–520。
串行约 1–2 天（fable 默认高思考可能更慢）。若需再砍半：只跑 casework
（2 run，≈$200–260），但失去配对差，只能看轨迹形状。

## 有效性与分析
- 同一套门槛：DONE、月份 0–24、决策非空、静默 ≤10%、LLM 错误率 ≤5%。
- 额外门槛：trace 里每条 llm.model 必须等于 manifest 的模型，混模即判无效。
- 分析：每模型的 casework−none 配对差（iso_iv/iso_post/iso_rebound）与 sol 臂并排，
  单 seed，只做描述性比较，不做显著性/排名声称。

## 2026-09-10 执行现状
- **astra 臂**：tokenflux 网关探测 ✓（`gpt-6-astra` 在列且主账号可调用）。主批次
  platform_s2 收口后立即启动（同网关避免争用）。
- **fable 臂**：走 yinlihupo 网关（`https://model.api.yinlihupo.cn/v1`，Anthropic
  原生格式，`AGENTSOCIETY_LLM_PROVIDER=anthropic`），思考强度
  `AGENTSOCIETY_LLM_REASONING_EFFORT=medium`。**当前网关全部 Claude 模型实调用
  503 no_available_providers（模型列表正常）**，等网关商恢复；脚本已加实调用
  预检，上游不可用不开跑不花钱。
- 分析脚本 `tools/model_compare_report.py` 已就绪（sol 臂试跑 ✓：Δiso_iv=-0.171、
  Δiso_reb=+0.188，同向判据成立）。
- 启动命令（密钥运行时注入，不落盘）：
  ```zsh
  # astra（tokenflux）
  AGENTSOCIETY_LLM_API_KEY=... ./run_model_compare.sh gpt-6-astra
  # fable（yinlihupo，Anthropic 格式 + 中等思考）
  AGENTSOCIETY_LLM_API_KEY=... AGENTSOCIETY_LLM_API_BASE=https://model.api.yinlihupo.cn/v1 \
    AGENTSOCIETY_LLM_PROVIDER=anthropic AGENTSOCIETY_LLM_REASONING_EFFORT=medium \
    ./run_model_compare.sh claude-fable-5-1
  ```

## 启动时机
主批次（run_batch.sh, PID 54756）完全收口之后再启动，避免同机 Ray/CPU 争用
和网关限流影响正式数据。启动命令：
  AGENTSOCIETY_LLM_API_KEY=... ./run_model_compare.sh gpt-6-astra
  AGENTSOCIETY_LLM_API_KEY=... ./run_model_compare.sh claude-fable-5-1
