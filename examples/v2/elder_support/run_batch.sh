#!/bin/zsh
# 正式实验批量编排：条件 × 种子 串行跑（并发压测通过前不并行跑多个实验）
# 用法：
#   AGENTSOCIETY_LLM_API_KEY=sk-xxx ./examples/v2/elder_support/run_batch.sh [months] [seeds...]
# 例：跑 24 个月、种子 1 2 3：
#   AGENTSOCIETY_LLM_API_KEY=... ./run_batch.sh 24 1 2 3
# 已完成的 (condition, seed) 会被跳过；中断后重跑本脚本即自动 --resume。
#
# 可选环境变量：
#   DECAY=0.15   关系月衰减率（默认 0.06）。非默认值会写进 run 目录名，
#                便于 0.06/0.15/0.25 三点敏感性扫描互不覆盖。
#                注意：LLM 批量跑 decay 扫描成本 ×3，通常应改用免费的规则层扫描
#                （tests/scan_decay_outcomes.py），仅在需要 LLM 行为层证据时才用本变量。
#   MAX_TRIES=3  单个 run 的启动重试次数。Ray 在 macOS 上会间歇性地在启动阶段因
#                psutil.virtual_memory() 的 host_statistics64 syscall 失败而崩溃
#                （baseline12 实测 3 次启动挂 2 次）。这是启动期失败，重试即可。
set -e

REPO=/Users/silas/Desktop/AgentSociety
PY=/Users/silas/Documents/Codex/2026-08-21/ba/work/agentsociety-runtime/.venv/bin/python
EXP=$REPO/examples/v2/elder_support
MONTHS=${1:-24}
shift 2>/dev/null || true
SEEDS=(${@:-1 2 3})
CONDITIONS=(none casework timebank platform)
IV_START=7
IV_END=18
DECAY=${DECAY:-0.06}
MAX_TRIES=${MAX_TRIES:-3}
# 非默认衰减率单独存放，避免覆盖主批次
DECAY_SUFFIX=""
[ "$DECAY" != "0.06" ] && DECAY_SUFFIX="_d${DECAY}"

if [ -z "$AGENTSOCIETY_LLM_API_KEY" ]; then
  echo "请设置 AGENTSOCIETY_LLM_API_KEY"; exit 1
fi
export AGENTSOCIETY_LLM_API_BASE=${AGENTSOCIETY_LLM_API_BASE:-https://tokenflux.dev/v1}
export AGENTSOCIETY_LLM_MODEL=${AGENTSOCIETY_LLM_MODEL:-gpt-5.6-sol}
export AGENTSOCIETY_LLM_REQUEST_TIMEOUT=${AGENTSOCIETY_LLM_REQUEST_TIMEOUT:-180}
# 重试 120 次、退避封顶 60s：纯连接错误可原地扛约 1.9 小时的供应商断连，
# 模拟时钟随之冻结，避免调用耗尽后记静默、整 run 作废重跑（比重跑省时省 token）。
# 观测到的失败均为瞬态型（连接错误/超时/502），无 4xx，故大预算无死循环风险。
export AGENTSOCIETY_LLM_MAX_RETRIES=${AGENTSOCIETY_LLM_MAX_RETRIES:-120}
export WORKSPACE_PATH=$REPO
cd $REPO

for seed in $SEEDS; do
  # 同种子共享同一套画像：干预对照的是"同一批老人"
  $PY $EXP/init/gen_profiles.py --num 20 --focal 6 --seed $seed \
    --out $EXP/tmp/init/profiles_s$seed.json
  for cond in $CONDITIONS; do
    tag="${cond}_s${seed}${DECAY_SUFFIX}"
    RUN_DIR=$EXP/tmp/batch/$tag
    if [ -f "$RUN_DIR/INVALID" ]; then
      stamp=$(date +%Y%m%d-%H%M%S)
      archive="${RUN_DIR}.invalid-${stamp}"
      echo "== 归档先前无效 run: $tag -> $(basename "$archive")；随后干净重跑"
      mv "$RUN_DIR" "$archive"
    fi
    if [ -f "$RUN_DIR/DONE" ]; then
      $PY $EXP/tools/analyze.py --run-dir $RUN_DIR >/dev/null || true
      if grep -q '决策记录为空\|整体静默率\|LLM completion 错误率' "$RUN_DIR/analysis/reflections.md" 2>/dev/null; then
        stamp=$(date +%Y%m%d-%H%M%S)
        archive="${RUN_DIR}.invalid-${stamp}"
        echo "== 归档无效 run: $tag -> $(basename "$archive")；随后按相同条件和 seed 干净重跑"
        mv "$RUN_DIR" "$archive"
      else
        echo "== 跳过已验证完成: $tag"
        continue
      fi
    fi
    echo "== 运行: $tag (months=$MONTHS iv=$IV_START-$IV_END)"
    mkdir -p $RUN_DIR
    $PY $EXP/init/config_params.py --months $MONTHS --seed $seed \
      --profiles $EXP/tmp/init/profiles_s$seed.json \
      --decay-rate $DECAY \
      --intervention $cond --iv-start $IV_START --iv-end $IV_END
    cp $EXP/tmp/init/init_config.json $RUN_DIR/init_config.json
    cp $EXP/tmp/init/steps.yaml $RUN_DIR/steps.yaml
    # Ray 启动期崩溃（host_statistics64）重试；每次重试都带 --resume，
    # 已完成的月份不会重跑
    try=1
    while [ $try -le $MAX_TRIES ]; do
      RESUME_FLAG=""
      [ -f "$RUN_DIR/SOCIETY.json" ] && RESUME_FLAG="--resume"
      if caffeinate -is $PY -m agentsociety2.society.cli \
          --config $RUN_DIR/init_config.json \
          --steps $RUN_DIR/steps.yaml \
          --run-dir $RUN_DIR \
          --experiment-id elder_support_$tag \
          $RESUME_FLAG \
          --log-file $RUN_DIR/output.log; then
        $PY $EXP/tools/analyze.py --run-dir $RUN_DIR
        if grep -q '决策记录为空\|整体静默率\|LLM completion 错误率' "$RUN_DIR/analysis/reflections.md"; then
          echo "   ✗ $tag completed but failed scientific validity gate"
          rm -f "$RUN_DIR/DONE"
          touch "$RUN_DIR/INVALID"
          break
        fi
        touch $RUN_DIR/DONE
        break
      fi
      if grep -q "host_statistics64" $RUN_DIR/output.log 2>/dev/null; then
        echo "   ↻ Ray 启动崩溃（macOS host_statistics64），第 $try/$MAX_TRIES 次重试"
      else
        echo "   ✗ $tag 失败（非 Ray 启动问题），第 $try/$MAX_TRIES 次重试；见 $RUN_DIR/output.log"
      fi
      try=$((try + 1))
      sleep 5
    done
    if [ ! -f "$RUN_DIR/DONE" ]; then
      if [ -f "$RUN_DIR/INVALID" ]; then
        echo "   ✗✗ $tag 已完成但未通过科学有效性门槛，留待下一次启动时归档并干净重跑"
      else
        echo "   ✗✗ $tag 连续 $MAX_TRIES 次执行失败，跳过（不中断整批）"
      fi
      continue
    fi
  done
done
echo "批量完成。汇总分析："
$PY $EXP/tools/compare_conditions.py --batch-dir $EXP/tmp/batch || true
