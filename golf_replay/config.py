from dataclasses import asdict, dataclass, fields
import json
from pathlib import Path
from typing import Any


@dataclass
class AppConfig:
    camera_index: int = 0
    requested_width: int = 1280
    requested_height: int = 720
    requested_fps: float = 30.0
    pre_impact_seconds: float = 3.0
    post_impact_seconds: float = 1.5
    replay_speed: float = 0.25
    replay_count: int = 2
    replay_start_before_impact: float = 2.5
    replay_end_after_impact: float = 1.25
    auto_pause_at_impact: bool = False
    save_prompt_seconds: float = 5.0
    impact_threshold: float = 0.25
    trigger_cooldown_seconds: float = 4.0
    audio_device: Any = None
    audio_sample_rate: int = 44100
    audio_block_size: int = 1024
    fullscreen: bool = True
    window_name: str = "Golf Swing Replay"

    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        if not path.exists():
            config = cls()
            config.save(path)
            return config
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            allowed = {field.name for field in fields(cls)}
            values = {key: value for key, value in raw.items() if key in allowed}
            return cls(**values)
        except (OSError, ValueError, TypeError) as error:
            print(f"Settings could not be loaded ({error}); using defaults.")
            return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
