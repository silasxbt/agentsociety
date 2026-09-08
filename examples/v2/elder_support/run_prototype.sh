#!/bin/zsh
# ElderSupport 原型一键运行：画像 → 配置 → 仿真 → 分析
# 用法（在仓库根目录）：
#   AGENTSOCIETY_LLM_API_KEY=sk-xxx ./examples/v2/elder_support/run_prototype.sh
set -e

REPO=/Users/silas/Desktop/AgentSociety
PY=/Users/silas/Documents/Codex/2026-08-21/ba/work/agentsociety-runtime/.venv/bin/python
EXP=$REPO/examples/v2/elder_support

if [ -z "$AGENTSOCIETY_LLM_API_KEY" ]; then
  echo "请先设置 AGENTSOCIETY_LLM_API_KEY（不会写盘）"; exit 1
fi
export AGENTSOCIETY_LLM_API_BASE=${AGENTSOCIETY_LLM_API_BASE:-https://tokenflux.dev/v1}
export AGENTSOCIETY_LLM_MODEL=${AGENTSOCIETY_LLM_MODEL:-gpt-5.6-sol}
# gpt-5.6-sol 为推理模型，长推理可超 60s 默认超时
export AGENTSOCIETY_LLM_REQUEST_TIMEOUT=${AGENTSOCIETY_LLM_REQUEST_TIMEOUT:-180}
export WORKSPACE_PATH=$REPO

cd $REPO
$PY $EXP/init/gen_profiles.py --num 20 --focal 6 --seed 42
$PY $EXP/init/config_params.py --months 12

RUN_DIR=$EXP/tmp/run_$(date +%m%d_%H%M)
$PY -m agentsociety2.society.cli \
  --config $EXP/tmp/init/init_config.json \
  --steps $EXP/tmp/init/steps.yaml \
  --run-dir $RUN_DIR \
  --experiment-id elder_support_prototype \
  --log-file $RUN_DIR/output.log

$PY $EXP/tools/analyze.py --run-dir $RUN_DIR
echo "运行产物：$RUN_DIR"
