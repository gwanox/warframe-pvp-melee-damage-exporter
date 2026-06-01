# Warframe PvP Melee Damage Exporter

Export Warframe PvP melee attack and slam damage metadata from extracted JSON into an Excel workbook.

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

## Workbook

The default workbook contains these sheets:

- `Hit Damage Database`: one readable row per exported hit.
- `Combo Damage Database`: one total row per weapon, stance state, combo context, and attack set.
- `Weapons`: deduplicated weapon metadata, including quick normal/heavy slam damage and radius columns.
- `Stances`: PvP stance/category summaries.
- `Combos`: combo references with hit and attack counts.
- `Attacks`: attack usage references and effective PvP damage attenuation.
- `Slams`: normal aerial slam and heavy aerial slam damage, radius, falloff edge multiplier, combo-multiplier eligibility, damage type, and forced procs.
- `Combo Context`: readable names for raw combo context identifiers.
- `Warnings`: unresolved references and data-quality notices.
- `Readme`: generation metadata and methodology notes embedded in the workbook.

Package/database ID columns are kept at the right side of sheets where useful.

## Data Model

The exporter resolves each JSON file as a package inheritance chain. Extracted files are ordered derived-first, so the resolver merges base packages first and lets derived packages override them.

PvP melee weapons are discovered by scanning `Lotus/Weapons/**/*.json` for melee sweep behavior markers, then filtering to effective weapon data with `AvailableOnPvp = 1`, plus known PvP-usable exceptions.

The weapon PvP base damage comes from a melee sweep behavior with:

- `fire:Type`: `/EE/Types/Game/WeaponMeleeSweepFireBehavior`
- `impact:Type`: `/Lotus/Types/Game/MeleeImpactBehavior`

The base PvP damage input is:

```text
impact:MeleeImpactBehavior.AttackData.Amount
* impact:MeleeImpactBehavior.PvpDamageMultiplier
```

Weapon categories are normalized to public melee weapon type labels, and known alternate names are applied for readable output.

## Attack Damage

For each attack, the exporter resolves its effective PvP damage attenuation in this order:

1. Per-swing `pvpAttackProperties.BaseDamageAtten` when `overrideAttackProperties = 1`.
2. Attack-level `PvpAttackProperties.BaseDamageAtten`.
3. Attack-level `AttackProperties.BaseDamageAtten`.
4. `1`.

Per-hit damage is calculated as:

```text
round_half_up(base_damage * pvp_multiplier * effective_attack_atten * quant_multiplier)
```

Physical-only weapons use IPS quantization based on rounded 32nds. Elemental and mixed damage rows use a neutral quant multiplier.

Identical equipped and unequipped rows are collapsed to `stance_equipped = any`. Weapon-level slam rows also use `stance_equipped = any`.

## Slams

Slams are read from each weapon's effective `PvpSlams`, not from stance attack sets.

The exporter handles the core PvP slam events:

- `MeleeSlam`: normal aerial slam.
- `HeavySlam`: heavy aerial slam.

Slam damage is calculated as:

```text
round_half_up(base_damage * pvp_multiplier * BaseDamageAttenuation * quant_multiplier)
```

Core slams are also appended to `Hit Damage Database` and `Combo Damage Database` as one-hit rows using the existing combo and attack columns. `PvpSlams` may include a `MeleeAttack` reference, but it is not exported as a column because the concrete PvP damage and radius fields come from the `PvpSlams` entry.

## Special Cases

The exporter includes a small set of metadata overrides for known PvP-visible behavior:

- Dark Split-Sword dual and heavy-sword modes are exported as separate rows with separate category handling.
- Paracesis and Broken War use embedded no-stance trees for their no-stance rows.
- Selected weapon package IDs are renamed for readable workbook output.
- AI-only, quest-only, or non-player weapon packages are filtered out.

These rules live in `pvp_melee_damage/constants.py`.

## Layout Options

Default layout:

```powershell
py -m pvp_melee_damage --root .. --output .\Melee_attack_dmg_analysis\pvp_melee_damage.xlsx
```

Raw layout:

```powershell
py -m pvp_melee_damage --root .. --output .\Melee_attack_dmg_analysis\pvp_melee_damage_raw.xlsx --layout raw
```

Full table layout:

```powershell
py -m pvp_melee_damage --root .. --output .\Melee_attack_dmg_analysis\pvp_melee_damage_full.xlsx --layout full
```
