"""Human-readable weapon, category, and stance labels."""

from __future__ import annotations

import re

from .constants import (
    CANONICAL_WEAPON_CATEGORIES,
    CATEGORY_KEYWORDS,
    EMBEDDED_NO_STANCE_TREES,
    PVP_STANCE_NAMES_BY_BASENAME,
    SPECIAL_STANCE_NAMES_BY_BASENAME,
    VARIANT_STANCE_CATEGORIES_BY_BASENAME,
    WEAPON_CATEGORY_OVERRIDES,
    WEAPON_NAME_OVERRIDES,
)
from .models import PackageDoc
from .utils import clean_label

def clean_weapon_category(raw: str) -> str:
    label = clean_label(raw)
    label = re.sub(r"\s+Category$", "", label).strip()
    if label in CANONICAL_WEAPON_CATEGORIES:
        return CANONICAL_WEAPON_CATEGORIES[label]

    searchable = label.lower().replace("-", " ")
    searchable = re.sub(r"\bmelee\s+tree\b", " ", searchable)
    searchable = re.sub(r"\bcategory\b", " ", searchable)
    searchable = re.sub(r"\s+", " ", searchable).strip()
    for keyword, category in CATEGORY_KEYWORDS:
        if keyword in searchable:
            return category
    return label


def ignored_ai_weapon_basename(name: str) -> bool:
    return bool(re.match(r"^(?:AI|Ai)[A-Z]", name))


def best_effort_weapon_name(value: dict[str, Any], weapon_id: str) -> str:
    if weapon_id in WEAPON_NAME_OVERRIDES:
        return WEAPON_NAME_OVERRIDES[weapon_id]
    for key in ("Icon", "LocalizeTag"):
        label = clean_label(str(value.get(key, "")))
        if label:
            return label
    return clean_label(weapon_id) or weapon_id


def category_from_tree(tree_doc: PackageDoc | None, weapon_doc: PackageDoc) -> str:
    if weapon_doc.package_id in WEAPON_CATEGORY_OVERRIDES:
        return WEAPON_CATEGORY_OVERRIDES[weapon_doc.package_id]
    if tree_doc is not None:
        label = clean_weapon_category(str(tree_doc.value.get("ItemCompatibilityLocOverride", "")))
        if label:
            return label
    parts = weapon_doc.package_id.strip("/").split("/")
    try:
        melee_index = parts.index("Melee")
        return clean_weapon_category(parts[melee_index + 1])
    except (ValueError, IndexError):
        return clean_weapon_category(weapon_doc.package_id)

def stance_display_name(stance_id: str) -> str:
    if not stance_id:
        return "base tree"

    embedded_names = {override[2]: override[0] for override in EMBEDDED_NO_STANCE_TREES.values()}
    if stance_id in embedded_names:
        return embedded_names[stance_id]

    stance_basename = stance_id.rsplit("/", 1)[-1]
    if is_variant_stance_id(stance_id):
        return f"{variant_stance_category(stance_basename)} Variant"

    special_name = SPECIAL_STANCE_NAMES_BY_BASENAME.get(stance_basename)
    if special_name is not None:
        return special_name

    stance_name = PVP_STANCE_NAMES_BY_BASENAME.get(stance_basename)
    if stance_name is not None:
        return stance_name

    label = clean_label(stance_id) or stance_id
    return label.replace("Pv P", "PvP")


def is_variant_stance_id(stance_id: str) -> bool:
    stance_basename = stance_id.rsplit("/", 1)[-1]
    return (
        "/StanceVariants/" in stance_id
        or "Variant" in stance_basename
        or "Varant" in stance_basename
    )


def variant_stance_category(stance_basename: str) -> str:
    normalized = stance_basename.replace("Varant", "Variant")
    normalized = normalized.removeprefix("PvP").removeprefix("Variant").removesuffix("Variant")
    normalized = normalized.removesuffix("Xmas").removesuffix("One").removesuffix("Stance")
    return VARIANT_STANCE_CATEGORIES_BY_BASENAME.get(normalized, clean_weapon_category(normalized))
