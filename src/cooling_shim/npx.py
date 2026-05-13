from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cooling_shim.errors import PolicyError
from cooling_shim.models import PackageRequest


FLAGS_REQUIRING_VALUES = frozenset({
    "--cache",
    "-c",
    "--userconfig",
    "--call",
    "-p",
    "--shell",
})


def parse_package_spec(spec: str) -> PackageRequest:
    if not spec:
        raise PolicyError("Package spec must not be empty")

    if spec.startswith("@"):
        name, separator, version = spec[1:].rpartition("@")
        if separator:
            return PackageRequest(package_name=f"@{name}", requested_version=version or None)
        return PackageRequest(package_name=spec, requested_version=None)

    name, separator, version = spec.partition("@")
    if separator:
        if not version or not _looks_like_plain_version(version):
            raise PolicyError(f"Unsupported package spec: {spec}")
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


def rewrite_npm_exec_args(
    args: tuple[str, ...],
    selected_versions: dict[str, str],
) -> tuple[str, ...]:
    rewritten = list(args)
    rewritten_any = False

    for index, value in enumerate(rewritten):
        if value == "--package":
            if index + 1 >= len(rewritten):
                raise PolicyError("npm exec is missing a --package value")
            spec = rewritten[index + 1]
            rewritten[index + 1] = rewrite_package_spec(spec, selected_versions[spec])
            rewritten_any = True
            continue

        if value.startswith("--package="):
            spec = value.split("=", 1)[1]
            rewritten[index] = f"--package={rewrite_package_spec(spec, selected_versions[spec])}"
            rewritten_any = True

    if not rewritten_any:
        raise PolicyError("npm exec is missing a --package value")

    return tuple(rewritten)


def package_spec_argument_index(args: tuple[str, ...]) -> int:
    if not args:
        raise PolicyError("npx requires a package name")

    skip_next = False

    for index, value in enumerate(args):
        if skip_next:
            skip_next = False
            continue

        if value == "--":
            break
        if value.startswith("--package="):
            continue
        if value in {"--package", "-p"}:
            skip_next = True
            continue
        if value in FLAGS_REQUIRING_VALUES:
            skip_next = True
            continue
        if value.startswith("-"):
            continue
        return index

    raise PolicyError("npx requires a package name")


def rewrite_npx_args(args: tuple[str, ...], spec_index: int, selected_version: str) -> tuple[str, ...]:
    rewritten = list(args)
    rewritten[spec_index] = rewrite_package_spec(rewritten[spec_index], selected_version)

    for index, value in enumerate(rewritten):
        if value == "--package":
            if index + 1 >= len(rewritten):
                raise PolicyError("npx is missing a --package value")
            rewritten[index + 1] = rewrite_package_spec(rewritten[index + 1], selected_version)
            continue

        if value.startswith("--package="):
            spec = value.split("=", 1)[1]
            rewritten[index] = f"--package={rewrite_package_spec(spec, selected_version)}"

    return tuple(rewritten)


def npm_exec_package_specs(args: tuple[str, ...]) -> tuple[str, ...]:
    specs: list[str] = []

    for index, value in enumerate(args):
        if value == "--package":
            if index + 1 >= len(args):
                raise PolicyError("npm exec is missing a --package value")
            specs.append(args[index + 1])
            continue

        if value.startswith("--package="):
            specs.append(value.split("=", 1)[1])

    if not specs:
        raise PolicyError("npm exec is missing a --package value")

    return tuple(specs)


def _looks_like_plain_version(version: str) -> bool:
    if version.startswith(("^", "~", ">", "<", "=", "*")):
        return False

    pieces = version.split(".")
    if not pieces or any(not piece for piece in pieces):
        return False

    for piece in pieces:
        head = piece.split("-", 1)[0].split("+", 1)[0]
        if not head.isdigit():
            return False

    return True


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
