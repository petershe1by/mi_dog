(() => {
  "use strict";
  const token = document.querySelector('meta[name="mi-dog-token"]').content;
  const target = document.querySelector('meta[name="mi-dog-target"]').content;
  const log = document.getElementById("log");
  let busy = false;
  let refreshInFlight = false;

  const fields = {
    service_active: document.getElementById("service"),
    state: document.getElementById("state"),
    stage: document.getElementById("stage"),
    run_allowed: document.getElementById("runAllowed"),
    enable_motion: document.getElementById("motionEnabled"),
    battery_percent: document.getElementById("batteryPercent"),
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
      if (button.dataset.jog === "stop" || button.dataset.action === "stop") return;
      button.disabled = value;
    });
  }

  function render(values, ok) {
    Object.entries(fields).forEach(([key, element]) => {
      let value = values[key] ?? "—";
      if (value !== "—" && key === "battery_percent") value = `${value}%`;
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
    const jogReady = values.enable_motion === "True" && values.run_allowed === "true";
    const jogLock = document.getElementById("jogLock");
    jogLock.textContent = jogReady ? "调试移动已放行" : "调试移动锁定";
    jogLock.className = `lock ${jogReady ? "unlocked" : ""}`;
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

  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", () => action(button.dataset.action));
  });
  document.querySelectorAll("[data-jog]").forEach((button) => {
    button.addEventListener("click", () => jog(button.dataset.jog));
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
  refresh(false);
  window.setInterval(() => refresh(true), 10000);
})();
