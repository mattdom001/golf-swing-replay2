from enum import Enum, auto
import time

import cv2
import numpy as np

from .config import AppConfig
from .ui import OpenCVUI


class ReplayResult(Enum):
    COMPLETE = auto()
    SKIPPED = auto()


class ReplayPlayer:
    def __init__(self, ui: OpenCVUI, config: AppConfig):
        self.ui = ui
        self.config = config

    def _render(self, frame: np.ndarray, frame_index: int, impact_index: int,
                speed: float, paused: bool, zoom: float) -> np.ndarray:
        source = frame
        if zoom > 1.0:
            height, width = source.shape[:2]
            crop_width, crop_height = int(width / zoom), int(height / zoom)
            left = (width - crop_width) // 2
            top = (height - crop_height) // 2
            source = source[top:top + crop_height, left:left + crop_width]
        output = cv2.resize(source, (self.ui.WIDTH, self.ui.HEIGHT))
        overlay = output.copy()
        cv2.rectangle(overlay, (0, 0), (self.ui.WIDTH, 90), (0, 0, 0), -1)
        cv2.rectangle(overlay, (0, 640), (self.ui.WIDTH, self.ui.HEIGHT), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.76, output, 0.24, 0, output)
        state = "PAUSED" if paused else "SWING REPLAY"
        self.ui.text(output, state, (25, 42), 0.95, thickness=2)
        self.ui.text(output, f"{speed:.2f}x   FRAME {frame_index + 1}", (25, 76), 0.55, self.ui.theme.muted, 1)
        if abs(frame_index - impact_index) <= 1:
            self.ui.text(output, "IMPACT", (1070, 50), 0.8, self.ui.theme.warning, 2)
        legend = "SPACE pause  ,/. frame  LEFT/RIGHT seek  +/- speed  Z zoom  R restart  ESC skip"
        self.ui.text(output, legend, (25, 685), 0.47, self.ui.theme.muted, 1)
        return output

    def play(self, frames: list[np.ndarray], impact_index: int, fps: float,
             replay_count: int | None = None) -> ReplayResult:
        if not frames:
            return ReplayResult.SKIPPED
        fps = max(1.0, fps)
        start = max(0, impact_index - int(fps * self.config.replay_start_before_impact))
        end = min(len(frames) - 1, impact_index + int(fps * self.config.replay_end_after_impact))
        if end <= start:
            start, end = 0, len(frames) - 1
        speed = max(0.05, self.config.replay_speed)
        zoom = 1.0
        paused = False
        index = start
        pass_number = 0
        passes = replay_count if replay_count is not None else self.config.replay_count
        auto_pause_remaining = self.config.auto_pause_at_impact
        last_advance = time.monotonic()
        while pass_number < max(1, passes):
            delay = 1.0 / (fps * speed)
            key = self.ui.show(
                self._render(frames[index], index, impact_index, speed, paused, zoom), 10
            )
            if key == 27:
                return ReplayResult.SKIPPED
            if key == 32:
                paused = not paused
                last_advance = time.monotonic()
            elif key in (ord(","), ord("<")):
                paused = True
                index = max(start, index - 1)
            elif key in (ord("."), ord(">")):
                paused = True
                index = min(end, index + 1)
            elif key in (63234, 2424832, 81):
                index = max(start, index - max(1, int(fps / 2)))
            elif key in (63235, 2555904, 83):
                index = min(end, index + max(1, int(fps / 2)))
            elif key in (ord("+"), ord("=")):
                speed = min(2.0, speed * 2)
            elif key in (ord("-"), ord("_")):
                speed = max(0.05, speed / 2)
            elif key in (ord("z"), ord("Z")):
                zoom = {1.0: 1.5, 1.5: 2.0}.get(zoom, 1.0)
            elif key in (ord("r"), ord("R")):
                index = start
                pass_number = 0
                paused = False
            now = time.monotonic()
            if not paused and now - last_advance >= delay:
                if auto_pause_remaining and index < impact_index <= index + 1:
                    index = impact_index
                    paused = True
                    auto_pause_remaining = False
                elif index >= end:
                    pass_number += 1
                    index = start
                else:
                    index += 1
                last_advance = now
        return ReplayResult.COMPLETE
