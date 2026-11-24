import threading


class ProgressStore:
    """Per-run, per-clause current step. In memory only: lost on restart (Q7)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._steps: dict[str, dict[str, str]] = {}

    def set(self, run_id: str, clause_id: str, step: str) -> None:
        with self._lock:
            self._steps.setdefault(run_id, {})[clause_id] = step

    def get(self, run_id: str) -> dict[str, str]:
        with self._lock:
            return dict(self._steps.get(run_id, {}))

    def clear(self, run_id: str) -> None:
        with self._lock:
            self._steps.pop(run_id, None)
