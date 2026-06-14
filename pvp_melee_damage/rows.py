"""Build normalized workbook rows from discovered metadata."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .attack_sets import audit_stance_source, iter_attack_set_entries
from .combo import attack_combo_multiplier, initial_combo_application_note
from .constants import (
    ACTUAL_STANCE_NAMES,
    ACTUAL_STANCE_ORDER,
    ATTACK_DIM_HEADERS,
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
    STANCE_DIM_HEADERS,
    STANCELESS_CATEGORY_NAMES,
    UNCERTAIN_PVP_CONTEXTS,
    WEAPON_DIM_HEADERS,
)
from .damage import calculate_final_damage, quant_info, swing_atten
from .discovery import discover_stances, discover_weapons, matching_stances
from .labels import (
    clean_weapon_category,
    is_variant_stance_id,
    stance_display_name,
    variant_stance_category,
)
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

TONFA_STANCE_SLIDE_ATTACK_ID = "/Lotus/Weapons/Tenno/Melee/Attacks/PVPTonfaSlideAEquipped"
TONFA_STANCE_SLIDE_NOTE = (
    "In-game verified Tonfa stance slide: two 1x blade hits. "
    "The empty PVPTonfaSlideAEquipped derived package acts as a runtime marker, "
    "so inherited JSON properties alone do not describe these hits."
)


def tonfa_stance_slide_note(attack_id: str) -> str:
    if attack_id == TONFA_STANCE_SLIDE_ATTACK_ID:
        return TONFA_STANCE_SLIDE_NOTE
    return ""


def sliding_pvp_charge_note(
    combo_context: str,
    source_map_key: str,
    attack_set_id: str,
    attack_refs: list[Any],
) -> str:
    if combo_context != "CC_SLIDING_PVP" or source_map_key != "EquippedAttackSets":
        return ""
    refs = [attack_set_id, *(str(ref) for ref in attack_refs if isinstance(ref, str))]
    if any(
        re.search(r"(Melee30Charge|WhipCharge|Charge)", ref, flags=re.IGNORECASE) for ref in refs
    ):
        return (
            "Excluded legacy source alias: EquippedAttackSets.CC_SLIDING_PVP "
            "resolves to charge/heavy attack data instead of the current PvP slide attack"
        )
    return ""


def uncertain_context_note(combo_context: str) -> str:
    if combo_context in UNCERTAIN_PVP_CONTEXTS:
        return "Source-defined context; current in-game PvP reachability has not been independently verified"
    return ""


def should_export_combo_context(
    combo_context: str,
    weapon_category: str,
    include_non_tonfa_air_right: bool,
    include_unverified_pvp_contexts: bool = False,
) -> bool:
    if combo_context in UNCERTAIN_PVP_CONTEXTS and not include_unverified_pvp_contexts:
        return False
    if (
        combo_context == "CC_AIR_RIGHT"
        and weapon_category != "Tonfa"
        and not include_non_tonfa_air_right
    ):
        return False
    return combo_context_allowed_for_category(combo_context, weapon_category)


def attack_hit_attens(attack_doc: PackageDoc) -> list[float]:
    if attack_doc.package_id == TONFA_STANCE_SLIDE_ATTACK_ID:
        return [1.0, 1.0]

    swings = attack_doc.value.get("PerSwingOverrides")
    if isinstance(swings, list) and swings:
        return [
            swing_atten(attack_doc.value, swing if isinstance(swing, dict) else None)
            for swing in swings
        ]
    return [swing_atten(attack_doc.value, None)]


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
        ref = default_overrides.get("Stance") if isinstance(default_overrides, dict) else None
    elif source_field == "MeleeTreeType":
        ref = weapon.tree_ref
    else:
        ref = None

    return stance_name, str(ref or fallback_ref)


def stanceless_weapon_category(weapon: WeaponInfo) -> str:
    return f"{weapon.weapon_name} (stanceless)"


def special_weapon_note(weapon: WeaponInfo, embedded_override: tuple[str, str] | None) -> str:
    notes: list[str] = [weapon.note] if weapon.note else []
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
    include_non_tonfa_air_right: bool = False,
    include_unverified_pvp_contexts: bool = False,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, str]],
    list[StanceInfo],
]:
    resolver = Resolver(root)
    discovered_stances = discover_stances(resolver)
    stances = [stance for stance in discovered_stances if stance.is_actual]
    misc_stances = [stance for stance in discovered_stances if not stance.is_actual]
    weapons = discover_weapons(resolver)
    slam_rows = build_slam_rows(resolver, weapons)
    rows: list[dict[str, Any]] = []
    sliding_pvp_charge_warnings: set[str] = set()
    uncertain_context_warnings: set[tuple[str, str]] = set()
    skipped_no_stance_warnings: set[str] = set()
    audited_stance_sources: set[tuple[str, str]] = set()
    unvalidated_runtime_markers: set[str] = set()
    resolver.warn(
        "note",
        "<exporter>",
        (
            "Current PvP attack rows use effective EquippedAttackSets only. "
            "UnequippedAttackSets is legacy quick-melee routing and is not exported as a "
            "simultaneous damage variant."
        ),
    )
    resolver.warn(
        "note",
        TONFA_STANCE_SLIDE_ATTACK_ID,
        TONFA_STANCE_SLIDE_NOTE,
    )
    resolver.warn(
        "note",
        "<exporter>",
        (
            "Direct AerialAttacks button-routing refs are not exported as combo rows; "
            "CC_AIR_RIGHT is exported for Tonfas and all other categories"
            if include_non_tonfa_air_right
            else "Direct AerialAttacks button-routing refs are not exported as combo rows; "
            "CC_AIR_RIGHT is exported for Tonfas only because non-Tonfa A/B aerial sets "
            "currently have redundant PvP damage"
        ),
    )
    resolver.warn(
        "note",
        "<exporter>",
        (
            "Unverified PvP contexts are included for source-data auditing: "
            + ", ".join(sorted(UNCERTAIN_PVP_CONTEXTS))
            if include_unverified_pvp_contexts
            else "Unverified PvP contexts are excluded by default because they could not be "
            "triggered in current PvP testing: " + ", ".join(sorted(UNCERTAIN_PVP_CONTEXTS))
        ),
    )
    resolver.warn(
        "note",
        "<exporter>",
        (
            "Charge-named EquippedAttackSets.CC_SLIDING_PVP mappings are excluded as legacy "
            "aliases. Current slide attacks resolve through EquippedAttackSets.CC_SLIDING."
        ),
    )
    resolver.warn(
        "note",
        "<exporter>",
        (
            "The context key in EquippedAttackSets is treated as the runtime trigger. "
            "Attack-set ComboContext values are not used to relabel rows because inherited "
            "and reused attack sets frequently retain a different internal context."
        ),
    )
    resolver.warn(
        "note",
        "<exporter>",
        (
            "Damage rows model melee sweep impacts. Projectile throws use separate weapon "
            "fire behaviors and are not calculated as blade hits; this includes direct "
            "AerialAttacks routing such as glaive throws and the Sigma and Octantis shield throw."
        ),
    )

    for weapon in weapons:
        tree_doc = resolver.load_ref(weapon.tree_ref, weapon.doc)
        if tree_doc is None:
            resolver.warn(
                "warning", weapon.weapon_id, f"Could not resolve melee tree {weapon.tree_ref}"
            )
            continue

        quant_label, quant_multiplier, quant_units = quant_info(weapon.attack_data)
        if quant_units is not None and quant_units not in {31, 32, 33}:
            resolver.warn(
                "warning", weapon.weapon_id, f"Unusual physical quantization value: {quant_label}"
            )

        stance_matches = matching_stances(tree_doc, stances)
        if not stance_matches:
            resolver.warn(
                "warning",
                weapon.weapon_id,
                f"No PvP stance matched melee tree {tree_doc.package_id}; using base tree only",
            )
            stance_matches = [make_base_tree_stance(tree_doc)]

        embedded_stance_doc: PackageDoc | None = None
        embedded_stance_name = ""
        embedded_override = embedded_no_stance_tree(weapon)
        weapon_note = special_weapon_note(weapon, embedded_override)
        if embedded_override is not None:
            embedded_stance_name, embedded_stance_ref = embedded_override
            embedded_stance_doc = resolver.load_ref(embedded_stance_ref, weapon.doc)
            if embedded_stance_doc is None:
                resolver.warn(
                    "warning",
                    weapon.weapon_id,
                    f"Could not resolve embedded no-stance tree {embedded_stance_ref}",
                )
            else:
                resolver.warn(
                    "note",
                    weapon.weapon_id,
                    f"No-stance combo source uses embedded stance tree {embedded_stance_name}: {embedded_stance_doc.package_id}",
                )

        no_stance_source_emitted = False
        for stance in stance_matches:
            audit_key = (stance.stance_id, tree_doc.package_id)
            if audit_key not in audited_stance_sources:
                audit_stance_source(resolver, tree_doc, stance)
                audited_stance_sources.add(audit_key)

            sources: list[tuple[str, StanceInfo, PackageDoc, str, str]] = []
            if embedded_stance_doc is not None:
                if not no_stance_source_emitted:
                    sources.append(
                        (
                            "no",
                            make_embedded_tree_stance(embedded_stance_doc),
                            embedded_stance_doc,
                            stanceless_weapon_category(weapon),
                            f"No-stance state uses embedded stance tree: {embedded_stance_name}",
                        )
                    )
                    no_stance_source_emitted = True
            elif weapon.weapon_id in REMOVE_STANCELESS_ONLY_WEAPON_IDS:
                if weapon.weapon_id not in skipped_no_stance_warnings:
                    resolver.warn(
                        "note",
                        weapon.weapon_id,
                        "Skipped stanceless-only combo rows for this weapon",
                    )
                    skipped_no_stance_warnings.add(weapon.weapon_id)
            else:
                sources.append(("no", stance, tree_doc, weapon.category, ""))

            sources.append(("yes", stance, stance.doc, weapon.category, ""))

            for (
                stance_equipped,
                source_stance,
                source_doc,
                row_weapon_category,
                source_note,
            ) in sources:
                entries = iter_attack_set_entries(
                    source_doc,
                    resolver,
                    allowed_maps={"equipped"},
                )
                if not entries:
                    resolver.warn(
                        "warning",
                        source_doc.package_id,
                        f"No attack-set entries for stance state {stance_equipped}",
                    )
                    continue

                for entry in entries:
                    combo_context = entry.combo_context
                    attack_set_ref = entry.attack_set_ref
                    if combo_context in IGNORED_DAMAGE_COMBO_CONTEXTS:
                        continue
                    if not should_export_combo_context(
                        str(combo_context),
                        weapon.category,
                        include_non_tonfa_air_right,
                        include_unverified_pvp_contexts,
                    ):
                        continue

                    attack_set_doc = resolver.load_ref(attack_set_ref, source_doc)
                    if attack_set_doc is None:
                        continue

                    attacks = attack_set_doc.value.get("Attacks", [])
                    if not isinstance(attacks, list) or not attacks:
                        resolver.warn(
                            "warning", attack_set_doc.package_id, "Attack set has no Attacks array"
                        )
                        continue

                    attack_set_id = attack_set_doc.package_id
                    charge_note = sliding_pvp_charge_note(
                        str(combo_context),
                        entry.map_key,
                        attack_set_id,
                        attacks,
                    )
                    if charge_note:
                        warning_key = f"{entry.map_key}|{attack_set_id}"
                        if warning_key not in sliding_pvp_charge_warnings:
                            resolver.warn("note", attack_set_id, charge_note)
                            sliding_pvp_charge_warnings.add(warning_key)
                        continue

                    reachability_note = uncertain_context_note(str(combo_context))
                    if reachability_note:
                        warning_key = (str(combo_context), attack_set_id)
                        if warning_key not in uncertain_context_warnings:
                            resolver.warn(
                                "note",
                                attack_set_id,
                                f"{combo_context}: {reachability_note}",
                            )
                            uncertain_context_warnings.add(warning_key)

                    note = combine_notes(
                        source_note,
                        entry.note,
                        charge_note,
                        reachability_note,
                    )
                    combo_multiplier = attack_combo_multiplier(
                        weapon,
                        str(combo_context),
                    )
                    note = combine_notes(
                        note,
                        initial_combo_application_note(
                            weapon,
                            combo_multiplier,
                            "heavy attack",
                        ),
                    )

                    for attack_index, attack_ref in enumerate(attacks, start=1):
                        if not isinstance(attack_ref, str):
                            resolver.warn(
                                "warning",
                                attack_set_doc.package_id,
                                f"Non-string attack ref at index {attack_index}",
                            )
                            continue

                        attack_doc = resolver.load_ref(attack_ref, attack_set_doc)
                        if attack_doc is None:
                            continue

                        if (
                            not attack_doc.first_value
                            and attack_doc.package_id != TONFA_STANCE_SLIDE_ATTACK_ID
                            and attack_doc.package_id not in unvalidated_runtime_markers
                        ):
                            resolver.warn(
                                "warning",
                                attack_doc.package_id,
                                (
                                    "Derived attack package defines no direct fields. Hit count "
                                    "and attenuation are inherited from JSON, but engine-side "
                                    "runtime-marker behavior cannot be proven from the dump; "
                                    "in-game validation is recommended."
                                ),
                            )
                            unvalidated_runtime_markers.add(attack_doc.package_id)

                        hit_attens = attack_hit_attens(attack_doc)
                        hit_count = len(hit_attens)
                        attack_note = tonfa_stance_slide_note(attack_doc.package_id)
                        for hit_index, atten in enumerate(hit_attens, start=1):
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
                                    "stance_equipped": stance_equipped,
                                    "stance_id": ""
                                    if source_stance.stance_id == "base tree"
                                    else source_stance.stance_id,
                                    "weapon_category": row_weapon_category,
                                    "weapon_base_category": weapon.category,
                                    "weapon_note": weapon_note,
                                    "attack_speed": weapon.attack_speed,
                                    "impact": weapon.impact,
                                    "puncture": weapon.puncture,
                                    "slash": weapon.slash,
                                    "elem": weapon.elem,
                                    "elem_dmg": weapon.elem_dmg,
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
                                    "note": combine_notes(note, attack_note),
                                }
                            )

    rows = collapse_dimension_rows(rows, PIVOT_HEADERS, "stance_equipped")
    rows.extend(build_slam_hit_rows(slam_rows))
    totals = build_combo_totals(rows)
    return rows, totals, slam_rows, resolver.warnings, misc_stances


def collapse_dimension_rows(
    rows: list[dict[str, Any]],
    headers: list[str],
    field: str,
) -> list[dict[str, Any]]:
    if field not in headers:
        return rows

    key_fields = [header for header in headers if header != field]
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
        states = {str(row.get(field, "")) for row in group_rows}
        if {"yes", "no"}.issubset(states):
            template = next(
                (row for row in group_rows if row.get(field) == "yes"), group_rows[0]
            ).copy()
            template[field] = "any"
            collapsed.append(template)
            collapsed.extend(row for row in group_rows if row.get(field) not in {"yes", "no"})
        elif {"equipped", "unequipped"}.issubset(states):
            template = next(
                (row for row in group_rows if row.get(field) == "equipped"), group_rows[0]
            ).copy()
            template[field] = "any"
            collapsed.append(template)
            collapsed.extend(
                row for row in group_rows if row.get(field) not in {"equipped", "unequipped"}
            )
        else:
            collapsed.extend(group_rows)

    return collapsed


def collapse_stance_equipped_rows(
    rows: list[dict[str, Any]], headers: list[str]
) -> list[dict[str, Any]]:
    """Compatibility wrapper for callers and older tests."""
    return collapse_dimension_rows(rows, headers, "stance_equipped")


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
        damage_instances_by_key[key].append(
            (int(row["attack_index"]), int(row["hit_index"]), int(row["final_damage"]))
        )
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


def build_stance_rows(
    pivot_rows: list[dict[str, Any]], misc_stances: list[StanceInfo]
) -> list[dict[str, Any]]:
    stance_stats: dict[tuple[Any, ...], dict[str, Any]] = {}

    for row in pivot_rows:
        stance_id = str(row.get("stance_id", ""))
        weapon_category = str(row["weapon_category"])
        is_embedded_exception = weapon_category in STANCELESS_CATEGORY_NAMES
        if not stance_id and not is_embedded_exception:
            continue
        if row.get("stance_equipped") not in {"yes", "any"} and not is_embedded_exception:
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
    category_weapons: dict[str, set[str]] = defaultdict(set)
    slam_lookup = build_slam_lookup(slam_rows)

    weapon_rows: list[dict[str, Any]] = []
    attack_rows: list[dict[str, Any]] = []
    fact_rows: list[dict[str, Any]] = []

    for row in pivot_rows:
        fact_rows.append({header: row.get(header, "") for header in FACT_HEADERS})
        if is_slam_hit_row(row):
            continue

        weapon_category = row.get("weapon_base_category") or row["weapon_category"]
        category_weapons[str(row["weapon_category"])].add(str(row["weapon_name"]))
        slam_damage = slam_lookup_value(
            slam_lookup, row["weapon_id"], "Slam Attack", "final_damage"
        )
        heavy_slam_damage = slam_lookup_value(
            slam_lookup, row["weapon_id"], "Heavy Slam Attack", "final_damage"
        )
        slam_radius = slam_lookup_value(slam_lookup, row["weapon_id"], "Slam Attack", "radius")
        heavy_slam_radius = slam_lookup_value(
            slam_lookup, row["weapon_id"], "Heavy Slam Attack", "radius"
        )
        weapon_key_tuple = (
            row["weapon_name"],
            row["weapon_id"],
            weapon_category,
            row.get("attack_speed"),
            row["base_damage"],
            row.get("impact"),
            row.get("puncture"),
            row.get("slash"),
            row.get("elem"),
            row.get("elem_dmg"),
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
            "weapon_key",
            {
                "weapon_name": row["weapon_name"],
                "weapon_id": row["weapon_id"],
                "weapon_category": weapon_category,
                "attack_speed": row.get("attack_speed", ""),
                "base_damage": row["base_damage"],
                "impact": row.get("impact", ""),
                "puncture": row.get("puncture", ""),
                "slash": row.get("slash", ""),
                "elem": row.get("elem", ""),
                "elem_dmg": row.get("elem_dmg", ""),
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
                "weapon_ids": set(),
                "weapon_names": set(),
                "notes": set(),
            }
        combo_stats[combo_key_tuple]["hit_units"].add(
            (row["attack_index"], row["attack_id"], row["hit_index"])
        )
        combo_stats[combo_key_tuple]["attack_ids"].add((row["attack_index"], row["attack_id"]))
        combo_stats[combo_key_tuple]["weapon_ids"].add(row["weapon_id"])
        combo_stats[combo_key_tuple]["weapon_names"].add(row["weapon_name"])
        for note_part in split_note_parts(
            combine_notes(row.get("weapon_note", ""), row.get("note", ""))
        ):
            combo_stats[combo_key_tuple]["notes"].add(note_part)

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
            "attack_key",
            {
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
        all_category_weapons = category_weapons.get(str(combo["weapon_category"]), set())
        combo_weapon_names = combo["weapon_names"]
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
                "weapon_scope": (
                    "all category weapons"
                    if combo_weapon_names == all_category_weapons
                    else "weapon-specific"
                ),
                "weapon_count": len(combo["weapon_ids"]),
                "weapon_names": ", ".join(sorted(combo_weapon_names)),
                "note": "; ".join(sorted(combo["notes"])),
            }
        )

    return {
        "Hit Damage Database": (FACT_HEADERS, rows_to_matrix(FACT_HEADERS, fact_rows)),
        "Weapons": (WEAPON_DIM_HEADERS, rows_to_matrix(WEAPON_DIM_HEADERS, weapon_rows)),
        "Stances": (
            STANCE_DIM_HEADERS,
            rows_to_matrix(STANCE_DIM_HEADERS, build_stance_rows(pivot_rows, misc_stances)),
        ),
        "Combos": (COMBO_DIM_HEADERS, rows_to_matrix(COMBO_DIM_HEADERS, combo_rows)),
        "Attacks": (ATTACK_DIM_HEADERS, rows_to_matrix(ATTACK_DIM_HEADERS, attack_rows)),
    }


def build_combo_context_rows(
    pivot_rows: list[dict[str, Any]],
    include_non_tonfa_air_right: bool = False,
    include_unverified_pvp_contexts: bool = False,
) -> list[dict[str, Any]]:
    contexts = {str(row.get("combo_context", "")) for row in pivot_rows if row.get("combo_context")}
    contexts.update(COMBO_CONTEXT_LABELS)
    rows: list[dict[str, Any]] = []

    for context in sorted(contexts):
        human_readable = COMBO_CONTEXT_LABELS.get(
            context, clean_label(context.replace("CC_", "")) or context
        )
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
                "damage_export": combo_context_export_label(
                    context,
                    include_non_tonfa_air_right,
                    include_unverified_pvp_contexts,
                ),
                "source": source,
            }
        )

    return rows


def combo_context_export_label(
    context: str,
    include_non_tonfa_air_right: bool = False,
    include_unverified_pvp_contexts: bool = False,
) -> str:
    if context in IGNORED_DAMAGE_COMBO_CONTEXTS:
        return "ignored"
    if context == "CC_AIR_RIGHT":
        if include_non_tonfa_air_right:
            return "included for all categories"
        return "included for Tonfa only; non-Tonfa export disabled by default"
    if context in CATEGORY_LIMITED_DAMAGE_COMBO_CONTEXTS:
        categories = ", ".join(sorted(CATEGORY_LIMITED_DAMAGE_COMBO_CONTEXTS[context]))
        return f"included for {categories} only"
    if context in UNCERTAIN_PVP_CONTEXTS:
        if include_unverified_pvp_contexts:
            return "included by option; not triggerable in current PvP testing"
        return "excluded by default; not triggerable in current PvP testing"
    return "included"
