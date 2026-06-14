"""Discovery of PvP melee weapons and stance metadata."""

from __future__ import annotations

from pathlib import Path

from .constants import (
    ACTUAL_STANCE_NAMES,
    FORCED_PVP_WEAPON_IDS,
    IGNORED_WEAPON_BASENAMES,
    MELEE_ROOT_PACKAGE,
    MELEE_SWEEP_MARKERS,
    PVP_STANCE_ROOT,
    WEAPON_SCAN_ROOT_PACKAGE,
)
from .damage import (
    find_melee_attack_speed,
    find_melee_impact,
    find_melee_initial_combo,
    weapon_damage_components,
)
from .labels import (
    best_effort_weapon_name,
    category_from_tree,
    ignored_ai_weapon_basename,
    stance_display_name,
)
from .models import PackageDoc, StanceInfo, WeaponInfo
from .resolver import Resolver
from .skins import add_legacy_skin_variants


def file_mentions_melee_sweep(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return False
    return any(marker in text for marker in MELEE_SWEEP_MARKERS)


def iter_weapon_json_paths(root: Path) -> list[Path]:
    weapon_root = root / Path(*WEAPON_SCAN_ROOT_PACKAGE.strip("/").split("/"))
    if not weapon_root.exists():
        return []

    paths: list[Path] = []
    for path in weapon_root.rglob("*.json"):
        if file_mentions_melee_sweep(path):
            paths.append(path)
    return sorted(paths)


def discover_stances(resolver: Resolver) -> list[StanceInfo]:
    stance_root = resolver.root / Path(*PVP_STANCE_ROOT.strip("/").split("/"))
    stances: list[StanceInfo] = []

    for path in sorted(stance_root.rglob("*.json")):
        if path.parent.name == "Combos":
            continue
        doc = resolver.load_path(path)
        if doc is None or doc.value.get("AvailableOnPvp") != 1:
            continue

        tree_package: str | None = None
        for package in doc.packages[1:]:
            value = package.get("value", {})
            if isinstance(value, dict) and (
                "CompatibilityTags" in value
                or "EquippedAttackSets" in value
                or "UnequippedAttackSets" in value
            ):
                candidate = str(package.get("package", ""))
                if candidate.startswith(f"{MELEE_ROOT_PACKAGE}/MeleeTrees/"):
                    tree_package = candidate
                    break

        tags = set(doc.value.get("CompatibilityTags", []) or [])
        if not tree_package and not tags:
            resolver.warn(
                "warning", doc.package_id, "PvP stance has no tree package or compatibility tags"
            )

        stance_name = stance_display_name(doc.package_id)
        stances.append(
            StanceInfo(
                doc=doc,
                stance_id=doc.package_id,
                tree_package=tree_package,
                compatibility_tags=tags,
                stance_name=stance_name,
                is_actual=stance_name in ACTUAL_STANCE_NAMES,
            )
        )

    return stances


def discover_weapons(resolver: Resolver) -> list[WeaponInfo]:
    weapons: list[WeaponInfo] = []
    seen_files: set[Path] = set()

    for path in iter_weapon_json_paths(resolver.root):
        if path.stem in IGNORED_WEAPON_BASENAMES:
            resolver.warn(
                "ignored", str(path.relative_to(resolver.root)), "Ignored not-in-game weapon file"
            )
            continue

        doc = resolver.load_path(path)
        if doc is None or path.resolve() in seen_files:
            continue
        seen_files.add(path.resolve())

        if doc.package_id.rsplit("/", 1)[-1] in IGNORED_WEAPON_BASENAMES:
            resolver.warn("ignored", doc.package_id, "Ignored not-in-game weapon package")
            continue

        value = doc.value
        force_pvp = doc.package_id in FORCED_PVP_WEAPON_IDS
        # Dark Split-Sword heavy mode is usable in Conclave, but this dump
        # does not mark that package AvailableOnPvp like normal weapons.
        if value.get("AvailableOnPvp") != 1 and not force_pvp:
            continue
        if force_pvp and value.get("AvailableOnPvp") != 1:
            resolver.warn(
                "note",
                doc.package_id,
                "Forced include: Dark Split-Sword heavy sword mode is PvP-usable through stance category despite AvailableOnPvp metadata",
            )

        impact = find_melee_impact(value)
        if impact is None:
            continue

        if ignored_ai_weapon_basename(path.stem):
            resolver.warn(
                "ignored", str(path.relative_to(resolver.root)), "Ignored not-in-game weapon file"
            )
            continue
        if ignored_ai_weapon_basename(doc.package_id.rsplit("/", 1)[-1]):
            resolver.warn("ignored", doc.package_id, "Ignored not-in-game weapon package")
            continue

        tree_ref = str(value.get("MeleeTreeType") or value.get("Stance") or "")
        if not tree_ref:
            resolver.warn(
                "warning", doc.package_id, "PvP melee weapon has no MeleeTreeType/Stance ref"
            )
            continue

        tree_doc = resolver.load_ref(tree_ref, doc)
        category = category_from_tree(tree_doc, doc)
        attack_data, base_damage, pvp_multiplier = impact
        attack_speed = find_melee_attack_speed(value)
        initial_combo_count, initial_heavy_multiplier = find_melee_initial_combo(value)
        impact_damage, puncture_damage, slash_damage, elem, elem_dmg = weapon_damage_components(
            attack_data
        )
        if attack_speed is None:
            resolver.warn(
                "warning",
                doc.package_id,
                "PvP melee weapon has no attack speed on its melee behavior",
            )
        note = ""
        if initial_combo_count:
            note = (
                f"Initial combo {initial_combo_count} gives a "
                f"{initial_heavy_multiplier:g}x starting combo multiplier; applied to "
                "heavy attacks and combo-enabled PvP heavy slams"
            )
            resolver.warn(
                "note",
                doc.package_id,
                f"InitialHitCounter={initial_combo_count} produces a "
                f"{initial_heavy_multiplier:g}x heavy-attack multiplier in PvP; "
                "treated as a PvE-oriented mechanic carried into Conclave",
            )

        weapons.append(
            WeaponInfo(
                doc=doc,
                weapon_id=doc.package_id,
                weapon_name=best_effort_weapon_name(value, doc.package_id),
                category=category,
                tree_ref=tree_ref,
                base_damage=base_damage,
                pvp_multiplier=pvp_multiplier,
                attack_speed=attack_speed,
                impact=impact_damage,
                puncture=puncture_damage,
                slash=slash_damage,
                elem=elem,
                elem_dmg=elem_dmg,
                attack_data=attack_data,
                note=note,
                initial_combo_count=initial_combo_count,
                initial_heavy_multiplier=initial_heavy_multiplier,
            )
        )

    return add_legacy_skin_variants(weapons, resolver)


def matching_stances(tree_doc: PackageDoc | None, stances: list[StanceInfo]) -> list[StanceInfo]:
    if tree_doc is None:
        return []

    tree_tags = set(tree_doc.value.get("CompatibilityTags", []) or [])
    matches: list[StanceInfo] = []
    seen: set[str] = set()

    for stance in stances:
        exact_tree = stance.tree_package == tree_doc.package_id
        tag_match = bool(
            tree_tags and stance.compatibility_tags and tree_tags & stance.compatibility_tags
        )
        if (exact_tree or tag_match) and stance.stance_id not in seen:
            matches.append(stance)
            seen.add(stance.stance_id)

    return matches
