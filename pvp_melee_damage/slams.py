"""PvP melee slam extraction and hit-row conversion."""

from __future__ import annotations

from typing import Any

from .combo import initial_combo_application_note, slam_combo_multiplier
from .constants import (
    CORE_PVP_SLAM_EVENT_ORDER,
    CORE_PVP_SLAM_EVENTS,
    CORE_PVP_SLAM_EVENTS_BY_KIND,
    KNOWN_MISSING_PVP_SLAM_WARNINGS,
)
from .damage import calculate_final_damage, quant_info
from .models import WeaponInfo
from .resolver import Resolver
from .utils import clean_label, combine_notes, number


def pvp_slam_entries(weapon: WeaponInfo) -> list[dict[str, Any]]:
    slams = weapon.doc.value.get("PvpSlams", [])
    if not isinstance(slams, list):
        return []
    return [slam for slam in slams if isinstance(slam, dict)]


def forced_procs_text(attack_data: dict[str, Any]) -> str:
    forced_procs = attack_data.get("ForcedProcs", [])
    if not isinstance(forced_procs, list):
        return ""
    return ", ".join(str(proc) for proc in forced_procs if proc)


def slam_note(slam: dict[str, Any]) -> str:
    notes: list[str] = []
    if number(slam.get("UseImpactBehaviorAttackDataAmount")) != 1:
        notes.append("Unexpected: does not use weapon impact base damage")
    if slam.get("UseCurrentMeleeAttackForDamage") == 1:
        notes.append("Uses current melee attack for damage")
    return combine_notes(*notes)


def build_slam_rows(resolver: Resolver, weapons: list[WeaponInfo]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    noted_non_core_events: set[tuple[str, str]] = set()
    noted_missing_core_events: set[tuple[str, str]] = set()

    for weapon in weapons:
        source_weapon_id = weapon.doc.package_id
        quant_label, quant_multiplier, quant_units = quant_info(weapon.attack_data)
        if quant_units is not None and quant_units not in {31, 32, 33}:
            resolver.warn(
                "warning", weapon.weapon_id, f"Unusual physical quantization value: {quant_label}"
            )

        slams = pvp_slam_entries(weapon)
        if not slams:
            resolver.warn("warning", weapon.weapon_id, "PvP melee weapon has no PvpSlams array")
            continue

        seen_core_events: set[str] = set()
        for slam in slams:
            trigger_event = str(slam.get("TriggeringAnimEvent", ""))
            slam_kind = CORE_PVP_SLAM_EVENTS.get(trigger_event)

            attack_data = slam.get("AttackData", {})
            if not isinstance(attack_data, dict):
                attack_data = {}

            if slam_kind is None:
                non_core_key = (source_weapon_id, trigger_event)
                if (
                    number(attack_data.get("Amount")) > 0
                    and non_core_key not in noted_non_core_events
                ):
                    # Unique impact events are not the standard aerial slam
                    # pair, so flag them for manual review instead of mixing
                    # them into the core slam damage rows.
                    resolver.warn(
                        "note",
                        source_weapon_id,
                        f"Non-core PvP slam event {trigger_event} has AttackData.Amount={attack_data.get('Amount')}; not exported",
                    )
                    noted_non_core_events.add(non_core_key)
                continue

            seen_core_events.add(trigger_event)
            atten = number(slam.get("BaseDamageAttenuation"), 1.0)
            combo_multiplier = slam_combo_multiplier(weapon, slam)
            final_damage, _raw = calculate_final_damage(
                weapon.base_damage,
                weapon.pvp_multiplier,
                atten * combo_multiplier,
                quant_multiplier,
            )

            rows.append(
                {
                    "weapon_name": weapon.weapon_name,
                    "weapon_id": weapon.weapon_id,
                    "weapon_category": weapon.category,
                    "slam_kind": slam_kind,
                    "base_damage": weapon.base_damage,
                    "pvp_damage_multiplier": weapon.pvp_multiplier,
                    "slam_damage_atten": atten,
                    "quant": quant_label,
                    "quant_multiplier": float(quant_multiplier),
                    "final_damage": final_damage,
                    "radius": number(slam.get("Radius")),
                    "edge_damage_multiplier": number(slam.get("FallOffMax")),
                    "can_use_combo_multiplier": number(slam.get("CanUseComboMultiplier")),
                    "slam_attack_data_amount": number(attack_data.get("Amount")),
                    "damage_type": attack_data.get("Type", ""),
                    "proc_chance": number(attack_data.get("ProcChance")),
                    "forced_procs": forced_procs_text(attack_data),
                    "note": combine_notes(
                        weapon.note,
                        slam_note(slam),
                        initial_combo_application_note(
                            weapon,
                            combo_multiplier,
                            "heavy slam",
                        ),
                    ),
                }
            )

        for trigger_event in CORE_PVP_SLAM_EVENT_ORDER:
            if trigger_event not in seen_core_events:
                missing_key = (source_weapon_id, trigger_event)
                if missing_key in noted_missing_core_events:
                    continue
                message = KNOWN_MISSING_PVP_SLAM_WARNINGS.get(
                    missing_key,
                    f"Missing PvP {CORE_PVP_SLAM_EVENTS[trigger_event]} entry",
                )
                resolver.warn("warning", source_weapon_id, message)
                noted_missing_core_events.add(missing_key)

    order = {kind: index for index, kind in enumerate(CORE_PVP_SLAM_EVENTS.values())}
    return sorted(
        rows,
        key=lambda row: (
            str(row["weapon_category"]),
            str(row["weapon_name"]),
            order.get(str(row["slam_kind"]), 99),
            str(row["weapon_id"]),
        ),
    )


def slam_attack_set_id(weapon_id: str) -> str:
    return f"{weapon_id}#PvpSlams"


def slam_attack_id(weapon_id: str, slam_kind: str) -> str:
    trigger_event = CORE_PVP_SLAM_EVENTS_BY_KIND.get(slam_kind, clean_label(slam_kind))
    return f"{slam_attack_set_id(weapon_id)}/{trigger_event}"


def is_slam_hit_row(row: dict[str, Any]) -> bool:
    return str(row.get("attack_set_combo_id", "")).endswith("#PvpSlams")


def build_slam_hit_rows(slam_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for slam in slam_rows:
        weapon_id = str(slam["weapon_id"])
        slam_kind = str(slam["slam_kind"])
        trigger_event = CORE_PVP_SLAM_EVENTS_BY_KIND.get(slam_kind, slam_kind)
        # Keep pivots simple by representing each weapon-level slam as a
        # one-hit combo row without adding slam-only columns to the hit sheet.
        rows.append(
            {
                "weapon_name": slam["weapon_name"],
                "weapon_id": weapon_id,
                "stance_equipped": "any",
                "stance_id": "",
                "weapon_category": slam["weapon_category"],
                "weapon_base_category": slam["weapon_category"],
                "weapon_note": "",
                "combo": slam_kind,
                "combo_context": trigger_event,
                "attack_set_combo_id": slam_attack_set_id(weapon_id),
                "attack_index": 1,
                "attack_id": slam_attack_id(weapon_id, slam_kind),
                "hit_index": 1,
                "hit_count": 1,
                "hit_index / hit_count": "1 / 1",
                "base_damage": slam["base_damage"],
                "pvp_damage_multiplier": slam["pvp_damage_multiplier"],
                "attack_pvp_damage_atten": slam["slam_damage_atten"],
                "quant": slam["quant"],
                "quant_multiplier": slam["quant_multiplier"],
                "final_damage": slam["final_damage"],
                "note": slam.get("note", ""),
            }
        )
    return rows
