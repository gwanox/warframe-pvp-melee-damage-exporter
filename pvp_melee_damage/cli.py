"""Command line interface and lightweight self-tests."""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

from .attack_sets import iter_attack_set_entries
from .combo import attack_combo_multiplier
from .constants import MELEE_IMPACT_TYPE
from .damage import (
    calculate_final_damage,
    find_melee_attack_speed,
    find_melee_impact,
    find_melee_initial_combo,
    quant_info,
    weapon_damage_components,
)
from .labels import clean_weapon_category
from .models import PackageDoc, WeaponInfo
from .resolver import Resolver
from .rows import (
    TONFA_STANCE_SLIDE_ATTACK_ID,
    attack_hit_attens,
    build_rows,
    collapse_dimension_rows,
    should_export_combo_context,
    sliding_pvp_charge_note,
)
from .skins import (
    LEGACY_SKIN_SPECS,
    make_legacy_skin_variant,
    read_legacy_skin_effects,
)
from .slams import build_slam_hit_rows, build_slam_rows
from .workbook import write_workbook


def run_self_tests() -> None:
    tests = [
        ("Dual Keres slide", 115, 0.48699999, 2, Decimal(33) / Decimal(32), 116),
        ("Dark Split-Sword dual slide", 116, 0.88, 2, Decimal(1), 204),
        ("Kronen stanceless slide", 130, 0.454, 6, Decimal(1), 354),
        ("Kronen stance slide hit", 130, 0.454, 1, Decimal(1), 59),
        ("Furax Wraith slide", 139, 0.45300001, 3, Decimal(1), 189),
    ]

    for name, base_damage, pvp_multiplier, atten, quant_multiplier, expected in tests:
        actual, raw = calculate_final_damage(base_damage, pvp_multiplier, atten, quant_multiplier)
        if actual != expected:
            raise AssertionError(f"{name}: expected {expected}, got {actual} from raw {raw}")

    dual_keres_quant, dual_keres_multiplier, _ = quant_info(
        {
            "Type": "DT_PHYSICAL",
            "DT_IMPACT": 0.12,
            "DT_PUNCTURE": 0.30000001,
            "DT_SLASH": 0.57999998,
            "Amount": 115,
        }
    )
    if dual_keres_quant != "positive (33/32)" or dual_keres_multiplier != Decimal(33) / Decimal(32):
        raise AssertionError(f"Dual Keres quant failed: {dual_keres_quant} {dual_keres_multiplier}")

    elemental_quant, elemental_multiplier, _ = quant_info({"Type": "DT_RADIATION", "Amount": 116})
    if elemental_quant != "n/a" or elemental_multiplier != Decimal(1):
        raise AssertionError(f"Elemental quant failed: {elemental_quant} {elemental_multiplier}")

    category_tests = {
        "/Lotus/Language/Items/WhipsCategoryName": "Whip",
        "/Lotus/Language/Items/AxesCategoryName": "Heavy Blade",
        "/Lotus/Language/Items/SwordShieldCategoryName": "Sword and Shield",
        "/Lotus/Language/Items/LongKatanasCategoryName": "Two-Handed Nikana",
    }
    for raw_category, expected_category in category_tests.items():
        actual_category = clean_weapon_category(raw_category)
        if actual_category != expected_category:
            raise AssertionError(
                f"Category cleanup failed: expected {expected_category}, got {actual_category}"
            )

    dark_sector_impact = find_melee_impact(
        {
            "Behaviors": [
                {
                    "fire:Type": "/Lotus/Types/Weapon/DarkSectorMeleeSweepFireBehavior",
                    "fire:DarkSectorMeleeSweepFireBehavior": {},
                    "impact:Type": MELEE_IMPACT_TYPE,
                    "impact:MeleeImpactBehavior": {
                        "AttackData": {"Amount": 230},
                        "PvpDamageMultiplier": 0.31,
                    },
                }
            ]
        }
    )
    if dark_sector_impact is None:
        raise AssertionError(
            "DarkSector melee sweep behavior was not detected as melee impact data"
        )

    attack_speed = find_melee_attack_speed(
        {
            "Behaviors": [
                {
                    "fire:Type": "/EE/Types/Game/WeaponMeleeSweepFireBehavior",
                    "impact:Type": MELEE_IMPACT_TYPE,
                    "impact:MeleeImpactBehavior": {"AttackData": {"Amount": 100}},
                    "state:LotusMeleeStateBehavior": {"fireRate": 55},
                }
            ]
        }
    )
    if attack_speed != 0.917:
        raise AssertionError(
            f"Melee attack speed conversion failed: expected 0.917, got {attack_speed}"
        )

    initial_combo = find_melee_initial_combo(
        {
            "Behaviors": [
                {
                    "fire:Type": "/EE/Types/Game/WeaponMeleeSweepFireBehavior",
                    "impact:Type": MELEE_IMPACT_TYPE,
                    "impact:MeleeImpactBehavior": {
                        "AttackData": {"Amount": 100},
                        "InitialHitCounter": 30,
                        "BaseHitCount": 20,
                        "BaseHitMultipler": 1,
                        "HitReqNextTierOperator": 20,
                        "HitReqNextTierOperationType": "HTO_ADDITIVE",
                    },
                }
            ]
        }
    )
    if initial_combo != (30, 2.0):
        raise AssertionError(f"Initial combo multiplier failed: {initial_combo}")

    old_format_components = weapon_damage_components(
        {
            "UseNewFormat": 0,
            "Type": "DT_PHYSICAL",
            "Amount": 120,
            "DT_IMPACT": 0.05,
            "DT_PUNCTURE": 0.2,
            "DT_SLASH": 0.75,
        }
    )
    if old_format_components != (6.0, 24.0, 90.0, "", 0):
        raise AssertionError(f"Old-format damage components failed: {old_format_components}")

    elemental_only_components = weapon_damage_components(
        {"UseNewFormat": 0, "Type": "DT_FIRE", "Amount": 98}
    )
    if elemental_only_components != (0, 0, 0, "Heat", 98):
        raise AssertionError(
            f"Elemental-only damage components failed: {elemental_only_components}"
        )

    skin_resolver = Resolver(Path("."))
    manticore_doc = PackageDoc(
        path=Path("GrnAxe.json"),
        packages=[],
        package_id="/Lotus/Upgrades/Skins/HeavyAxe/GrnAxe",
        first_value={},
        value={
            "Weapon": "/Lotus/Weapons/Test/Scindo",
            "Upgrades": [
                {
                    "UpgradeType": "WEAPON_MELEE_DAMAGE",
                    "OperationType": "STACKING_MULTIPLY",
                    "Value": 0.15,
                },
                {
                    "UpgradeType": "WEAPON_FIRE_RATE",
                    "OperationType": "MULTIPLY",
                    "Value": 0.85,
                },
            ],
        },
    )
    manticore_effects = read_legacy_skin_effects(manticore_doc, skin_resolver)
    skin_base_weapon = WeaponInfo(
        doc=manticore_doc,
        weapon_id="/Lotus/Weapons/Test/Scindo",
        weapon_name="Scindo",
        category="Heavy Blade",
        tree_ref="/Lotus/Weapons/Test/AxeTree",
        base_damage=200,
        pvp_multiplier=0.4,
        attack_speed=1.0,
        impact=20,
        puncture=40,
        slash=140,
        elem="",
        elem_dmg=0,
        attack_data={
            "UseNewFormat": 0,
            "Type": "DT_PHYSICAL",
            "Amount": 200,
            "DT_IMPACT": 0.1,
            "DT_PUNCTURE": 0.2,
            "DT_SLASH": 0.7,
        },
    )
    manticore_variant = make_legacy_skin_variant(
        skin_base_weapon,
        "Scindo with Manticore Skin",
        LEGACY_SKIN_SPECS[0],
        manticore_doc,
        manticore_effects,
    )
    if manticore_variant.base_damage != 230 or manticore_variant.attack_speed != 0.85:
        raise AssertionError("Manticore damage or attack-speed modifier failed")
    if (
        manticore_variant.impact,
        manticore_variant.puncture,
        manticore_variant.slash,
    ) != (23.0, 46.0, 161.0):
        raise AssertionError("Manticore old-format damage components were not scaled correctly")

    brokk_doc = PackageDoc(
        path=Path("GrnHammer.json"),
        packages=[],
        package_id="/Lotus/Upgrades/Skins/Hammer/GrnHammer",
        first_value={},
        value={
            "Weapon": "/Lotus/Weapons/Test/Fragor",
            "Upgrades": [
                {
                    "UpgradeType": "WEAPON_FIRE_RATE",
                    "OperationType": "STACKING_MULTIPLY",
                    "Value": 0.05,
                },
                {
                    "UpgradeType": "WEAPON_MELEE_COMBO_DURATION_BONUS",
                    "OperationType": "ADD",
                    "Value": -1,
                },
            ],
        },
    )
    brokk_effects = read_legacy_skin_effects(brokk_doc, skin_resolver)
    if brokk_effects.attack_speed_multiplier != 1.05:
        raise AssertionError("Brokk attack-speed modifier failed")
    if brokk_effects.combo_duration_bonus != -1:
        raise AssertionError("Brokk combo-duration modifier failed")
    skin_base_weapon.initial_combo_count = 30
    skin_base_weapon.initial_heavy_multiplier = 2
    if attack_combo_multiplier(skin_base_weapon, "CC_GROUND_HEAVY") != 2:
        raise AssertionError("Initial combo was not applied to a ground heavy attack")
    if attack_combo_multiplier(skin_base_weapon, "CC_GROUND") != 1:
        raise AssertionError("Initial combo was applied to a normal attack")
    if should_export_combo_context("CC_AIR_RIGHT", "Sword", False):
        raise AssertionError("Non-Tonfa CC_AIR_RIGHT should be disabled by default")
    if not should_export_combo_context("CC_AIR_RIGHT", "Sword", True):
        raise AssertionError("Non-Tonfa CC_AIR_RIGHT option did not enable the context")
    if not should_export_combo_context("CC_AIR_RIGHT", "Tonfa", False):
        raise AssertionError("Tonfa CC_AIR_RIGHT should always be exported")
    for context in (
        "CC_ATTACK_BLOCKED",
        "CC_DOWNED_ENEMY",
        "CC_GUARD_BROKEN",
        "CC_PARRY_HEAVY",
    ):
        if should_export_combo_context(context, "Sword", False):
            raise AssertionError(f"{context} should be disabled by default")
        if not should_export_combo_context(context, "Sword", False, True):
            raise AssertionError(f"{context} audit option did not enable the context")

    charge_note = sliding_pvp_charge_note(
        "CC_SLIDING_PVP",
        "EquippedAttackSets",
        "/Lotus/Weapons/Tenno/Melee/AttackSets/TonfaMelee30ChargeB",
        ["/Lotus/Weapons/Tenno/Melee/Attacks/TonfaMelee30ChargeB"],
    )
    if not charge_note.startswith("Excluded legacy source alias"):
        raise AssertionError("Equipped CC_SLIDING_PVP charge alias was not detected")
    if sliding_pvp_charge_note(
        "CC_SLIDING_PVP",
        "UnequippedAttackSets",
        "/Lotus/Weapons/Tenno/Melee/AttackSets/PVPSwordSlideDefaults",
        ["/Lotus/Weapons/Tenno/Melee/Attacks/PVPSwordSlideA"],
    ):
        raise AssertionError("Genuine unequipped CC_SLIDING_PVP slide data was excluded")
    if sliding_pvp_charge_note(
        "CC_GROUND_HEAVY",
        "EquippedAttackSets",
        "/Lotus/Weapons/Tenno/Melee/AttackSets/SwordMelee30ChargeA",
        ["/Lotus/Weapons/Tenno/Melee/Attacks/SwordMelee30ChargeA"],
    ):
        raise AssertionError("Normal heavy attack data was treated as a sliding alias")

    source_doc = PackageDoc(
        path=Path("SyntheticMeleeTree.json"),
        packages=[],
        package_id="/Lotus/Weapons/Test/SyntheticMeleeTree",
        first_value={},
        value={
            "UnequippedAttackSets": {"CC_GROUND": "/Lotus/Weapons/Test/Quick"},
            "EquippedAttackSets": {
                "CC_GROUND_HEAVY": "/Lotus/Weapons/Test/Heavy",
                "CC_GROUND_BRANCH_B": "/Lotus/Weapons/Test/BranchB",
            },
            "ContextFallbacks": [
                {"context": "CC_GROUND_BRANCH_C", "fallback": "CC_GROUND_BRANCH_B"}
            ],
        },
    )
    source_entries = iter_attack_set_entries(source_doc, Resolver(Path(".")))
    fallback_entries = [
        entry for entry in source_entries if entry.combo_context == "CC_GROUND_BRANCH_C"
    ]
    if (
        len(fallback_entries) != 1
        or fallback_entries[0].attack_set_ref != "/Lotus/Weapons/Test/BranchB"
    ):
        raise AssertionError("ContextFallbacks was not expanded from the matching attack-set map")
    current_entries = iter_attack_set_entries(
        source_doc,
        Resolver(Path(".")),
        allowed_maps={"equipped"},
    )
    if any(entry.attack_set_ref.endswith("/Quick") for entry in current_entries):
        raise AssertionError("Legacy quick-melee attack set leaked into current attack rows")

    cleared_source_doc = PackageDoc(
        path=Path("SyntheticClearedMeleeTree.json"),
        packages=[],
        package_id="/Lotus/Weapons/Test/SyntheticClearedMeleeTree",
        first_value={},
        value={
            "EquippedAttackSets": {
                "CC_GROUND_BRANCH_B": "/Lotus/Weapons/Test/BranchB",
                "CC_GROUND_BRANCH_C": "",
            },
            "ContextFallbacks": [
                {"context": "CC_GROUND_BRANCH_C", "fallback": "CC_GROUND_BRANCH_B"}
            ],
        },
    )
    cleared_entries = iter_attack_set_entries(
        cleared_source_doc,
        Resolver(Path(".")),
        allowed_maps={"equipped"},
    )
    if any(entry.combo_context == "CC_GROUND_BRANCH_C" for entry in cleared_entries):
        raise AssertionError("ContextFallbacks revived an explicitly cleared context")

    tonfa_slide_doc = PackageDoc(
        path=Path("PVPTonfaSlideAEquipped.json"),
        packages=[],
        package_id=TONFA_STANCE_SLIDE_ATTACK_ID,
        first_value={},
        value={
            "AttackProperties": {"BaseDamageAtten": 6},
            "PerSwingOverrides": [{"overrideAttackProperties": 0}],
        },
    )
    if attack_hit_attens(tonfa_slide_doc) != [1.0, 1.0]:
        raise AssertionError("Tonfa stance slide runtime hits were not applied")

    collapsed = collapse_dimension_rows(
        [
            {"stance_equipped": "no", "attack_id": "same"},
            {"stance_equipped": "yes", "attack_id": "same"},
        ],
        ["stance_equipped", "attack_id"],
        "stance_equipped",
    )
    if len(collapsed) != 1 or collapsed[0]["stance_equipped"] != "any":
        raise AssertionError(
            "Identical base-tree and stance-derived rows should collapse to stance_equipped = any"
        )

    slam_doc = PackageDoc(
        path=Path("SyntheticSlamWeapon.json"),
        packages=[],
        package_id="/Lotus/Weapons/Test/SyntheticSlamWeapon",
        first_value={},
        value={
            "PvpSlams": [
                {
                    "TriggeringAnimEvent": "MeleeSlam",
                    "RadiusMin": 0,
                    "Radius": 3,
                    "FallOff": 1,
                    "FallOffMax": 0.5,
                    "CanUseComboMultiplier": 0,
                    "UseImpactBehaviorAttackDataAmount": 1,
                    "UseModifiedRadius": 1,
                    "BaseDamageAttenuation": 1,
                    "AttackData": {"Type": "DT_IMPACT", "Amount": 50, "ProcChance": 0.1},
                    "UseCurrentMeleeAttackForDamage": 0,
                    "MeleeAttack": "",
                },
                {
                    "TriggeringAnimEvent": "HeavySlam",
                    "RadiusMin": 0,
                    "Radius": 3,
                    "FallOff": 1,
                    "FallOffMax": 0.7,
                    "CanUseComboMultiplier": 1,
                    "UseImpactBehaviorAttackDataAmount": 1,
                    "UseModifiedRadius": 1,
                    "BaseDamageAttenuation": 4,
                    "AttackData": {"Type": "DT_IMPACT", "Amount": 50, "ProcChance": 0.1},
                    "UseCurrentMeleeAttackForDamage": 0,
                    "MeleeAttack": "/Lotus/Weapons/Tenno/Melee/Attacks/SlamAoE",
                },
            ]
        },
    )
    slam_weapon = WeaponInfo(
        doc=slam_doc,
        weapon_id=slam_doc.package_id,
        weapon_name="Synthetic Slam Weapon",
        category="Sword",
        tree_ref="/Lotus/Weapons/Tenno/Melee/MeleeTrees/SwordMeleeTree",
        base_damage=100,
        pvp_multiplier=0.5,
        attack_speed=1.0,
        impact=100,
        puncture=0,
        slash=0,
        elem="",
        elem_dmg=0,
        attack_data={"Type": "DT_IMPACT", "Amount": 100},
        initial_combo_count=30,
        initial_heavy_multiplier=2,
    )
    slam_rows = build_slam_rows(Resolver(Path(".")), [slam_weapon])
    slam_by_kind = {row["slam_kind"]: row for row in slam_rows}
    if slam_by_kind["Slam Attack"]["final_damage"] != 50:
        raise AssertionError(f"Slam damage failed: {slam_by_kind['Slam Attack']['final_damage']}")
    if slam_by_kind["Heavy Slam Attack"]["final_damage"] != 400:
        raise AssertionError(
            f"Heavy slam damage failed: {slam_by_kind['Heavy Slam Attack']['final_damage']}"
        )
    slam_hit_rows = build_slam_hit_rows(slam_rows)
    slam_hit_by_context = {row["combo_context"]: row for row in slam_hit_rows}
    if slam_hit_by_context["MeleeSlam"]["final_damage"] != 50:
        raise AssertionError("Normal slam was not converted to a hit-database row")
    if slam_hit_by_context["MeleeSlam"]["stance_equipped"] != "any":
        raise AssertionError("Slam hit rows should use stance_equipped = any")
    if slam_hit_by_context["HeavySlam"]["attack_pvp_damage_atten"] != 4:
        raise AssertionError("Heavy slam attenuation was not preserved in the hit-database row")
    if slam_hit_by_context["HeavySlam"]["final_damage"] != 400:
        raise AssertionError("Initial combo multiplier was not preserved in the slam hit row")

    print("Self-test passed.")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Warframe metadata root containing Lotus/")
    parser.add_argument(
        "--output",
        default="Melee_attack_dmg_analysis/pvp_melee_damage.xlsx",
        help="Output .xlsx path",
    )
    parser.add_argument(
        "--layout",
        choices=("thematic", "raw", "compact", "full"),
        default="thematic",
        help="thematic writes normalized raw sheets; compact is an alias; raw writes one denormalized sheet; full writes older Excel table sheets",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="Run calculation self-tests and exit"
    )
    parser.add_argument(
        "--include-non-tonfa-air-right",
        action="store_true",
        help="Include CC_AIR_RIGHT for non-Tonfa categories; disabled by default because its current PvP damage duplicates CC_AIR",
    )
    parser.add_argument(
        "--include-unverified-pvp-contexts",
        action="store_true",
        help="Include CC_ATTACK_BLOCKED, CC_DOWNED_ENEMY, CC_GUARD_BROKEN, and CC_PARRY_HEAVY for source-data auditing",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(sys.argv[1:] if argv is None else argv))

    if args.self_test:
        run_self_tests()
        return 0

    root = Path(args.root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output

    layout = "thematic" if args.layout == "compact" else args.layout
    rows, totals, slam_rows, warnings, misc_stances = build_rows(
        root,
        include_non_tonfa_air_right=args.include_non_tonfa_air_right,
        include_unverified_pvp_contexts=args.include_unverified_pvp_contexts,
    )
    write_workbook(
        output,
        rows,
        totals,
        slam_rows,
        warnings,
        misc_stances,
        " ".join([Path(sys.argv[0]).name, *sys.argv[1:]]),
        layout,
        include_non_tonfa_air_right=args.include_non_tonfa_air_right,
        include_unverified_pvp_contexts=args.include_unverified_pvp_contexts,
    )
    print(f"Wrote {output}")
    print(f"Layout: {layout}")
    print(
        f"Non-Tonfa CC_AIR_RIGHT: {'included' if args.include_non_tonfa_air_right else 'excluded'}"
    )
    print(
        "Unverified PvP contexts: "
        f"{'included' if args.include_unverified_pvp_contexts else 'excluded'}"
    )
    print(f"Hit rows: {len(rows)}")
    print(f"Internal combo groups: {len(totals)}")
    print(f"Slam rows: {len(slam_rows)}")
    print(f"Warnings rows: {len(warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
