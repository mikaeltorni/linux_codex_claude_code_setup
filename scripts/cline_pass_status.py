#!/usr/bin/env python3
"""Render authenticated Cline Pass rolling usage for a terminal status row.

The Cline API stores credit amounts as micro-dollars. This helper follows the
CLI's own conversion, computes the 5-hour, 7-day, and 30-day rolling windows,
and caches only the rendered non-secret line. TUI stdout is never used for
diagnostics; best-effort logging is file-only through ``logging_utils``.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from logging_utils import get_logger, log_call


LOGGER = get_logger("cline_pass_status", "cline-pass-status.log")
API_BASE_URL = "https://api.cline.bot"
MICRO_DOLLARS = 1_000_000
CACHE_TTL_SECONDS = 60
WINDOWS = (
    ("5h", timedelta(hours=5), "last5HoursUsageCostUSDPerUser"),
    ("7d", timedelta(days=7), "last7daysUsageCostUSDPerUser"),
    ("30d", timedelta(days=30), "last30daysUsageCostUSDPerUser"),
)


class Credentials:
    """Secret Cline OAuth values with an intentionally redacted repr."""

    __slots__ = ("access_token", "refresh_token", "expires_at")

    def __init__(self, access_token: str, refresh_token: str, expires_at: float) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at

    def __repr__(self) -> str:
        return "Credentials(<redacted>)"


def _provider_settings(stored: dict[str, Any]) -> dict[str, Any]:
    """Return the persisted Cline Pass provider settings, if present."""
    providers = stored.get("providers")
    if not isinstance(providers, dict):
        return {}
    entry = providers.get("cline-pass")
    if not isinstance(entry, dict):
        return {}
    settings = entry.get("settings")
    return settings if isinstance(settings, dict) else {}


def extract_credentials(stored: dict[str, Any]) -> Credentials:
    """Extract Cline Pass OAuth credentials using Cline's API-key formatting."""
    settings = _provider_settings(stored)
    auth = settings.get("auth")
    if not isinstance(auth, dict):
        raise ValueError("Cline Pass is not authenticated")
    access = str(auth.get("accessToken") or "").strip()
    refresh = str(auth.get("refreshToken") or "").strip()
    if not access or not refresh:
        raise ValueError("Cline Pass credentials are incomplete")
    if not access.lower().startswith("workos:"):
        access = f"workos:{access}"
    expires_at = float(auth.get("expiresAt") or 0) / 1000
    return Credentials(access, refresh, expires_at)


def _parse_time(value: Any) -> datetime | None:
    """Parse a Cline ISO timestamp into an aware UTC datetime."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _money(micro_dollars: float, *, cap: bool = False) -> str:
    """Format Cline credit micro-dollars as USD."""
    dollars = micro_dollars / MICRO_DOLLARS
    if cap and dollars >= 100:
        return f"${dollars:,.0f}"
    return f"${dollars:,.2f}"


def _compact_money(micro_dollars: float) -> str:
    """Format micro-dollars with compact suffixes for narrow terminals."""
    dollars = micro_dollars / MICRO_DOLLARS
    if dollars >= 1_000:
        value = dollars / 1_000
        return f"${value:g}k"
    if dollars >= 10:
        return f"${dollars:,.0f}"
    return f"${dollars:g}"


def _duration(delta: timedelta) -> str:
    """Format a positive duration compactly for a one-row status display."""
    seconds = max(0, int(delta.total_seconds()))
    days, remainder = divmod(seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes = remainder // 60
    if days:
        return f"{days}d" if not hours else f"{days}d{hours}h"
    if hours:
        return f"{hours}h" if not minutes else f"{hours}h{minutes}m"
    return f"{max(1, minutes)}m"


def _thresholds(plan: dict[str, Any]) -> dict[str, float]:
    """Extract Cline Pass rolling caps from a current-plan response."""
    current: Any = plan
    for key in ("plan", "entitlements", "cline_pass", "inferenceCapThreshold"):
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    if not isinstance(current, dict):
        return {}
    return {
        key: float(value)
        for key, value in current.items()
        if isinstance(value, (int, float)) and value > 0
    }


def format_status_line(
    plan: dict[str, Any],
    usages: list[dict[str, Any]],
    now: datetime,
    width: int | None = None,
) -> str:
    """Render 5h, 7d, and 30d Cline Pass rolling consumption."""
    now = now.astimezone(timezone.utc)
    thresholds = _thresholds(plan)
    segments: list[str] = []
    for label, window, threshold_key in WINDOWS:
        cap = thresholds.get(threshold_key)
        if not cap:
            continue
        cutoff = now - window
        included: list[tuple[datetime, float]] = []
        for usage in usages:
            created = _parse_time(usage.get("createdAt"))
            cost = usage.get("costUsd")
            if created and created > cutoff and isinstance(cost, (int, float)) and cost > 0:
                included.append((created, float(cost)))
        spent = sum(cost for _, cost in included)
        percent = spent / cap * 100
        next_release = (
            f" next {_duration(min(created for created, _ in included) + window - now)}"
            if included
            else ""
        )
        if width is not None and width < 75:
            segments.append(f"{label} {percent:.1f}%")
        elif width is not None and width < 130:
            segments.append(
                f"{label} {percent:.1f}% {_compact_money(spent)}/{_compact_money(cap)}"
            )
        else:
            segments.append(
                f"{label} {_money(spent)}/{_money(cap, cap=True)} {percent:.1f}%{next_release}"
            )
    if len(segments) != len(WINDOWS):
        raise ValueError("Cline Pass rolling limits are unavailable")
    if width is not None and width < 75:
        return "CP " + " | ".join(segments)
    if width is not None and width < 130:
        return "ClinePass " + " | ".join(segments)
    return "Cline Pass  " + "  |  ".join(segments)


def _request_json(
    endpoint: str, *, token: str | None = None, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Make a secret-safe Cline API request and unwrap its data envelope."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{API_BASE_URL}{endpoint}",
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers=headers,
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Cline API returned an invalid response")
    if isinstance(payload.get("success"), bool):
        if not payload["success"] or not isinstance(payload.get("data"), dict):
            raise ValueError("Cline API request failed")
        return payload["data"]
    return payload


def _atomic_json(path: Path, payload: dict[str, Any], mode: int = 0o600) -> None:
    """Atomically write private JSON state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    temporary.chmod(mode)
    os.replace(temporary, path)


