const loginView = document.querySelector("#loginView");
const devicesView = document.querySelector("#devicesView");
const controlView = document.querySelector("#controlView");
const loginForm = document.querySelector("#loginForm");
const loginError = document.querySelector("#loginError");
const registerButton = document.querySelector("#registerButton");
const usernameInput = document.querySelector("#username");
const passwordInput = document.querySelector("#password");
const userLabel = document.querySelector("#userLabel");
const deviceList = document.querySelector("#deviceList");
const logoutButton = document.querySelector("#logoutButton");
const backButton = document.querySelector("#backButton");
const deviceStatus = document.querySelector("#deviceStatus");
const pad = document.querySelector("#pad");
const cursor = document.querySelector("#cursor");
const controls = document.querySelector("#controls");
const buttonOptions = document.querySelectorAll(".button-option");
const zoomButtons = document.querySelectorAll(".zoom-button");
const shortcutButtons = document.querySelectorAll(".shortcut-button");
const remoteInputPanel = document.querySelector("#remoteInputPanel");
const remoteInput = document.querySelector("#remoteInput");

const TAP_MAX_MS = 260;
const TAP_MAX_DISTANCE = 12;
const DOUBLE_TAP_MS = 320;
const LONG_PRESS_MS = 560;
const MOVE_SENSITIVITY = 1.55;
const MIN_MOVE_DELTA = 0.12;
const SCROLL_SENSITIVITY = 1.8;
const ZOOM_WHEEL_DELTA = 140;
const ZOOM_REPEAT_MS = 110;
const BLOCKED_TOUCH_EVENTS = ["touchstart", "touchmove", "gesturestart", "gesturechange"];
const FETCH_TIMEOUT_MS = 10000;
const RECONNECT_MIN_DELAY = 1000;
const RECONNECT_MAX_DELAY = 30000;

let token = localStorage.getItem("csToken") || "";
let username = localStorage.getItem("csUsername") || "";
let ws = null;
let reconnectDelay = RECONNECT_MIN_DELAY;
let reconnectTimer = null;
let devices = [];
let selectedDevice = null;
let selectedButton = "left";
let activePointers = new Map();
let primaryPointerId = null;
let startX = 0;
let startY = 0;
let lastX = 0;
let lastY = 0;
let startTime = 0;
let movedDistance = 0;
let lastTwoFingerCenter = null;
let scrollRemainder = 0;
let didTwoFingerGesture = false;
let pendingMoveX = 0;
let pendingMoveY = 0;
let moveFrame = null;
let tapTimer = null;
let lastTap = null;
let longPressTimer = null;
let longPressActive = false;
let longPressButton = "left";
let zoomRepeatTimer = null;

function basePath() {
  const path = location.pathname;
  if (path.endsWith("/")) return path.slice(0, -1);
  return path.replace(/\/[^/]*$/, "");
}

function appUrl(path) {
  return `${basePath()}${path}`;
}

function wsUrl() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const port = window.CS_WS_PORT;
  const host = port === "same-origin" ? location.host : port ? `${location.hostname}:${port}` : location.host;
  return `${protocol}//${host}${appUrl("/ws")}?role=mobile&token=${encodeURIComponent(token)}`;
}

function show(view) {
  [loginView, devicesView, controlView].forEach((item) => item.classList.add("hidden"));
  view.classList.remove("hidden");
}

function setCursorPosition(x, y) {
  cursor.style.left = `${x}px`;
  cursor.style.top = `${y}px`;
}

function pointerList() {
  return Array.from(activePointers.values());
}

function midpoint(points) {
  return {
    x: points.reduce((sum, point) => sum + point.x, 0) / points.length,
    y: points.reduce((sum, point) => sum + point.y, 0) / points.length,
  };
}

function sendCommand(command) {
  if (!selectedDevice || !ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ type: "command", deviceId: selectedDevice.id, command }));
}

async function fetchWithTimeout(url, options, timeout = FETCH_TIMEOUT_MS) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("网络超时，请稍后重试");
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

function setConnectionState(text, isWeak = false) {
  if (!selectedDevice || controlView.classList.contains("hidden")) return;
  deviceStatus.textContent = text;
  deviceStatus.style.opacity = isWeak ? "0.62" : "1";
}

