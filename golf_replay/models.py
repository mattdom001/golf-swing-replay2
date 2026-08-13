from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Optional
from uuid import uuid4


class AppState(Enum):
    MENU = auto()
    READY = auto()
    CAPTURING = auto()
    REPLAYING = auto()
    POST_REPLAY = auto()
    SESSION_SUMMARY = auto()
    EXITING = auto()


def new_id() -> str:
    return uuid4().hex


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class User:
    id: str
    name: str
    created_at: str = field(default_factory=now_iso)

    @classmethod
    def create(cls, name: str) -> "User":
        return cls(id=new_id(), name=name.strip())

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "User":
        return cls(**value)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Session:
    id: str
    user_id: Optional[str]
    user_name: str
    started_at: str = field(default_factory=now_iso)
    ended_at: Optional[str] = None
    shot_count: int = 0
    saved_count: int = 0
    shots_by_club: dict[str, int] = field(default_factory=dict)

    @classmethod
    def create(cls, user: Optional[User]) -> "Session":
        return cls(
            id=new_id(),
            user_id=user.id if user else None,
            user_name=user.name if user else "Quick Practice",
        )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Session":
        return cls(**value)

    def record_shot(self, club: str) -> int:
        self.shot_count += 1
        self.shots_by_club[club] = self.shots_by_club.get(club, 0) + 1
        return self.shot_count

    def finish(self) -> None:
        if self.ended_at is None:
            self.ended_at = now_iso()

    def duration_seconds(self) -> int:
        end = datetime.fromisoformat(self.ended_at) if self.ended_at else datetime.now().astimezone()
        start = datetime.fromisoformat(self.started_at)
        return max(0, int((end - start).total_seconds()))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SavedSwing:
    id: str
    session_id: str
    user_id: Optional[str]
    user_name: str
    club: str
    shot_number: int
    captured_at: str
    video_path: str
    impact_frame: int
    fps: float
    camera_angle: str = "Unspecified"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SavedSwing":
        return cls(**value)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_CLUBS = [
    "DRIVER", "3 WOOD", "5 IRON", "6 IRON", "7 IRON", "8 IRON",
    "9 IRON", "PW", "GW", "SW", "OTHER",
]
