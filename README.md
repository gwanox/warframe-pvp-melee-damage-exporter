# Warframe PvP Melee Damage Exporter

Export Warframe PvP melee attack and slam damage metadata from extracted JSON into a pivot-ready Excel workbook.

The exporter expects a metadata root that contains `Lotus/`, `EE/`, and the other extracted game-data folders. In this workspace, that root is the parent folder of this project.

## Quick Start

Install dependencies:

```powershell
py -m pip install -r requirements.txt
```

Run from the metadata root:

```powershell
py .\Melee_attack_dmg_analysis\export_pvp_melee_damage.py --root . --output .\Melee_attack_dmg_analysis\pvp_melee_damage.xlsx
```

Run from this project folder:

```powershell
py -m pvp_melee_damage --root .. --output .\Melee_attack_dmg_analysis\pvp_melee_damage.xlsx
```

Relative `--output` paths are resolved from `--root`.

Run the lightweight self-tests:

```powershell
py -m pvp_melee_damage --self-test
```

Generated `.xlsx` files are ignored by git by default.

## Project Layout

- `export_pvp_melee_damage.py`: compatibility wrapper for the package CLI.
- `pvp_melee_damage/cli.py`: argument parsing and self-tests.
- `pvp_melee_damage/constants.py`: workbook schemas, known overrides, and metadata IDs.
- `pvp_melee_damage/resolver.py`: JSON package inheritance and reference resolution.
- `pvp_melee_damage/discovery.py`: PvP melee weapon and stance discovery.
- `pvp_melee_damage/damage.py`: damage math, PvP attenuation, and IPS quantization.
- `pvp_melee_damage/slams.py`: PvP slam extraction and hit-row conversion.
- `pvp_melee_damage/rows.py`: normalized workbook row construction.
- `pvp_melee_damage/workbook.py`: Excel workbook writing.
- `pvp_melee_damage/labels.py`: readable weapon, category, and stance names.
- `pvp_melee_damage/utils.py`: small shared helpers.

## Data Resolution

- Scan all `Lotus/Weapons/**/*.json` files for melee sweep behavior markers, not only files under `Lotus/Weapons/Tenno/Melee`.
- Only include melee weapons whose effective weapon data has `"AvailableOnPvp": 1`.
- JSON files are package inheritance chains. Merge from the last/base package toward the first/derived package; earlier packages override later packages.
- Weapon copies often keep the useful base data in later packages. Example: `FuraxWraith` inherits from `Fist`, `LotusFist`, `PlayerMeleeWeapon`, and `LotusMeleeWeapon`.
- PvP stance files live under `Lotus/Upgrades/Mods/PvPMods/Stances`.
- The first stance package contains only PvP overrides. The later package is usually the base melee tree, such as `Lotus/Weapons/Tenno/Melee/MeleeTrees/FistMeleeTree`.
- Merge stance `EquippedAttackSets` and `UnequippedAttackSets` onto the base melee tree's attack sets.
- Resolve relative stance combo paths, such as `Combos/PvPFistComboA`, relative to the stance folder.
- Weapon categories are normalized to the public melee weapon type labels from <https://warframe.fandom.com/wiki/Category:Melee_Weapon_Type>; metadata suffixes such as `Category` are removed from cell values.
- PvP damage rows use only the actual Conclave stance names plus the embedded `Vengeful Revenant` and `Tempo Royale` exceptions. Misc stance packages such as variants and `TennoballStanceOne` are summarized once in `Stances` and excluded from damage sheets.
- Identical hit rows that appear in equipped and unequipped stance states are collapsed to one row with `stance_equipped = any`.
- Paracesis and Broken War have embedded no-stance trees in local metadata. Their unequipped PvP rows use those embedded trees; PvP stance rows still use the PvP stance override.

## Methodology

