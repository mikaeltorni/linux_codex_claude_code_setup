"""Tests for the authenticated Cline Pass rolling-limit status helper."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "cline_pass_status.py"


def load_module():
    """Load the repository-local Cline Pass helper."""
    spec = importlib.util.spec_from_file_location("cline_pass_status", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_formats_all_three_rolling_pass_limits() -> None:
    """The row should include spend, cap, percent, and release for every cap."""
    module = load_module()
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    plan = {
        "plan": {
            "entitlements": {
                "cline_pass": {
                    "inferenceCapThreshold": {
                        "last5HoursUsageCostUSDPerUser": 1_000_000_000,
                        "last7daysUsageCostUSDPerUser": 2_500_000_000,
                        "last30daysUsageCostUSDPerUser": 5_000_000_000,
                    }
                }
            }
        }
    }
    usages = [
        {"costUsd": 25_000_000, "createdAt": "2026-06-30T10:00:00Z"},
        {"costUsd": 75_000_000, "createdAt": "2026-06-26T12:00:00Z"},
        {"costUsd": 150_000_000, "createdAt": "2026-06-10T12:00:00Z"},
    ]

    line = module.format_status_line(plan, usages, now)

    assert line.startswith("Cline Pass")
    assert "5h $25.00/$1,000 2.5% next 3h" in line
    assert "7d $100.00/$2,500 4.0% next 3d" in line
    assert "30d $250.00/$5,000 5.0% next 10d" in line


def test_ignores_usage_outside_each_rolling_window() -> None:
    """Each displayed numerator must be computed from its own rolling window."""
    module = load_module()
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    plan = {
        "plan": {
            "entitlements": {
                "cline_pass": {
                    "inferenceCapThreshold": {
                        "last5HoursUsageCostUSDPerUser": 1_000_000,
                        "last7daysUsageCostUSDPerUser": 2_000_000,
                        "last30daysUsageCostUSDPerUser": 4_000_000,
                    }
                }
            }
        }
    }
    usages = [
        {"costUsd": 500_000, "createdAt": "2026-06-30T11:00:00Z"},
        {"costUsd": 500_000, "createdAt": "2026-06-29T11:00:00Z"},
        {"costUsd": 1_000_000, "createdAt": "2026-06-01T11:59:59Z"},
        {"costUsd": 9_000_000, "createdAt": "2026-05-01T00:00:00Z"},
    ]

    line = module.format_status_line(plan, usages, now)

    assert "5h $0.50/$1.00 50.0%" in line
    assert "7d $1.00/$2.00 50.0%" in line
    assert "30d $2.00/$4.00 50.0%" in line


def test_compacts_all_three_limits_for_an_eighty_column_terminal() -> None:
    """Narrow terminals should retain every window instead of clipping 5h."""
    module = load_module()
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    plan = {
        "plan": {
            "entitlements": {
                "cline_pass": {
                    "inferenceCapThreshold": {
                        "last5HoursUsageCostUSDPerUser": 1_000_000_000,
                        "last7daysUsageCostUSDPerUser": 2_500_000_000,
                        "last30daysUsageCostUSDPerUser": 5_000_000_000,
                    }
                }
            }
        }
    }
    usages = [{"costUsd": 90_000_000, "createdAt": "2026-06-30T11:00:00Z"}]

    line = module.format_status_line(plan, usages, now, width=80)

    assert len(line) <= 80
    assert "5h 9.0% $90/$1k" in line
    assert "7d 3.6% $90/$2.5k" in line
    assert "30d 1.8% $90/$5k" in line


def test_extracts_cline_pass_credentials_without_exposing_them() -> None:
    """Credential parsing should select cline-pass and apply Cline's prefix."""
    module = load_module()
    stored = {
        "lastUsedProvider": "cline-pass",
        "providers": {
            "cline-pass": {
                "settings": {
                    "provider": "cline-pass",
                    "auth": {
                        "accessToken": "secret-access",
                        "refreshToken": "secret-refresh",
                        "expiresAt": 1_800_000_000_000,
                    },
                }
            }
        },
    }

    credentials = module.extract_credentials(stored)

    assert credentials.access_token == "workos:secret-access"
    assert credentials.refresh_token == "secret-refresh"
    assert "secret" not in repr(credentials)
