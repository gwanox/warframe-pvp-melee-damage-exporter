"""Attack-set source maps, fallbacks, and stance metadata audits."""

from __future__ import annotations

from dataclasses import dataclass

from .constants import ATTACK_SET_MAPS
from .models import PackageDoc, StanceInfo
from .resolver import Resolver


@dataclass(frozen=True)
class AttackSetEntry:
    map_key: str
    combo_context: str
    attack_set_ref: str
    note: str = ""


def iter_attack_set_entries(
    doc: PackageDoc,
    resolver: Resolver,
    allowed_maps: set[str] | None = None,
) -> list[AttackSetEntry]:
    entries: list[AttackSetEntry] = []
    value = doc.value

    for map_label, map_key in ATTACK_SET_MAPS:
        if allowed_maps is not None and map_label not in allowed_maps:
            continue
        attack_sets = value.get(map_key, {})
        if not isinstance(attack_sets, dict):
            resolver.warn("warning", doc.package_id, f"{map_key} is not a dictionary")
            continue

        declared_contexts = {str(context) for context in attack_sets}
        refs: dict[str, str] = {}
        for context, ref in attack_sets.items():
            context = str(context)
            if not isinstance(ref, str):
                resolver.warn(
                    "warning", doc.package_id, f"Non-string attack set ref for {map_key}.{context}"
                )
                continue
            if not ref.strip():
                resolver.warn(
                    "note",
                    doc.package_id,
                    f"{map_key}.{context} is explicitly empty; context omitted and any inherited mapping is cleared",
                )
                continue
            refs[context] = ref
            entries.append(AttackSetEntry(map_key, context, ref))

        fallbacks = value.get("ContextFallbacks", [])
        if not isinstance(fallbacks, list):
            resolver.warn("warning", doc.package_id, "ContextFallbacks is not a list")
            continue

        for fallback in fallbacks:
            if not isinstance(fallback, dict):
                resolver.warn(
                    "warning", doc.package_id, "ContextFallbacks contains a non-dictionary entry"
                )
                continue
            context = str(fallback.get("context", ""))
            target = str(fallback.get("fallback", ""))
            if not context or not target or context in declared_contexts:
                continue
            target_ref = refs.get(target)
            if target_ref is None:
                continue
            note = f"Context fallback: {context} uses {target} from {map_key}"
            entries.append(AttackSetEntry(map_key, context, target_ref, note))
            resolver.warn("note", doc.package_id, note)

    return entries


def audit_stance_source(resolver: Resolver, tree_doc: PackageDoc, stance: StanceInfo) -> None:
    if stance.tree_package != tree_doc.package_id:
        resolver.warn(
            "note",
            stance.stance_id,
            f"Stance matched {tree_doc.package_id} by compatibility tag rather than an inherited tree package",
        )

    for _map_label, map_key in ATTACK_SET_MAPS:
        own = stance.doc.first_value.get(map_key, {})
        base = tree_doc.value.get(map_key, {})
        if not isinstance(own, dict):
            continue
        if not isinstance(base, dict):
            base = {}

        for context, ref in own.items():
            if context == "CC_GROUND_HEAVY" and ref != base.get(context):
                resolver.warn(
                    "note",
                    stance.stance_id,
                    f"Stance overrides base heavy attack: {base.get(context) or '<none>'} -> {ref or '<empty>'}",
                )
