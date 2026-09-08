#!/bin/zsh
# 同步本机实验数据+面板代码到 GCP 面板 (agentsociety.shangdian.me)
# 用法: sync_panel_gcp.sh [--loop]   # --loop: 每 5 分钟同步一次，批次结束后再同步一轮退出
# 凭据走 gcloud 本地登录，不写入项目。数据用原子换名，面板无空窗。
set -e
EXP=/Users/silas/Desktop/AgentSociety/examples/v2/elder_support
APP=/srv/agentsociety-panel/app
SSH=(gcloud compute ssh silasvps --zone us-west1-b --tunnel-through-iap --command)

sync_once() {
  # 数据: tmp/batch 全量 tar 管道 -> 远端 batch.new -> 原子换名
  tar -czf - -C $EXP tmp/batch | "${SSH[@]}" \
    "sudo rm -rf $APP/tmp/batch.new && sudo mkdir -p $APP/tmp/batch.new && \
     sudo tar -xzf - -C $APP/tmp/batch.new --strip-components=2 && \
     sudo rm -rf $APP/tmp/batch.old && \
     sudo mv $APP/tmp/batch $APP/tmp/batch.old 2>/dev/null; \
     sudo mv $APP/tmp/batch.new $APP/tmp/batch && sudo rm -rf $APP/tmp/batch.old"
  # 代码: 成套传 (server/index/presets/llm_probe/settings/qa/mechanism)，变更才重启服务
  local sum_now=$(cat $EXP/panel/server.py $EXP/panel/index.html $EXP/panel/presets.py \
    $EXP/panel/llm_probe.py $EXP/panel/settings.json $EXP/panel/qa.json \
    $EXP/panel/mechanism.json 2>/dev/null | md5)
  if [ "$sum_now" != "$(cat /tmp/elder-panel-gcp-code.md5 2>/dev/null)" ]; then
    tar -czf - -C $EXP panel/server.py panel/index.html panel/presets.py \
      panel/llm_probe.py panel/settings.json panel/qa.json panel/mechanism.json | "${SSH[@]}" \
      "sudo tar -xzf - -C $APP && sudo systemctl restart agentsociety-panel.service"
    echo "$sum_now" > /tmp/elder-panel-gcp-code.md5
    echo "[$(date +%H:%M:%S)] 代码已更新并重启远端面板"
  fi
  echo "[$(date +%H:%M:%S)] 同步完成"
}

if [ "$1" = "--loop" ]; then
  while :; do
    sync_once || echo "[$(date +%H:%M:%S)] 本轮同步失败，下轮重试"
    pgrep -f "run_batch.sh" >/dev/null || { sleep 30; sync_once || true; echo "批次已结束，最后一轮同步完成，退出"; break; }
    sleep 300
  done
else
  sync_once
fi
