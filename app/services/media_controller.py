from __future__ import annotations

import threading
from typing import Any

import pyautogui

try:
    import pythoncom
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    PYCAW_AVAILABLE = True
except Exception:
    pythoncom = None
    AudioUtilities = None
    IAudioEndpointVolume = None
    CLSCTX_ALL = None
    cast = None
    POINTER = None
    PYCAW_AVAILABLE = False


class MediaController:
    """Controls system-wide media playback and volume on Windows."""

    def __init__(self) -> None:
        self._volume_interface = None
        self._lock = threading.Lock()
        self._last_known_volume = 0
        self._last_known_muted = False

    def _get_volume_interface(self):
        if not PYCAW_AVAILABLE:
            return None
        try:
            # Initialize COM for the current thread (needed when pycaw is used across threads).
            pythoncom.CoInitialize()
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            return cast(interface, POINTER(IAudioEndpointVolume))
        except Exception:
            return None

    def _press_key(self, key: str, success_message: str) -> dict[str, Any]:
        try:
            pyautogui.press(key)
            return {"ok": True, "message": success_message}
        except Exception as exc:
            return {"ok": False, "message": f"Failed to send key '{key}': {exc}"}

    def execute_action(self, action: str) -> dict[str, Any]:
        with self._lock:
            actions = {
                "play-pause": self.play_pause,
                "next": self.next_track,
                "previous": self.previous_track,
                "volume-up": self.volume_up,
                "volume-down": self.volume_down,
                "mute-toggle": self.toggle_mute,
            }
            operation = actions.get(action)
            if operation is None:
                return {"ok": False, "message": f"Unknown action: {action}"}
            return operation()

    def play_pause(self) -> dict[str, Any]:
        return self._press_key("playpause", "Play/Pause toggled")

    def next_track(self) -> dict[str, Any]:
        return self._press_key("nexttrack", "Next track")

    def previous_track(self) -> dict[str, Any]:
        return self._press_key("prevtrack", "Previous track")

    def volume_up(self, step_percent: int = 5) -> dict[str, Any]:
        # Keypress-based volume control is the most robust path across Windows audio devices.
        presses = max(1, step_percent // 2)
        result: dict[str, Any] = {"ok": True, "message": "Volume up"}
        for _ in range(presses):
            result = self._press_key("volumeup", "Volume up")
            if not result.get("ok"):
                return result
        return {"ok": True, "message": f"Volume increased ({presses} steps)"}

    def volume_down(self, step_percent: int = 5) -> dict[str, Any]:
        presses = max(1, step_percent // 2)
        result: dict[str, Any] = {"ok": True, "message": "Volume down"}
        for _ in range(presses):
            result = self._press_key("volumedown", "Volume down")
            if not result.get("ok"):
                return result
        return {"ok": True, "message": f"Volume decreased ({presses} steps)"}

    def toggle_mute(self) -> dict[str, Any]:
        return self._press_key("volumemute", "Mute toggled")

    def get_audio_state(self) -> dict[str, Any]:
        if not self._volume_interface:
            self._volume_interface = self._get_volume_interface()

        if self._volume_interface:
            try:
                self._last_known_volume = int(self._volume_interface.GetMasterVolumeLevelScalar() * 100)
                self._last_known_muted = bool(self._volume_interface.GetMute())
            except Exception:
                self._volume_interface = None

        return {
            "volume_percent": self._last_known_volume,
            "muted": self._last_known_muted,
        }

    def get_volume_percent(self) -> int | None:
        return self.get_audio_state().get("volume_percent")

    def is_muted(self) -> bool | None:
        return self.get_audio_state().get("muted")
