from __future__ import annotations

import json
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from importlib import metadata
from typing import Any, Callable

import cv2
import mediapipe as mp

from app.services.gesture_recognizer import GestureRecognizer


@dataclass
class GestureEvent:
    timestamp: float
    gesture: str
    action: str
    success: bool
    detail: str


class GestureService:
    """Runs webcam gesture detection in a background thread."""

    def __init__(self, action_callback: Callable[[str], dict[str, Any]]) -> None:
        self._action_callback = action_callback
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._startup_event = threading.Event()
        self._lock = threading.Lock()

        self._recognizer = GestureRecognizer()
        self._last_trigger_time: dict[str, float] = {}

        self._running = False
        self._camera_index = 0
        self._capture_target: int | str = 0
        self._camera_source: str | None = None
        self._available_cameras: list[int] = []
        self._last_gesture: str | None = None
        self._last_action: str | None = None
        self._fps = 0.0
        self._error: str | None = None
        self._events: deque[GestureEvent] = deque(maxlen=20)
        self._latest_frame: bytes | None = None

        self._gesture_to_action = {
            "OPEN_PALM": "play-pause",
            "THUMB_UP": "volume-up",
            "THUMB_DOWN": "volume-down",
            "V_SIGN": "next",
            "FIST": "previous",
            "PINCH": "mute-toggle",
        }
        self._cooldowns = {
            "OPEN_PALM": 1.2,
            "THUMB_UP": 0.6,
            "THUMB_DOWN": 0.6,
            "V_SIGN": 1.2,
            "FIST": 1.2,
            "PINCH": 1.2,
        }

    def _windows_backends(self) -> list[tuple[str, int | None]]:
        return [
            ("MSMF", cv2.CAP_MSMF),
            ("DSHOW", cv2.CAP_DSHOW),
            ("AUTO", None),
        ]

    def _open_camera(
        self, camera_index: int, require_frame: bool
    ) -> tuple[cv2.VideoCapture | None, str | None]:
        for backend_name, backend in self._windows_backends():
            if backend is None:
                cap = cv2.VideoCapture(camera_index)
            else:
                cap = cv2.VideoCapture(camera_index, backend)

            if not cap.isOpened():
                cap.release()
                continue

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)

            if require_frame:
                ok, _ = cap.read()
                if not ok:
                    cap.release()
                    continue

            return cap, backend_name

        return None, None

    def _open_camera_url(
        self, camera_url: str, require_frame: bool
    ) -> tuple[cv2.VideoCapture | None, str | None]:
        for backend_name, backend in [("AUTO", None), ("FFMPEG", cv2.CAP_FFMPEG)]:
            if backend is None:
                cap = cv2.VideoCapture(camera_url)
            else:
                cap = cv2.VideoCapture(camera_url, backend)

            if not cap.isOpened():
                cap.release()
                continue

            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if require_frame:
                frame_ok = False
                for _ in range(25):
                    ok, _ = cap.read()
                    if ok:
                        frame_ok = True
                        break
                    time.sleep(0.04)
                if not frame_ok:
                    cap.release()
                    continue

            return cap, backend_name

        return None, None

    def list_available_cameras(self, max_index: int = 10) -> list[int]:
        available: list[int] = []
        for idx in range(0, max_index + 1):
            cap, _ = self._open_camera(idx, require_frame=True)
            if cap is not None:
                available.append(idx)
                cap.release()

        with self._lock:
            self._available_cameras = available

        return available

    def diagnose_cameras(self, max_index: int = 10) -> dict[str, Any]:
        details: list[dict[str, Any]] = []

        for idx in range(0, max_index + 1):
            for backend_name, backend in self._windows_backends():
                if backend is None:
                    cap = cv2.VideoCapture(idx)
                else:
                    cap = cv2.VideoCapture(idx, backend)

                opened = cap.isOpened()
                frame_ok = False
                if opened:
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    frame_ok, _ = cap.read()

                details.append(
                    {
                        "index": idx,
                        "backend": backend_name,
                        "opened": opened,
                        "frame_ok": frame_ok,
                    }
                )
                cap.release()

        conflict = False
        installed: dict[str, str] = {}
        for pkg in ("opencv-python", "opencv-contrib-python"):
            try:
                installed[pkg] = metadata.version(pkg)
            except metadata.PackageNotFoundError:
                pass

        if "opencv-python" in installed and "opencv-contrib-python" in installed:
            conflict = True

        windows_devices = self._windows_camera_devices()
        has_phantom = any(str(d.get("status", "")).lower() == "unknown" for d in windows_devices)

        recommendation = "No OpenCV package conflict detected."
        if conflict:
            recommendation = "Uninstall opencv-python and keep only opencv-contrib-python when using MediaPipe."
        elif not self._available_cameras and has_phantom:
            recommendation = (
                "Windows reports your camera as Unknown/phantom. Reinstall or roll back camera driver "
                "from Device Manager, then reboot."
            )
        elif not self._available_cameras:
            recommendation = (
                "No camera opened via MSMF/DSHOW/AUTO. Check Windows Camera privacy, close apps using webcam, "
                "and verify camera works in the Camera app."
            )

        return {
            "opencv_version": cv2.__version__,
            "installed_opencv_packages": installed,
            "opencv_package_conflict": conflict,
            "available_cameras": self.list_available_cameras(max_index=max_index),
            "windows_camera_devices": windows_devices,
            "attempts": details,
            "recommendation": recommendation,
        }

    def _windows_camera_devices(self) -> list[dict[str, Any]]:
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-PnpDevice -Class Camera | "
            "Select-Object Status,FriendlyName,InstanceId,Problem,ConfigManagerErrorCode | "
            "ConvertTo-Json -Compress",
        ]

        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except Exception:
            return []

        output = (proc.stdout or "").strip()
        if not output:
            return []

        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            return []

        if isinstance(parsed, dict):
            parsed = [parsed]

        devices: list[dict[str, Any]] = []
        if isinstance(parsed, list):
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                devices.append(
                    {
                        "status": item.get("Status"),
                        "friendly_name": item.get("FriendlyName"),
                        "instance_id": item.get("InstanceId"),
                        "problem": item.get("Problem"),
                        "config_manager_error_code": item.get("ConfigManagerErrorCode"),
                    }
                )

        return devices

    def video_feed(self) -> Any:
        try:
            while True:
                with self._lock:
                    frame = self._latest_frame
                    if not self._running:
                        break

                if frame:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                time.sleep(0.04)
        except Exception:
            pass

    def start(self, camera_index: int = 0, camera_source: str | None = None) -> dict[str, Any]:
        source = (camera_source or "").strip()
        available_cameras = self.list_available_cameras() if not source else []

        with self._lock:
            if self._running:
                return {"ok": True, "message": "Gesture service is already running"}

            if source:
                self._capture_target = source
                self._camera_index = -1
                self._camera_source = source
            elif not available_cameras:
                self._error = (
                    "No responsive webcam detected. Please check if your camera is "
                    "connected and not being used by another app (like Zoom/Teams)."
                )
                return {"ok": False, "message": self._error, "available_cameras": []}

            elif camera_index not in available_cameras:
                camera_index = available_cameras[0]
                self._camera_index = camera_index
                self._capture_target = camera_index
                self._camera_source = f"Windows Cam {camera_index}"
            else:
                self._camera_index = camera_index
                self._capture_target = camera_index
                self._camera_source = f"Windows Cam {camera_index}"

            self._stop_event.clear()
            self._startup_event.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._running = True
            self._error = None
            self._thread.start()

        started = self._startup_event.wait(timeout=3.0)
        if not started:
            self.stop()
            timeout_message = (
                "Camera URL startup timed out. Verify phone camera app is running and stream URL is correct."
                if source
                else "Camera startup timed out. Close other apps using the webcam and try again."
            )
            return {
                "ok": False,
                "message": timeout_message,
                "available_cameras": available_cameras,
            }

        with self._lock:
            if self._error:
                return {
                    "ok": False,
                    "message": self._error,
                    "available_cameras": available_cameras,
                }

        if source:
            return {"ok": True, "message": f"Gesture service started with source URL: {source}"}

        return {"ok": True, "message": f"Gesture service started with camera {camera_index}"}

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if not self._running:
                return {"ok": True, "message": "Gesture service is already stopped"}
            self._stop_event.set()

        if self._thread is not None:
            self._thread.join(timeout=2.0)

        with self._lock:
            self._running = False
        return {"ok": True, "message": "Gesture service stopped"}

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            events = [
                {
                    "timestamp": event.timestamp,
                    "gesture": event.gesture,
                    "action": event.action,
                    "success": event.success,
                    "detail": event.detail,
                }
                for event in self._events
            ]
            return {
                "running": self._running,
                "camera_index": self._camera_index,
                "camera_source": self._camera_source,
                "available_cameras": list(self._available_cameras),
                "last_gesture": self._last_gesture,
                "last_action": self._last_action,
                "fps": round(self._fps, 2),
                "error": self._error,
                "events": events,
                "gesture_map": self._gesture_to_action,
            }

    def _run_loop(self) -> None:
        capture_target = self._capture_target
        if isinstance(capture_target, str):
            cap, backend_name = self._open_camera_url(capture_target, require_frame=True)
        else:
            cap, backend_name = self._open_camera(capture_target, require_frame=True)

        if not cap or not cap.isOpened():
            with self._lock:
                self._running = False
                if isinstance(capture_target, str):
                    self._error = (
                        "Could not open camera URL. Ensure phone and server are on the same network "
                        "and the stream URL is correct."
                    )
                else:
                    self._error = (
                        f"Could not open Windows webcam (index {self._camera_index}). "
                        "Ensure no other apps (Camera app, Zoom, etc.) are using it."
                    )
            self._startup_event.set()
            return

        with self._lock:
            if isinstance(capture_target, str):
                self._camera_source = f"URL Stream ({backend_name})"
            else:
                self._camera_source = f"Windows Cam {self._camera_index} ({backend_name})"

        self._startup_event.set()

        mp_hands = mp.solutions.hands
        hands = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.65,
            min_tracking_confidence=0.6,
        )

        prev_time = time.time()

        try:
            while not self._stop_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    with self._lock:
                        self._error = "Failed to read frame from webcam"
                    time.sleep(0.05)
                    continue

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = hands.process(rgb)
                gesture_result = self._recognizer.recognize(results)

                # Update latest frame for video feed
                _, jpeg = cv2.imencode(".jpg", frame)
                with self._lock:
                    self._latest_frame = jpeg.tobytes()
                    self._last_gesture = gesture_result.gesture

                if gesture_result.gesture:
                    self._trigger_action(gesture_result.gesture)

                now = time.time()
                delta = now - prev_time
                prev_time = now
                fps = 1.0 / delta if delta > 0 else 0.0

                with self._lock:
                    self._fps = fps

                time.sleep(0.01)
        except Exception as exc:
            with self._lock:
                self._error = f"Gesture thread error: {exc}"
        finally:
            hands.close()
            cap.release()
            with self._lock:
                self._running = False

    def _trigger_action(self, gesture: str) -> None:
        now = time.time()
        cooldown = self._cooldowns.get(gesture, 1.0)
        last_time = self._last_trigger_time.get(gesture, 0.0)
        if now - last_time < cooldown:
            return

        action = self._gesture_to_action.get(gesture)
        if not action:
            return

        response = self._action_callback(action)
        success = bool(response.get("ok"))
        detail = str(response.get("message", ""))
        self._last_trigger_time[gesture] = now

        with self._lock:
            self._last_action = action
            self._events.append(
                GestureEvent(
                    timestamp=now,
                    gesture=gesture,
                    action=action,
                    success=success,
                    detail=detail,
                )
            )
