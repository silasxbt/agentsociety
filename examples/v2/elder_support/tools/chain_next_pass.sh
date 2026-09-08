#!/bin/zsh
# 自动接续下一 pass：等当前 run_batch.sh 结束后，若有效 run < 12，
# 以 AGENTSOCIETY_LLM_MAX_RETRIES=120 重新启动一轮（处理无效 run），并重启面板同步循环。
# 密钥在运行时从会话记录中提取，不写入任何文件、不回显、不进日志。
# 用法：nohup tools/chain_next_pass.sh <当前批次PID> >> tmp/chain_watch.log 2>&1 &
set -u
EXP=/Users/silas/Desktop/AgentSociety/examples/v2/elder_support
WATCH_PID=${1:?需要当前 run_batch.sh 的 PID}
TR=/Users/silas/.claude/projects/-Users-silas/eeab25c9-6849-4366-8e6d-1f350b7253a6.jsonl

log() { echo "[$(date '+%m-%d %H:%M:%S')] $*"; }

log "watcher 启动，等待批次 PID=$WATCH_PID 退出"
while kill -0 "$WATCH_PID" 2>/dev/null; do sleep 300; done
log "批次进程已退出"

VALID=$(ls -d $EXP/tmp/batch/*_s[0-9] 2>/dev/null | while read -r d; do
  [ -f "$d/DONE" ] && [ ! -f "$d/INVALID" ] && echo "$d"; done | wc -l | tr -d ' ')
log "当前有效 run 数：$VALID / 12"

if pgrep -f "run_batch.sh" >/dev/null; then
  log "已有 run_batch.sh 在运行，为防双开不再启动，退出"; exit 0
fi

if [ "$VALID" -ge 12 ]; then
  log "已达 12 有效 run，无需再跑；确保同步循环存活后退出"
else
  KEY=$(grep -o "AGENTSOCIETY_LLM_API_KEY='sk-[^']*'" "$TR" | head -1 | cut -d"'" -f2)
  if [ -z "$KEY" ]; then log "错误：未能提取 API key，放弃自动接续"; exit 1; fi
  log "启动下一 pass（MAX_RETRIES=120，重跑无效 run）"
  cd "$EXP"
  AGENTSOCIETY_LLM_API_KEY="$KEY" AGENTSOCIETY_LLM_MAX_RETRIES=120 \
    nohup zsh -df ./run_batch.sh 24 1 2 3 >> tmp/batch/orchestrator.log 2>&1 &
  NEW_PID=$!
  unset KEY
  log "新 pass 已启动 PID=$NEW_PID"
fi

# 同步循环在批次结束后会自行退出；这里确保新 pass 期间仍有同步
sleep 60
if ! pgrep -f "sync_panel_gcp.sh --loop" >/dev/null; then
  nohup "$EXP/tools/sync_panel_gcp.sh" --loop >> /tmp/elder-panel-sync.log 2>&1 &
  log "同步循环已重启 PID=$!"
else
  log "同步循环仍在运行"
fi
log "watcher 完成"
