#!/bin/bash
# VM 上每小时由 systemd timer 调用：把实验目录里的模型对比臂同步到面板数据目录，
# 重算 tests/cost_report.json 与 panel/mechanism.json。不接触密钥、不重启服务（面板按请求读文件）。
set -euo pipefail
SRC=/srv/agentsociety/examples/v2/elder_support/tmp/model_compare
APP=/srv/agentsociety-panel/app
PY=/srv/agentsociety-panel/venv/bin/python
mkdir -p "$APP/tmp/model_compare" "$APP/tests"
if [ -d "$SRC" ]; then
  # 只带成本/效度所需内容：trace、env 状态、标记文件；不带 agents 工作区
  rsync -a --delete \
    --include='*/' --include='trace/**' --include='env/**' --include='DONE' --include='INVALID' --include='manifest.json' --include='SOCIETY_STEP.json' \
    --exclude='*' "$SRC/" "$APP/tmp/model_compare/"
fi
"$PY" "$APP/tools/cost_report.py" >/dev/null
"$PY" "$APP/tools/collect_evidence.py" >/dev/null
chown -R www-data:www-data "$APP/tmp/model_compare" "$APP/tests" "$APP/panel/mechanism.json" 2>/dev/null || true
echo "$(date -u +%FT%TZ) panel refresh ok"
