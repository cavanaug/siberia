from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Callable
from urllib.parse import quote
from urllib.request import urlopen

from cooling_shim.cache import JsonCache


def default_cache() -> JsonCache:
    return JsonCache(Path.home() / ".cache" / "cooling" / "npm-packuments.json")


def load_packument(
    package_name: str,
    now_utc: datetime,
    ttl_seconds: int,
    cache: JsonCache | None = None,
    fetcher: Callable[[str], bytes] | None = None,
) -> dict[str, object]:
    active_cache = cache or default_cache()
    cached = active_cache.get(package_name, now_utc=now_utc, ttl_seconds=ttl_seconds)
    if cached is not None:
        return cached

    active_fetcher = fetcher or _fetch_url
    url = f"https://registry.npmjs.org/{quote(package_name, safe='')}"
    payload = json.loads(active_fetcher(url).decode("utf-8"))
    active_cache.put(package_name, payload, fetched_at=now_utc)
    return payload


def _fetch_url(url: str) -> bytes:
    with urlopen(url) as response:
        return response.read()
