"""Static configuration and workbook schemas."""

from __future__ import annotations

MELEE_ROOT_PACKAGE = "/Lotus/Weapons/Tenno/Melee"
WEAPON_SCAN_ROOT_PACKAGE = "/Lotus/Weapons"
MELEE_SWEEP_TYPES = {
    "/EE/Types/Game/WeaponMeleeSweepFireBehavior",
    "/Lotus/Types/Weapon/DarkSectorMeleeSweepFireBehavior",
}
MELEE_SWEEP_MARKERS = tuple(sweep_type.rsplit("/", 1)[-1] for sweep_type in MELEE_SWEEP_TYPES)
MELEE_IMPACT_TYPE = "/Lotus/Types/Game/MeleeImpactBehavior"
PVP_STANCE_ROOT = "/Lotus/Upgrades/Mods/PvPMods/Stances"
PVP_STANCE_NAME_SOURCE = "https://wiki.warframe.com/w/Stance#Conclave-Exclusive_Stance_Mods"
CORE_PVP_SLAM_EVENTS = {
    "MeleeSlam": "Slam Attack",
    "HeavySlam": "Heavy Slam Attack",
}
CORE_PVP_SLAM_EVENT_ORDER = tuple(CORE_PVP_SLAM_EVENTS)
CORE_PVP_SLAM_EVENTS_BY_KIND = {label: event for event, label in CORE_PVP_SLAM_EVENTS.items()}
SLAM_CONTEXT_SOURCE = "weapon PvpSlams TriggeringAnimEvent"
IGNORED_DAMAGE_COMBO_CONTEXTS = {
    "CC_ATTACK_BLOCKED",
    "CC_DOWNED_ENEMY",
    "CC_PARRY_HEAVY",
    "CC_SLIDING",
}
CATEGORY_LIMITED_DAMAGE_COMBO_CONTEXTS = {
    "CC_AIR_RIGHT": {"Tonfa"},
}
IGNORED_WEAPON_BASENAMES = {
    "CaptainVorCronusLongSword",
    "DarkDaggerBase",
    "LightGlaiveWeaponVariant",
    "DuviriGrappleGlaiveWep",
    "NekrosDeluxeScytheWeapon",
    "VariantXmasScythe",
    "TnStaffNewPlayerXp",
    "DaxDuviriKatanaSwordAi",
    "UndercroftDaxDuviriKatanaSwordAi",
    "DaxDuviriTwoHandedKatanaWeaponAi",
    "GladiusSword",
    "GladiusDungeonEncounterSword",
    "VariantKatana",
    "AiStalkerTwoGreatSword",
    "StalkerTwoGreatSwordQuest",
    "DaxDuviriHammerPlayerWeapon",
    "DaxDuviriKatanaPlayerWeapon",
    "PrimeNikanaTennoCon",
    "DaxDuviriKatanaSword",
    "ArchonDualDaggersWep",
    "GrnMiniSawMeleeWeapon",
    "DrifterTazerWep",
    "ArchonTridentWep",
    "GrineerStaffWeapon",
    "TauDaxMedicStaff",
    "Skana1999Weapon",
    "TauDaxHeavyHammer",
    "DrillbitArmWeapon",
    "InfestedZekeWhipWeapon",
    "TauDaxKatana",
    "DualKamasLettieQuestWeapon",
    "TNWQuestBallasSwordWeapon",
}
FORCED_PVP_WEAPON_IDS = {
    "/Lotus/Weapons/Tenno/Melee/Swords/DarkSword/DarkSwordDaggerSingle",
}
EMBEDDED_NO_STANCE_TREES = {
    "/Lotus/Weapons/Orokin/BallasSword/BallasSwordWeapon": (
        "Tempo Royale",
        "DefaultModOverrides.Stance",
        "/Lotus/Weapons/Tenno/Melee/MeleeTrees/AxeCmbThreeMeleeTree",
    ),
    "/Lotus/Weapons/Tenno/Melee/Swords/StalkerTwo/StalkerTwoSmallSword": (
        "Vengeful Revenant",
        "MeleeTreeType",
        "/Lotus/Weapons/Tenno/Melee/MeleeTrees/StalkerSwordMeleeTree",
    ),
}
REMOVE_STANCELESS_ONLY_WEAPON_IDS = {
    "/Lotus/Weapons/Tenno/Melee/Swords/DarkSword/DarkSwordDaggerDuals",
    *EMBEDDED_NO_STANCE_TREES,
}
SPECIAL_WEAPON_NOTES = {
    "/Lotus/Weapons/Tenno/Melee/Swords/DarkSword/DarkSwordDaggerDuals": "Dual melee mode requires the dual-sword PvP stance; no-stance behavior belongs to heavy sword mode",
    "/Lotus/Weapons/Tenno/Melee/Swords/DarkSword/DarkSwordDaggerSingle": "Forced include: heavy sword mode is PvP-usable despite AvailableOnPvp metadata",
    "/Lotus/Weapons/Tenno/Melee/SwordsAndBoards/SundialSwordBoard/SundialBoardSword": "Unique aerial shield throw: SupportAirThrow=1 and PvP projectile ShieldProjectilePvP in weapon fire behavior",
}
STANCELESS_CATEGORY_NAMES = {"Broken War (stanceless)", "Paracesis (stanceless)"}
ACTUAL_STANCE_NAME_ORDER = (
    "Tainted Hydra",
    "Scarlet Hurricane",
    "Piercing Fury",
    "Biting Piranha",
    "Dividing Blades",
    "Quaking Hand",
    "Celestial Nightfall",
    "Crashing Havoc",
    "Noble Cadence",
    "Rending Wind",
    "Fateful Truth",
    "Mafic Rain",
    "Argent Scourge",
    "Cunning Aspect",
    "Shadow Harvest",
    "Vicious Approach",
    "Crashing Timber",
    "Rising Steel",
    "Last Herald",
    "Star Divide",
    "Lashing Coil",
    "Vengeful Revenant",
    "Tempo Royale",
)
ACTUAL_STANCE_NAMES = set(ACTUAL_STANCE_NAME_ORDER)
ACTUAL_STANCE_ORDER = {name: index for index, name in enumerate(ACTUAL_STANCE_NAME_ORDER, start=1)}
PVP_STANCE_NAMES_BY_BASENAME = {
    "PvPClawStanceOne": "Scarlet Hurricane",
    "PvPDaggerStanceOne": "Piercing Fury",
    "PvPDualDaggersStanceOne": "Biting Piranha",
    "PvPDualSwordStanceOne": "Dividing Blades",
    "PvPFistStanceOne": "Quaking Hand",
    "PvPGlaiveStanceOne": "Celestial Nightfall",
    "PvPHammerStanceOne": "Crashing Havoc",
    "PvPHeavyBladeStanceOne": "Noble Cadence",
    "PvPKatanaStanceOne": "Fateful Truth",
    "PvPMacheteStanceOne": "Rending Wind",
    "PvPNunchakuStanceOne": "Mafic Rain",
    "PvPPolearmStanceOne": "Argent Scourge",
    "PvPPunchKickStanceOne": "Vicious Approach",
    "PvPRapierStanceOne": "Cunning Aspect",
    "PvPScytheStanceOne": "Shadow Harvest",
    "PvPStavesStanceOne": "Crashing Timber",
    "PvPSwordShieldStanceOne": "Last Herald",
    "PvPSwordStanceOne": "Rising Steel",
    "PvPSwordWhipStanceOne": "Tainted Hydra",
    "PvPTonfaStanceOne": "Star Divide",
    "PvPWhipStanceOne": "Lashing Coil",
}
SPECIAL_STANCE_NAMES_BY_BASENAME = {
    "TennoballStanceOne": "Lunaro",
}
VARIANT_STANCE_CATEGORIES_BY_BASENAME = {
    "Claw": "Claws",
    "DualDaggers": "Dual Daggers",
    "DualSword": "Dual Swords",
    "Fist": "Fist",
    "Glaive": "Glaive",
    "Hammer": "Hammer",
    "HeavyBlade": "Heavy Blade",
    "Katana": "Nikana",
    "Machete": "Machete",
    "Nunchaku": "Nunchaku",
    "Polearm": "Polearm",
    "PunchKick": "Sparring",
    "Rapier": "Rapier",
    "Scythe": "Scythe",
    "Staves": "Staff",
    "SwordShield": "Sword and Shield",
    "SwordWhip": "Blade and Whip",
    "Sword": "Sword",
    "Whip": "Whip",
}
WEAPON_NAME_OVERRIDES = {
    "/Lotus/Weapons/Tenno/Melee/Swords/DarkSword/DarkSwordDaggerDuals": "Dark Split-Sword (dual melee mode)",
    "/Lotus/Weapons/Tenno/Melee/Swords/DarkSword/DarkSwordDaggerSingle": "Dark Split-Sword (heavy sword mode)",
    "/Lotus/Weapons/Orokin/BallasSword/BallasSwordWeapon": "Paracesis",
    "/Lotus/Weapons/Syndicates/SteelMeridian/Melee/SMSydon": "Vaykor Sydon",
    "/Lotus/Weapons/Syndicates/CephalonSuda/Melee/CSHeliocor": "Synoid Heliocor",
    "/Lotus/Weapons/Infested/Melee/Staff/InfStaff/InfStaff": "Pupacyst",
    "/Lotus/Weapons/Grineer/Melee/GrnSparring/GrnSpiderSparring/GrnSpiderSparring": "Korrudo",
    "/Lotus/Weapons/MK1Series/MK1Bo": "MK1-Bo",
    "/Lotus/Weapons/MK1Series/MK1Furax": "MK1-Furax",
    "/Lotus/Weapons/Tenno/Melee/SwordsAndBoards/SundialSwordBoard/SundialBoardSword": "Sigma and Octantis",
    "/Lotus/Weapons/Tenno/Melee/SwordsAndBoards/MeleeContestWinnerOne/TennoSwordShield": "Silva and Aegis",
    "/Lotus/Weapons/Tenno/Melee/PrimeSilvaAegis/PrimeSilvaAegis": "Silva and Aegis Prime",
    "/Lotus/Weapons/Tenno/Melee/DualKamas/DualKamas": "Dual Kamas",
    "/Lotus/Weapons/Tenno/Melee/DualShortSword/DualShortSword": "Dual Skana",
}
WEAPON_CATEGORY_OVERRIDES = {
    "/Lotus/Weapons/Tenno/Melee/Swords/DarkSword/DarkSwordDaggerDuals": "Dual Swords",
    "/Lotus/Weapons/Tenno/Melee/Swords/DarkSword/DarkSwordDaggerSingle": "Heavy Blade",
}
CANONICAL_WEAPON_CATEGORIES = {
    "Axes": "Heavy Blade",
    "Claws": "Claws",
    "Daggers": "Dagger",
    "Dual Daggers": "Dual Daggers",
    "Dual Katana": "Dual Nikanas",
    "Dual Katanas": "Dual Nikanas",
    "Dual Swords": "Dual Swords",
    "Fists": "Fist",
    "Glaives": "Glaive",
    "Gunblade": "Gunblade",
    "Hammers": "Hammer",
    "Heavy Scythes": "Heavy Scythe",
    "Katanas": "Nikana",
    "Long Katanas": "Two-Handed Nikana",
    "Machete": "Machete",
    "Nunchaku": "Nunchaku",
    "Pole Arms": "Polearm",
    "Punch Kick": "Sparring",
    "Rapier": "Rapier",
    "Saw": "Assault Saw",
    "Scythes": "Scythe",
    "Staves": "Staff",
    "Sword Shield": "Sword and Shield",
    "Sword Whip": "Blade and Whip",
    "Swords": "Sword",
    "Tonfa": "Tonfa",
    "War Fan": "Warfan",
    "Warfan": "Warfan",
    "Whips": "Whip",
}
CATEGORY_KEYWORDS = (
    ("sword shield", "Sword and Shield"),
    ("shield sword", "Sword and Shield"),
    ("sword whip", "Blade and Whip"),
    ("whip sword", "Blade and Whip"),
    ("blade whip", "Blade and Whip"),
    ("dual dagger", "Dual Daggers"),
    ("dual sword", "Dual Swords"),
    ("dual katana", "Dual Nikanas"),
    ("dual nikana", "Dual Nikanas"),
    ("long katana", "Two-Handed Nikana"),
    ("two handed katana", "Two-Handed Nikana"),
    ("two handed nikana", "Two-Handed Nikana"),
    ("heavy scythe", "Heavy Scythe"),
    ("gunblade", "Gunblade"),
    ("punch kick", "Sparring"),
    ("kick punch", "Sparring"),
    ("sparring", "Sparring"),
    ("fighting", "Sparring"),
    ("pole arm", "Polearm"),
    ("polearm", "Polearm"),
    ("nunchaku", "Nunchaku"),
    ("nunchuck", "Nunchaku"),
    ("war fan", "Warfan"),
    ("warfan", "Warfan"),
    ("assault saw", "Assault Saw"),
    ("glaive", "Glaive"),
    ("claw", "Claws"),
    ("fist", "Fist"),
    ("dagger", "Dagger"),
    ("katana", "Nikana"),
    ("nikana", "Nikana"),
    ("machete", "Machete"),
    ("scythe", "Scythe"),
    ("hammer", "Hammer"),
    ("staff", "Staff"),
    ("stave", "Staff"),
    ("tonfa", "Tonfa"),
    ("rapier", "Rapier"),
    ("whip", "Whip"),
    ("axe", "Heavy Blade"),
    ("sword", "Sword"),
    ("saw", "Assault Saw"),
)
PHYSICAL_TYPES = ("DT_IMPACT", "DT_PUNCTURE", "DT_SLASH")
DAMAGE_TYPES = (
    "DT_IMPACT",
    "DT_PUNCTURE",
    "DT_SLASH",
    "DT_FIRE",
    "DT_FREEZE",
    "DT_ELECTRICITY",
    "DT_POISON",
    "DT_EXPLOSION",
    "DT_RADIATION",
    "DT_GAS",
    "DT_MAGNETIC",
    "DT_VIRAL",
    "DT_CORROSIVE",
    "DT_RADIANT",
    "DT_SENTIENT",
    "DT_CINEMATIC",
    "DT_SHIELD_DRAIN",
    "DT_HEALTH_DRAIN",
    "DT_ENERGY_DRAIN",
    "DT_FINISHER",
)


