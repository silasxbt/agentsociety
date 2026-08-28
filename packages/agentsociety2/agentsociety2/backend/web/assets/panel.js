"use strict";

const state = {
  status: null,
  experiments: [],
  replay: {
    selected: null,
    timeline: [],
    profiles: [],
    schema: null,
    bundle: null,
    index: 0,
    selectedAgent: null,
    playTimer: null,
    requestVersion: 0,
  },
  refreshTimer: null,
  refreshInFlight: false,
};

const byId = (value) => document.getElementById(value);

function setText(id, value, fallback = "--") {
  const element = byId(id);
  if (element) element.textContent = value === undefined || value === null || value === "" ? fallback : String(value);
}

function setBadge(id, text, tone = "") {
  const element = byId(id);
  if (!element) return;
  element.textContent = text;
  element.className = `badge${tone ? ` ${tone}` : ""}`;
}

function formatDate(value, includeDate = true) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("zh-CN", {
    month: includeDate ? "2-digit" : undefined,
    day: includeDate ? "2-digit" : undefined,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function formatDuration(totalSeconds) {
  const seconds = Math.max(0, Number(totalSeconds) || 0);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) return `${hours} 小时 ${minutes} 分`;
  if (minutes > 0) return `${minutes} 分 ${Math.floor(seconds % 60)} 秒`;
  return `${Math.floor(seconds)} 秒`;
}

function showToast(message) {
  const toast = byId("toast");
  toast.textContent = message;
  toast.classList.remove("hidden");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.add("hidden"), 3200);
}

async function fetchJson(path) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetch(path, { headers: { Accept: "application/json" }, signal: controller.signal });
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const body = await response.json();
        detail = body.detail || body.error || detail;
      } catch (_) {
        // Keep the HTTP status when the response is not JSON.
      }
      throw new Error(detail);
    }
    return await response.json();
  } finally {
    window.clearTimeout(timeout);
  }
}

function setConnection(online, label) {
  const element = byId("connectionState");
  element.className = `connection ${online ? "online" : "offline"}`;
  element.lastChild.textContent = label;
}

function renderStatus(status) {
  state.status = status;
  setConnection(true, "后端在线");
  setText("lastUpdated", `更新于 ${formatDate(new Date().toISOString())}`);
  setText("metricBackend", status.status === "healthy" ? "正常" : status.status);
  setText("metricExperiments", status.experiments.total);
  setText("metricRunning", status.experiments.running);
  setText("metricCompleted", status.experiments.completed);
  setBadge("serviceBadge", status.status === "healthy" ? "Healthy" : status.status, status.status === "healthy" ? "success" : "warning");
  setText("serviceVersion", status.version);
  setText("servicePid", `PID ${status.pid}`);
  setText("serviceUptime", formatDuration(status.uptime_seconds));
  setText("serviceBind", `${status.host}:${status.port}`);
  setBadge("keyBadge", status.llm.key_configured ? "Key 已加载" : "缺少 Key", status.llm.key_configured ? "success" : "error");
  setText("llmModel", status.llm.model);
  setText("llmBase", status.llm.base_url);
  byId("llmBase").title = status.llm.base_url || "";
  setText("coderModel", status.llm.coder_model);
  setText("embeddingState", status.llm.embedding_configured ? "已配置" : "未配置");

  const workspace = status.workspace;
  setBadge("workspaceBadge", workspace.configured ? "已连接" : "未配置", workspace.configured ? "success" : "error");
  setText("workspaceName", workspace.name);
  setText("workspacePath", workspace.path);
  const error = byId("workspaceError");
  if (workspace.error) {
    error.textContent = workspace.error;
    error.classList.remove("hidden");
  } else {
    error.classList.add("hidden");
  }
}

const statusLabels = {
  completed: ["已完成", "success"],
  running: ["運行中", "success"],
  failed: ["失败", "error"],
  pending: ["等待中", ""],
  stale: ["进程已停止", "warning"],
  unknown: ["未知", "warning"],
};

function appendCell(row, content, className = "") {
  const cell = document.createElement("td");
  if (className) cell.className = className;
  if (content instanceof Node) cell.appendChild(content);
  else cell.textContent = content;
  row.appendChild(cell);
  return cell;
}

