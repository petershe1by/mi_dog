(() => {
  "use strict";
  const token = document.querySelector('meta[name="mi-dog-token"]').content;
  const target = document.querySelector('meta[name="mi-dog-target"]').content;
  const maintenanceControlsEnabled =
    document.querySelector('meta[name="mi-dog-maintenance-controls"]').content === "true";
  const log = document.getElementById("log");
  let busy = false;
  let refreshInFlight = false;
  let batteryAllowsMotion = false;
  let postureControlsReady = false;
  let lieDownReady = false;
  let videoActive = false;
  let videoMetricsTimer = null;

  const fields = {
    service_active: document.getElementById("service"),
    state: document.getElementById("state"),
    stage: document.getElementById("stage"),
    run_allowed: document.getElementById("runAllowed"),
    enable_motion: document.getElementById("motionEnabled"),
    battery_percent: document.getElementById("batteryPercent"),
    min_battery_soc: document.getElementById("minBatteryPercent"),
    wired_charging: document.getElementById("wiredCharging"),
    battery_temp_c: document.getElementById("batteryTemp"),
    safety_reason: document.getElementById("reason"),
  };

  function stamp(message) {
    const now = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    log.textContent = `[${now}] ${message}\n${log.textContent === "等待操作…" ? "" : log.textContent}`;
  }

  function setBusy(value) {
    busy = value;
    document.querySelectorAll("button").forEach((button) => {
      if (button.dataset.action === "stop") return;
      if (button.dataset.jog === "stop") {
        button.disabled = !maintenanceControlsEnabled;
        return;
      }
      const requestsMotion = button.dataset.action === "start" ||
        button.id === "continueStage" ||
        (button.dataset.jog && button.dataset.jog !== "stop");
      const requestsPosture = Boolean(button.dataset.posture);
      const maintenanceBlocked = (requestsPosture || Boolean(button.dataset.jog)) &&
        !maintenanceControlsEnabled;
      const postureBlocked = requestsPosture && (
        !postureControlsReady || (button.dataset.posture === "lie-down" && !lieDownReady));
      button.disabled = value || maintenanceBlocked ||
        (requestsMotion && !batteryAllowsMotion) || postureBlocked;
    });
  }

  function render(values, ok) {
    Object.entries(fields).forEach(([key, element]) => {
      let value = values[key] ?? "—";
      if (value !== "—" && (key === "battery_percent" || key === "min_battery_soc")) {
        value = `${value}%`;
      }
      if (value !== "—" && key === "battery_temp_c") value = `${value} °C`;
      if (key === "wired_charging") {
        value = value === "true" ? "是" : value === "false" ? "否" : "—";
      }
      element.textContent = value;
    });
    const connected = ok && values.service_active === "active";
    const badge = document.getElementById("connectionBadge");
    badge.textContent = connected ? "已连接" : "连接异常";
    badge.className = `badge ${connected ? "online" : "offline"}`;
    const batteryPercent = Number(values.battery_percent);
    const minBatteryPercent = Number(values.min_battery_soc);
    batteryAllowsMotion = Number.isFinite(batteryPercent) &&
      Number.isFinite(minBatteryPercent) && batteryPercent >= minBatteryPercent &&
      values.wired_charging === "false" && values.power_normal === "true";
    const jogReady = maintenanceControlsEnabled && batteryAllowsMotion &&
      values.enable_motion === "True" &&
      values.run_allowed === "true";
    postureControlsReady = maintenanceControlsEnabled && batteryAllowsMotion &&
      ["DOWN_WAITING", "PAUSED"].includes(values.state) && values.run_allowed === "false";
    lieDownReady = postureControlsReady && values.safe_to_lie_down === "true" &&
      values.safety_reason === "ready";
    const jogLock = document.getElementById("jogLock");
    jogLock.textContent = jogReady ? "调试移动已放行" : "调试移动锁定";
    jogLock.className = `lock ${jogReady ? "unlocked" : ""}`;
    const maintenanceMode = document.getElementById("maintenanceMode");
    maintenanceMode.textContent = maintenanceControlsEnabled ? "维护控制已启用" : "正式比赛模式";
    maintenanceMode.className = `lock ${maintenanceControlsEnabled ? "unlocked" : ""}`;
    document.getElementById("maintenanceHint").hidden = maintenanceControlsEnabled;
    const workflowHint = document.getElementById("workflowHint");
    if (workflowHint) {
      workflowHint.textContent = values.state === "EMERGENCY_STOP" ?
        "急停已锁定：请先点击上方“重启进程”，等待 DOWN_WAITING，再执行起立 → START。" :
        "操作顺序：起立 → START → 方向脉冲 → STOP。STOP 会锁定急停，必须重启进程后才能再次操作。";
      workflowHint.className = `workflow-hint ${values.state === "EMERGENCY_STOP" ? "alert" : ""}`;
    }
    setBusy(busy);
  }

  async function request(path, method = "GET", payload = null) {
    const options = { method, headers: { "X-Mi-Dog-Token": token } };
    if (payload !== null) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(payload);
    }
    const response = await fetch(path, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
  }

  async function refresh(silent = false) {
    if ((busy && silent) || refreshInFlight) return;
    refreshInFlight = true;
    try {
      const result = await request("/api/status");
      render(result.values || {}, result.ok);
      if (!silent && !result.ok) stamp(`状态读取失败：${result.stderr || result.stdout}`);
    } catch (error) {
      render({}, false);
      if (!silent) stamp(`状态读取失败：${error.message}`);
    } finally {
      refreshInFlight = false;
    }
  }

  async function action(actionName, stage = null) {
    if (busy && actionName !== "stop") return;
    setBusy(true);
    stamp(`发送操作：${actionName}${stage ? `，赛段 ${stage}` : ""}`);
    try {
      const result = await request("/api/action", "POST", { action: actionName, stage });
      stamp(`${result.ok ? "完成" : "拒绝"}：${result.stdout || result.stderr || "无输出"}`);
    } catch (error) {
      stamp(`操作失败：${error.message}`);
    } finally {
      setBusy(false);
      await refresh(true);
    }
  }

  async function jog(direction) {
    if (busy && direction !== "stop") return;
    setBusy(true);
    try {
      const result = await request("/api/jog", "POST", { direction });
      stamp(`${result.ok ? "调试脉冲完成" : "调试脉冲被拒绝"}：${result.stdout || result.stderr}`);
    } catch (error) {
      stamp(`调试移动失败：${error.message}`);
    } finally {
      setBusy(false);
      await refresh(true);
    }
  }

  async function posture(actionName) {
    if (busy || !postureControlsReady) return;
    if (actionName === "lie-down" && !lieDownReady) return;
    const label = actionName === "stand" ? "起立" : "安全趴下";
    if (!window.confirm(`确认执行“${label}”？请确保机器狗周围无人、无充电线且地面安全。`)) return;
    setBusy(true);
    stamp(`发送姿态操作：${label}`);
    try {
      const result = await request("/api/posture", "POST", { action: actionName });
      stamp(`${result.ok ? "姿态操作完成" : "姿态操作被拒绝"}：${result.stdout || result.stderr}`);
    } catch (error) {
      stamp(`姿态操作失败：${error.message}`);
    } finally {
      setBusy(false);
      await refresh(true);
    }
  }

  async function refreshVideoMetrics() {
    if (!videoActive) return;
    try {
      const metrics = await request("/api/camera/metrics");
      if (!metrics.active && Number(metrics.frames) > 0) {
        stopVideo("视频流已断开");
        return;
      }
      const rate = document.getElementById("videoRate");
      rate.textContent = metrics.active ?
        `${Number(metrics.fps).toFixed(1)} fps · ${Number(metrics.megabits_per_second).toFixed(1)} Mb/s` :
        "正在连接";
      rate.className = `lock ${metrics.active ? "unlocked" : ""}`;
    } catch (error) {
      document.getElementById("videoRate").textContent = "视频状态异常";
    }
  }

  function stopVideo(message = "视频已停止") {
    videoActive = false;
    const image = document.getElementById("cameraStream");
    image.onerror = null;
    image.removeAttribute("src");
    image.classList.remove("visible");
    document.getElementById("videoPlaceholder").hidden = false;
    document.getElementById("videoToggle").textContent = "开启视频";
    document.getElementById("videoRate").textContent = "未开启";
    document.getElementById("videoRate").className = "lock";
    if (videoMetricsTimer !== null) window.clearInterval(videoMetricsTimer);
    videoMetricsTimer = null;
    if (message) stamp(message);
  }

  async function startVideo() {
    videoActive = true;
    const image = document.getElementById("cameraStream");
    document.getElementById("videoPlaceholder").hidden = true;
    document.getElementById("videoToggle").textContent = "停止视频";
    document.getElementById("videoRate").textContent = "正在连接";
    videoMetricsTimer = window.setInterval(refreshVideoMetrics, 2000);
    refreshVideoMetrics();
    stamp("开启头部 RGB 视频");
    try {
      const authorization = await request("/api/camera/token");
      if (!videoActive) return;
      image.classList.add("visible");
      image.onerror = () => {
        if (videoActive) stopVideo("视频连接失败或已断开");
      };
      image.src = `/api/camera/stream?token=${encodeURIComponent(authorization.stream_token)}`;
    } catch (error) {
      if (videoActive) stopVideo(`视频授权失败：${error.message}`);
    }
  }

  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", () => action(button.dataset.action));
  });
  document.querySelectorAll("[data-jog]").forEach((button) => {
    button.addEventListener("click", () => jog(button.dataset.jog));
  });
  document.querySelectorAll("[data-posture]").forEach((button) => {
    button.addEventListener("click", () => posture(button.dataset.posture));
  });
  document.getElementById("videoToggle").addEventListener("click", () => {
    if (videoActive) stopVideo(); else startVideo();
  });
  document.getElementById("continueStage").addEventListener("click", () => {
    action("continue-stage", Number(document.getElementById("stageSelect").value));
  });
  document.getElementById("refreshButton").addEventListener("click", () => refresh(false));
  document.getElementById("testConnection").addEventListener("click", () => refresh(false));
  document.getElementById("copySsh").addEventListener("click", async () => {
    await navigator.clipboard.writeText("./scripts/connect_robot.sh");
    stamp(`已复制 SSH 连接命令，目标 ${target}`);
  });
  document.getElementById("clearLog").addEventListener("click", () => { log.textContent = "等待操作…"; });
  document.getElementById("target").textContent = target;
  setBusy(false);
  refresh(false);
  window.setInterval(() => refresh(true), 10000);
})();
