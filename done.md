# AgentSociety 交接记录

## 项目位置

- 仓库已移动到 `/Users/silas/Desktop/AgentSociety`，原路径 `/Users/silas/Documents/Codex/2026-08-21/ba/AgentSociety` 已不存在。
- Git 远端为 `https://github.com/tsinghua-fib-lab/AgentSociety.git`。
- 当前 HEAD 为 `13e28b5e chore(ci): 不让 npm audit 失败阻断 lint job`。
- 当前存在未提交内容：修改了 `packages/agentsociety2/agentsociety2/backend/app.py`；新增了 `packages/agentsociety2/agentsociety2/backend/dashboard.py`、`packages/agentsociety2/agentsociety2/backend/web/`；另有未跟踪文件 `challenge.md`。

## 运行环境

- Python 3.12 虚拟环境位于 `/Users/silas/Documents/Codex/2026-08-21/ba/work/agentsociety-runtime/.venv`。
- 虚拟环境中的 editable `agentsociety2` 指向桌面仓库的 `packages/agentsociety2`。
- 运行配置位于 `/Users/silas/Documents/Codex/2026-08-21/ba/work/agentsociety-lab/.env`。
- 后端工作区仍为 `/Users/silas/Documents/Codex/2026-08-21/ba/work/agentsociety-lab`。

## 模型与后端

- 后端已启动并监听 `127.0.0.1:8001`，健康检查当前返回 `{"status":"healthy"}`。
- API base 配置为 `https://tokenflux.dev/v1`，模型为 `gpt-5.6-sol`。
- API key 仅注入运行进程，没有写入项目或 `.env`，本文也未记录密钥内容。
- Embedding 未配置；当前工作区没有实验记录，面板状态显示实验总数为 0。

## 浏览器面板

- 面板地址：`http://127.0.0.1:8001/panel`
- API 文档：`http://127.0.0.1:8001/docs`
- 面板由后端在同一端口提供，是只读本地页面，没有使用仓库根目录的旧版 `frontend/`。
- 页面包含概览、实验、Replay、日志、请求五个子页面。
- 页面文字已改为简体中文；五个子页面均有默认收起的“使用说明”。
- 面板会遮盖常见 API key 和 Bearer token；内部轮询、静态资源及健康检查不会写入请求列表。

## 已完成验证

- 后端与面板相关测试：`16 passed`，另有 1 个 Starlette/httpx 弃用警告。
- Ruff 检查通过。
- `panel.js` 语法检查通过。
- `git diff --check` 通过。
- VS Code 扩展包位于 `/Users/silas/Desktop/AgentSociety/extension/ai-social-scientist.vsix`，已安装到本机 VS Code。