function showRemoteInput() {
  if (!selectedDevice) return;
  remoteInputPanel.classList.remove("hidden");
  controls.classList.add("input-open");
  requestAnimationFrame(() => {
    remoteInput.focus({ preventScroll: false });
  });
}

function hideRemoteInput() {
  remoteInputPanel.classList.add("hidden");
  controls.classList.remove("input-open");
  remoteInput.value = "";
  remoteInput.blur();
}

function flushMove() {
  moveFrame = null;
  if (Math.abs(pendingMoveX) < MIN_MOVE_DELTA && Math.abs(pendingMoveY) < MIN_MOVE_DELTA) return;
  sendCommand({ type: "move", dx: pendingMoveX, dy: pendingMoveY });
  pendingMoveX = 0;
  pendingMoveY = 0;
}

function queueMove(dx, dy) {
  pendingMoveX += dx;
  pendingMoveY += dy;
  if (!moveFrame) {
    moveFrame = requestAnimationFrame(flushMove);
  }
}

function renderDevices() {
  userLabel.textContent = username;
  if (!devices.length) {
    deviceList.innerHTML = `<div class="device-card"><div><div class="device-name">暂无电脑在线</div><p>请先启动电脑端 Agent</p></div><span class="status-pill offline">离线</span></div>`;
    return;
  }
  deviceList.innerHTML = "";
  devices.forEach((device) => {
    const button = document.createElement("button");
    button.className = "device-card";
    button.type = "button";
    button.disabled = !device.online;
    button.innerHTML = `
      <div>
        <div class="device-name">${device.name}</div>
        <p>${device.id}</p>
      </div>
      <span class="status-pill ${device.online ? "" : "offline"}">${device.online ? "在线" : "离线"}</span>
    `;
    button.addEventListener("click", () => {
      selectedDevice = device;
      deviceStatus.textContent = `${device.name} 在线`;
      show(controlView);
    });
    deviceList.appendChild(button);
  });
}

function connectWs() {
  if (!token) return;
  clearTimeout(reconnectTimer);
  ws = new WebSocket(wsUrl());
  ws.addEventListener("open", () => {
    reconnectDelay = RECONNECT_MIN_DELAY;
    setConnectionState(selectedDevice ? `${selectedDevice.name} 在线` : "已连接");
  });
  ws.addEventListener("message", (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "devices") {
      devices = data.devices;
      if (selectedDevice) {
        selectedDevice = devices.find((device) => device.id === selectedDevice.id) || selectedDevice;
        deviceStatus.textContent = selectedDevice.online ? `${selectedDevice.name} 在线` : `${selectedDevice.name} 离线`;
      }
      renderDevices();
    } else if (data.type === "inputFocus") {
      if (!selectedDevice || data.deviceId !== selectedDevice.id) return;
      if (data.active) {
        showRemoteInput();
      } else {
        hideRemoteInput();
      }
    }
  });
  ws.addEventListener("close", () => {
    setConnectionState("网络已断开，正在重连...", true);
    reconnectTimer = setTimeout(connectWs, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_DELAY);
  });
}

async function login(usernameValue, passwordValue) {
  const response = await fetchWithTimeout(appUrl("/api/login"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: usernameValue, password: passwordValue }),
  });
  if (response.status === 429) throw new Error("登录尝试过多，请稍后再试");
  if (!response.ok) throw new Error("账号或密码错误");
  return response.json();
}

async function registerAccount(usernameValue, passwordValue) {
  const response = await fetchWithTimeout(appUrl("/api/register"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: usernameValue, password: passwordValue }),
  });
  if (response.status === 409) throw new Error("账号已存在");
  if (response.status === 400) throw new Error("注册失败，账号至少3位，密码至少8位，并包含大写字母和数字");
  if (!response.ok) throw new Error("注册失败，请稍后重试");
  return response.json();
}

function logout() {
  token = "";
  username = "";
  selectedDevice = null;
  localStorage.removeItem("csToken");
  localStorage.removeItem("csUsername");
  clearTimeout(reconnectTimer);
  if (ws) ws.close();
  show(loginView);
}

function selectButton(button) {
  selectedButton = button;
  buttonOptions.forEach((option) => {
    const isActive = option.dataset.button === button;
    option.classList.toggle("active", isActive);
    option.setAttribute("aria-pressed", String(isActive));
  });
}

