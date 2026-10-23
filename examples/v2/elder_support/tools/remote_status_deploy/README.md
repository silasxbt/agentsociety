# 远程状态通道部署（2026-10-23 上线）

韩国机（权威，只读实验目录）：
- `/opt/elder-support-remote-status/{tools/export_remote_status.py,panel/remote_status.py}`
- `elder-support-status-export.{service,timer}`：每 2 分钟，User=silas，`ProtectSystem=strict`，只写 `/var/lib/elder-support-remote-status/status.json`
- 系统用户 `statusread`：`authorized_keys` 为 `restrict,from="<美国机内网 IP>",command="cat .../status.json"`，只能读这一个文件

美国机（面板）：
- `/usr/local/bin/elder-support-pull-status`（即本目录同名脚本）：VPC 内网 ssh 拉取 → schema 校验 → 时间单调 → 原子替换 `app/remote_status/status.json`
- 密钥与 known_hosts：`/etc/elder-support-remote-status/`（root 700）
- `elder-support-status-pull.{service,timer}`：每 2 分钟
- `agentsociety-panel.service.d/remote-status.conf`：`PANEL_REMOTE_STATUS_FILE=/srv/agentsociety-panel/app/remote_status/status.json`

更新 `remote_status.py` 的 schema 时先部署美国机（拉取端与面板），再部署韩国机导出端，否则新快照会被拉取端拒收、页面转为陈旧。
回滚：停用两个 timer，恢复 `backups/20261023-astra-final/` 下的 `server.py`、`index.html`。
