"""Initial combo multipliers for heavy attacks and eligible slams."""

from __future__ import annotations

from typing import Any

from .constants import COMBO_MULTIPLIER_ATTACK_CONTEXTS
from .models import WeaponInfo
from .utils import number


def attack_combo_multiplier(weapon: WeaponInfo, combo_context: str) -> float:
    if combo_context in COMBO_MULTIPLIER_ATTACK_CONTEXTS:
        return weapon.initial_heavy_multiplier
    return 1.0


def slam_combo_multiplier(weapon: WeaponInfo, slam: dict[str, Any]) -> float:
    if number(slam.get("CanUseComboMultiplier")) == 1:
        return weapon.initial_heavy_multiplier
    return 1.0


def initial_combo_application_note(
    weapon: WeaponInfo,
    multiplier: float,
    target: str,
) -> str:
    if weapon.initial_combo_count <= 0 or multiplier == 1:
        return ""
    return (
        f"Initial combo {weapon.initial_combo_count} applies a "
        f"{multiplier:g}x combo multiplier to this {target}"
    )