function zoom(direction) {
  sendCommand({ type: "zoom", delta: direction * ZOOM_WHEEL_DELTA });
}

function stopZoomRepeat() {
  clearInterval(zoomRepeatTimer);
  zoomRepeatTimer = null;
}

function clearTapTimer() {
  clearTimeout(tapTimer);
  tapTimer = null;
}

function clearLongPressTimer() {
  clearTimeout(longPressTimer);
  longPressTimer = null;
}

function queueTap(button, x, y) {
  const now = performance.now();
  if (
    lastTap &&
    lastTap.button === button &&
    now - lastTap.time <= DOUBLE_TAP_MS &&
    Math.hypot(x - lastTap.x, y - lastTap.y) <= TAP_MAX_DISTANCE * 1.8
  ) {
    clearTapTimer();
    lastTap = null;
    sendCommand({ type: "doubleClick", button });
    return;
  }

  lastTap = { button, time: now, x, y };
  clearTapTimer();
  tapTimer = setTimeout(() => {
    sendCommand({ type: "click", button });
    lastTap = null;
    tapTimer = null;
  }, DOUBLE_TAP_MS);
}

function resetTwoFingerScroll() {
  lastTwoFingerCenter = null;
  scrollRemainder = 0;
}

BLOCKED_TOUCH_EVENTS.forEach((type) => {
  document.addEventListener(
    type,
    (event) => {
      if (controlView.classList.contains("hidden")) return;
      if (event.target.closest("#controls, #backButton, input, button, label")) return;
      event.preventDefault();
    },
    { passive: false },
  );
});

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.textContent = "";
  try {
    const auth = await login(usernameInput.value.trim(), passwordInput.value);
    token = auth.token;
    username = auth.username;
    localStorage.setItem("csToken", token);
    localStorage.setItem("csUsername", username);
    connectWs();
    show(devicesView);
  } catch (error) {
    loginError.textContent = error.message;
  }
});

registerButton.addEventListener("click", async () => {
  loginError.textContent = "";
  try {
    await registerAccount(usernameInput.value.trim(), passwordInput.value);
    loginError.textContent = "注册成功，请点击登录";
  } catch (error) {
    loginError.textContent = error.message;
  }
});

logoutButton.addEventListener("click", logout);
backButton.addEventListener("click", () => show(devicesView));

controls.addEventListener("pointerdown", (event) => event.stopPropagation());
remoteInputPanel.addEventListener("pointerdown", (event) => event.stopPropagation());
remoteInputPanel.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = remoteInput.value;
  if (!text) return;
  sendCommand({ type: "text", value: text });
  remoteInput.value = "";
  remoteInput.focus();
});
controls.addEventListener("pointerup", (event) => {
  event.stopPropagation();
  const option = event.target.closest(".button-option");
  if (option) selectButton(option.dataset.button);
});

zoomButtons.forEach((button) => {
  button.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    event.stopPropagation();
    const direction = Number(button.dataset.zoom);
    zoom(direction);
    stopZoomRepeat();
    zoomRepeatTimer = setInterval(() => zoom(direction), ZOOM_REPEAT_MS);
  });
  button.addEventListener("pointerup", stopZoomRepeat);
  button.addEventListener("pointercancel", stopZoomRepeat);
  button.addEventListener("pointerleave", stopZoomRepeat);
});

shortcutButtons.forEach((button) => {
  button.addEventListener("pointerup", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (button.dataset.hotkey) {
      sendCommand({ type: "hotkey", name: button.dataset.hotkey });
    } else if (button.dataset.key) {
      sendCommand({ type: "key", name: button.dataset.key });
    }
  });
});