1. Resolve each JSON file as a package inheritance chain, merging from the last/base package toward the first/derived package.
2. Discover candidate melee weapons by scanning `Lotus/Weapons/**/*.json` for melee sweep behavior markers.
3. Include effective PvP melee weapons with `"AvailableOnPvp": 1`, plus explicit PvP exceptions such as Dark Split-Sword heavy sword mode.
4. Read base weapon damage and `PvpDamageMultiplier` from the melee sweep behavior's `MeleeImpactBehavior`.
5. Match PvP stances by inherited melee tree package or compatibility tags.
6. Name PvP stances from the Conclave-exclusive stance mod list; misc stance packages are excluded from damage rows and summarized once in `Stances`.
7. Resolve attack sets from the selected stance state. First-package PvP stance overrides replace inherited base tree slots.
8. Exclude non-damage or superseded combo contexts from calculated damage rows, and export category-limited contexts such as `CC_AIR_RIGHT` only for relevant categories.
9. Resolve each attack in attack-set order and export one visible damage row per hit/swing.
10. Calculate visible hit damage as `round_half_up(base_damage * pvp_multiplier * effective_attack_atten * quant_multiplier)`.
11. Use per-swing PvP attenuation when `overrideAttackProperties == 1`; otherwise use attack-level PvP attenuation, regular attack attenuation, then `1`.
12. Sum ordered visible hit values for combo totals. The workbook stores this as `damage_instances` before `total_damage`; multi-hit attacks are grouped with parentheses.

## Attack Sets

- Base attack sets live in `Lotus/Weapons/Tenno/Melee/AttackSets`.
- PvP override combo sets live in `Lotus/Upgrades/Mods/PvPMods/Stances/Combos`.
- Attack set `Attacks` arrays are ordered combo attacks.
- `ComboContext` is useful for sanity checking, but current damage resolution mostly follows the tree slot that selected the attack set.

## Weapon Damage

The weapon's PvP base damage usually comes from the behavior that has:

- `fire:Type`: `/EE/Types/Game/WeaponMeleeSweepFireBehavior`
- `impact:Type`: `/Lotus/Types/Game/MeleeImpactBehavior`

Use:

```text
pvp_weapon_base = impact:MeleeImpactBehavior.AttackData.Amount
                * impact:MeleeImpactBehavior.PvpDamageMultiplier
```

Keep `AttackData.Type` and the damage distribution fields. Physical-only weapons appear to receive physical damage quantization; weapons with elemental damage do not appear to use the same shortcut.

Slams are separate. Check weapon `PvpSlams` instead of regular melee tree attack sets for those. The exporter writes core aerial PvP `MeleeSlam` and `HeavySlam` entries to `Slams` and also appends them to the hit/combo damage sheets as one-hit rows.

## Attack Damage

For an effective attack object:

- Prefer `PvpAttackProperties.BaseDamageAtten`.
- If absent, fall back to `AttackProperties.BaseDamageAtten`.
- If both are absent, treat the multiplier as `1`.
- Check `PerSwingOverrides[].pvpAttackProperties.BaseDamageAtten`.
- When `overrideAttackProperties` is `1`, observed behavior matches using the per-swing PvP value for that hit.
- When `overrideAttackProperties` is `0`, observed behavior so far matches keeping the attack-level multiplier and treating the per-swing block as hit metadata.

Per-hit formula:

```text
raw_hit = AttackData.Amount
        * PvpDamageMultiplier
        * effective_hit_BaseDamageAtten

visible_hit = round_or_quantize(raw_hit, AttackData)
```

Total damage is the sum of visible hits.

For physical-only weapons, the current shorthand is:

```text
base damage * pvp multiplier * attack atten * quant
```

Observed `quant` shortcuts include `31/32`, `1`, and `33/32`. For tooling, this should eventually be implemented as per-damage-type physical quantization instead of a universal post-multiplier.

## Verified Examples

| Case | Path | Calculation | Result |
| --- | --- | --- | --- |
| Dual Keres slide | `Lotus/Weapons/Tenno/Melee/Swords/QuillSword/QuillDualSwords.json` | `115 * 0.48699999 * 2 * 33/32 = 115.51` | `116` |
| Dark Split-Sword dual slide | `Lotus/Weapons/Tenno/Melee/Swords/DarkSword/DarkSwordDaggerDuals.json` | `116 * 0.88 * 2 = 204.16` | `204` |
| Kronen stance slide | `Lotus/Weapons/Tenno/Melee/Tonfa/TonfaContestWinner/TennoTonfa.json` + `PVPTonfaSlideA` | `130 * 0.454 * 6 = 354.12` | `354` |
| Kronen stanceless PvP slide fallback | `TonfaMelee30ChargeB` + `TonfaMelee30ChargeA` | `2 hits * (130 * 0.454 * 1) = 2 * 59.02` | `2 x 59` |
| Furax Wraith slide | `Lotus/Weapons/Tenno/Melee/Fist/FuraxWraith.json` + `PVPFistSlideA` | `139 * 0.45300001 * 3 = 188.90` | `189` |

