from dataclasses import dataclass
from enum import Enum, auto
import time
from typing import Optional

import cv2
import numpy as np

from .config import AppConfig


class Action(Enum):
    NONE = auto()
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()
    SELECT = auto()
    BACK = auto()
    QUIT = auto()


def action_for_key(key: int) -> Action:
    if key in (-1, 255):
        return Action.NONE
    if key in (ord("w"), ord("W"), 63232, 2490368, 82):
        return Action.UP
    if key in (ord("s"), ord("S"), 63233, 2621440, 84):
        return Action.DOWN
    if key in (ord("a"), ord("A"), 63234, 2424832, 81):
        return Action.LEFT
    if key in (ord("d"), ord("D"), 63235, 2555904, 83):
        return Action.RIGHT
    if key in (13, 10, 32):
        return Action.SELECT
    if key in (8, 127):
        return Action.BACK
    if key == 27:
        return Action.QUIT
    return Action.NONE


@dataclass
class Theme:
    background: tuple[int, int, int] = (18, 30, 22)
    panel: tuple[int, int, int] = (28, 47, 34)
    selected: tuple[int, int, int] = (42, 126, 74)
    text: tuple[int, int, int] = (245, 245, 240)
    muted: tuple[int, int, int] = (170, 184, 173)
    warning: tuple[int, int, int] = (40, 170, 245)


class OpenCVUI:
    WIDTH = 1280
    HEIGHT = 720

    def __init__(self, config: AppConfig):
        self.config = config
        self.theme = Theme()
        cv2.namedWindow(config.window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(config.window_name, self.WIDTH, self.HEIGHT)
        if config.fullscreen:
            cv2.setWindowProperty(
                config.window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN
            )

    def close(self) -> None:
        cv2.destroyAllWindows()

    def show(self, image: np.ndarray, delay: int = 1) -> int:
        cv2.imshow(self.config.window_name, image)
        return cv2.waitKeyEx(max(1, delay))

    def canvas(self) -> np.ndarray:
        return np.full((self.HEIGHT, self.WIDTH, 3), self.theme.background, np.uint8)

    def text(self, image, value, point, scale=1.0, color=None, thickness=2) -> None:
        cv2.putText(
            image, str(value), point, cv2.FONT_HERSHEY_SIMPLEX, scale,
            color or self.theme.text, thickness, cv2.LINE_AA,
        )

    def title(self, image, value: str, subtitle: str = "") -> None:
        self.text(image, value, (70, 90), 1.45, thickness=3)
        if subtitle:
            self.text(image, subtitle, (72, 130), 0.65, self.theme.muted, 1)

    def menu(self, title: str, options: list[str], subtitle: str = "") -> Optional[int]:
        if not options:
            options = ["BACK"]
        selected = 0
        while True:
            image = self.canvas()
            self.title(image, title, subtitle)
            top = 185
            height = 56
            visible_count = 8
            first = min(max(0, selected - visible_count + 1), max(0, len(options) - visible_count))
            visible = options[first:first + visible_count]
            for row, option in enumerate(visible):
                index = first + row
                y = top + row * height
                if index == selected:
                    cv2.rectangle(image, (65, y - 37), (760, y + 16), self.theme.selected, -1)
                    prefix = ">  "
                else:
                    prefix = "   "
                self.text(image, prefix + option, (85, y), 0.83)
            if len(options) > visible_count:
                self.text(image, f"{selected + 1} / {len(options)}", (850, 205), 0.6, self.theme.muted, 1)
            self.text(image, "W/S or arrows: move    ENTER: select    ESC: back", (70, 680), 0.55, self.theme.muted, 1)
            action = action_for_key(self.show(image, 30))
            if action is Action.UP:
                selected = (selected - 1) % len(options)
            elif action is Action.DOWN:
                selected = (selected + 1) % len(options)
            elif action is Action.SELECT:
                return selected
            elif action in (Action.BACK, Action.QUIT):
                return None

    def message(self, title: str, lines: list[str], wait: bool = True) -> None:
        image = self.canvas()
        self.title(image, title)
        for index, line in enumerate(lines):
            self.text(image, line, (75, 190 + index * 48), 0.72, self.theme.text if index == 0 else self.theme.muted, 1)
        if wait:
            self.text(image, "Press ENTER or ESC to continue", (75, 670), 0.55, self.theme.muted, 1)
            while True:
                if action_for_key(self.show(image, 30)) in (Action.SELECT, Action.QUIT, Action.BACK):
                    return
        else:
            self.show(image, 1)

    def prompt_text(self, title: str, prompt: str) -> Optional[str]:
        value = ""
        while True:
            image = self.canvas()
            self.title(image, title, prompt)
            cv2.rectangle(image, (70, 210), (900, 285), self.theme.panel, -1)
            self.text(image, value + "_", (90, 262), 1.0)
            self.text(image, "Type a name, ENTER to save, ESC to cancel", (70, 680), 0.55, self.theme.muted, 1)
            key = self.show(image, 30)
            if key == 27:
                return None
            if key in (13, 10):
                return value.strip() or None
            if key in (8, 127):
                value = value[:-1]
            elif 32 <= key <= 126 and len(value) < 30:
                value += chr(key)

    def practice_frame(self, frame, user_name: str, club: str, shot_count: int,
                       elapsed: str, mic_level: float, mic_ok: bool, status: str) -> np.ndarray:
        output = cv2.resize(frame, (self.WIDTH, self.HEIGHT))
        overlay = output.copy()
        cv2.rectangle(overlay, (0, 0), (self.WIDTH, 105), (0, 0, 0), -1)
        cv2.rectangle(overlay, (0, 620), (self.WIDTH, self.HEIGHT), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.76, output, 0.24, 0, output)
        self.text(output, user_name.upper(), (28, 42), 0.82)
        self.text(output, club, (28, 82), 0.65, self.theme.muted, 1)
        self.text(output, f"SESSION {elapsed}", (930, 40), 0.58)
        self.text(output, f"SHOT {shot_count}", (1020, 80), 0.75)
        status_color = self.theme.text if status == "READY - HIT WHEN READY" else self.theme.warning
        self.text(output, status, (28, 672), 0.9, status_color, 2)
        mic = "MIC OK" if mic_ok else "MIC OFF - SPACE TO TRIGGER"
        self.text(output, f"{mic}  {mic_level:.3f}    P: previous  C: club  E/ESC: end", (560, 670), 0.47, self.theme.muted, 1)
        return output

    def save_prompt(self, frame, timeout: float) -> bool:
        started = time.monotonic()
        while True:
            remaining = max(0.0, timeout - (time.monotonic() - started))
            output = cv2.resize(frame, (self.WIDTH, self.HEIGHT))
            overlay = output.copy()
            cv2.rectangle(overlay, (240, 245), (1040, 475), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.84, output, 0.16, 0, output)
            self.text(output, "SAVE THIS SWING?", (390, 315), 1.25, thickness=3)
            self.text(output, "S / ENTER  SAVE", (345, 385), 0.85, self.theme.text)
            self.text(output, "D / ESC     DISCARD", (690, 385), 0.85, self.theme.muted)
            self.text(output, f"Returning to READY in {remaining:.1f}s", (455, 438), 0.55, self.theme.muted, 1)
            key = self.show(output, 30)
            if key in (ord("s"), ord("S"), 13, 10):
                return True
            if key in (ord("d"), ord("D"), 27):
                return False
            if remaining <= 0:
                return False
