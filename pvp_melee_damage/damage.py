"""Damage, quantization, and attack attenuation math."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .constants import DAMAGE_TYPES, MELEE_IMPACT_TYPE, MELEE_SWEEP_TYPES, PHYSICAL_TYPES
from .utils import decimal_number, number, round_half_up_decimal

def find_melee_impact(value: dict[str, Any]) -> tuple[dict[str, Any], float, float] | None:
    for behavior in value.get("Behaviors", []):
        if not isinstance(behavior, dict):
            continue
        is_sweep = (
            behavior.get("fire:Type") in MELEE_SWEEP_TYPES
            or any(key.startswith("fire:") and key.endswith("MeleeSweepFireBehavior") for key in behavior)
        )
        is_impact = (
            behavior.get("impact:Type") == MELEE_IMPACT_TYPE
            or "impact:MeleeImpactBehavior" in behavior
        )
        if not is_sweep or not is_impact:
            continue
        impact = behavior.get("impact:MeleeImpactBehavior", {})
        attack_data = impact.get("AttackData", {})
        if not isinstance(attack_data, dict):
            continue
        return attack_data, number(attack_data.get("Amount")), number(impact.get("PvpDamageMultiplier"), 1.0)
    return None

def is_physical_only(attack_data: dict[str, Any]) -> bool:
    if attack_data.get("Type") != "DT_PHYSICAL":
        return False
    return all(number(attack_data.get(dt)) <= 0 for dt in DAMAGE_TYPES if dt not in PHYSICAL_TYPES)


def physical_fraction(attack_data: dict[str, Any], damage_type: str) -> Decimal:
    amount = decimal_number(attack_data.get("Amount"))
    value = decimal_number(attack_data.get(damage_type))
    if amount > 0 and value > 1:
        return value / amount
    return value


def quant_info(attack_data: dict[str, Any]) -> tuple[str, Decimal, int | None]:
    if not is_physical_only(attack_data):
        return "n/a", Decimal("1"), None

    # Physical damage appears to be quantized by rounded 32nds per IPS type.
    # The common visible shortcuts become 31/32, 1, or 33/32.
    units = 0
    for damage_type in PHYSICAL_TYPES:
        units += round_half_up_decimal(physical_fraction(attack_data, damage_type) * Decimal(32))

    if units == 31:
        return "negative (31/32)", Decimal(31) / Decimal(32), units
    if units == 32:
        return "neutral (1)", Decimal("1"), units
    if units == 33:
        return "positive (33/32)", Decimal(33) / Decimal(32), units
    return f"custom ({units}/32)", Decimal(units) / Decimal(32), units


def attack_level_atten(attack_value: dict[str, Any]) -> float:
    pvp_props = attack_value.get("PvpAttackProperties", {})
    attack_props = attack_value.get("AttackProperties", {})
    if isinstance(pvp_props, dict) and "BaseDamageAtten" in pvp_props:
        return number(pvp_props.get("BaseDamageAtten"), 1.0)
    if isinstance(attack_props, dict) and "BaseDamageAtten" in attack_props:
        return number(attack_props.get("BaseDamageAtten"), 1.0)
    return 1.0


def swing_atten(attack_value: dict[str, Any], swing: dict[str, Any] | None) -> float:
    base = attack_level_atten(attack_value)
    if not swing or swing.get("overrideAttackProperties") != 1:
        return base

    pvp_props = swing.get("pvpAttackProperties", {})
    attack_props = swing.get("attackProperties", {})
    if isinstance(pvp_props, dict) and "BaseDamageAtten" in pvp_props:
        return number(pvp_props.get("BaseDamageAtten"), base)
    if isinstance(attack_props, dict) and "BaseDamageAtten" in attack_props:
        return number(attack_props.get("BaseDamageAtten"), base)
    return base


def calculate_final_damage(base_damage: float, pvp_multiplier: float, atten: float, quant_multiplier: Decimal) -> tuple[int, Decimal]:
    raw = (
        decimal_number(base_damage)
        * decimal_number(pvp_multiplier)
        * decimal_number(atten)
        * quant_multiplier
    )
    return round_half_up_decimal(raw), raw
