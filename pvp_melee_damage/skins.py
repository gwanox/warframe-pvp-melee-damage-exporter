"""Derived weapon variants created by stat-changing legacy skins."""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from typing import Any

from .constants import DAMAGE_TYPES
from .damage import weapon_damage_components
from .models import PackageDoc, WeaponInfo
from .resolver import Resolver
from .utils import combine_notes, number


@dataclass(frozen=True)
class LegacySkinVariantSpec:
    weapon_id: str
    weapon_name: str


@dataclass(frozen=True)
class LegacySkinSpec:
    skin_id: str
    variants: tuple[LegacySkinVariantSpec, ...]


@dataclass(frozen=True)
class LegacySkinEffects:
    damage_multiplier: float = 1.0
    attack_speed_multiplier: float = 1.0
    combo_duration_bonus: float = 0.0


LEGACY_SKIN_SPECS = (
    LegacySkinSpec(
        skin_id="/Lotus/Upgrades/Skins/HeavyAxe/GrnAxe",
        variants=(
            LegacySkinVariantSpec(
                weapon_id="/Lotus/Weapons/Tenno/Melee/Axe/AxeWeapon",
                weapon_name="Scindo with Manticore Skin",
            ),
            LegacySkinVariantSpec(
                weapon_id="/Lotus/Weapons/Tenno/Melee/Axe/PrimeScindo/PrimeScindoWeapon",
                weapon_name="Scindo Prime with Manticore Skin",
            ),
        ),
    ),
    LegacySkinSpec(
        skin_id="/Lotus/Upgrades/Skins/Hammer/GrnHammer",
        variants=(
            LegacySkinVariantSpec(
                weapon_id="/Lotus/Weapons/Tenno/Melee/Hammer/HammerWeapon",
                weapon_name="Fragor with Brokk Skin",
            ),
            LegacySkinVariantSpec(
                weapon_id="/Lotus/Weapons/Tenno/Melee/PrimeFragor/PrimeFragor",
                weapon_name="Fragor Prime with Brokk Skin",
            ),
        ),
    ),
)


def upgrade_multiplier(operation: str, value: float) -> float | None:
    if operation == "STACKING_MULTIPLY":
        return round(1 + value, 6)
    if operation == "MULTIPLY":
        return round(value, 6)
    return None


def read_legacy_skin_effects(skin_doc: PackageDoc, resolver: Resolver) -> LegacySkinEffects:
    damage_multiplier = 1.0
    attack_speed_multiplier = 1.0
    combo_duration_bonus = 0.0
    upgrades = skin_doc.value.get("Upgrades", [])
    if not isinstance(upgrades, list):
        resolver.warn("warning", skin_doc.package_id, "Legacy skin Upgrades is not an array")
        return LegacySkinEffects()

    for upgrade in upgrades:
        if not isinstance(upgrade, dict):
            continue
        upgrade_type = str(upgrade.get("UpgradeType", ""))
        operation = str(upgrade.get("OperationType", ""))
        value = round(number(upgrade.get("Value")), 6)

        if upgrade_type == "WEAPON_MELEE_DAMAGE":
            multiplier = upgrade_multiplier(operation, value)
            if multiplier is None:
                resolver.warn(
                    "warning",
                    skin_doc.package_id,
                    f"Unsupported melee-damage skin operation {operation}",
                )
            else:
                damage_multiplier *= multiplier
        elif upgrade_type == "WEAPON_FIRE_RATE":
            multiplier = upgrade_multiplier(operation, value)
            if multiplier is None:
                resolver.warn(
                    "warning",
                    skin_doc.package_id,
                    f"Unsupported fire-rate skin operation {operation}",
                )
            else:
                attack_speed_multiplier *= multiplier
        elif upgrade_type == "WEAPON_MELEE_COMBO_DURATION_BONUS" and operation == "ADD":
            combo_duration_bonus += value
        elif upgrade_type == "WEAPON_MELEE_COMBO_DURATION_BONUS":
            resolver.warn(
                "warning",
                skin_doc.package_id,
                f"Unsupported combo-duration skin operation {operation}",
            )

    return LegacySkinEffects(
        damage_multiplier=round(damage_multiplier, 6),
        attack_speed_multiplier=round(attack_speed_multiplier, 6),
        combo_duration_bonus=round(combo_duration_bonus, 6),
    )