pad.addEventListener("pointerdown", (event) => {
  event.preventDefault();
  pad.setPointerCapture(event.pointerId);
  activePointers.set(event.pointerId, { x: event.clientX, y: event.clientY });

  if (activePointers.size === 1) {
    primaryPointerId = event.pointerId;
    startX = event.clientX;
    startY = event.clientY;
    lastX = event.clientX;
    lastY = event.clientY;
    startTime = performance.now();
    movedDistance = 0;
    didTwoFingerGesture = false;
    pendingMoveX = 0;
    pendingMoveY = 0;
    longPressActive = false;
    longPressButton = selectedButton;
    clearLongPressTimer();
    longPressTimer = setTimeout(() => {
      if (activePointers.size !== 1 || primaryPointerId !== event.pointerId) return;
      if (movedDistance > TAP_MAX_DISTANCE) return;
      clearTapTimer();
      lastTap = null;
      longPressActive = true;
      sendCommand({ type: "mouseDown", button: longPressButton });
    }, LONG_PRESS_MS);
    setCursorPosition(event.clientX, event.clientY);
  } else if (activePointers.size === 2) {
    clearLongPressTimer();
    lastTwoFingerCenter = midpoint(pointerList());
    scrollRemainder = 0;
    didTwoFingerGesture = false;
  }
});

pad.addEventListener("pointermove", (event) => {
  if (!activePointers.has(event.pointerId)) return;
  event.preventDefault();
  const events = event.getCoalescedEvents ? event.getCoalescedEvents() : [event];
  const latestEvent = events[events.length - 1] || event;
  activePointers.set(event.pointerId, { x: latestEvent.clientX, y: latestEvent.clientY });

  if (activePointers.size >= 2) {
    const center = midpoint(pointerList());
    if (!lastTwoFingerCenter) {
      lastTwoFingerCenter = center;
      return;
    }
    scrollRemainder += center.y - lastTwoFingerCenter.y;
    if (Math.abs(scrollRemainder) >= 1.5) {
      didTwoFingerGesture = true;
      sendCommand({ type: "scroll", delta: -scrollRemainder * SCROLL_SENSITIVITY });
      scrollRemainder = 0;
    }
    lastTwoFingerCenter = center;
    return;
  }

  if (event.pointerId !== primaryPointerId) return;

  let totalDx = 0;
  let totalDy = 0;
  for (const item of events) {
    const dx = item.clientX - lastX;
    const dy = item.clientY - lastY;
    lastX = item.clientX;
    lastY = item.clientY;
    totalDx += dx;
    totalDy += dy;
    movedDistance += Math.hypot(dx, dy);
  }

  if (!longPressActive && movedDistance > TAP_MAX_DISTANCE) clearLongPressTimer();
  setCursorPosition(latestEvent.clientX, latestEvent.clientY);
  queueMove(totalDx * MOVE_SENSITIVITY, totalDy * MOVE_SENSITIVITY);
});

function endPointer(event) {
  if (!activePointers.has(event.pointerId)) return;
  event.preventDefault();

  const wasPrimary = event.pointerId === primaryPointerId;
  const hadTwoPointers = activePointers.size === 2;
  const wasLongPress = wasPrimary && longPressActive;
  activePointers.delete(event.pointerId);

  if (wasPrimary) {
    clearLongPressTimer();
    if (wasLongPress) {
      sendCommand({ type: "mouseUp", button: longPressButton });
      longPressActive = false;
    }

    const elapsed = performance.now() - startTime;
    const distance = Math.hypot(event.clientX - startX, event.clientY - startY);
    if (!wasLongPress && elapsed < TAP_MAX_MS && distance < TAP_MAX_DISTANCE && movedDistance < TAP_MAX_DISTANCE && !didTwoFingerGesture) {
      queueTap(hadTwoPointers ? "right" : selectedButton, event.clientX, event.clientY);
    }
    primaryPointerId = null;
  }

  if (activePointers.size === 1) {
    const [remaining] = pointerList();
    lastX = remaining.x;
    lastY = remaining.y;
    resetTwoFingerScroll();
  } else if (activePointers.size === 0) {
    resetTwoFingerScroll();
    didTwoFingerGesture = false;
  }
}

pad.addEventListener("pointerup", endPointer);
pad.addEventListener("pointercancel", endPointer);
pad.addEventListener("contextmenu", (event) => event.preventDefault());
window.addEventListener("pointerup", stopZoomRepeat);
window.addEventListener("blur", () => {
  stopZoomRepeat();
  clearLongPressTimer();
  if (longPressActive) {
    sendCommand({ type: "mouseUp", button: longPressButton });
    longPressActive = false;
  }
});

if (token && username) {
  userLabel.textContent = username;
  connectWs();
  show(devicesView);
} else {
  show(loginView);
}
