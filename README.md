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

Include non-Tonfa `CC_AIR_RIGHT` damage rows:

```powershell
py -m pvp_melee_damage --root .. --output .\Melee_attack_dmg_analysis\pvp_melee_damage.xlsx --include-non-tonfa-air-right
```

By default, `CC_AIR_RIGHT` is retained for Tonfas and omitted for other categories. Non-Tonfa A/B aerial sets reference distinct attack packages, but the current PvP data gives every inspected pair the same hit count and damage attenuation.

Include source-defined contexts that could not be triggered in current PvP testing:

```powershell
py -m pvp_melee_damage --root .. --output .\Melee_attack_dmg_analysis\pvp_melee_damage.xlsx --include-unverified-pvp-contexts
```

By default, `CC_ATTACK_BLOCKED`, `CC_DOWNED_ENEMY`, `CC_GUARD_BROKEN`, and `CC_PARRY_HEAVY` are omitted from damage sheets.

Install and run the optional code-quality tools:

```powershell
py -m pip install -e ".[dev]"
py -m ruff check pvp_melee_damage
py -m ruff format --check pvp_melee_damage
```

Generated `.xlsx` files are ignored by git by default.

## Project Layout

- `export_pvp_melee_damage.py`: compatibility wrapper for the package CLI.
- `pvp_melee_damage/cli.py`: argument parsing and self-tests.
- `pvp_melee_damage/constants.py`: workbook schemas, known overrides, and metadata IDs.
- `pvp_melee_damage/resolver.py`: JSON package inheritance and reference resolution.
- `pvp_melee_damage/discovery.py`: PvP melee weapon and stance discovery.
- `pvp_melee_damage/skins.py`: data-driven legacy skin weapon variants.
- `pvp_melee_damage/combo.py`: initial combo multiplier eligibility.
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
- `Weapons`: deduplicated weapon metadata, including attack speed, base Impact/Puncture/Slash and elemental damage, plus quick normal/heavy slam damage and radius columns.
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

Weapon attack speed is read from the matching melee behavior's state `fireRate` and divided by `60` to convert the stored attacks-per-minute rate to attacks per second.

Initial combo is read from the melee impact behavior's `InitialHitCounter` and tier fields. The exporter derives the starting combo multiplier and applies it before final rounding to `CC_GROUND_HEAVY` and to PvP slam entries with `CanUseComboMultiplier = 1`. The source attenuation columns remain unchanged.

The current PvP weapon set exposes this mechanic on Synoid Heliocor and Furax Wraith at `20` initial combo, and Fragor Prime at `30`; each starts at a `2x` heavy-attack multiplier. The Fragor Prime value also carries into its Brokk Skin variant.

The `impact`, `puncture`, `slash`, `elem`, and `elem_dmg` columns normalize both weapon damage formats. Old-format component fractions are multiplied by `AttackData.Amount`; new-format component values are already absolute damage. Elemental-only old-format weapons use `AttackData.Type` and `AttackData.Amount`.

Weapon categories are normalized to public melee weapon type labels, and known alternate names are applied for readable output.

The exporter also creates four stat-changing legacy skin variants from the local skin `Upgrades`:

- Scindo and Scindo Prime with Manticore Skin: `+15%` melee damage and `-15%` attack speed.
- Fragor and Fragor Prime with Brokk Skin: `+5%` attack speed and `-1s` combo duration.

Damage and attack-speed modifiers flow through the weapon, hit, combo, and slam calculations. Combo duration is preserved in `Weapons.note` and `Warnings` because this exporter does not calculate combo decay. Each skin package directly names only the base weapon, so Prime compatibility is an explicit mapping in `pvp_melee_damage/skins.py`.

## Attack Damage

For each attack, the exporter resolves its effective PvP damage attenuation in this order:

1. Per-swing `pvpAttackProperties.BaseDamageAtten` when `overrideAttackProperties = 1`.
2. Attack-level `PvpAttackProperties.BaseDamageAtten`.
3. Attack-level `AttackProperties.BaseDamageAtten`.
4. `1`.

Per-hit damage is calculated as:

```text
round_half_up(base_damage * pvp_multiplier * effective_attack_atten * quant_multiplier * eligible_initial_combo_multiplier)
```

Physical-only weapons use IPS quantization based on rounded 32nds. Elemental and mixed damage rows use a neutral quant multiplier.

Identical base-tree and stance-derived rows collapse to `stance_equipped = any`. Weapon-level slam rows also use `stance_equipped = any`.

### Stance State

Current PvP attacks are resolved from the effective `EquippedAttackSets` map:

- `stance_equipped = no`: mapping from the weapon's base melee tree.
- `stance_equipped = yes`: mapping from the PvP stance-derived tree.
- `stance_equipped = any`: both resolve to the same attacks and damage.