function renderExperiments(payload) {
  state.experiments = payload.experiments || [];
  const rows = byId("experimentRows");
  rows.replaceChildren();
  setBadge("experimentCount", `${state.experiments.length} 个实验`);
  byId("experimentEmpty").classList.toggle("hidden", state.experiments.length > 0);

  for (const experiment of state.experiments) {
    const row = document.createElement("tr");
    const status = statusLabels[experiment.status] || statusLabels.unknown;
    const statusBadge = document.createElement("span");
    statusBadge.className = `badge${status[1] ? ` ${status[1]}` : ""}`;
    statusBadge.textContent = status[0];
    appendCell(row, statusBadge);

    const title = document.createElement("div");
    title.className = "run-title";
    const strong = document.createElement("strong");
    strong.textContent = experiment.title;
    strong.title = experiment.title;
    const secondary = document.createElement("span");
    secondary.textContent = `${experiment.hypothesis_title} · ${experiment.hypothesis_id}/${experiment.experiment_id}`;
    secondary.title = secondary.textContent;
    title.append(strong, secondary);
    appendCell(row, title, "run-title");
    appendCell(row, String(experiment.step_count));
    appendCell(row, formatDate(experiment.start_time));

    if (experiment.has_replay) {
      const replayButton = document.createElement("button");
      replayButton.type = "button";
      replayButton.className = "text-button";
      replayButton.textContent = "打开";
      replayButton.addEventListener("click", () => openReplay(experiment));
      appendCell(row, replayButton);
    } else {
      appendCell(row, "--", "muted");
    }
    appendCell(row, String(experiment.artifact_count));
    rows.appendChild(row);
  }

  renderExperimentSelectors();
}

function renderExperimentSelectors() {
  const replaySelect = byId("replaySelect");
  const currentReplay = replaySelect.value;
  replaySelect.replaceChildren(new Option("选择 Replay", ""));
  for (const experiment of state.experiments.filter((item) => item.has_replay)) {
    replaySelect.add(new Option(`${experiment.hypothesis_id}/${experiment.experiment_id} · ${experiment.title}`, `${experiment.hypothesis_id}:${experiment.experiment_id}`));
  }
  if ([...replaySelect.options].some((option) => option.value === currentReplay)) replaySelect.value = currentReplay;

  const logSource = byId("logSource");
  const currentLog = logSource.value;
  logSource.replaceChildren(new Option("后端服务", "backend"));
  for (const experiment of state.experiments.filter((item) => item.has_log)) {
    logSource.add(new Option(`实验 ${experiment.hypothesis_id}/${experiment.experiment_id}`, `experiment:${experiment.hypothesis_id}:${experiment.experiment_id}`));
  }
  if ([...logSource.options].some((option) => option.value === currentLog)) logSource.value = currentLog;
}

function renderRequests(payload) {
  const entries = payload.entries || [];
  const rows = byId("requestRows");
  rows.replaceChildren();
  setBadge("requestCount", `${entries.length} 条`);
  for (const entry of entries.slice().reverse()) {
    const row = document.createElement("tr");
    appendCell(row, formatDate(entry.timestamp, false));
    appendCell(row, entry.method);
    const pathCell = appendCell(row, entry.path);
    pathCell.title = entry.path;
    const status = document.createElement("span");
    const tone = entry.status >= 500 ? "error" : entry.status >= 400 ? "warning" : "success";
    status.className = `badge ${tone}`;
    status.textContent = String(entry.status);
    appendCell(row, status);
    appendCell(row, `${entry.duration_ms.toFixed(1)} ms`);
    rows.appendChild(row);
  }
}

function renderLogs(payload) {
  const view = byId("logView");
  const shouldFollow = byId("logFollow").checked;
  view.replaceChildren();
  const entries = payload.entries || [];
  if (entries.length === 0) {
    const empty = document.createElement("div");
    empty.className = "log-line";
    const message = document.createElement("span");
    message.className = "log-message muted";
    message.textContent = "目前没有日志";
    empty.appendChild(message);
    view.appendChild(empty);
    return;
  }
  for (const entry of entries) {
    const line = document.createElement("div");
    line.className = `log-line ${entry.level || "info"}`;
    const values = [
      ["log-time", formatDate(entry.timestamp)],
      ["log-level", entry.level || "info"],
      ["log-source", entry.source || "backend"],
      ["log-message", entry.message || ""],
    ];
    for (const [className, value] of values) {
      const span = document.createElement("span");
      span.className = className;
      span.textContent = value;
      line.appendChild(span);
    }
    view.appendChild(line);
  }
  if (shouldFollow) view.scrollTop = view.scrollHeight;
}

function replayQuery(experiment) {
  return new URLSearchParams({ workspace_path: state.status.workspace.path });
}

async function openReplay(experiment) {
  byId("replaySelect").value = `${experiment.hypothesis_id}:${experiment.experiment_id}`;
  activateTab("replay");
  await loadReplay(experiment);
}