PIVOT_HEADERS = [
    "weapon_name",
    "weapon_category",
    "stance_equipped",
    "combo",
    "attack_index",
    "hit_index / hit_count",
    "base_damage",
    "pvp_damage_multiplier",
    "attack_pvp_damage_atten",
    "quant",
    "quant_multiplier",
    "final_damage",
    "note",
    "weapon_id",
    "stance_id",
    "attack_set_combo_id",
    "combo_context",
    "attack_id",
]
FACT_HEADERS = PIVOT_HEADERS

TOTAL_HEADERS = [
    "weapon_name",
    "weapon_category",
    "stance_equipped",
    "combo",
    "attack_count",
    "hit_count",
    "damage_instances",
    "total_damage",
    "note",
    "weapon_id",
    "stance_id",
    "attack_set_combo_id",
    "combo_context",
]

SLAM_HEADERS = [
    "weapon_name",
    "weapon_category",
    "slam_kind",
    "final_damage",
    "base_damage",
    "pvp_damage_multiplier",
    "slam_damage_atten",
    "quant",
    "quant_multiplier",
    "radius",
    "edge_damage_multiplier",
    "can_use_combo_multiplier",
    "slam_attack_data_amount",
    "damage_type",
    "proc_chance",
    "forced_procs",
    "note",
    "weapon_id",
]

