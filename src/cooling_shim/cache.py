from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path


class JsonCache:
    def __init__(self, cache_path: Path) -> None:
        self.cache_path = cache_path

    def _load(self) -> dict[str, dict[str, object]]:
        if not self.cache_path.exists():
            return {}
        return json.loads(self.cache_path.read_text(encoding="utf-8"))

    def _save(self, payload: dict[str, dict[str, object]]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def get(self, key: str, now_utc: datetime, ttl_seconds: int) -> dict[str, object] | None:
        payload = self._load()
        entry = payload.get(key)
        if entry is None:
            return None

        fetched_at = datetime.fromisoformat(str(entry["fetched_at"]))
        age_seconds = (now_utc.astimezone(timezone.utc) - fetched_at).total_seconds()
        if age_seconds > ttl_seconds:
            return None
        return dict(entry["value"])

    def put(self, key: str, value: dict[str, object], fetched_at: datetime) -> None:
        payload = self._load()
        payload[key] = {
            "fetched_at": fetched_at.astimezone(timezone.utc).isoformat(),
            "value": value,
        }
        self._save(payload)
