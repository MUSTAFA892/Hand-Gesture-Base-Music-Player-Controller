from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Any


@dataclass
class GestureResult:
    gesture: str | None
    confidence: float


class GestureRecognizer:
    """Maps a hand-landmark frame into a high-level gesture."""

    def __init__(self, pinch_threshold: float = 0.28) -> None:
        self.pinch_threshold = pinch_threshold

    def recognize(self, results: Any) -> GestureResult:
        if not getattr(results, "multi_hand_landmarks", None):
            return GestureResult(None, 0.0)

        hand_landmarks = results.multi_hand_landmarks[0]
        handedness_label = "Right"
        if getattr(results, "multi_handedness", None):
            handedness_label = results.multi_handedness[0].classification[0].label

        lm = hand_landmarks.landmark

        wrist = lm[0]
        middle_mcp = lm[9]
        palm_size = max(hypot(wrist.x - middle_mcp.x, wrist.y - middle_mcp.y), 1e-6)

        thumb_tip = lm[4]
        thumb_ip = lm[3]
        index_tip = lm[8]

        pinch_dist = hypot(thumb_tip.x - index_tip.x, thumb_tip.y - index_tip.y) / palm_size
        if pinch_dist <= self.pinch_threshold:
            confidence = max(0.5, min(1.0, 1.0 - pinch_dist))
            return GestureResult("PINCH", confidence)

        fingers = self._fingers_up(lm, handedness_label)
        total_up = sum(fingers.values())

        if total_up == 0:
            return GestureResult("FIST", 0.9)

        if total_up == 5:
            return GestureResult("OPEN_PALM", 0.95)

        v_sign = (
            fingers["index"]
            and fingers["middle"]
            and not fingers["ring"]
            and not fingers["pinky"]
        )
        if v_sign:
            return GestureResult("V_SIGN", 0.9)

        thumbs_only = (
            fingers["thumb"]
            and not fingers["index"]
            and not fingers["middle"]
            and not fingers["ring"]
            and not fingers["pinky"]
        )
        if thumbs_only:
            if thumb_tip.y < thumb_ip.y:
                return GestureResult("THUMB_UP", 0.85)
            return GestureResult("THUMB_DOWN", 0.85)

        return GestureResult(None, 0.0)

    def _fingers_up(self, lm: Any, handedness: str) -> dict[str, bool]:
        thumb_tip = lm[4]
        thumb_ip = lm[3]

        if handedness == "Right":
            thumb_up = thumb_tip.x < thumb_ip.x
        else:
            thumb_up = thumb_tip.x > thumb_ip.x

        return {
            "thumb": thumb_up,
            "index": lm[8].y < lm[6].y,
            "middle": lm[12].y < lm[10].y,
            "ring": lm[16].y < lm[14].y,
            "pinky": lm[20].y < lm[18].y,
        }
