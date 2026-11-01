"""Single source of time. Every timestamp in the app comes from clock.now()."""
import time
from datetime import datetime, timedelta, timezone


class Clock:
    def __init__(self):
        self._real0 = time.time()
        self._sim0 = datetime.fromtimestamp(self._real0, timezone.utc)
        self.speed = 1.0

    def now(self) -> datetime:
        return self._sim0 + timedelta(seconds=(time.time() - self._real0) * self.speed)

    def set(self, sim_time: datetime | None = None, speed: float | None = None):
        cur = self.now()
        self._real0 = time.time()
        self._sim0 = (sim_time if sim_time is not None else cur).astimezone(timezone.utc)
        if speed is not None:
            self.speed = float(speed)

    def iso(self) -> str:
        return self.now().isoformat(timespec="seconds").replace("+00:00", "Z")


clock = Clock()