def _refresh_credentials(
    stored: dict[str, Any], settings_path: Path, credentials: Credentials
) -> Credentials:
    """Refresh expired OAuth credentials and preserve unrelated provider data."""
    response = _request_json(
        "/api/v1/auth/refresh",
        body={"refreshToken": credentials.refresh_token, "grantType": "refresh_token"},
    )
    access = str(response.get("accessToken") or "").strip()
    refresh = str(response.get("refreshToken") or credentials.refresh_token).strip()
    expires = _parse_time(response.get("expiresAt"))
    if not access or not refresh or expires is None:
        raise ValueError("Cline token refresh response was incomplete")
    settings = _provider_settings(stored)
    auth = settings.setdefault("auth", {})
    if not isinstance(auth, dict):
        raise ValueError("Cline Pass auth settings are invalid")
    auth.update(
        {
            "accessToken": access,
            "refreshToken": refresh,
            "expiresAt": int(expires.timestamp() * 1000),
        }
    )
    _atomic_json(settings_path, stored)
    normalized = access if access.lower().startswith("workos:") else f"workos:{access}"
    return Credentials(normalized, refresh, expires.timestamp())


def _fetch_line(settings_path: Path, width: int | None) -> str:
    """Fetch plan and usage data using the persisted Cline Pass account."""
    stored = json.loads(settings_path.read_text(encoding="utf-8"))
    if not isinstance(stored, dict):
        raise ValueError("Cline provider settings are invalid")
    credentials = extract_credentials(stored)
    if credentials.expires_at <= time.time() + 300:
        credentials = _refresh_credentials(stored, settings_path, credentials)
    plan = _request_json("/api/v1/users/me/plan", token=credentials.access_token)
    user = _request_json("/api/v1/users/me", token=credentials.access_token)
    user_id = str(user.get("id") or "").strip()
    if not user_id:
        raise ValueError("Cline account response has no user id")
    usage_response = _request_json(
        f"/api/v1/users/{urllib.parse.quote(user_id, safe='')}/usages",
        token=credentials.access_token,
    )
    items = usage_response.get("items")
    usages = [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    return format_status_line(plan, usages, datetime.now(timezone.utc), width=width)


def _cached_line(cache_path: Path, *, fresh_only: bool, width: int | None = None) -> str:
    """Read the cached non-secret status line."""
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        age = time.time() - float(cache.get("fetchedAt") or 0)
        line = str(cache.get("line") or "")
        same_width = cache.get("width") == width
        return line if line and (not fresh_only or (same_width and age < CACHE_TTL_SECONDS)) else ""
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return ""


@log_call(LOGGER)
def render_status(
    settings_path: Path,
    cache_path: Path,
    force: bool = False,
    width: int | None = None,
) -> str:
    """Return a cached or freshly fetched line without logging credentials."""
    if not force:
        cached = _cached_line(cache_path, fresh_only=True, width=width)
        if cached:
            return cached
    try:
        line = _fetch_line(settings_path, width)
        _atomic_json(
            cache_path, {"fetchedAt": time.time(), "line": line, "width": width}
        )
        return line
    except (OSError, ValueError, KeyError, urllib.error.URLError, json.JSONDecodeError) as error:
        LOGGER.warning("Cline Pass status refresh failed: %s", error)
        return _cached_line(cache_path, fresh_only=False)


def _is_enabled(settings_path: Path) -> bool:
    """Return whether an authenticated Cline Pass provider is configured."""
    try:
        stored = json.loads(settings_path.read_text(encoding="utf-8"))
        extract_credentials(stored)
        return stored.get("lastUsedProvider") == "cline-pass"
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return False


def main(argv: list[str] | None = None) -> int:
    """Print a Cline Pass status line, or probe whether the row applies."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--enabled", action="store_true")
    parser.add_argument("--width", type=int, default=None)
    parser.add_argument(
        "--settings",
        type=Path,
        default=Path.home() / ".cline/data/settings/providers.json",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        / "linux_codex_claude_code_setup/cline-pass-status.json",
    )
    args = parser.parse_args(argv)
    if args.enabled:
        return 0 if _is_enabled(args.settings) else 1
    line = render_status(args.settings, args.cache, force=args.refresh, width=args.width)
    if line:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
