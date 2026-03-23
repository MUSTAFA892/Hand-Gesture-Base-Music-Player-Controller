from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from glob import glob
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
        self._lock = threading.Lock()

        self._recognizer = GestureRecognizer()
        self._last_trigger_time: dict[str, float] = {}

        self._running = False
        self._camera_index = 0
        self._camera_source: str | None = None
        self._last_gesture: str | None = None
        self._last_action: str | None = None
        self._fps = 0.0
        self._error: str | None = None
        self._events: deque[GestureEvent] = deque(maxlen=20)

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

    def list_available_cameras(self, max_index: int = 8) -> list[int]:
        camera_nodes = sorted(glob("/dev/video*"))
        if not camera_nodes:
            return []

        available: list[int] = []
        for idx in range(0, max_index + 1):
            cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
            if cap.isOpened():
                available.append(idx)
            cap.release()
        return available

    def start(self, camera_index: int = 0) -> dict[str, Any]:
        with self._lock:
            if self._running:
                return {"ok": True, "message": "Gesture service is already running"}

            available_cameras = self.list_available_cameras()
            if not available_cameras:
                self._error = (
                    "No webcam devices detected by OS. Ensure camera is connected/passthrough enabled "
                    "and available under /dev/video*."
                )
                return {"ok": False, "message": self._error, "available_cameras": []}

            if camera_index not in available_cameras:
                self._error = (
                    f"Camera index {camera_index} is unavailable. "
                    f"Available indices: {available_cameras}"
                )
                return {
                    "ok": False,
                    "message": self._error,
                    "available_cameras": available_cameras,
                }

            self._camera_index = camera_index
            self._camera_source = str(camera_index)
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            self._running = True
            self._error = None
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
                "available_cameras": self.list_available_cameras(),
                "last_gesture": self._last_gesture,
                "last_action": self._last_action,
                "fps": round(self._fps, 2),
                "error": self._error,
                "events": events,
                "gesture_map": self._gesture_to_action,
            }

    def _run_loop(self) -> None:
        cap = cv2.VideoCapture(self._camera_index, cv2.CAP_V4L2)
        if not cap.isOpened():
            with self._lock:
                self._running = False
                self._error = (
                    f"Could not open webcam (index {self._camera_index}). "
                    f"Detected cameras: {self.list_available_cameras()}"
                )
            return

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

                with self._lock:
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
