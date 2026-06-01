"""Small generic helpers for labels, rounding, rows, and warnings."""

from __future__ import annotations

import copy
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from .constants import (
    CATEGORY_LIMITED_DAMAGE_COMBO_CONTEXTS,
    COMBO_CONTEXT_LABELS,
    IGNORED_DAMAGE_COMBO_CONTEXTS,
    SEVERITY_ORDER,
)

def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def decimal_number(value: Any) -> Decimal:
    return Decimal(str(number(value)))


def round_half_up_decimal(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_HALF_UP))

def clean_label(raw: str) -> str:
    raw = raw.strip().replace("\\", "/").split("/")[-1]
    raw = re.sub(r"\.(png|jpg|jpeg|tga|webp)$", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"(Name|Desc)$", "", raw)
    raw = re.sub(r"^(Tno|Tenno)(?=[A-Z])", "", raw)
    raw = raw.replace("_", " ").replace("-", " ")
    raw = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", raw)
    raw = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw or ""

def combine_notes(*notes: str) -> str:
    seen: set[str] = set()
    combined: list[str] = []
    for note in notes:
        if note and note not in seen:
            combined.append(note)
            seen.add(note)
    return "; ".join(combined)


def combo_context_label(combo_context: Any) -> str:
    context = str(combo_context or "")
    if not context:
        return ""
    return COMBO_CONTEXT_LABELS.get(context, clean_label(context.replace("CC_", "")) or context)


def combo_context_allowed_for_category(combo_context: Any, weapon_category: str) -> bool:
    allowed_categories = CATEGORY_LIMITED_DAMAGE_COMBO_CONTEXTS.get(str(combo_context or ""))
    return allowed_categories is None or weapon_category in allowed_categories


def split_note_parts(note: Any) -> list[str]:
    return [part.strip() for part in str(note or "").split(";") if part.strip()]

def rows_to_matrix(headers: list[str], rows: list[dict[str, Any]]) -> list[list[Any]]:
    return [[row.get(header, "") for header in headers] for row in rows]


def sorted_warnings(warnings: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        warnings,
        key=lambda row: (
            SEVERITY_ORDER.get(str(row.get("severity", "")), 99),
            str(row.get("severity", "")),
            str(row.get("ref", "")),
            str(row.get("message", "")),
        ),
    )


def get_or_create_key(
    mapping: dict[tuple[Any, ...], int],
    rows: list[dict[str, Any]],
    key: tuple[Any, ...],
    make_row: Any,
) -> int:
    if key not in mapping:
        mapping[key] = len(mapping) + 1
        rows.append(make_row(mapping[key]))
    return mapping[key]
