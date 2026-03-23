from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any


class MediaController:
    """Controls system-wide media playback and default sink volume."""

    def __init__(self) -> None:
        self.playerctl_available = shutil.which("playerctl") is not None
        self.pactl_available = shutil.which("pactl") is not None

    def _run(self, command: list[str]) -> dict[str, Any]:
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True)
            if result.returncode != 0:
                return {
                    "ok": False,
                    "message": result.stderr.strip() or "Command failed",
                    "command": " ".join(command),
                }
            return {
                "ok": True,
                "message": result.stdout.strip() or "OK",
                "command": " ".join(command),
            }
        except Exception as exc:
            return {"ok": False, "message": str(exc), "command": " ".join(command)}

    def play_pause(self) -> dict[str, Any]:
        if not self.playerctl_available:
            return {"ok": False, "message": "playerctl is not installed"}
        return self._run(["playerctl", "play-pause"])

    def next_track(self) -> dict[str, Any]:
        if not self.playerctl_available:
            return {"ok": False, "message": "playerctl is not installed"}
        return self._run(["playerctl", "next"])

    def previous_track(self) -> dict[str, Any]:
        if not self.playerctl_available:
            return {"ok": False, "message": "playerctl is not installed"}
        return self._run(["playerctl", "previous"])

    def volume_up(self, step_percent: int = 5) -> dict[str, Any]:
        if not self.pactl_available:
            return {"ok": False, "message": "pactl is not installed"}
        return self._run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"+{step_percent}%"])

    def volume_down(self, step_percent: int = 5) -> dict[str, Any]:
        if not self.pactl_available:
            return {"ok": False, "message": "pactl is not installed"}
        return self._run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"-{step_percent}%"])

    def toggle_mute(self) -> dict[str, Any]:
        if not self.pactl_available:
            return {"ok": False, "message": "pactl is not installed"}
        return self._run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])

    def get_volume_percent(self) -> int | None:
        if not self.pactl_available:
            return None
        info = self._run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"]) 
        if not info.get("ok"):
            return None
        match = re.search(r"(\d+)%", info.get("message", ""))
        if not match:
            return None
        return int(match.group(1))

    def is_muted(self) -> bool | None:
        if not self.pactl_available:
            return None
        info = self._run(["pactl", "get-sink-mute", "@DEFAULT_SINK@"]) 
        if not info.get("ok"):
            return None
        text = info.get("message", "").lower()
        if "yes" in text:
            return True
        if "no" in text:
            return False
        return None

    def execute_action(self, action: str) -> dict[str, Any]:
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

    def get_audio_state(self) -> dict[str, Any]:
        return {
            "volume_percent": self.get_volume_percent(),
            "muted": self.is_muted(),
            "playerctl_available": self.playerctl_available,
            "pactl_available": self.pactl_available,
        }
