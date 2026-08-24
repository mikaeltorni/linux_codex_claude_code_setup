#!/usr/bin/env python3
"""Write Codex model-catalog.json for plain qwen/openr CLI homes."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from logging_utils import get_logger

logger = get_logger(__name__, "generate_model_catalog.log")


def load_defaults(defaults_py_path: str | Path) -> dict:
    defaults_py_path = Path(defaults_py_path).resolve()
    parsed: dict = {}
    try:
        source = defaults_py_path.read_text(encoding="utf-8")
        parsed["__file__"] = str(defaults_py_path)
        exec(source, parsed)
        nested = parsed.get("defaults")
        if isinstance(nested, dict):
            parsed.update(nested)
    except OSError as exc:
        logger.warning("Could not read defaults file %s: %s", defaults_py_path, exc)
    except Exception as exc:
        logger.error("Error executing defaults.py: %s", exc)
    return parsed


def resolve_defaults_py_path() -> Path:
    candidates = [
        Path(__file__).resolve().parent.parent / "configs" / "codex_instances" / "defaults.sh",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def _get(key: str, fallback: str = "", defaults: dict | None = None) -> str:
    val = os.environ.get(key)
    if val is not None:
        return val
    if defaults is not None:
        return str(defaults.get(key, fallback))
    return fallback


# Short TUI labels; keep in sync with agent_command_center free OpenRouter defaults.
_KNOWN_DISPLAY_NAMES = {
    "nvidia/nemotron-3-ultra-550b-a55b:free": "Nemotron 3 Ultra (free)",
    "nvidia/nemotron-3-super-120b-a12b:free": "Nemotron 3 Super (free)",
}


def catalog_display_name(base_model: str) -> str:
    """Return a short human label for the Codex model catalog."""
    known = _KNOWN_DISPLAY_NAMES.get(base_model)
    if known:
        return known
    free = base_model.endswith(":free")
    core = base_model[: -len(":free")] if free else base_model
    if "/" in core:
        core = core.split("/", 1)[1]
    label = core.replace("-", " ").replace("_", " ").title()
    if free:
        label = f"{label} (free)"
    return label


def build_model_catalog(base_model: str, context_window: int = 40960) -> dict:
    display_name = catalog_display_name(base_model)
    return {
        "slug": base_model,
        "display_name": display_name,
        "description": "Model catalog entry for the Codex TUI",
        "default_reasoning_level": "high",
        "supported_reasoning_levels": [
            {"effort": "low", "description": "Fast responses with lighter reasoning"},
            {"effort": "medium", "description": "Balances speed and reasoning depth for everyday tasks"},
            {"effort": "high", "description": "Greater reasoning depth for complex problems"},
        ],
        "shell_type": "shell_command",
        "visibility": "list",
        "supported_in_api": True,
        "priority": 0,
        "additional_speed_tiers": [],
        "service_tiers": [],
        "availability_nux": None,
        "upgrade": None,
        "base_instructions": "",
        "supports_reasoning_summaries": True,
        "default_reasoning_summary": "detailed",
        "support_verbosity": False,
        "apply_patch_tool_type": "freeform",
        "web_search_tool_type": "text",
        "truncation_policy": {"mode": "tokens", "limit": 10000},
        "supports_parallel_tool_calls": True,
        "supports_streaming": True,
        "supports_function_calling": True,
        "supports_image_detail_original": True,
        "context_window": context_window,
        "max_context_window": context_window,
        "effective_context_window_percent": 95,
        "experimental_supported_tools": [],
        "input_modalities": ["text", "image"],
        "supports_search_tool": False,
    }


def write_model_catalog(
    codex_home: str | Path,
    base_model: str,
    context_window: int = 40960,
) -> Path:
    codex_home = Path(codex_home)
    out_path = codex_home / "model-catalog.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    catalog = {"models": [build_model_catalog(base_model, context_window)]}
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(catalog, handle, indent=2)
    logger.info("Catalog updated: %s models written to %s", len(catalog["models"]), out_path)
    return out_path


def main() -> int:
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <codex_home> <model_name>", file=sys.stderr)
        return 1

    codex_home = Path(sys.argv[1])
    model_name = sys.argv[2]
    defaults = load_defaults(resolve_defaults_py_path())
    base_model = model_name.split("@")[0]
    context_window_str = os.environ.get(
        "QWEN_CODEX_CONTEXT_WINDOW",
        _get("QWEN_CODEX_CONTEXT_WINDOW", "40960", defaults),
    )
    try:
        context_window = int(context_window_str)
    except ValueError:
        context_window = 40960

    try:
        write_model_catalog(codex_home, base_model, context_window)
        return 0
    except Exception as exc:
        logger.error("Error writing model catalog: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
