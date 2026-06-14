"""Damage, quantization, and attack attenuation math."""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

from .constants import DAMAGE_TYPES, MELEE_IMPACT_TYPE, MELEE_SWEEP_TYPES, PHYSICAL_TYPES
from .utils import decimal_number, number, round_half_up_decimal

ELEMENT_LABELS = {
    "DT_FIRE": "Heat",
    "DT_FREEZE": "Cold",
    "DT_ELECTRICITY": "Electricity",
    "DT_POISON": "Toxin",
    "DT_EXPLOSION": "Blast",
    "DT_RADIATION": "Radiation",
    "DT_GAS": "Gas",
    "DT_MAGNETIC": "Magnetic",
    "DT_VIRAL": "Viral",
    "DT_CORROSIVE": "Corrosive",
    "DT_RADIANT": "Radiant",
    "DT_SENTIENT": "Sentient",
    "DT_CINEMATIC": "Cinematic",
    "DT_SHIELD_DRAIN": "Shield Drain",
    "DT_HEALTH_DRAIN": "Health Drain",
    "DT_ENERGY_DRAIN": "Energy Drain",
    "DT_FINISHER": "Finisher",
}


def is_melee_impact_behavior(behavior: dict[str, Any]) -> bool:
    is_sweep = behavior.get("fire:Type") in MELEE_SWEEP_TYPES or any(
        key.startswith("fire:") and key.endswith("MeleeSweepFireBehavior") for key in behavior
    )
    is_impact = (
        behavior.get("impact:Type") == MELEE_IMPACT_TYPE or "impact:MeleeImpactBehavior" in behavior
    )
    return is_sweep and is_impact


def melee_impact_behaviors(value: dict[str, Any]):
    for behavior in value.get("Behaviors", []):
        if isinstance(behavior, dict) and is_melee_impact_behavior(behavior):
            yield behavior


def find_melee_impact(value: dict[str, Any]) -> tuple[dict[str, Any], float, float] | None:
    for behavior in melee_impact_behaviors(value):
        impact = behavior.get("impact:MeleeImpactBehavior", {})
        attack_data = impact.get("AttackData", {})
        if not isinstance(attack_data, dict):
            continue
        return (
            attack_data,
            number(attack_data.get("Amount")),
            number(impact.get("PvpDamageMultiplier"), 1.0),
        )
    return None


def find_melee_attack_speed(value: dict[str, Any]) -> float | None:
    for behavior in melee_impact_behaviors(value):
        for key, state in behavior.items():
            if not key.startswith("state:") or not isinstance(state, dict):
                continue
            fire_rate = state.get("fireRate")
            if isinstance(fire_rate, (int, float)) and not isinstance(fire_rate, bool):
                # Weapon state fireRate is stored per minute; player-facing
                # melee attack speed is expressed as attacks per second.
                return round(number(fire_rate) / 60, 3)
    return None


def find_melee_initial_combo(value: dict[str, Any]) -> tuple[int, float]:
    for behavior in melee_impact_behaviors(value):
        impact = behavior.get("impact:MeleeImpactBehavior", {})
        if not isinstance(impact, dict):
            continue

        initial_count = max(0, round(number(impact.get("InitialHitCounter"))))
        if initial_count == 0:
            return 0, 1.0

        base_multiplier = number(impact.get("BaseHitMultipler"), 1.0)
        tier_size = number(
            impact.get("HitReqNextTierOperator"),
            number(impact.get("BaseHitCount"), 20),
        )
        operation = str(impact.get("HitReqNextTierOperationType", "HTO_ADDITIVE"))
        if operation != "HTO_ADDITIVE" or tier_size <= 0:
            return initial_count, 1.0

        multiplier = base_multiplier + math.floor(initial_count / tier_size)
        return initial_count, max(1.0, float(multiplier))

    return 0, 1.0


def attack_data_component_damage(attack_data: dict[str, Any], damage_type: str) -> float:
    amount = number(attack_data.get("Amount"))
    component = number(attack_data.get(damage_type))
    if number(attack_data.get("UseNewFormat")) != 1 and component:
        component *= amount
    return round(component, 3)


def weapon_damage_components(attack_data: dict[str, Any]) -> tuple[float, float, float, str, float]:
    components = {
        damage_type: attack_data_component_damage(attack_data, damage_type)
        for damage_type in DAMAGE_TYPES
    }
    primary_type = str(attack_data.get("Type", ""))

    # Some old-format weapons omit component fields when all damage uses one
    # type, so recover that component from Type and Amount.
    if not any(components.values()) and primary_type in DAMAGE_TYPES:
        components[primary_type] = round(number(attack_data.get("Amount")), 3)

    elemental = [
        (damage_type, damage)
        for damage_type, damage in components.items()
        if damage_type not in PHYSICAL_TYPES and damage
    ]
    elem = ", ".join(
        ELEMENT_LABELS.get(damage_type, damage_type.removeprefix("DT_").title())
        for damage_type, _ in elemental
    )
    elem_dmg = round(sum(damage for _, damage in elemental), 3)

    return (
        components["DT_IMPACT"],
        components["DT_PUNCTURE"],
        components["DT_SLASH"],
        elem,
        elem_dmg,
    )


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


def calculate_final_damage(
    base_damage: float, pvp_multiplier: float, atten: float, quant_multiplier: Decimal
) -> tuple[int, Decimal]:
    raw = (
        decimal_number(base_damage)
        * decimal_number(pvp_multiplier)
        * decimal_number(atten)
        * quant_multiplier
    )
    return round_half_up_decimal(raw), raw
