"""JSON package loading and inheritance resolution."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .constants import MELEE_ROOT_PACKAGE
from .models import PackageDoc
from .utils import deep_merge


def normalize_package_ref(ref: str, context_doc: PackageDoc | None = None) -> str:
    ref = ref.strip()
    if ref.endswith(".json"):
        ref = ref[:-5]

    if ref.startswith("/"):
        package = ref
    elif ref.startswith(("MeleeTrees/", "AttackSets/", "Attacks/")):
        package = f"{MELEE_ROOT_PACKAGE}/{ref}"
    elif ref.startswith("Combos/") and context_doc is not None:
        context_dir = context_doc.package_id.rsplit("/", 1)[0]
        if context_dir.endswith("/StanceVariants"):
            context_dir = context_dir.rsplit("/", 1)[0]
        package = f"{context_dir}/{ref}"
    elif context_doc is not None:
        context_dir = context_doc.package_id.rsplit("/", 1)[0]
        package = f"{context_dir}/{ref}"
    else:
        package = f"{MELEE_ROOT_PACKAGE}/{ref}"

    return "/" + package.strip("/")


def package_to_path(root: Path, package: str) -> Path:
    relative = package.strip("/") + ".json"
    return root / Path(*relative.split("/"))


class Resolver:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.cache: dict[Path, PackageDoc | None] = {}
        self.warnings: list[dict[str, str]] = []
        self.warning_keys: set[tuple[str, str, str]] = set()

    def warn(self, severity: str, ref: str, message: str) -> None:
        key = (severity, ref, message)
        if key in self.warning_keys:
            return
        self.warning_keys.add(key)
        self.warnings.append({"severity": severity, "ref": ref, "message": message})

    def load_path(self, path: Path) -> PackageDoc | None:
        path = path.resolve()
        if path in self.cache:
            return self.cache[path]

        if not path.exists():
            self.cache[path] = None
            return None

        try:
            packages = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as exc:  # noqa: BLE001 - preserve export despite bad metadata
            self.warn("error", str(path), f"Failed to parse JSON: {exc}")
            self.cache[path] = None
            return None

        if not isinstance(packages, list) or not packages:
            self.warn("warning", str(path), "JSON file is not a non-empty package list")
            self.cache[path] = None
            return None

        # Extracted files are inheritance chains ordered derived-first. Apply
        # base packages first so the first package's overrides win.
        effective: dict[str, Any] = {}
        for package in reversed(packages):
            value = package.get("value", {})
            if isinstance(value, dict):
                effective = deep_merge(effective, value)

        first = packages[0]
        doc = PackageDoc(
            path=path,
            packages=packages,
            package_id=str(first.get("package", "")),
            first_value=copy.deepcopy(first.get("value", {})),
            value=effective,
        )
        self.cache[path] = doc
        return doc

    def load_ref(self, ref: str, context_doc: PackageDoc | None = None) -> PackageDoc | None:
        if not isinstance(ref, str) or not ref.strip():
            self.warn(
                "warning",
                context_doc.package_id if context_doc else "<root>",
                "Tried to resolve an empty ref",
            )
            return None

        package = normalize_package_ref(ref, context_doc)
        path = package_to_path(self.root, package)
        doc = self.load_path(path)
        if doc is None:
            self.warn(
                "warning",
                package,
                f"Unresolved ref from {context_doc.package_id if context_doc else 'root'}",
            )
        return doc
