import json
from pathlib import Path
from typing import Any, Callable, Generic, TypeVar

from .models import SavedSwing, Session, User

T = TypeVar("T")


class JsonCollection(Generic[T]):
    def __init__(self, path: Path, factory: Callable[[dict[str, Any]], T]):
        self.path = path
        self.factory = factory

    def load(self) -> list[T]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                raise ValueError("expected a JSON list")
            return [self.factory(item) for item in raw]
        except (OSError, ValueError, TypeError, KeyError) as error:
            print(f"Could not load {self.path.name}: {error}")
            return []

    def save(self, values: list[T]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [value.to_dict() for value in values]  # type: ignore[attr-defined]
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)


class LocalStore:
    def __init__(self, root: Path):
        self.root = root
        self.data_dir = root / "data"
        self.saved_swings_dir = root / "saved_swings"
        self.users_store = JsonCollection(self.data_dir / "users.json", User.from_dict)
        self.sessions_store = JsonCollection(self.data_dir / "sessions.json", Session.from_dict)
        self.swings_store = JsonCollection(
            self.data_dir / "saved_swings.json", SavedSwing.from_dict
        )
        self.users = self.users_store.load()
        self.sessions = self.sessions_store.load()
        self.saved_swings = self.swings_store.load()

    def add_user(self, name: str) -> User:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("User name cannot be empty")
        existing = next((u for u in self.users if u.name.lower() == cleaned.lower()), None)
        if existing:
            return existing
        user = User.create(cleaned)
        self.users.append(user)
        self.users_store.save(self.users)
        return user

    def save_session(self, session: Session) -> None:
        for index, existing in enumerate(self.sessions):
            if existing.id == session.id:
                self.sessions[index] = session
                break
        else:
            self.sessions.append(session)
        self.sessions_store.save(self.sessions)

    def add_saved_swing(self, swing: SavedSwing) -> None:
        self.saved_swings.append(swing)
        try:
            self.swings_store.save(self.saved_swings)
        except OSError:
            self.saved_swings.pop()
            raise

    def user_totals(self, user_id: str) -> tuple[int, int, dict[str, int]]:
        sessions = [session for session in self.sessions if session.user_id == user_id]
        clubs: dict[str, int] = {}
        for session in sessions:
            for club, count in session.shots_by_club.items():
                clubs[club] = clubs.get(club, 0) + count
        return sum(s.shot_count for s in sessions), len(sessions), clubs