Note: Furax Wraith's weapon base amount is `139`; `39` would not produce the observed `189`.

## Tonfa Anomaly

`Lotus/Upgrades/Mods/PvPMods/Stances/PvPTonfaStanceOne.json` currently has:

```text
EquippedAttackSets.CC_SLIDING = /Lotus/Weapons/Tenno/Melee/AttackSets/PVPTonfaSlideEquipped
```

The inherited Tonfa melee tree has:

```text
EquippedAttackSets.CC_SLIDING_PVP = /Lotus/Weapons/Tenno/Melee/AttackSets/TonfaMelee30ChargeB
```

That explains the `2 x 59` fallback path when PvP slide resolution uses `CC_SLIDING_PVP`. If stance slide resolution uses the stance's `CC_SLIDING` override, it reaches `PVPTonfaSlideEquipped`, which inherits `PVPTonfaSlideA` and gives the `6x` slide.

This makes Tonfa a good test case for whether PvP stance slide resolution prefers `CC_SLIDING`, `CC_SLIDING_PVP`, or has a special stance path.

## Open Questions

- Confirm the exact physical quantization implementation and replace the shorthand multiplier in tooling.
- Confirm whether `ImpulseAtten` only affects impulse/push/stagger behavior. It does not appear to be part of HP damage.
- Confirm whether animation hit events or `PerSwingOverrides` length is the source of hit count in every case.
- Audit inherited attack sets where `CC_SLIDING_PVP` points at `Melee30Charge*`; many weapon categories use this pattern intentionally, but Tonfa has an extra PvP slide attack set that makes it suspicious.

## Export Tool

Run from the metadata root:

```powershell
py .\Melee_attack_dmg_analysis\export_pvp_melee_damage.py --root . --output .\Melee_attack_dmg_analysis\pvp_melee_damage.xlsx
```

Or run the package directly from this project folder:

```powershell
py -m pvp_melee_damage --root .. --output .\Melee_attack_dmg_analysis\pvp_melee_damage.xlsx
```

The default workbook layout is thematic and ordered for pivot work:

- `Hit Damage Database` stores one readable row per hit with weapon, stance, human-readable combo context, attack, damage, quant, and note columns. Raw package IDs and raw `combo_context` are kept at the right.
- `Combo Damage Database` stores total combo damage per weapon, stance state/id, human-readable combo context, and attack set. `damage_instances` shows the ordered hit damage expression before `total_damage`, with multi-hit attacks grouped in parentheses; raw package IDs and raw `combo_context` are kept at the right.
- `Slams` stores PvP normal aerial slam and heavy aerial slam damage, radius, falloff edge multiplier, combo-multiplier eligibility, damage type, and forced procs. The underlying `MeleeAttack` ref is intentionally not exported as a column because the concrete PvP damage/radius fields come from `PvpSlams`.
- `Weapons` stores the deduplicated weapon table, including quick normal/heavy slam damage and radius columns plus a `note` column for embedded stances, forced modes, and known unique weapon behavior.
- `Stances` stores equipped actual PvP stance/category rows using Conclave stance names, plus the embedded stanceless Paracesis/Broken War exceptions and one row per excluded misc stance package.
- `Combos` stores combo references with weapon category, stance state/id, and combo hit/attack counts.
- `Attacks` stores attack usage references with weapon category, stance state/id, human-readable combo, raw combo context, attack set id, combined hit index/count, and effective PvP damage attenuation.
- `Combo Context` translates metadata combo contexts into human-readable labels, using <https://wiki.warframe.com/w/Module:Enum/data> and <https://wiki.warframe.com/w/Stance#All_Combos> as references. It also flags contexts excluded from calculated damage rows or limited to specific categories.
- `Warnings` flags missing refs, ignored not-in-game weapons, and suspicious `CC_SLIDING_PVP` mappings that resolve to charge attack data. It is sorted by severity.
- `Readme` stores generation metadata, methodology, assumptions, and pivot tips.

Package/database ID address columns are placed at the right side of each sheet where practical.

AI-prefixed weapon files/packages such as `AiRVDarkDagger` are skipped automatically.

Ignored not-in-game weapon files/packages:

