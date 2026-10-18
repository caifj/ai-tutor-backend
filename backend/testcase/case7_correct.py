"""案例 7 演示样例：SQL 执行计划分析与 B+ 树查找。"""

from __future__ import annotations

import re
from dataclasses import dataclass


def _parse_mysql_line(line: str) -> dict[str, object] | None:
    """Parse one simplified MySQL EXPLAIN line."""

    fields: dict[str, str] = {}
    for part in line.replace("->", "").split(","):
        if "=" not in part:
            continue
        key, value = part.strip().split("=", 1)
        fields[key.strip()] = value.strip()
    if not fields:
        return None
    rows_text = fields.get("rows", "0")
    return {
        "engine": "mysql",
        "table": fields.get("table", "unknown"),
        "operation": fields.get("type", "unknown"),
        "index": fields.get("key"),
        "estimated_rows": int(rows_text) if rows_text.isdigit() else 0,
        "raw": line.strip(),
    }


def _parse_postgresql_line(line: str) -> dict[str, object] | None:
    """Parse one common PostgreSQL text-plan line."""

    match = re.search(
        r"(?P<operation>Seq Scan|Index Scan|Index Only Scan|Bitmap Heap Scan)"
        r"(?: using (?P<index>\S+))? on (?P<table>\S+).*?rows=(?P<rows>\d+)",
        line,
        re.IGNORECASE,
    )
    if not match:
        return None
    values = match.groupdict()
    return {
        "engine": "postgresql",
        "table": values["table"],
        "operation": values["operation"],
        "index": values.get("index"),
        "estimated_rows": int(values["rows"]),
        "raw": line.strip(),
    }


def parse_explain(plan_text: str) -> dict[str, list[dict[str, object]]]:
    """Parse MySQL/PostgreSQL plans and report index use and full scans."""

    nodes: list[dict[str, object]] = []
    for line in plan_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        node = (
            _parse_mysql_line(stripped)
            if "table=" in stripped and "type=" in stripped
            else _parse_postgresql_line(stripped)
        )
        if node:
            nodes.append(node)

    index_usage = [
        {
            "table": node["table"],
            "index": node["index"],
            "operation": node["operation"],
        }
        for node in nodes
        if node.get("index") not in {None, "", "NULL"}
        or str(node["operation"]).lower() in {"index", "ref", "range"}
    ]
    full_scan_findings = [
        {
            "table": node["table"],
            "operation": node["operation"],
            "estimated_rows": node["estimated_rows"],
            "suggestion": "考虑为过滤列或连接列建立索引。",
        }
        for node in nodes
        if str(node["operation"]).lower() in {"all", "seq scan"}
    ]
    return {
        "nodes": nodes,
        "index_usage": index_usage,
        "full_scan_findings": full_scan_findings,
    }


@dataclass(frozen=True)
class BPlusTree:
    """A compact B+ tree representation suitable for lookup visualization."""

    levels: list[list[list[int]]]
    order: int

    @property
    def keys(self) -> list[int]:
        """Return all keys stored in leaf order."""

        return [key for leaf in self.levels[-1] for key in leaf]

    def lookup(self, key: int) -> list[list[int]]:
        """Return the nodes visited while locating a key."""

        path: list[list[int]] = []
        for level in self.levels:
            node = next((item for item in level if not item or key <= item[-1]), level[-1])
            path.append(node)
        return path


def build_btree(keys: list[int], order: int = 3) -> BPlusTree:
    """Build balanced B+ tree levels from a collection of integer keys."""

    if order < 3:
        raise ValueError("order must be at least 3")
    sorted_keys = sorted(set(keys))
    if not sorted_keys:
        return BPlusTree(levels=[[[]]], order=order)

    width = order - 1
    leaves = [sorted_keys[index : index + width] for index in range(0, len(sorted_keys), width)]
    levels: list[list[list[int]]] = [leaves]
    current = leaves
    while len(current) > 1:
        parents = [
            [child[-1] for child in current[index : index + order]]
            for index in range(0, len(current), order)
        ]
        levels.insert(0, parents)
        current = parents
    return BPlusTree(levels=levels, order=order)


def lookup(root: BPlusTree, key: int) -> list[list[int]]:
    """Compatibility function that delegates to the tree lookup method."""

    return root.lookup(key)


def main() -> dict[str, object]:
    """Run a small local demonstration without external services."""

    plan = (
        "id=1, table=orders, type=ALL, key=NULL, rows=1200\n"
        "id=2, table=users, type=ref, key=idx_user_id, rows=5"
    )
    tree = build_btree([1, 5, 10, 15, 20, 25, 30, 35], order=3)
    return {"plan": parse_explain(plan), "lookup_path": lookup(tree, 25)}


if __name__ == "__main__":
    print(main())
