# Elder Support 实验（独居老人社会支持网络）

AISS 2026 参赛研究：独居老人支持网络的衰减、韧性与介入时机。
混合分层仿真：规则层老人（零 LLM）+ LLM 焦点老人（PersonAgent，决策带理由）。

## 组件

| 路径 | 用途 |
|---|---|
| `../../custom/envs/elder_support_env.py` | 环境：关系账本、月度事件、规则层、三种干预 |
| `init/gen_profiles.py` | 画像生成：默认 CLHLS/CHARLS 校准分布，`--placeholder` 为文献占位 |
| `init/config_params.py` | 生成配置；`--intervention casework\|timebank\|platform --iv-start --iv-end` |
| `data_pipeline/extract_clhls2021.py` | CLHLS 2021 → 独居老人画像分布 |
| `data_pipeline/extract_harmonized.py` | Harmonized CHARLS → 纵向转移锚点（衰减/丧偶冲击）|
| `data_pipeline/out/calibration_targets.md` | 校准靶标总表（模拟必须对齐的真实数字）|
| `tools/analyze.py` | 单运行分析：曲线 + 决策定性摘要 + 打靶 + 异常检测 + 反思沉淀 |
| `tools/compare_conditions.py` | 跨条件对比（干预期/撤出后指标，均值±极差）|
| `run_prototype.sh` | 单次原型运行（基线）|
| `run_batch.sh` | 正式实验：4 条件 × 多种子，断点自动续跑 |
| `tests/smoke_rules_only.py` | 机制冒烟：可复现/基线恶化/衰减/restore |
| `tests/smoke_interventions.py` | 干预冒烟：三种干预方向 + 时间银行撤出可持续性 |

## 三种干预（对应 H3/H4）

1. **casework** 专业社工个案管理：风险评估 → 高危探访 + 家庭联结（自上而下，精准但受个案量约束）
2. **timebank** 时间银行互助：低龄健康老人结对高危老人，服务换积分；结对是真实人际关系，
   撤出后以 `post_persist`（默认 0.5，做敏感性扫描）概率延续——可持续性机制
3. **platform** 数字平台志愿匹配：响应式、覆盖广、志愿者轮换、关系浅

## 运行环境变量

```
AGENTSOCIETY_LLM_API_KEY / _API_BASE / _MODEL     # tokenflux + gpt-5.6-sol
AGENTSOCIETY_LLM_REQUEST_TIMEOUT=180              # 推理模型长思考
AGENTSOCIETY_LLM_MAX_RETRIES=6                    # 供应商瞬断容错
WORKSPACE_PATH=<repo根>                            # custom/ 扫描授权
```

长时运行用 `nohup caffeinate -is ... --resume` 防休眠防误杀；中断后原命令加 `--resume` 续跑。

## 已知工程问题与对策

- tokenflux 偶发分钟级断连 → 指数退避补丁（llm_dispatcher.py）+ 重试次数环境变量
- macOS 休眠唤醒后 psutil 偶发 syscall 失败（Ray 启动即崩）→ 重试即可；caffeinate 预防
- embedding 不可用 → CodeGen 语义缓存自动降级，仅损失缓存命中率
- 焦点老人整月零决策 = LLM 调用丢失 → analyze.py 异常检测自动标记

## 实测成本（mini2，20人/6焦点/4步）

约 9 次 LLM 调用 / agent·月；230 次调用 ≈ 2 小时墙钟（并行）。