```text
CaptainVorCronusLongSword
DarkDaggerBase
LightGlaiveWeaponVariant
DuviriGrappleGlaiveWep
NekrosDeluxeScytheWeapon
VariantXmasScythe
TnStaffNewPlayerXp
DaxDuviriKatanaSwordAi
UndercroftDaxDuviriKatanaSwordAi
DaxDuviriTwoHandedKatanaWeaponAi
GladiusSword
GladiusDungeonEncounterSword
VariantKatana
AiStalkerTwoGreatSword
StalkerTwoGreatSwordQuest
DaxDuviriHammerPlayerWeapon
DaxDuviriKatanaPlayerWeapon
PrimeNikanaTennoCon
DaxDuviriKatanaSword
ArchonDualDaggersWep
GrnMiniSawMeleeWeapon
DrifterTazerWep
ArchonTridentWep
GrineerStaffWeapon
TauDaxMedicStaff
Skana1999Weapon
TauDaxHeavyHammer
DrillbitArmWeapon
InfestedZekeWhipWeapon
TauDaxKatana
DualKamasLettieQuestWeapon
TNWQuestBallasSwordWeapon
```

Special weapon overrides:

- `DarkSwordDaggerDuals` is exported as `Dark Split-Sword (dual melee mode)`.
- `DarkSwordDaggerDuals` only exports equipped dual-sword PvP stance rows; its no-stance behavior belongs to heavy sword mode.
- `DarkSwordDaggerSingle` is force-included as `Dark Split-Sword (heavy sword mode)` even though its metadata does not expose `AvailableOnPvp: 1`; it uses the heavy sword/`AxeMeleeTree` stance path in PvP.
- `BallasSwordWeapon` is exported as `Paracesis`.
- `BallasSwordWeapon` uses embedded `AxeCmbThreeMeleeTree` no-stance rows, identified by the Tempo Royale stance icon in local metadata. Those rows use `Paracesis (stanceless)` as their category label in the hit/combo/attack sheets.
- `StalkerTwoSmallSword`/Broken War uses embedded `StalkerSwordMeleeTree` no-stance rows, corresponding to the Stalker/Vengeful Revenant stance path in local metadata. Those rows use `Broken War (stanceless)` as their category label in the hit/combo/attack sheets.
- `SMSydon`, `CSHeliocor`, `InfStaff`, and `GrnSpiderSparring` are exported as `Vaykor Sydon`, `Synoid Heliocor`, `Pupacyst`, and `Korrudo`.
- `MK1Bo` and `MK1Furax` are exported as `MK1-Bo` and `MK1-Furax`.
- `SundialBoardSword`, `TennoSwordShield`, `PrimeSilvaAegis`, and `DualShortSword` are exported as `Sigma and Octantis`, `Silva and Aegis`, `Silva and Aegis Prime`, and `Dual Skana`.
- `SundialBoardSword`/Sigma and Octantis is marked in `Weapons.note` for its unique aerial shield throw metadata (`SupportAirThrow=1`, `ShieldProjectilePvP`).

Use `--layout raw` for one denormalized sheet, or `--layout full` for denormalized Excel-table workbook output.

The default workbook already includes `Combo Damage Database`, which is the common total-damage pivot precomputed from `Hit Damage Database`. You can still make custom pivots from any sheet.

## Pivot Tutorials

### Google Sheets: combo total damage

1. Upload or open `pvp_melee_damage.xlsx` in Google Sheets.
2. Select the `Hit Damage Database` sheet.
3. Choose `Insert > Pivot table`.
4. Use `Hit Damage Database` as the data range and place the pivot in a new sheet.
5. Add rows in this order:
   - `weapon_name`
   - `weapon_category`
   - `stance_equipped`
   - `stance_id`
   - `combo_context`
   - `attack_set_combo_id`
6. Add values:
   - `final_damage`, summarized by `SUM`
7. Use filters for `quant`, `note`, or `attack_pvp_damage_atten` when needed.

### Google Sheets: suspicious slide attacks

1. Select the `Hit Damage Database` sheet.
2. Choose `Data > Create a filter`.
3. Filter `combo_context` to `CC_SLIDING_PVP`.
4. Filter `note` by text containing `charge`.
5. Inspect `weapon_name`, `attack_set_combo_id`, and `attack_id`.

### Excel: combo total damage

1. Open the workbook in Excel.
2. Select `Hit Damage Database` and choose `Insert > PivotTable`.
3. Use rows:
   - `weapon_name`
   - `weapon_category`
   - `stance_equipped`
   - `stance_id`
   - `combo_context`
   - `attack_set_combo_id`
4. Use values:
   - `final_damage`, summarized by `Sum`
5. Use filters or slicers for `weapon_category`, `quant`, and `note`.
