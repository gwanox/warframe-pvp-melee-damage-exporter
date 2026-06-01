"""Command line interface and lightweight self-tests."""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

from .constants import MELEE_IMPACT_TYPE
from .damage import calculate_final_damage, find_melee_impact, quant_info
from .labels import clean_weapon_category
from .models import PackageDoc, WeaponInfo
from .resolver import Resolver
from .rows import build_rows, sliding_pvp_charge_note
from .slams import build_slam_hit_rows, build_slam_rows
from .workbook import write_workbook

def run_self_tests() -> None:
    tests = [
        ("Dual Keres slide", 115, 0.48699999, 2, Decimal(33) / Decimal(32), 116),
        ("Dark Split-Sword dual slide", 116, 0.88, 2, Decimal(1), 204),
        ("Kronen PvP slide", 130, 0.454, 6, Decimal(1), 354),
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
            raise AssertionError(f"Category cleanup failed: expected {expected_category}, got {actual_category}")

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
        raise AssertionError("DarkSector melee sweep behavior was not detected as melee impact data")

    charge_note = sliding_pvp_charge_note(
        "CC_SLIDING_PVP",
        "/Lotus/Weapons/Tenno/Melee/AttackSets/TonfaMelee30ChargeB",
        ["/Lotus/Weapons/Tenno/Melee/Attacks/TonfaMelee30ChargeB"],
    )
    if not charge_note:
        raise AssertionError("CC_SLIDING_PVP charge mapping note was not detected")

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
        attack_data={"Type": "DT_IMPACT", "Amount": 100},
    )
    slam_rows = build_slam_rows(Resolver(Path(".")), [slam_weapon])
    slam_by_kind = {row["slam_kind"]: row for row in slam_rows}
    if slam_by_kind["Slam Attack"]["final_damage"] != 50:
        raise AssertionError(f"Slam damage failed: {slam_by_kind['Slam Attack']['final_damage']}")
    if slam_by_kind["Heavy Slam Attack"]["final_damage"] != 200:
        raise AssertionError(f"Heavy slam damage failed: {slam_by_kind['Heavy Slam Attack']['final_damage']}")
    slam_hit_rows = build_slam_hit_rows(slam_rows)
    slam_hit_by_context = {row["combo_context"]: row for row in slam_hit_rows}
    if slam_hit_by_context["MeleeSlam"]["final_damage"] != 50:
        raise AssertionError("Normal slam was not converted to a hit-database row")
    if slam_hit_by_context["MeleeSlam"]["stance_equipped"] != "any":
        raise AssertionError("Slam hit rows should use stance_equipped = any")
    if slam_hit_by_context["HeavySlam"]["attack_pvp_damage_atten"] != 4:
        raise AssertionError("Heavy slam attenuation was not preserved in the hit-database row")

    print("Self-test passed.")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Warframe metadata root containing Lotus/")
    parser.add_argument("--output", default="Melee_attack_dmg_analysis/pvp_melee_damage.xlsx", help="Output .xlsx path")
    parser.add_argument(
        "--layout",
        choices=("thematic", "raw", "compact", "full"),
        default="thematic",
        help="thematic writes normalized raw sheets; compact is an alias; raw writes one denormalized sheet; full writes older Excel table sheets",
    )
    parser.add_argument("--self-test", action="store_true", help="Run calculation self-tests and exit")
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
    rows, totals, slam_rows, warnings, misc_stances = build_rows(root)
    write_workbook(output, rows, totals, slam_rows, warnings, misc_stances, " ".join([Path(sys.argv[0]).name, *sys.argv[1:]]), layout)
    print(f"Wrote {output}")
    print(f"Layout: {layout}")
    print(f"Hit rows: {len(rows)}")
    print(f"Internal combo groups: {len(totals)}")
    print(f"Slam rows: {len(slam_rows)}")
    print(f"Warnings rows: {len(warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
