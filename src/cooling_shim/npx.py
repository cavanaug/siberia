from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cooling_shim.errors import PolicyError
from cooling_shim.models import PackageRequest


def parse_package_spec(spec: str) -> PackageRequest:
    if spec.startswith("@"):
        name, separator, version = spec[1:].rpartition("@")
        if separator:
            return PackageRequest(package_name=f"@{name}", requested_version=version or None)
        return PackageRequest(package_name=spec, requested_version=None)

    name, separator, version = spec.partition("@")
    if separator:
        return PackageRequest(package_name=name, requested_version=version or None)
    return PackageRequest(package_name=spec, requested_version=None)


def rewrite_package_spec(spec: str, selected_version: str) -> str:
    request = parse_package_spec(spec)
    return f"{request.package_name}@{selected_version}"


def validate_requested_version(
    package_name: str,
    requested_version: str,
    packument: dict[str, object],
    now_utc: datetime,
    min_age_days: int,
) -> str:
    cutoff = now_utc.astimezone(timezone.utc) - timedelta(days=min_age_days)
    time_data = dict(packument.get("time", {}))
    published_at = time_data.get(requested_version)
    if published_at is None:
        raise PolicyError(f"Missing publish time for {package_name}@{requested_version}")

    published = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
    if published > cutoff:
        raise PolicyError(f"Requested version is too new: {package_name}@{requested_version}")
    return requested_version


def rewrite_npm_exec_args(args: tuple[str, ...], selected_version: str) -> tuple[str, ...]:
    rewritten = list(args)
    for index, value in enumerate(rewritten[:-1]):
        if value == "--package":
            rewritten[index + 1] = rewrite_package_spec(rewritten[index + 1], selected_version)
            return tuple(rewritten)
    raise PolicyError("npm exec is missing a --package value")


def select_cooled_version(packument: dict[str, object], now_utc: datetime, min_age_days: int) -> str:
    cutoff = now_utc.astimezone(timezone.utc) - timedelta(days=min_age_days)
    time_data = dict(packument.get("time", {}))
    candidates: list[tuple[datetime, str]] = []

    for version, published_at in time_data.items():
        if version in {"created", "modified"}:
            continue
        published = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
        if published <= cutoff:
            candidates.append((published, version))

    if not candidates:
        raise PolicyError(f"No cooled version is available for {packument.get('name', 'package')}")

    candidates.sort(key=lambda item: item[0])
    return candidates[-1][1]
