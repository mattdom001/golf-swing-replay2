from collections import deque
from dataclasses import dataclass
from pathlib import Path
import shutil
import time
from typing import Optional

import cv2
import numpy as np
import sounddevice as sd

from .config import AppConfig
from .state import StateController


@dataclass
class CapturedSwing:
    frames: list[np.ndarray]
    impact_index: int
    fps: float
    captured_at: str


class AudioImpactDetector:
    def __init__(self, config: AppConfig, state: StateController):
        self.config = config
        self.state = state
        self.level = 0.0
        self.stream: Optional[sd.InputStream] = None
        self.error: Optional[str] = None

    @property
    def healthy(self) -> bool:
        return self.stream is not None and self.stream.active

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            self.error = str(status)
        self.level = float(np.max(np.abs(indata))) if len(indata) else 0.0
        if self.level >= self.config.impact_threshold:
            self.state.request_impact(self.config.trigger_cooldown_seconds)

    def start(self) -> None:
        try:
            self.stream = sd.InputStream(
                device=self.config.audio_device,
                channels=1,
                samplerate=self.config.audio_sample_rate,
                blocksize=self.config.audio_block_size,
                callback=self._callback,
            )
            self.stream.start()
            self.error = None
        except Exception as error:
            self.stream = None
            self.error = str(error)
            print(f"Microphone unavailable: {error}. Space bar trigger remains available.")

    def close(self) -> None:
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            finally:
                self.stream = None


class CameraCapture:
    def __init__(self, config: AppConfig):
        self.config = config
        self.camera: Optional[cv2.VideoCapture] = None
        self.width = config.requested_width
        self.height = config.requested_height
        self.fps = config.requested_fps
        self.last_error: Optional[str] = None
        self.buffer: deque[tuple[float, np.ndarray]] = deque()

    @property
    def healthy(self) -> bool:
        return self.camera is not None and self.camera.isOpened()

    def open(self) -> bool:
        self.camera = cv2.VideoCapture(self.config.camera_index)
        if not self.camera.isOpened():
            self.last_error = f"Could not open camera {self.config.camera_index}"
            return False
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.requested_width)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.requested_height)
        self.camera.set(cv2.CAP_PROP_FPS, self.config.requested_fps)
        self.width = int(self.camera.get(cv2.CAP_PROP_FRAME_WIDTH)) or self.config.requested_width
        self.height = int(self.camera.get(cv2.CAP_PROP_FRAME_HEIGHT)) or self.config.requested_height
        reported_fps = float(self.camera.get(cv2.CAP_PROP_FPS))
        self.fps = reported_fps if reported_fps > 1 else self.config.requested_fps
        max_frames = max(1, int(self.fps * self.config.pre_impact_seconds * 1.25))
        self.buffer = deque(maxlen=max_frames)
        self.last_error = None
        return True

    def read(self, buffer_frame: bool = True) -> tuple[bool, Optional[np.ndarray], float]:
        if self.camera is None:
            return False, None, time.monotonic()
        ok, frame = self.camera.read()
        timestamp = time.monotonic()
        if not ok:
            self.last_error = "Camera frame lost"
            return False, None, timestamp
        self.last_error = None
        if buffer_frame:
            self.buffer.append((timestamp, frame.copy()))
        return True, frame, timestamp

    def capture_after_impact(self, impact_at: float, draw_callback=None) -> CapturedSwing:
        from datetime import datetime

        buffered = list(self.buffer)
        frames = [frame for _, frame in buffered]
        measured_fps = self.fps
        if len(buffered) > 2:
            elapsed = buffered[-1][0] - buffered[0][0]
            if elapsed > 0:
                estimate = (len(buffered) - 1) / elapsed
                if 1.0 <= estimate <= 500.0:
                    measured_fps = estimate
        if buffered:
            impact_index = min(
                range(len(buffered)), key=lambda index: abs(buffered[index][0] - impact_at)
            )
        else:
            impact_index = 0
        deadline = time.monotonic() + self.config.post_impact_seconds
        while time.monotonic() < deadline:
            ok, frame, _ = self.read(buffer_frame=False)
            if not ok or frame is None:
                time.sleep(0.01)
                continue
            frames.append(frame.copy())
            if draw_callback:
                draw_callback(frame)
        return CapturedSwing(
            frames=frames,
            impact_index=impact_index,
            fps=measured_fps,
            captured_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )

    def clear_buffer(self) -> None:
        self.buffer.clear()

    def close(self) -> None:
        if self.camera is not None:
            self.camera.release()
            self.camera = None


def save_video(frames: list[np.ndarray], path: Path, fps: float) -> Path:
    if not frames:
        raise ValueError("Cannot save an empty swing")
    path.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(path.parent).free < 100 * 1024 * 1024:
        raise OSError("Less than 100 MB of free disk space remains")
    height, width = frames[0].shape[:2]
    # AVFoundation usually offers H.264, while FFmpeg OpenCV builds commonly
    # offer mp4v. MJPEG/AVI is a larger but dependable local fallback.
    attempts = [(path, "avc1"), (path, "mp4v"), (path.with_suffix(".avi"), "MJPG")]
    for output_path, codec in attempts:
        if output_path.exists():
            output_path.unlink()
        writer = cv2.VideoWriter(
            str(output_path), cv2.VideoWriter_fourcc(*codec), fps, (width, height)
        )
        if not writer.isOpened():
            writer.release()
            continue
        for frame in frames:
            if frame.shape[1] != width or frame.shape[0] != height:
                frame = cv2.resize(frame, (width, height))
            writer.write(frame)
        writer.release()
        verification = cv2.VideoCapture(str(output_path))
        readable, _ = verification.read()
        verification.release()
        if readable:
            return output_path
        if output_path.exists():
            output_path.unlink()
    raise OSError(f"No available OpenCV encoder could create {path}")


def load_video(path: Path) -> tuple[list[np.ndarray], float]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise OSError(f"Could not open {path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS)) or 30.0
    frames: list[np.ndarray] = []
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            frames.append(frame)
    finally:
        capture.release()
    return frames, fps