WARNING_HEADERS = ["severity", "message", "ref"]
SEVERITY_ORDER = {"error": 0, "warning": 1, "ignored": 2, "note": 3}

WEAPON_DIM_HEADERS = [
    "weapon_name",
    "weapon_category",
    "base_damage",
    "pvp_damage_multiplier",
    "quant",
    "quant_multiplier",
    "slam_damage",
    "heavy_slam_damage",
    "slam_radius",
    "heavy_slam_radius",
    "note",
    "weapon_id",
    "weapon_key",
]

STANCE_DIM_HEADERS = [
    "stance_name",
    "weapon_category",
    "weapon_count",
    "combo_count",
    "note",
    "stance_id",
    "stance_key",
]

COMBO_DIM_HEADERS = [
    "weapon_category",
    "stance_equipped",
    "combo",
    "attack_count",
    "hit_count",
    "stance_id",
    "attack_set_combo_id",
    "combo_context",
    "combo_key",
]
ATTACK_DIM_HEADERS = [
    "weapon_category",
    "stance_equipped",
    "combo",
    "attack_index",
    "hit_index / hit_count",
    "attack_pvp_damage_atten",
    "stance_id",
    "attack_set_combo_id",
    "combo_context",
    "attack_id",
    "attack_key",
]

ENUM_REFERENCE_SOURCE = "https://wiki.warframe.com/w/Module:Enum/data"
COMBO_CONTEXT_HEADERS = ["combo_context", "human_readable", "damage_export", "source"]
COMBO_CONTEXT_SOURCE = "https://wiki.warframe.com/w/Stance#All_Combos"
COMBO_CONTEXT_ENUM_CONTEXTS = {
    "CC_AIR",
    "CC_AIR_RIGHT",
    "CC_DOWNED_ENEMY",
    "CC_GROUND",
    "CC_GROUND_BRANCH_A",
    "CC_GROUND_BRANCH_B",
    "CC_GROUND_BRANCH_C",
    "CC_GROUND_HEAVY",
    "CC_SLIDING",
    "CC_SLIDING_PVP",
    "CC_WALLRUN",
}
COMBO_CONTEXT_LABELS = {
    "CC_GROUND": "Neutral combo",
    "CC_GROUND_BRANCH_A": "Forward combo",
    "CC_GROUND_BRANCH_B": "Forward + block combo",
    "CC_GROUND_BRANCH_C": "Block combo",
    "CC_GROUND_HEAVY": "Heavy attack",
    "CC_SLIDING": "Slide attack",
    "CC_SLIDING_PVP": "PvP slide attack",
    "CC_AIR": "Aerial attack",
    "CC_AIR_RIGHT": "Aerial right attack",
    "CC_WALLRUN": "Wall attack",
    "CC_DOWNED_ENEMY": "Downed enemy attack",
    "CC_ATTACK_BLOCKED": "Blocked attack",
    "CC_PARRY_HEAVY": "Heavy parry attack",
    "MeleeSlam": "Slam Attack",
    "HeavySlam": "Heavy Slam Attack",
}