async function loadReplay(experiment) {
  stopReplay();
  state.replay.selected = experiment;
  state.replay.index = 0;
  state.replay.selectedAgent = null;
  const version = ++state.replay.requestVersion;
  byId("replayEmpty").classList.remove("hidden");
  byId("replayEmpty").querySelector("strong").textContent = "加载 Replay...";
  byId("replayEmpty").querySelector("span").textContent = `${experiment.hypothesis_id}/${experiment.experiment_id}`;
  byId("replayWorkspace").classList.add("hidden");
  const base = `/api/v1/replay/${encodeURIComponent(experiment.hypothesis_id)}/${encodeURIComponent(experiment.experiment_id)}`;
  const query = replayQuery(experiment);
  try {
    const [info, timeline, profiles, schema] = await Promise.all([
      fetchJson(`${base}/info?${query}`),
      fetchJson(`${base}/timeline?${query}`),
      fetchJson(`${base}/agents/profiles?${query}`),
      fetchJson(`${base}/panel-schema?${query}`),
    ]);
    if (version !== state.replay.requestVersion) return;
    state.replay.timeline = timeline;
    state.replay.profiles = profiles;
    state.replay.schema = schema;
    setText("replayAgents", info.agent_count);
    setBadge("replayLayout", schema.supports_map ? "地理位置" : "相对布局");
    const slider = byId("replaySlider");
    slider.max = String(Math.max(0, timeline.length - 1));
    slider.value = "0";
    byId("replayEmpty").classList.add("hidden");
    byId("replayWorkspace").classList.remove("hidden");
    if (timeline.length === 0) {
      renderReplayBundle(null);
      return;
    }
    await loadReplayStep(0);
  } catch (error) {
    if (version !== state.replay.requestVersion) return;
    byId("replayEmpty").querySelector("strong").textContent = "Replay 加载失败";
    byId("replayEmpty").querySelector("span").textContent = error.message;
    showToast(`Replay: ${error.message}`);
  }
}

async function loadReplayStep(index) {
  const replay = state.replay;
  if (!replay.selected || replay.timeline.length === 0) return;
  const nextIndex = Math.max(0, Math.min(Number(index) || 0, replay.timeline.length - 1));
  replay.index = nextIndex;
  const point = replay.timeline[nextIndex];
  const version = ++replay.requestVersion;
  const base = `/api/v1/replay/${encodeURIComponent(replay.selected.hypothesis_id)}/${encodeURIComponent(replay.selected.experiment_id)}`;
  try {
    const bundle = await fetchJson(`${base}/steps/${encodeURIComponent(point.step)}/bundle?${replayQuery(replay.selected)}`);
    if (version !== replay.requestVersion) return;
    replay.bundle = bundle;
    renderReplayBundle(bundle);
  } catch (error) {
    if (version === replay.requestVersion) showToast(`Step ${point.step}: ${error.message}`);
  }
}

function hashPosition(id, axis) {
  let hash = 2166136261;
  const text = `${id}:${axis}`;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return 8 + (Math.abs(hash) % 8400) / 100;
}

function agentPositions(bundle) {
  if (bundle && bundle.positions && bundle.positions.length > 0) {
    const valid = bundle.positions.filter((item) => Number.isFinite(item.lng) && Number.isFinite(item.lat));
    if (valid.length > 0) {
      const lngs = valid.map((item) => item.lng);
      const lats = valid.map((item) => item.lat);
      const minLng = Math.min(...lngs);
      const maxLng = Math.max(...lngs);
      const minLat = Math.min(...lats);
      const maxLat = Math.max(...lats);
      return valid.map((item) => ({
        id: item.agent_id,
        x: 7 + ((item.lng - minLng) / Math.max(maxLng - minLng, 0.000001)) * 86,
        y: 93 - ((item.lat - minLat) / Math.max(maxLat - minLat, 0.000001)) * 86,
      }));
    }
  }
  return state.replay.profiles.map((profile) => ({ id: profile.id, x: hashPosition(profile.id, "x"), y: hashPosition(profile.id, "y") }));
}

function currentAgentState(agentId) {
  const bundle = state.replay.bundle;
  if (!bundle) return null;
  const result = {};
  for (const [datasetId, group] of Object.entries(bundle.agent_state_rows || {})) {
    const row = group.rows_by_agent_id ? group.rows_by_agent_id[String(agentId)] : null;
    if (row) result[group.dataset?.title || datasetId] = row;
  }
  return Object.keys(result).length > 0 ? result : null;
}