`UnequippedAttackSets` describes legacy quick-melee routing and is not exported as a simultaneous current damage variant. Treating both maps as active alternatives produces incorrect duplicates and hides stance overrides when both routes happen to deal the same damage.

Most heavy attacks are inherited unchanged from the base melee tree and therefore export as `stance_equipped = any`. Biting Piranha is the notable exception because it explicitly changes the Dual Dagger heavy attack from `DualDaggerMelee30ChargeB` to `DualDaggerMelee30ChargeA`.

`stance_id` identifies the compatible stance used for comparison even when `stance_equipped` is `no` or `any`; the ID alone does not mean the stance is installed.

The category-level `Combos` sheet includes `weapon_scope`, `weapon_count`, and `weapon_names`. This prevents special cases such as Broken War, Paracesis, or a Dark Split-Sword mode from making a weapon-specific mapping appear to apply to an entire category.

Declared `ContextFallbacks` are expanded inside their matching attack-set map and identified in row notes. Any context explicitly present in that map blocks its fallback; an empty attack-set reference therefore clears an inherited mapping and is recorded in `Warnings`.

The context key in `EquippedAttackSets` is treated as the runtime trigger. An attack set's own `ComboContext` is not used to relabel rows because inherited and reused attack sets frequently retain a different internal context.

Resolvable contexts from `EquippedAttackSets` are retained except known legacy charge aliases stored under `CC_SLIDING_PVP` and contexts that could not be triggered in current PvP testing. `CC_ATTACK_BLOCKED`, `CC_DOWNED_ENEMY`, `CC_GUARD_BROKEN`, and `CC_PARRY_HEAVY` are excluded by default; use `--include-unverified-pvp-contexts` to restore them for source-data auditing. `CC_AIR_RIGHT` is always retained for Tonfas; use `--include-non-tonfa-air-right` to include it for other categories.

Current slide attacks resolve through `EquippedAttackSets.CC_SLIDING`; the charge/heavy aliases under `CC_SLIDING_PVP` are excluded. In-game testing confirms that Skana deals one 68-damage slide hit with or without Rising Steel. Star Divide overrides the Tonfa slide with `PVPTonfaSlideAEquipped`, which produces two 1x blade hits: Kronen deals `59 + 59` with the stance and one 6x hit (`354`) without it. The empty derived attack package is a runtime marker, so this verified two-hit behavior is recorded explicitly.

Hit counts are otherwise inferred from the effective `PerSwingOverrides` array. Empty derived attack packages can be engine-side runtime markers whose true hit behavior is not recoverable from inherited JSON alone. The exporter lists unvalidated cases in `Warnings` rather than silently presenting them as equally certain.

Direct `AerialAttacks` button-routing references are not mixed into combo rows because they form a separate input map. The exporter includes `CC_AIR`; `CC_AIR_RIGHT` is included for Tonfas by default and optionally for all categories. Damage rows model melee sweep impacts, not projectile fire behaviors, so glaive throws and the Sigma and Octantis aerial shield throw are not calculated as blade hits. These scope decisions are recorded in `Warnings` and the workbook `Readme`.

## Slams

Slams are read from each weapon's effective `PvpSlams`, not from stance attack sets.

The exporter handles the core PvP slam events:

- `MeleeSlam`: normal aerial slam.
- `HeavySlam`: heavy aerial slam.

Slam damage is calculated as:

```text
round_half_up(base_damage * pvp_multiplier * BaseDamageAttenuation * quant_multiplier * eligible_initial_combo_multiplier)
```

Core slams are also appended to `Hit Damage Database` and `Combo Damage Database` as one-hit rows using the existing combo and attack columns. `PvpSlams` may include a `MeleeAttack` reference, but it is not exported as a column because the concrete PvP damage and radius fields come from the `PvpSlams` entry.

Dark Split-Sword omits `HeavySlam` from `PvpSlams` in both weapon modes. Their heavy-slam cells are intentionally left blank rather than filled from the PvE `Slams.HeavySlam` entries. In-game PvP testing confirms that attempting the dual-mode heavy slam glitches instead of producing a valid heavy slam.

## Special Cases

The exporter includes a small set of metadata overrides for known PvP-visible behavior:

- Dark Split-Sword dual and heavy-sword modes are exported as separate rows with separate category handling and explicit missing-PvP-heavy-slam notes.
- Paracesis and Broken War use embedded no-stance trees for their no-stance rows.
- Selected weapon package IDs are renamed for readable workbook output.
- Manticore and Brokk stat-changing skins are exported as separate weapon variants for their base and Prime weapons.
- Source-defined initial combo is applied to eligible heavy attacks and heavy slams, including Fragor Prime and its Brokk Skin variant. This is documented as a PvE-oriented mechanic carried into PvP.
- AI-only, quest-only, or non-player weapon packages are filtered out.

These rules live in `pvp_melee_damage/constants.py` and `pvp_melee_damage/skins.py`.

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