def scaled_attack_data(
    attack_data: dict[str, Any],
    damage_multiplier: float,
) -> dict[str, Any]:
    scaled = copy.deepcopy(attack_data)
    if damage_multiplier == 1:
        return scaled

    if "Amount" in scaled:
        scaled["Amount"] = round(number(scaled.get("Amount")) * damage_multiplier, 6)

    # Old-format component fields are fractions of Amount. New-format fields
    # are absolute damage and must be scaled alongside Amount.
    if number(scaled.get("UseNewFormat")) == 1:
        for damage_type in DAMAGE_TYPES:
            if damage_type in scaled:
                scaled[damage_type] = round(
                    number(scaled.get(damage_type)) * damage_multiplier,
                    6,
                )
    return scaled


def percent_change(multiplier: float) -> str:
    change = round((multiplier - 1) * 100, 3)
    return f"{change:+g}%"


def skin_variant_note(
    base_weapon: WeaponInfo,
    spec: LegacySkinSpec,
    skin_doc: PackageDoc,
    effects: LegacySkinEffects,
) -> str:
    effect_parts: list[str] = []
    if effects.damage_multiplier != 1:
        effect_parts.append(f"melee damage {percent_change(effects.damage_multiplier)}")
    if effects.attack_speed_multiplier != 1:
        effect_parts.append(f"attack speed {percent_change(effects.attack_speed_multiplier)}")
    if effects.combo_duration_bonus:
        effect_parts.append(f"combo duration {effects.combo_duration_bonus:+g}s")

    base_weapon_id = str(skin_doc.value.get("Weapon", ""))
    note = f"Legacy skin variant from {spec.skin_id}: {', '.join(effect_parts)}"
    if base_weapon.weapon_id != base_weapon_id:
        note += (
            f"; compatibility is an explicit exporter mapping because the skin "
            f"package Weapon field names only {base_weapon_id}"
        )
    if effects.combo_duration_bonus:
        note += "; combo duration is retained as a note and does not affect the damage calculations"
    return note


def make_legacy_skin_variant(
    base_weapon: WeaponInfo,
    variant_name: str,
    spec: LegacySkinSpec,
    skin_doc: PackageDoc,
    effects: LegacySkinEffects,
) -> WeaponInfo:
    attack_data = scaled_attack_data(
        base_weapon.attack_data,
        effects.damage_multiplier,
    )
    impact, puncture, slash, elem, elem_dmg = weapon_damage_components(attack_data)
    attack_speed = (
        None
        if base_weapon.attack_speed is None
        else round(base_weapon.attack_speed * effects.attack_speed_multiplier, 3)
    )
    return replace(
        base_weapon,
        weapon_id=f"{base_weapon.weapon_id}#legacy-skin:{spec.skin_id}",
        weapon_name=variant_name,
        base_damage=round(base_weapon.base_damage * effects.damage_multiplier, 6),
        attack_speed=attack_speed,
        impact=impact,
        puncture=puncture,
        slash=slash,
        elem=elem,
        elem_dmg=elem_dmg,
        attack_data=attack_data,
        note=combine_notes(
            base_weapon.note,
            skin_variant_note(base_weapon, spec, skin_doc, effects),
        ),
    )


def add_legacy_skin_variants(
    weapons: list[WeaponInfo],
    resolver: Resolver,
) -> list[WeaponInfo]:
    weapons_by_id = {weapon.weapon_id: weapon for weapon in weapons}
    variants: list[WeaponInfo] = []

    for spec in LEGACY_SKIN_SPECS:
        skin_doc = resolver.load_ref(spec.skin_id)
        if skin_doc is None:
            continue
        effects = read_legacy_skin_effects(skin_doc, resolver)
        base_weapon_id = str(skin_doc.value.get("Weapon", ""))
        compatible_weapon_ids = {variant.weapon_id for variant in spec.variants}
        if base_weapon_id not in compatible_weapon_ids:
            resolver.warn(
                "warning",
                spec.skin_id,
                f"Skin Weapon field {base_weapon_id} does not match its compatibility mapping",
            )

        for variant in spec.variants:
            base_weapon = weapons_by_id.get(variant.weapon_id)
            if base_weapon is None:
                resolver.warn(
                    "warning",
                    spec.skin_id,
                    f"Could not create {variant.weapon_name}: base weapon "
                    f"{variant.weapon_id} was not discovered",
                )
                continue
            variants.append(
                make_legacy_skin_variant(
                    base_weapon,
                    variant.weapon_name,
                    spec,
                    skin_doc,
                    effects,
                )
            )

        resolver.warn(
            "note",
            spec.skin_id,
            "Added legacy skin weapon variants from local Upgrades; Prime compatibility is an explicit mapping because the package Weapon field names only the base weapon",
        )
        if effects.combo_duration_bonus:
            resolver.warn(
                "note",
                spec.skin_id,
                f"Combo duration modifier {effects.combo_duration_bonus:+g}s is preserved in weapon notes but is not used by damage calculations",
            )

    return [*weapons, *variants]