function renderReplayBundle(bundle) {
  const stage = byId("replayStage");
  stage.replaceChildren();
  const timeline = state.replay.timeline;
  const point = timeline[state.replay.index];
  setText("replayStep", bundle ? bundle.step : point?.step);
  setText("replayTime", formatDate(bundle?.t || point?.t));
  setText("replayPosition", `${timeline.length ? state.replay.index + 1 : 0} / ${timeline.length}`);
  byId("replaySlider").value = String(state.replay.index);
  setBadge("replayLayout", bundle?.layout_hint === "map" ? "地理位置" : "相对布局");

  const positions = agentPositions(bundle);
  for (const position of positions) {
    const dot = document.createElement("button");
    dot.type = "button";
    dot.className = `agent-dot${String(position.id) === String(state.replay.selectedAgent) ? " selected" : ""}`;
    dot.style.left = `${position.x}%`;
    dot.style.top = `${position.y}%`;
    dot.textContent = String(position.id).slice(-3);
    const profile = state.replay.profiles.find((item) => String(item.id) === String(position.id));
    dot.title = profile ? `${profile.name} · ${profile.id}` : `Agent ${position.id}`;
    dot.setAttribute("aria-label", dot.title);
    dot.addEventListener("click", () => {
      state.replay.selectedAgent = position.id;
      renderReplayBundle(state.replay.bundle);
    });
    stage.appendChild(dot);
  }

  let preview = "没有可显示的状态数据";
  if (state.replay.selectedAgent !== null) {
    const profile = state.replay.profiles.find((item) => String(item.id) === String(state.replay.selectedAgent));
    preview = JSON.stringify({ profile: profile || { id: state.replay.selectedAgent }, state: currentAgentState(state.replay.selectedAgent) }, null, 2);
  } else if (bundle && Object.keys(bundle.env_state_rows || {}).length > 0) {
    preview = JSON.stringify(bundle.env_state_rows, null, 2);
  }
  byId("replayStatePreview").textContent = preview;
}

function stopReplay() {
  if (state.replay.playTimer) {
    window.clearInterval(state.replay.playTimer);
    state.replay.playTimer = null;
  }
  byId("replayPlay").textContent = "▶";
  byId("replayPlay").title = "播放 Replay";
}

function toggleReplay() {
  if (state.replay.playTimer) {
    stopReplay();
    return;
  }
  if (state.replay.timeline.length < 2) return;
  byId("replayPlay").textContent = "Ⅱ";
  byId("replayPlay").title = "暂停 Replay";
  state.replay.playTimer = window.setInterval(() => {
    const next = state.replay.index + 1;
    if (next >= state.replay.timeline.length) {
      stopReplay();
      return;
    }
    loadReplayStep(next);
  }, 900);
}

async function refreshLogs() {
  const selected = byId("logSource").value;
  if (selected === "backend") {
    renderLogs(await fetchJson("/api/v1/dashboard/logs?source=backend&limit=300"));
    return;
  }
  const [, hypothesisId, experimentId] = selected.split(":");
  const query = new URLSearchParams({ source: "experiment", hypothesis_id: hypothesisId, experiment_id: experimentId, limit: "300" });
  renderLogs(await fetchJson(`/api/v1/dashboard/logs?${query}`));
}

async function refreshAll(showConfirmation = false) {
  if (state.refreshInFlight) return;
  state.refreshInFlight = true;
  try {
    const [status, experiments, requests] = await Promise.all([
      fetchJson("/api/v1/dashboard/status"),
      fetchJson("/api/v1/dashboard/experiments"),
      fetchJson("/api/v1/dashboard/requests?limit=150"),
    ]);
    renderStatus(status);
    renderExperiments(experiments);
    renderRequests(requests);
    await refreshLogs();
    if (showConfirmation) showToast("面板已同步");
  } catch (error) {
    setConnection(false, "后端离线");
    showToast(error.name === "AbortError" ? "后端响应超时" : error.message);
  } finally {
    state.refreshInFlight = false;
  }
}

function activateTab(name) {
  document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === name));
  document.querySelectorAll(".page").forEach((page) => page.classList.toggle("active", page.id === `page-${name}`));
  if (name === "logs") window.setTimeout(() => {
    const view = byId("logView");
    if (byId("logFollow").checked) view.scrollTop = view.scrollHeight;
  }, 0);
}

function bindEvents() {
  document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => activateTab(tab.dataset.tab)));
  byId("refreshButton").addEventListener("click", () => refreshAll(true));
  byId("logSource").addEventListener("change", () => refreshLogs().catch((error) => showToast(error.message)));
  byId("replaySelect").addEventListener("change", (event) => {
    const [hypothesisId, experimentId] = event.target.value.split(":");
    const experiment = state.experiments.find((item) => item.hypothesis_id === hypothesisId && item.experiment_id === experimentId);
    if (experiment) loadReplay(experiment);
  });
  byId("replaySlider").addEventListener("input", (event) => {
    stopReplay();
    loadReplayStep(Number(event.target.value));
  });
  byId("replayPlay").addEventListener("click", toggleReplay);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopReplay();
  });
}

bindEvents();
refreshAll();
state.refreshTimer = window.setInterval(() => refreshAll(), 3500);
