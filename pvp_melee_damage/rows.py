"""Build normalized workbook rows from discovered metadata."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from .constants import (
    ACTUAL_STANCE_NAMES,
    ACTUAL_STANCE_ORDER,
    CATEGORY_LIMITED_DAMAGE_COMBO_CONTEXTS,
    COMBO_CONTEXT_ENUM_CONTEXTS,
    COMBO_CONTEXT_LABELS,
    COMBO_CONTEXT_SOURCE,
    COMBO_DIM_HEADERS,
    CORE_PVP_SLAM_EVENT_ORDER,
    EMBEDDED_NO_STANCE_TREES,
    ENUM_REFERENCE_SOURCE,
    FACT_HEADERS,
    IGNORED_DAMAGE_COMBO_CONTEXTS,
    PIVOT_HEADERS,
    REMOVE_STANCELESS_ONLY_WEAPON_IDS,
    SLAM_CONTEXT_SOURCE,
    SPECIAL_WEAPON_NOTES,
    STANCELESS_CATEGORY_NAMES,
    STANCE_DIM_HEADERS,
    TOTAL_HEADERS,
    WEAPON_DIM_HEADERS,
    ATTACK_DIM_HEADERS,
)
from .damage import calculate_final_damage, quant_info, swing_atten
from .discovery import discover_stances, discover_weapons, matching_stances
from .labels import clean_weapon_category, is_variant_stance_id, stance_display_name, variant_stance_category
from .models import PackageDoc, StanceInfo, WeaponInfo
from .resolver import Resolver
from .slams import build_slam_hit_rows, build_slam_rows, is_slam_hit_row
from .utils import (
    clean_label,
    combine_notes,
    combo_context_allowed_for_category,
    combo_context_label,
    get_or_create_key,
    rows_to_matrix,
    split_note_parts,
)

def tonfa_anomaly_note(
    tree_doc: PackageDoc | None,
    stance: StanceInfo | None,
    attack_sets: dict[str, Any],
    combo_context: str,
    attack_set_id: str,
) -> str:
    if tree_doc is None or stance is None:
        return ""
    if not tree_doc.package_id.endswith("/TonfaMeleeTree"):
        return ""
    if not stance.stance_id.endswith("/PvPTonfaStanceOne"):
        return ""

    sliding = str(attack_sets.get("CC_SLIDING", ""))
    sliding_pvp = str(attack_sets.get("CC_SLIDING_PVP", ""))
    if "PVPTonfaSlideEquipped" in sliding and "TonfaMelee30ChargeB" in sliding_pvp:
        if combo_context in {"CC_SLIDING", "CC_SLIDING_PVP"} or "TonfaMelee30ChargeB" in attack_set_id:
            return "Tonfa anomaly: stance CC_SLIDING points to PVPTonfaSlideEquipped, inherited CC_SLIDING_PVP points to TonfaMelee30ChargeB"
    return ""


def sliding_pvp_charge_note(combo_context: str, attack_set_id: str, attack_refs: list[Any]) -> str:
    if combo_context != "CC_SLIDING_PVP":
        return ""
    refs = [attack_set_id, *(str(ref) for ref in attack_refs if isinstance(ref, str))]
    if any(re.search(r"(Melee30Charge|WhipCharge|Charge)", ref, flags=re.IGNORECASE) for ref in refs):
        return "Suspicious: CC_SLIDING_PVP resolves to charge attack data"
    return ""

def attack_hits(attack_value: dict[str, Any]) -> list[dict[str, Any] | None]:
    swings = attack_value.get("PerSwingOverrides")
    if isinstance(swings, list) and swings:
        return [swing if isinstance(swing, dict) else None for swing in swings]
    return [None]

def make_base_tree_stance(tree_doc: PackageDoc) -> StanceInfo:
    return StanceInfo(
        doc=tree_doc,
        stance_id="base tree",
        tree_package=tree_doc.package_id,
        compatibility_tags=set(),
        stance_name="base tree",
        is_actual=False,
    )


def make_embedded_tree_stance(tree_doc: PackageDoc) -> StanceInfo:
    tags = set(tree_doc.value.get("CompatibilityTags", []) or [])
    stance_name = stance_display_name(tree_doc.package_id)
    return StanceInfo(
        doc=tree_doc,
        stance_id=tree_doc.package_id,
        tree_package=tree_doc.package_id,
        compatibility_tags=tags,
        stance_name=stance_name,
        is_actual=stance_name in ACTUAL_STANCE_NAMES,
    )


def embedded_no_stance_tree(weapon: WeaponInfo) -> tuple[str, str] | None:
    override = EMBEDDED_NO_STANCE_TREES.get(weapon.weapon_id)
    if override is None:
        return None

    # Paracesis and Broken War expose useful no-stance combo sources through
    # embedded stance metadata rather than the normal PvP stance path.
    stance_name, source_field, fallback_ref = override
    if source_field == "DefaultModOverrides.Stance":
        default_overrides = weapon.doc.value.get("DefaultModOverrides", {})
        if isinstance(default_overrides, dict):
            ref = default_overrides.get("Stance")
        else:
            ref = None
    elif source_field == "MeleeTreeType":
        ref = weapon.tree_ref
    else:
        ref = None

    return stance_name, str(ref or fallback_ref)


def stanceless_weapon_category(weapon: WeaponInfo) -> str:
    return f"{weapon.weapon_name} (stanceless)"


def special_weapon_note(weapon: WeaponInfo, embedded_override: tuple[str, str] | None) -> str:
    notes: list[str] = []
    if embedded_override is not None:
        stance_name, stance_ref = embedded_override
        notes.append(
            f"Embedded no-stance tree: {stance_name} ({stance_ref}); no-stance rows use {stanceless_weapon_category(weapon)}"
        )
    if weapon.weapon_id in SPECIAL_WEAPON_NOTES:
        notes.append(SPECIAL_WEAPON_NOTES[weapon.weapon_id])
    return combine_notes(*notes)


def build_rows(
    root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]], list[StanceInfo]]:
    resolver = Resolver(root)
    discovered_stances = discover_stances(resolver)
    stances = [stance for stance in discovered_stances if stance.is_actual]
    misc_stances = [stance for stance in discovered_stances if not stance.is_actual]
    weapons = discover_weapons(resolver)
    slam_rows = build_slam_rows(resolver, weapons)
    rows: list[dict[str, Any]] = []
    anomaly_warnings: set[str] = set()
    sliding_pvp_charge_warnings: set[str] = set()
    skipped_no_stance_warnings: set[str] = set()

    for weapon in weapons:
        tree_doc = resolver.load_ref(weapon.tree_ref, weapon.doc)
        if tree_doc is None:
            resolver.warn("warning", weapon.weapon_id, f"Could not resolve melee tree {weapon.tree_ref}")
            continue

        quant_label, quant_multiplier, quant_units = quant_info(weapon.attack_data)
        if quant_units is not None and quant_units not in {31, 32, 33}:
            resolver.warn("warning", weapon.weapon_id, f"Unusual physical quantization value: {quant_label}")

        stance_matches = matching_stances(tree_doc, stances)
        if not stance_matches:
            resolver.warn("warning", weapon.weapon_id, f"No PvP stance matched melee tree {tree_doc.package_id}; using base tree only")
            stance_matches = [make_base_tree_stance(tree_doc)]

        embedded_stance_doc: PackageDoc | None = None
        embedded_stance_name = ""
        embedded_override = embedded_no_stance_tree(weapon)
        weapon_note = special_weapon_note(weapon, embedded_override)
        if embedded_override is not None:
            embedded_stance_name, embedded_stance_ref = embedded_override
            embedded_stance_doc = resolver.load_ref(embedded_stance_ref, weapon.doc)
            if embedded_stance_doc is None:
                resolver.warn("warning", weapon.weapon_id, f"Could not resolve embedded no-stance tree {embedded_stance_ref}")
            else:
                resolver.warn(
                    "note",
                    weapon.weapon_id,
                    f"No-stance combo source uses embedded stance tree {embedded_stance_name}: {embedded_stance_doc.package_id}",
                )

        no_stance_source_emitted = False
        for stance in stance_matches:
            for stance_equipped, map_key in (("no", "UnequippedAttackSets"), ("yes", "EquippedAttackSets")):
                source_stance = stance
                source_doc = stance.doc
                source_map_key = map_key
                embedded_note = ""
                row_weapon_category = weapon.category

                if stance_equipped == "no":
                    if embedded_stance_doc is not None:
                        if no_stance_source_emitted:
                            continue
                        source_stance = make_embedded_tree_stance(embedded_stance_doc)
                        source_doc = embedded_stance_doc
                        source_map_key = "EquippedAttackSets"
                        embedded_note = f"No-stance state uses embedded stance tree: {embedded_stance_name}"
                        row_weapon_category = stanceless_weapon_category(weapon)
                        no_stance_source_emitted = True
                    elif weapon.weapon_id in REMOVE_STANCELESS_ONLY_WEAPON_IDS:
                        if weapon.weapon_id not in skipped_no_stance_warnings:
                            resolver.warn("note", weapon.weapon_id, "Skipped stanceless-only combo rows for this weapon")
                            skipped_no_stance_warnings.add(weapon.weapon_id)
                        continue

                attack_sets = source_doc.value.get(source_map_key, {})
                if (
                    stance_equipped == "no"
                    and embedded_stance_doc is not None
                    and (not isinstance(attack_sets, dict) or not attack_sets)
                ):
                    attack_sets = source_doc.value.get("UnequippedAttackSets", {})
                if not isinstance(attack_sets, dict) or not attack_sets:
                    resolver.warn("warning", source_stance.stance_id, f"No {source_map_key} for stance state {stance_equipped}")
                    continue

                for combo_context, attack_set_ref in attack_sets.items():
                    if combo_context in IGNORED_DAMAGE_COMBO_CONTEXTS:
                        continue
                    if not combo_context_allowed_for_category(combo_context, weapon.category):
                        continue
                    if not isinstance(attack_set_ref, str):
                        resolver.warn("warning", source_stance.stance_id, f"Non-string attack set ref for {combo_context}")
                        continue

                    attack_set_doc = resolver.load_ref(attack_set_ref, source_doc)
                    if attack_set_doc is None:
                        continue

                    attacks = attack_set_doc.value.get("Attacks", [])
                    if not isinstance(attacks, list) or not attacks:
                        resolver.warn("warning", attack_set_doc.package_id, "Attack set has no Attacks array")
                        continue

                    attack_set_id = attack_set_doc.package_id
                    tonfa_note = tonfa_anomaly_note(tree_doc, source_stance, attack_sets, str(combo_context), attack_set_id)
                    if tonfa_note and tonfa_note not in anomaly_warnings:
                        resolver.warn("note", source_stance.stance_id, tonfa_note)
                        anomaly_warnings.add(tonfa_note)

                    charge_note = sliding_pvp_charge_note(str(combo_context), attack_set_id, attacks)
                    if charge_note:
                        warning_key = f"{source_stance.stance_id}|{attack_set_id}"
                        if warning_key not in sliding_pvp_charge_warnings:
                            resolver.warn("note", attack_set_id, charge_note)
                            sliding_pvp_charge_warnings.add(warning_key)

                    note = combine_notes(embedded_note, tonfa_note, charge_note)

                    for attack_index, attack_ref in enumerate(attacks, start=1):
                        if not isinstance(attack_ref, str):
                            resolver.warn("warning", attack_set_doc.package_id, f"Non-string attack ref at index {attack_index}")
                            continue

                        attack_doc = resolver.load_ref(attack_ref, attack_set_doc)
                        if attack_doc is None:
                            continue

                        hits = attack_hits(attack_doc.value)
                        hit_count = len(hits)
                        for hit_index, swing in enumerate(hits, start=1):
                            atten = swing_atten(attack_doc.value, swing)
                            final_damage, _raw = calculate_final_damage(
                                weapon.base_damage,
                                weapon.pvp_multiplier,
                                atten,
                                quant_multiplier,
                            )
                            rows.append(
                                {
                                    "weapon_name": weapon.weapon_name,
                                    "weapon_id": weapon.weapon_id,
                                    "stance_equipped": stance_equipped,
                                    "stance_id": "" if source_stance.stance_id == "base tree" else source_stance.stance_id,
                                    "weapon_category": row_weapon_category,
                                    "weapon_base_category": weapon.category,
                                    "weapon_note": weapon_note,
                                    "combo": combo_context_label(combo_context),
                                    "combo_context": combo_context,
                                    "attack_set_combo_id": attack_set_id,
                                    "attack_index": attack_index,
                                    "attack_id": attack_doc.package_id,
                                    "hit_index": hit_index,
                                    "hit_count": hit_count,
                                    "hit_index / hit_count": f"{hit_index} / {hit_count}",
                                    "base_damage": weapon.base_damage,
                                    "pvp_damage_multiplier": weapon.pvp_multiplier,
                                    "attack_pvp_damage_atten": atten,
                                    "quant": quant_label,
                                    "quant_multiplier": float(quant_multiplier),
                                    "final_damage": final_damage,
                                    "note": note,
                                }
                            )

    rows = collapse_stance_equipped_rows(rows, PIVOT_HEADERS)
    rows.extend(build_slam_hit_rows(slam_rows))
    totals = collapse_stance_equipped_rows(build_combo_totals(rows), TOTAL_HEADERS)
    return rows, totals, slam_rows, resolver.warnings, misc_stances


def collapse_stance_equipped_rows(rows: list[dict[str, Any]], headers: list[str]) -> list[dict[str, Any]]:
    if "stance_equipped" not in headers:
        return rows

    key_fields = [header for header in headers if header != "stance_equipped"]
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    order: list[tuple[Any, ...]] = []

    for row in rows:
        key = tuple(row.get(field, "") for field in key_fields)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(row)

    collapsed: list[dict[str, Any]] = []
    for key in order:
        group_rows = grouped[key]
        states = {str(row.get("stance_equipped", "")) for row in group_rows}
        if {"yes", "no"}.issubset(states):
            # Identical equipped and unequipped rows are one user-facing move.
            template = next((row for row in group_rows if row.get("stance_equipped") == "yes"), group_rows[0]).copy()
            template["stance_equipped"] = "any"
            collapsed.append(template)
            collapsed.extend(row for row in group_rows if row.get("stance_equipped") not in {"yes", "no"})
        else:
            collapsed.extend(group_rows)

    return collapsed


def build_combo_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    attacks_by_key: dict[tuple[Any, ...], set[str]] = defaultdict(set)
    notes_by_key: dict[tuple[Any, ...], set[str]] = defaultdict(set)
    damage_instances_by_key: dict[tuple[Any, ...], list[tuple[int, int, int]]] = defaultdict(list)

    group_fields = (
        "weapon_name",
        "weapon_id",
        "stance_equipped",
        "stance_id",
        "weapon_category",
        "combo",
        "combo_context",
        "attack_set_combo_id",
    )

    for row in rows:
        key = tuple(row[field] for field in group_fields)
        if key not in grouped:
            grouped[key] = {field: row[field] for field in group_fields}
            grouped[key]["hit_count"] = 0
            grouped[key]["total_damage"] = 0
        grouped[key]["hit_count"] += 1
        grouped[key]["total_damage"] += int(row["final_damage"])
        damage_instances_by_key[key].append((int(row["attack_index"]), int(row["hit_index"]), int(row["final_damage"])))
        attacks_by_key[key].add(str(row["attack_id"]))
        for note_part in split_note_parts(row.get("note")):
            notes_by_key[key].add(note_part)

    totals: list[dict[str, Any]] = []
    for key in sorted(grouped):
        item = grouped[key]
        item["attack_count"] = len(attacks_by_key[key])
        item["damage_instances"] = damage_instances_text(damage_instances_by_key[key])
        item["note"] = "; ".join(sorted(notes_by_key[key]))
        totals.append(item)
    return totals


def damage_instances_text(instances: list[tuple[int, int, int]]) -> str:
    by_attack: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for attack_index, hit_index, damage in sorted(instances):
        by_attack[attack_index].append((hit_index, damage))

    parts: list[str] = []
    for attack_index in sorted(by_attack):
        damages = [str(damage) for _hit_index, damage in sorted(by_attack[attack_index])]
        if len(damages) > 1:
            parts.append(f"({' + '.join(damages)})")
        else:
            parts.append(damages[0])

    return " + ".join(parts)


def stance_row_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    stance_name = str(item["stance_name"])
    actual_index = ACTUAL_STANCE_ORDER.get(stance_name)
    if actual_index is not None:
        return (0, actual_index, str(item["stance_id"]))
    return (1, stance_name, str(item["weapon_category"]), str(item["stance_id"]))


def misc_stance_category(stance: StanceInfo) -> str:
    if stance.stance_name == "Lunaro":
        return "Lunaro"
    if is_variant_stance_id(stance.stance_id):
        return variant_stance_category(stance.stance_id.rsplit("/", 1)[-1])
    tags = " ".join(sorted(stance.compatibility_tags))
    return clean_weapon_category(tags) or "Misc"


def build_stance_rows(pivot_rows: list[dict[str, Any]], misc_stances: list[StanceInfo]) -> list[dict[str, Any]]:
    stance_stats: dict[tuple[Any, ...], dict[str, Any]] = {}

    for row in pivot_rows:
        stance_id = str(row.get("stance_id", ""))
        weapon_category = str(row["weapon_category"])
        is_embedded_exception = weapon_category in STANCELESS_CATEGORY_NAMES
        if row.get("stance_equipped") != "yes" and not is_embedded_exception:
            continue

        key = (stance_id, weapon_category)
        if key not in stance_stats:
            stance_stats[key] = {
                "stance_name": stance_display_name(stance_id),
                "weapon_category": weapon_category,
                "weapon_ids": set(),
                "combo_ids": set(),
                "notes": set(),
                "stance_id": stance_id,
            }
        stance_stats[key]["weapon_ids"].add(row["weapon_id"])
        stance_stats[key]["combo_ids"].add(row["attack_set_combo_id"])
        for note_part in split_note_parts(row.get("note")):
            stance_stats[key]["notes"].add(note_part)

    for stance in misc_stances:
        key = (stance.stance_id, "Misc")
        if key in stance_stats:
            continue
        stance_stats[key] = {
            "stance_name": stance.stance_name,
            "weapon_category": misc_stance_category(stance),
            "weapon_ids": set(),
            "combo_ids": set(),
            "notes": {"Misc stance package excluded from damage sheets"},
            "stance_id": stance.stance_id,
        }

    rows: list[dict[str, Any]] = []
    sorted_keys = sorted(
        stance_stats,
        key=lambda key: stance_row_sort_key(stance_stats[key]),
    )
    for stance_key, key in enumerate(sorted_keys, start=1):
        item = stance_stats[key]
        rows.append(
            {
                "stance_name": item["stance_name"],
                "weapon_category": item["weapon_category"],
                "weapon_count": len(item["weapon_ids"]),
                "combo_count": len(item["combo_ids"]),
                "note": "; ".join(sorted(item["notes"])),
                "stance_id": item["stance_id"],
                "stance_key": stance_key,
            }
        )
    return rows


def build_slam_lookup(slam_rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    lookup: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in slam_rows:
        weapon_id = str(row.get("weapon_id", ""))
        slam_kind = str(row.get("slam_kind", ""))
        if weapon_id and slam_kind and slam_kind not in lookup[weapon_id]:
            lookup[weapon_id][slam_kind] = row
    return dict(lookup)


def slam_lookup_value(
    lookup: dict[str, dict[str, dict[str, Any]]],
    weapon_id: str,
    slam_kind: str,
    field: str,
) -> Any:
    return lookup.get(weapon_id, {}).get(slam_kind, {}).get(field, "")


def build_compact_tables(
    pivot_rows: list[dict[str, Any]],
    slam_rows: list[dict[str, Any]],
    misc_stances: list[StanceInfo],
) -> dict[str, tuple[list[str], list[list[Any]]]]:
    weapon_map: dict[tuple[Any, ...], int] = {}
    attack_map: dict[tuple[Any, ...], int] = {}
    combo_stats: dict[tuple[Any, ...], dict[str, Any]] = {}
    slam_lookup = build_slam_lookup(slam_rows)

    weapon_rows: list[dict[str, Any]] = []
    attack_rows: list[dict[str, Any]] = []
    fact_rows: list[dict[str, Any]] = []

    for row in pivot_rows:
        fact_rows.append({header: row.get(header, "") for header in FACT_HEADERS})
        if is_slam_hit_row(row):
            continue

        weapon_category = row.get("weapon_base_category") or row["weapon_category"]
        slam_damage = slam_lookup_value(slam_lookup, row["weapon_id"], "Slam Attack", "final_damage")
        heavy_slam_damage = slam_lookup_value(slam_lookup, row["weapon_id"], "Heavy Slam Attack", "final_damage")
        slam_radius = slam_lookup_value(slam_lookup, row["weapon_id"], "Slam Attack", "radius")
        heavy_slam_radius = slam_lookup_value(slam_lookup, row["weapon_id"], "Heavy Slam Attack", "radius")
        weapon_key_tuple = (
            row["weapon_name"],
            row["weapon_id"],
            weapon_category,
            row["base_damage"],
            row["pvp_damage_multiplier"],
            row["quant"],
            row["quant_multiplier"],
            slam_damage,
            heavy_slam_damage,
            slam_radius,
            heavy_slam_radius,
            row.get("weapon_note", ""),
        )
        get_or_create_key(
            weapon_map,
            weapon_rows,
            weapon_key_tuple,
            lambda key: {
                "weapon_key": key,
                "weapon_name": row["weapon_name"],
                "weapon_id": row["weapon_id"],
                "weapon_category": weapon_category,
                "base_damage": row["base_damage"],
                "pvp_damage_multiplier": row["pvp_damage_multiplier"],
                "quant": row["quant"],
                "quant_multiplier": row["quant_multiplier"],
                "slam_damage": slam_damage,
                "heavy_slam_damage": heavy_slam_damage,
                "slam_radius": slam_radius,
                "heavy_slam_radius": heavy_slam_radius,
                "note": row.get("weapon_note", ""),
            },
        )

        combo_key_tuple = (
            row["weapon_category"],
            row["stance_equipped"],
            row["stance_id"],
            row["combo"],
            row["combo_context"],
            row["attack_set_combo_id"],
        )
        if combo_key_tuple not in combo_stats:
            combo_stats[combo_key_tuple] = {
                "weapon_category": row["weapon_category"],
                "stance_equipped": row["stance_equipped"],
                "stance_id": row["stance_id"],
                "combo": row["combo"],
                "combo_context": row["combo_context"],
                "attack_set_combo_id": row["attack_set_combo_id"],
                "hit_units": set(),
                "attack_ids": set(),
            }
        combo_stats[combo_key_tuple]["hit_units"].add((row["attack_index"], row["attack_id"], row["hit_index"]))
        combo_stats[combo_key_tuple]["attack_ids"].add((row["attack_index"], row["attack_id"]))

        attack_key_tuple = (
            row["weapon_category"],
            row["stance_equipped"],
            row["stance_id"],
            row["combo"],
            row["combo_context"],
            row["attack_set_combo_id"],
            row["attack_index"],
            row["attack_id"],
            row["hit_index"],
            row["hit_count"],
            row["attack_pvp_damage_atten"],
        )
        get_or_create_key(
            attack_map,
            attack_rows,
            attack_key_tuple,
            lambda key: {
                "attack_key": key,
                "weapon_category": row["weapon_category"],
                "stance_equipped": row["stance_equipped"],
                "combo": row["combo"],
                "attack_index": row["attack_index"],
                "attack_id": row["attack_id"],
                "hit_index / hit_count": row["hit_index / hit_count"],
                "attack_pvp_damage_atten": row["attack_pvp_damage_atten"],
                "stance_id": row["stance_id"],
                "attack_set_combo_id": row["attack_set_combo_id"],
                "combo_context": row["combo_context"],
            },
        )

    combo_rows: list[dict[str, Any]] = []
    for combo_index, combo_key_tuple in enumerate(sorted(combo_stats), start=1):
        combo = combo_stats[combo_key_tuple]
        combo_rows.append(
            {
                "combo_key": combo_index,
                "weapon_category": combo["weapon_category"],
                "stance_equipped": combo["stance_equipped"],
                "stance_id": combo["stance_id"],
                "combo": combo["combo"],
                "combo_context": combo["combo_context"],
                "attack_set_combo_id": combo["attack_set_combo_id"],
                "hit_count": len(combo["hit_units"]),
                "attack_count": len(combo["attack_ids"]),
            }
        )

    return {
        "Hit Damage Database": (FACT_HEADERS, rows_to_matrix(FACT_HEADERS, fact_rows)),
        "Weapons": (WEAPON_DIM_HEADERS, rows_to_matrix(WEAPON_DIM_HEADERS, weapon_rows)),
        "Stances": (STANCE_DIM_HEADERS, rows_to_matrix(STANCE_DIM_HEADERS, build_stance_rows(pivot_rows, misc_stances))),
        "Combos": (COMBO_DIM_HEADERS, rows_to_matrix(COMBO_DIM_HEADERS, combo_rows)),
        "Attacks": (ATTACK_DIM_HEADERS, rows_to_matrix(ATTACK_DIM_HEADERS, attack_rows)),
    }


def build_combo_context_rows(pivot_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contexts = {str(row.get("combo_context", "")) for row in pivot_rows if row.get("combo_context")}
    contexts.update(COMBO_CONTEXT_LABELS)
    rows: list[dict[str, Any]] = []

    for context in sorted(contexts):
        human_readable = COMBO_CONTEXT_LABELS.get(context, clean_label(context.replace("CC_", "")) or context)
        if context in CORE_PVP_SLAM_EVENT_ORDER:
            source = SLAM_CONTEXT_SOURCE
        elif context in COMBO_CONTEXT_ENUM_CONTEXTS:
            source = ENUM_REFERENCE_SOURCE
        else:
            source = COMBO_CONTEXT_SOURCE
        rows.append(
            {
                "combo_context": context,
                "human_readable": human_readable,
                "damage_export": combo_context_export_label(context),
                "source": source,
            }
        )

    return rows


def combo_context_export_label(context: str) -> str:
    if context in IGNORED_DAMAGE_COMBO_CONTEXTS:
        return "ignored"
    if context in CATEGORY_LIMITED_DAMAGE_COMBO_CONTEXTS:
        categories = ", ".join(sorted(CATEGORY_LIMITED_DAMAGE_COMBO_CONTEXTS[context]))
        return f"included for {categories} only"
    return "included"
