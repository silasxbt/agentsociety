# 韩国实验运行节点迁移

用户授权：将学术实验项目迁移到韩国机器，继续只跑一场 Astra medium，
完成后停下看计费。其他线上服务保持原样；美国原文件保留。

- 项目、主机名、区域和公网地址不在仓库记录；两台机器均为约 1GB RAM，韩国节点已有 swap。
- 迁移 `/srv/agentsociety`（含原 Python 3.11.2 环境、定制模块、实验记录）
  和 `/srv/agentsociety-panel/app`（作为完整历史数据副本，不启动网页服务）。
- 包传输后校验 SHA256；不改 DNS、反向代理和现有 sing-box 服务。
- 凭证独立加密传输，目标目录 700，文件 600，不进入迁移档案或文档。
- 运行目录保持原路径，配置与步骤哈希不变。美国的两次启动失败留档；
  它们无模型调用，不能算科学实验失败样本或已消耗的模型 token。
- 单场启动器：`tools/run_astra_single.py`。Ray 1 worker，80MB 对象缓存，
  数值库线程数 1；不改变 agent 数量或科学参数。
- 仅 none_s1；没有队列续跑、整场自动重试或自动启动其余七场。
- 实际 token 记录在 request_audit.jsonl，执行与汇总在 execution.json。
  实际金额必须与提供商账单核对，不能用 token 数冒充扣费。

## 验证记录

- 2026-10-19：309MB 完整归档已传到韩国并解压；美国、本地中转、韩国
  三份 SHA256 一致：
  `82b645df9a5bced794ca40ccae2df5985f80e059868d46859f3b492d1c76fb61`。
- 韩国 Python 3.11.2 可运行。最小 Ray actor 在 07:47 UTC 返回
  `ray_actor_ok`，进程正常退出；此检查不调用模型。
- 第一场使用 `elder-astra6-single-kr-20261019.service` 启动，
  `Restart=no`、`UMask=0077`，进程与 SSH 会话独立。
- 完整初始化触发 Ray 物理内存保护，在 API 调用和模拟产物生成之前停止，
  启动日志保留。恢复使用 `elder-astra6-single-kr-20261019-recovery1.service`，
  单进程环境设置 `RAY_memory_monitor_refresh_ms=0`，允许使用现有 swap；
  没有修改全局 Ray 安装或科学参数，操作系统内存管理仍有效。
- 韩国仅安装了断点传输工具 rsync，没有升级实验依赖或云主机规格。
- 网站面板仍由美国提供；韩国历史面板目录仅作数据副本。

## 扩容 swap 后的单场尝试

- 用户授权增加 swap 后再次尝试完整一场。swap 从 1GB 增至 2GB，
  新文件 `/swapfile-extra`，fstab 已持久化，未升级云主机。
- 2026-10-19 08:34 UTC 的启动越过环境创建，发现旧 LiteLLM 在本地
  拒绝未知模型别名的 reasoning_effort；无请求审计或模拟指标，停止并留档。
- 韩国 `backend/panel_settings.py` 原文件备份为 `.before-astra-alias`。
  新增显式环境开关 `AGENTSOCIETY_LLM_ALLOW_REASONING_ALIAS=1`，
  只在指定推理深度时传 `allowed_openai_params=[reasoning_effort]`。
  不删除 medium、不更换模型；代理仍检查实际请求包含这两个字段。
- 当前单场服务：`elder-astra6-single-kr-swap2g-alias-20261019.service`，
  Restart=no，MemoryMax=1800M，MemorySwapMax=1500M，UMask=0077。
  金额不设上限；资源限制不是金额限制。

状态：文件迁移完成；2026-10-19 08:53 UTC 已核验前两条实际请求
HTTP 200、返回模型 gpt-6-astra、请求 medium，用量合计 16187 token。
这是运行中快照，不是整场用量或实际扣费。完整模拟仍在进行，尚未证明
科学有效性。聊天跟进自动化 astra 每 15 分钟检查，仅有可操作变化时通知；
完成或失败后停用，绝不继续其余七场或自动重跑。
