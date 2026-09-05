"""Prompt loader utility for loading versioned prompts from files."""

from __future__ import annotations

from pathlib import Path

PROMPT_DIR = Path(__file__).parent

_PROMPT_CACHE: dict[str, str] = {}


def load_prompt(name: str) -> str:
    """Load a prompt file by name (without .txt extension)."""
    if name in _PROMPT_CACHE:
        return _PROMPT_CACHE[name]

    path = PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")

    content = path.read_text(encoding="utf-8")
    _PROMPT_CACHE[name] = content
    return content


def get_temporal_prompt() -> str:
    return load_prompt("m27_temporal")


def get_payment_method_prompt() -> str:
    return load_prompt("m27_payment_method")


def get_cohort_prompt() -> str:
    return load_prompt("m27_cohort")


def get_failure_reason_prompt() -> str:
    return load_prompt("m27_failure_reason")


def get_m3_diagnosis_prompt() -> str:
    return load_prompt("m3_diagnosis")


def clear_cache() -> None:
    """Clear the prompt cache (useful for testing)."""
    _PROMPT_CACHE.clear()