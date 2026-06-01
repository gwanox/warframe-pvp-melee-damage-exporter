"""Excel workbook writer."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .constants import (
    COMBO_CONTEXT_HEADERS,
    COMBO_CONTEXT_SOURCE,
    ENUM_REFERENCE_SOURCE,
    PIVOT_HEADERS,
    PVP_STANCE_NAME_SOURCE,
    SLAM_HEADERS,
    TOTAL_HEADERS,
    WARNING_HEADERS,
)
from .models import StanceInfo
from .rows import build_combo_context_rows, build_compact_tables
from .utils import rows_to_matrix, sorted_warnings

def write_workbook(
    output_path: Path,
    pivot_rows: list[dict[str, Any]],
    total_rows: list[dict[str, Any]],
    slam_rows: list[dict[str, Any]],
    warnings: list[dict[str, str]],
    misc_stances: list[StanceInfo],
    command: str,
    layout: str = "thematic",
) -> None:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.worksheet.table import Table, TableStyleInfo
        from openpyxl.utils import get_column_letter
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: openpyxl. Install it with:\n"
            "  py -m pip install -r Melee_attack_dmg_analysis/requirements.txt"
        ) from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    default = workbook.active
    workbook.remove(default)
    warning_rows = sorted_warnings(warnings)

    def add_sheet(name: str, headers: list[str], data_rows: list[list[Any]], table_name: str | None = None) -> None:
        ws = workbook.create_sheet(name)
        ws.append(headers)
        for data_row in data_rows:
            ws.append(data_row)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

        if table_name and data_rows:
            end_col = get_column_letter(len(headers))
            end_row = len(data_rows) + 1
            table = Table(displayName=table_name, ref=f"A1:{end_col}{end_row}")
            style = TableStyleInfo(name="TableStyleMedium2", showFirstColumn=False, showLastColumn=False, showRowStripes=True)
            table.tableStyleInfo = style
            ws.add_table(table)

        for column_index, header in enumerate(headers, start=1):
            width = min(max(len(header) + 2, 12), 52)
            for row_index in range(2, min(ws.max_row, 80) + 1):
                width = min(max(width, len(str(ws.cell(row=row_index, column=column_index).value or "")) + 2), 52)
            ws.column_dimensions[get_column_letter(column_index)].width = width

    if layout == "raw":
        add_sheet("Raw Data", PIVOT_HEADERS, rows_to_matrix(PIVOT_HEADERS, pivot_rows))
        add_sheet("Slams", SLAM_HEADERS, rows_to_matrix(SLAM_HEADERS, slam_rows))
        add_sheet("Warnings", WARNING_HEADERS, rows_to_matrix(WARNING_HEADERS, warning_rows))
    elif layout == "full":
        add_sheet("Hit Damage Database", PIVOT_HEADERS, rows_to_matrix(PIVOT_HEADERS, pivot_rows), "HitDamageDatabase")
        add_sheet("Combo Damage Database", TOTAL_HEADERS, rows_to_matrix(TOTAL_HEADERS, total_rows), "ComboDamageDatabase")
        add_sheet("Slams", SLAM_HEADERS, rows_to_matrix(SLAM_HEADERS, slam_rows), "SlamsTable")
        add_sheet("Combo Context", COMBO_CONTEXT_HEADERS, rows_to_matrix(COMBO_CONTEXT_HEADERS, build_combo_context_rows(pivot_rows)), "ComboContext")
        add_sheet("Warnings", WARNING_HEADERS, rows_to_matrix(WARNING_HEADERS, warning_rows), "WarningsTable")
    else:
        compact_tables = build_compact_tables(pivot_rows, slam_rows, misc_stances)
        headers, data_rows = compact_tables["Hit Damage Database"]
        add_sheet("Hit Damage Database", headers, data_rows)
        add_sheet("Combo Damage Database", TOTAL_HEADERS, rows_to_matrix(TOTAL_HEADERS, total_rows))
        for name in ("Weapons", "Stances", "Combos", "Attacks"):
            headers, data_rows = compact_tables[name]
            add_sheet(name, headers, data_rows)
        add_sheet("Slams", SLAM_HEADERS, rows_to_matrix(SLAM_HEADERS, slam_rows))
        add_sheet("Combo Context", COMBO_CONTEXT_HEADERS, rows_to_matrix(COMBO_CONTEXT_HEADERS, build_combo_context_rows(pivot_rows)))
        add_sheet("Warnings", WARNING_HEADERS, rows_to_matrix(WARNING_HEADERS, warning_rows))

    readme = workbook.create_sheet("Readme")
    readme_rows = [
        ("Generated", datetime.now().isoformat(timespec="seconds")),
        ("Command", command),
        ("Layout", layout),
        ("Hit rows", len(pivot_rows)),
        ("Combo damage rows", len(total_rows)),
        ("Slam rows", len(slam_rows)),
        ("Warnings rows", len(warnings)),
        ("", ""),
        ("Section", "Methodology"),
        ("Methodology", "Resolve JSON package inheritance from base package to derived package using deep dictionary merge; lists and scalars are replaced."),
        ("Methodology", "Discover PvP melee weapons by scanning Lotus/Weapons/**/*.json for melee sweep behavior markers, then requiring effective AvailableOnPvp=1 unless force-included."),
        ("Methodology", "Read base damage and PvP multiplier from the melee sweep behavior's MeleeImpactBehavior AttackData and PvpDamageMultiplier."),
        ("Methodology", "Match PvP stances by inherited melee tree package or compatibility tags; stance first-package attack sets override inherited base tree maps."),
        ("Methodology", "Name PvP stances from the actual Conclave stance list; misc stance packages are excluded from damage rows and summarized once in Stances."),
        ("Methodology", "Calculate each hit as round_half_up(base_damage * pvp_multiplier * effective_attack_atten * quant_multiplier)."),
        ("Methodology", "Read PvP aerial slam and heavy slam rows from each weapon's effective PvpSlams entries for MeleeSlam and HeavySlam."),
        ("Methodology", "Calculate each PvP slam as round_half_up(base_damage * pvp_multiplier * BaseDamageAttenuation * quant_multiplier); radius and falloff come from the same PvpSlams entry."),
        ("Methodology", "Append core PvP slams to Hit Damage Database and Combo Damage Database as one-hit rows using the existing combo/attack columns."),
        ("Methodology", "PvpSlams may include a MeleeAttack reference, but it is not exported as a column because the concrete PvP damage/radius fields come from the PvpSlams entry."),
        ("Methodology", "Effective attack attenuation prefers per-swing PvP override, then attack PvP BaseDamageAtten, then regular attack BaseDamageAtten, then 1."),
        ("Methodology", "Physical-only weapons use IPS quantization from rounded 32nds; elemental/non-physical rows use quant multiplier 1."),
        ("Methodology", "Combo damage is the ordered sum of exported hit damages; damage_instances shows that ordered hit list before total_damage."),
        ("Methodology", "Non-damage or superseded combo contexts are excluded from calculated damage rows; category-limited contexts such as CC_AIR_RIGHT are exported only for relevant categories and flagged in Combo Context."),
        ("Quantization reference", "https://wiki.warframe.com/w/Damage/Calculation"),
        ("Combo context reference", COMBO_CONTEXT_SOURCE),
        ("Enum reference", ENUM_REFERENCE_SOURCE),
        ("Stance name reference", PVP_STANCE_NAME_SOURCE),
        ("", ""),
        ("Section", "Assumptions"),
        ("Assumption", "Thematic layout writes human-readable damage database sheets plus raw reference sheets and one combo-damage sum sheet."),
        ("Assumption", "Raw layout writes one denormalized data sheet."),
        ("Assumption", "Full layout keeps the older denormalized Excel table sheets."),
        ("Assumption", "Weapon source scans Lotus/Weapons/**/*.json for melee sweep behavior markers."),
        ("Assumption", "Weapon category labels are canonicalized against https://warframe.fandom.com/wiki/Category:Melee_Weapon_Type."),
        ("Assumption", "Known not-in-game and AI-like weapon files are excluded and listed as ignored warnings."),
        ("Assumption", "Identical yes/no stance rows and weapon-level slam rows use stance_equipped = any."),
        ("Assumption", "Stances sheet omits stance_equipped, keeps actual stance rows, and adds one summary row per excluded misc stance package."),
        ("Assumption", "Paracesis and Broken War no-stance states use embedded stance trees from local metadata."),
        ("Assumption", "Embedded no-stance rows use unique category labels such as Paracesis (stanceless) and Broken War (stanceless)."),
        ("Assumption", "Weapons.note flags embedded stances, forced modes, and known unique behavior such as Sigma and Octantis aerial shield throw."),
        ("Assumption", "Slams exports core aerial PvP slams only: MeleeSlam and HeavySlam. Non-core slam events with nonzero AttackData.Amount are noted in Warnings for later audit."),
        ("Assumption", "Rows are per hit/swing; ImpulseAtten is ignored for HP damage."),
        ("", ""),
        ("Section", "Pivot Tips"),
        ("Tip", "In Excel or Google Sheets, build pivots directly from the human-readable Hit Damage Database sheet."),
    ]
    for row in readme_rows:
        readme.append(row)

    section_fill = PatternFill("solid", fgColor="F3F4F6")
    readme.column_dimensions["A"].width = 32
    readme.column_dimensions["B"].width = 175
    for row_index, row in enumerate(readme_rows, start=1):
        label_cell = readme.cell(row=row_index, column=1)
        value_cell = readme.cell(row=row_index, column=2)
        label_cell.alignment = Alignment(vertical="center")
        value_cell.alignment = Alignment(vertical="center", wrap_text=False)

        if row[0] and row[0] not in {"Methodology", "Assumption", "Tip"}:
            label_cell.font = Font(bold=True)

        if row[0] == "Section":
            label_cell.alignment = Alignment(horizontal="center", vertical="center")
            value_cell.alignment = Alignment(horizontal="center", vertical="center")
            label_cell.font = Font(bold=True)
            value_cell.font = Font(bold=True)
            label_cell.fill = section_fill
            value_cell.fill = section_fill
        elif row[0] == "":
            readme.row_dimensions[row_index].height = 18

    workbook.save(output_path)
