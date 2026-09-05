from __future__ import annotations

from typing import Any


def _pointer(path: str, key: str) -> str:
    escaped = key.replace("~", "~0").replace("/", "~1")
    return f"{path}/{escaped}"


def diff_payloads(
    before: Any,
    after: Any,
    *,
    path: str = "",
) -> list[dict[str, Any]]:
    if isinstance(before, dict) and isinstance(after, dict):
        changes: list[dict[str, Any]] = []
        for key in sorted(before.keys() - after.keys()):
            changes.append({
                "op": "remove",
                "path": _pointer(path, str(key)),
                "before": before[key],
                "after": None,
            })
        for key in sorted(after.keys() - before.keys()):
            changes.append({
                "op": "add",
                "path": _pointer(path, str(key)),
                "before": None,
                "after": after[key],
            })
        for key in sorted(before.keys() & after.keys()):
            changes.extend(
                diff_payloads(before[key], after[key], path=_pointer(path, str(key)))
            )
        return changes
    if before != after:
        return [{
            "op": "replace",
            "path": path or "/",
            "before": before,
            "after": after,
        }]
    return []
