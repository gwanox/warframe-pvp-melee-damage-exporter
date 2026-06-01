"""Typed data models shared across the exporter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

@dataclass
class PackageDoc:
    path: Path
    packages: list[dict[str, Any]]
    package_id: str
    first_value: dict[str, Any]
    value: dict[str, Any]


@dataclass
class WeaponInfo:
    doc: PackageDoc
    weapon_id: str
    weapon_name: str
    category: str
    tree_ref: str
    base_damage: float
    pvp_multiplier: float
    attack_data: dict[str, Any]


@dataclass
class StanceInfo:
    doc: PackageDoc
    stance_id: str
    tree_package: str | None
    compatibility_tags: set[str]
    stance_name: str
    is_actual: bool
