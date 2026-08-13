from threading import Lock
import time

from .models import AppState


class StateController:
    """Thread-safe application state and impact-trigger gate."""

    def __init__(self) -> None:
        self._state = AppState.MENU
        self._impact_at: float | None = None
        self._last_trigger_at = 0.0
        self._lock = Lock()

    @property
    def state(self) -> AppState:
        with self._lock:
            return self._state

    def transition(self, state: AppState) -> None:
        with self._lock:
            self._state = state
            if state is not AppState.READY:
                self._impact_at = None

    def request_impact(self, cooldown_seconds: float, now: float | None = None) -> bool:
        timestamp = time.monotonic() if now is None else now
        with self._lock:
            if self._state is not AppState.READY:
                return False
            if timestamp - self._last_trigger_at < cooldown_seconds:
                return False
            self._last_trigger_at = timestamp
            self._impact_at = timestamp
            return True

    def consume_impact(self) -> float | None:
        with self._lock:
            impact_at = self._impact_at if self._state is AppState.READY else None
            self._impact_at = None
            return impact_at
