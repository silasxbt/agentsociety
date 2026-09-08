#!/bin/zsh
# 三模型敏感性对比：单模型 × (none, casework) × seed 1，见 MODEL_COMPARE.md
# 用法： AGENTSOCIETY_LLM_API_KEY=... ./run_model_compare.sh <model-id> [months]
# sol 臂复用 tmp/batch/{none,casework}_s1，本脚本只跑新模型，绝不写 tmp/batch/。
set -e
REPO=/Users/silas/Desktop/AgentSociety
PY=/Users/silas/Documents/Codex/2026-08-21/ba/work/agentsociety-runtime/.venv/bin/python
EXP=$REPO/examples/v2/elder_support
MODEL=${1:?用法: run_model_compare.sh <model-id> [months]}
MONTHS=${2:-24}
SLUG=$(echo "$MODEL" | tr -c 'a-zA-Z0-9._-' '-' | sed 's/-*$//')
CONDITIONS=(none casework)
SEED=1
MAX_TRIES=${MAX_TRIES:-3}

[ -z "$AGENTSOCIETY_LLM_API_KEY" ] && { echo "请设置 AGENTSOCIETY_LLM_API_KEY"; exit 1; }
export AGENTSOCIETY_LLM_API_BASE=${AGENTSOCIETY_LLM_API_BASE:-https://tokenflux.dev/v1}
export AGENTSOCIETY_LLM_MODEL=$MODEL
export AGENTSOCIETY_LLM_REQUEST_TIMEOUT=${AGENTSOCIETY_LLM_REQUEST_TIMEOUT:-180}
export AGENTSOCIETY_LLM_MAX_RETRIES=${AGENTSOCIETY_LLM_MAX_RETRIES:-6}
export WORKSPACE_PATH=$REPO
cd $REPO

# 主批次仍在跑时拒绝启动，避免争用污染正式数据
if pgrep -f "run_batch.sh" >/dev/null 2>&1; then
  echo "✗ 主批次 run_batch.sh 仍在运行，收口后再启动模型对比"; exit 1
fi

# 网关探测：模型不存在就不花钱
if ! curl -fsS -H "Authorization: Bearer $AGENTSOCIETY_LLM_API_KEY" \
    "$AGENTSOCIETY_LLM_API_BASE/models" | grep -q "\"$MODEL\""; then
  echo "✗ 网关 $AGENTSOCIETY_LLM_API_BASE 上找不到模型 $MODEL，中止"; exit 1
fi

for cond in $CONDITIONS; do
  SRC=$EXP/tmp/batch/${cond}_s${SEED}
  [ -f "$SRC/init_config.json" ] || { echo "✗ 缺少主批次配置 $SRC"; exit 1; }
  RUN_DIR=$EXP/tmp/model_compare/$SLUG/${cond}_s${SEED}
  [ -f "$RUN_DIR/DONE" ] && { echo "== 跳过已完成: $SLUG/${cond}_s${SEED}"; continue; }
  mkdir -p $RUN_DIR
  # 复用主批次同一份配置，保证三模型输入完全一致
  cp $SRC/init_config.json $RUN_DIR/init_config.json
  cp $SRC/steps.yaml $RUN_DIR/steps.yaml
  $PY - "$RUN_DIR" "$MODEL" "$cond" <<'PYEOF'
import hashlib,json,os,sys,time
run,model,cond=sys.argv[1:4]
h=lambda p:hashlib.sha256(open(p,'rb').read()).hexdigest()
json.dump({"model":model,"api_base":os.environ["AGENTSOCIETY_LLM_API_BASE"],
 "condition":cond,"seed":1,"months":int(os.environ.get("MONTHS",24)),
 "reasoning_effort":os.environ.get("AGENTSOCIETY_LLM_REASONING_EFFORT"),
 "temperature":None,"timeout":os.environ["AGENTSOCIETY_LLM_REQUEST_TIMEOUT"],
 "max_retries":os.environ["AGENTSOCIETY_LLM_MAX_RETRIES"],
 "init_config_sha256":h(f"{run}/init_config.json"),"steps_sha256":h(f"{run}/steps.yaml"),
 "started_at":time.strftime("%Y-%m-%dT%H:%M:%S")},open(f"{run}/manifest.json","w"),
 ensure_ascii=False,indent=2)
PYEOF
  tag="mc_${SLUG}_${cond}_s${SEED}"
  echo "== 运行: $tag (months=$MONTHS)"
  try=1
  while [ $try -le $MAX_TRIES ]; do
    RESUME_FLAG=""
    [ -f "$RUN_DIR/SOCIETY.json" ] && RESUME_FLAG="--resume"
    if caffeinate -is $PY -m agentsociety2.society.cli \
        --config $RUN_DIR/init_config.json --steps $RUN_DIR/steps.yaml \
        --run-dir $RUN_DIR --experiment-id elder_support_$tag \
        $RESUME_FLAG --log-file $RUN_DIR/output.log; then
      $PY $EXP/tools/analyze.py --run-dir $RUN_DIR
      # 额外门槛：trace 模型必须与 manifest 一致，混模即无效
      if $PY - "$RUN_DIR" "$MODEL" <<'PYEOF'
import json,sys
from pathlib import Path
run,model=Path(sys.argv[1]),sys.argv[2]
bad=set()
for p in run.glob('trace/trace_*.jsonl'):
    for line in p.read_text(errors='ignore').splitlines():
        try:r=json.loads(line)
        except Exception:continue
        m=r.get('attributes',{}).get('llm.model')
        if m and m!=model: bad.add(m)
sys.exit(1 if bad else 0)
PYEOF
      then :; else
        echo "   ✗ $tag trace 出现非 $MODEL 调用，判无效"; touch "$RUN_DIR/INVALID"; break
      fi
      if grep -q '决策记录为空\|整体静默率\|LLM completion 错误率' "$RUN_DIR/analysis/reflections.md"; then
        echo "   ✗ $tag 未通过科学有效性门槛"; touch "$RUN_DIR/INVALID"; break
      fi
      touch $RUN_DIR/DONE; break
    fi
    grep -q "host_statistics64" $RUN_DIR/output.log 2>/dev/null \
      && echo "   ↻ Ray 启动崩溃，第 $try/$MAX_TRIES 次重试" \
      || echo "   ✗ $tag 失败，第 $try/$MAX_TRIES 次重试；见 $RUN_DIR/output.log"
    try=$((try+1)); sleep 5
  done
done
echo "模型 $MODEL 对比批完成。目录: tmp/model_compare/$SLUG/"
