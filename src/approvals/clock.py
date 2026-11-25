"""Clock abstractions for injectable time control in testing and production."""

from datetime import datetime, timezone
from typing import Protocol


class Clock(Protocol):
    """Protocol for getting current time."""

    def now(self) -> datetime:
        """Return current datetime."""
        ...


class SystemClock:
    """Production clock using real system UTC time."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FakeClock:
    """Deterministic, controllable clock for testing timeouts, expirations, and timestamps."""

    def __init__(self, initial_time: datetime):
        if initial_time.tzinfo is None:
            self._current_time = initial_time.replace(tzinfo=timezone.utc)
        else:
            self._current_time = initial_time

    def now(self) -> datetime:
        return self._current_time

    def set_time(self, new_time: datetime) -> None:
        if new_time.tzinfo is None:
            self._current_time = new_time.replace(tzinfo=timezone.utc)
        else:
            self._current_time = new_time

    def advance(self, **kwargs) -> datetime:
        """Advance time by timedelta kwargs (days, seconds, minutes, hours)."""
        from datetime import timedelta
        self._current_time += timedelta(**kwargs)
        return self._current_time
