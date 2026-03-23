const engineState = document.getElementById("engineState");
const fps = document.getElementById("fps");
const volume = document.getElementById("volume");
const muted = document.getElementById("muted");
const lastGesture = document.getElementById("lastGesture");
const lastAction = document.getElementById("lastAction");
const engineError = document.getElementById("engineError");
const gestureMap = document.getElementById("gestureMap");
const eventFeed = document.getElementById("eventFeed");
const cameraHint = document.getElementById("cameraHint");
const videoFeed = document.getElementById("videoFeed");

const startGestureButton = document.getElementById("startGesture");
const stopGestureButton = document.getElementById("stopGesture");

function humanAction(action) {
  return action
    .replaceAll("-", " ")
    .split(" ")
    .map((chunk) => chunk.charAt(0).toUpperCase() + chunk.slice(1))
    .join(" ");
}

function updateStatus(payload) {
  const gesture = payload.gesture || {};
  const audio = payload.audio || {};

  engineState.textContent = gesture.running ? "Running" : "Stopped";
  fps.textContent = String(gesture.fps ?? 0);

  if (gesture.running) {
    if (!videoFeed.src || videoFeed.src.indexOf("/api/video_feed") === -1) {
      videoFeed.src = "/api/video_feed";
      videoFeed.style.display = "block";
    }
  } else {
    videoFeed.src = "";
    videoFeed.style.display = "none";
  }

  const vol = audio.volume_percent;
  volume.textContent = Number.isFinite(vol) ? `${vol}%` : "N/A";

  const mutedValue = audio.muted;
  muted.textContent = mutedValue === null || mutedValue === undefined ? "N/A" : mutedValue ? "Yes" : "No";

  lastGesture.textContent = gesture.last_gesture || "None";
  lastAction.textContent = gesture.last_action ? humanAction(gesture.last_action) : "None";
  engineError.textContent = gesture.error || "";

  renderGestureMap(gesture.gesture_map || {});
  renderEvents(gesture.events || []);
}

function renderGestureMap(map) {
  gestureMap.innerHTML = "";
  if (!map || typeof map !== "object") {
    return;
  }
  Object.entries(map).forEach(([gesture, action]) => {
    const li = document.createElement("li");
    li.innerHTML = `<span>${gesture}</span><strong>${humanAction(action)}</strong>`;
    gestureMap.appendChild(li);
  });
}

function renderEvents(events) {
  eventFeed.innerHTML = "";
  [...events].reverse().forEach((event) => {
    const row = document.createElement("div");
    row.className = `feed-item ${event.success ? "ok" : "bad"}`;
    const date = new Date(event.timestamp * 1000);
    row.textContent = `${date.toLocaleTimeString()} | ${event.gesture} => ${humanAction(event.action)} | ${event.detail || ""}`;
    eventFeed.appendChild(row);
  });
}

async function callJson(url, method = "GET") {
  const res = await fetch(url, { method });
  let payload = {};
  try {
    payload = await res.json();
  } catch {
    payload = {};
  }
  if (!res.ok) {
    const message = payload.message || `Request failed: ${res.status}`;
    throw new Error(message);
  }
  return payload;
}

async function sendMediaAction(action) {
  await callJson(`/api/media/${action}`, "POST");
}

const cameraIndexInput = document.getElementById("cameraIndex");
const cameraSourceInput = document.getElementById("cameraSource");

startGestureButton.addEventListener("click", async () => {
  try {
    const index = Number(cameraIndexInput.value || 0);
    const source = (cameraSourceInput.value || "").trim();
    const query = new URLSearchParams();

    if (source) {
      query.set("camera_source", source);
    } else {
      query.set("camera_index", String(index));
    }

    const data = await callJson(`/api/gesture/start?${query.toString()}`, "POST");
    if (!data.ok) {
      engineError.textContent = data.message || "Failed to start gesture engine";
      return;
    }
    engineError.textContent = "";
  } catch (error) {
    engineError.textContent = error.message;
  }
});

stopGestureButton.addEventListener("click", async () => {
  try {
    await callJson("/api/gesture/stop", "POST");
  } catch (error) {
    engineError.textContent = error.message;
  }
});

document.querySelectorAll("[data-action]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const action = btn.getAttribute("data-action");
    if (!action) {
      return;
    }
    await sendMediaAction(action);
  });
});

function connectWs() {
  const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${wsProtocol}://${window.location.host}/ws/status`);

  ws.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    updateStatus(payload);
  };

  ws.onclose = () => {
    setTimeout(connectWs, 1500);
  };
}

async function prime() {
  try {
    const status = await callJson("/api/status");
    updateStatus(status);
  } catch (error) {
    engineError.textContent = error.message;
  }
}

async function loadCameraInfo() {
  try {
    const payload = await callJson("/api/cameras");
    const available = payload.available_cameras || [];
    if (available.length === 0) {
      cameraHint.textContent =
        "No local cameras detected. You can still use phone stream URL (IP Webcam/DroidCam).";
      startGestureButton.disabled = false;
      return;
    }
    cameraHint.textContent =
      `Available camera indices: ${available.join(", ")}. ` +
      "Or enter phone stream URL to use mobile camera.";
    if (!available.includes(Number(cameraIndexInput.value))) {
      cameraIndexInput.value = String(available[0]);
    }
    startGestureButton.disabled = false;
  } catch (error) {
    cameraHint.textContent = `Camera check failed: ${error.message}`;
  }
}

prime();
loadCameraInfo();
connectWs();
