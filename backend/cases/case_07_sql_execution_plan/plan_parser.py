"""SQL 执行计划文本解析与性能分析（移植自案例原始 Flask 项目的 PlanParser）。

支持两种文本格式：
- MySQL：连接器输出的 ``key=value`` 行（每行一个计划节点）
- PostgreSQL：``Seq Scan on t (cost=.. rows=.. width=..)`` 缩进树
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_FULL_SCAN_SEVERE_ROWS = 10_000
_FULL_SCAN_WARNING_ROWS = 1_000
_FULL_SCAN_HINT_ROWS = 100
_HIGH_COST = 10_000.0
_MEDIUM_COST = 1_000.0
_LARGE_SCAN_ROWS = 100_000

_ATTRIBUTE_KEYWORDS = (
    "Sort Key:",
    "Sort Method:",
    "Scan Key:",
    "Filter:",
    "Hash Cond:",
    "Join Filter:",
    "Output:",
    "Buckets:",
)

_INDEX_ACCESS_TYPES = {"REF", "EQ_REF", "RANGE", "INDEX"}


@dataclass(slots=True)
class PlanNode:
    node_id: int
    level: int
    operation: str
    table: str = ""
    access_type: str = ""
    key_used: str = ""
    rows_estimated: int | None = None
    cost_start: float | None = None
    cost_end: float | None = None
    filter: str = ""
    raw_text: str = ""
    children: list[PlanNode] = field(default_factory=list)


@dataclass(slots=True)
class PlanAnalysis:
    roots: list[PlanNode]
    index_usage: list[dict]
    full_scan_findings: list[dict]
    issues: list[str]
    suggestions: list[str]
    details: list[str]
    node_count: int
    max_estimated_rows: int
    max_cost: float


def parse_plan(plan_lines: list[str]) -> list[PlanNode]:
    """把执行计划文本行解析为计划树列表（MySQL 多行同级，PostgreSQL 按缩进嵌套）。"""

    roots: list[PlanNode] = []
    stack: list[PlanNode] = []
    node_counter = 0

    for line in plan_lines:
        if not line.strip():
            continue
        stripped = line.strip()

        has_cost = "cost=" in stripped
        is_attribute = any(keyword in stripped for keyword in _ATTRIBUTE_KEYWORDS) and not has_cost
        if is_attribute:
            if stack:
                parent_filter = stack[-1].filter
                stack[-1].filter = f"{parent_filter} | {stripped}" if parent_filter else stripped
            continue

        indent_level = len(line) - len(line.lstrip())
        level = indent_level // 2 if indent_level >= 2 else 0

        node = _parse_plan_line(stripped)
        node.node_id = node_counter
        node.level = level
        node.raw_text = stripped
        node_counter += 1

        if level == 0 or not stack:
            roots.append(node)
            stack = [node]
            continue
        while len(stack) > 1 and stack[-1].level >= level:
            stack.pop()
        if stack[-1].level < level:
            stack[-1].children.append(node)
            stack.append(node)
        else:
            roots.append(node)
            stack = [node]

    return roots


def _parse_plan_line(line: str) -> PlanNode:
    if "cost=" in line or "QUERY PLAN=" in line:
        return _parse_postgres_line(line)
    return _parse_mysql_line(line)


def _parse_postgres_line(line: str) -> PlanNode:
    node = PlanNode(node_id=0, level=0, operation="")

    op_match = re.search(r"(\w+(?:\s+\w+)*?)\s+on\s+(\w+)", line, re.IGNORECASE)
    if op_match:
        node.operation = op_match.group(1)
        node.table = op_match.group(2)
    else:
        op_match = re.search(r"^\s*([A-Z][a-zA-Z\s]+)", line)
        if op_match:
            node.operation = op_match.group(1).strip()

    cost_match = re.search(r"cost=([0-9.]+)\.\.([0-9.]+)", line)
    if cost_match:
        node.cost_start = float(cost_match.group(1))
        node.cost_end = float(cost_match.group(2))
    rows_match = re.search(r"rows=(\d+)", line)
    if rows_match:
        node.rows_estimated = int(rows_match.group(1))
    return node


def _parse_mysql_line(line: str) -> PlanNode:
    node = PlanNode(node_id=0, level=0, operation="")

    patterns = {
        "table": r"\btable=([^\s,]+)",
        "access_type": r"\btype=([^\s,]+)",
        "key_used": r"\bkey=([^\s,]+)",
        "filter": r"\bExtra=([^\s,]+)",
    }
    for attr, pattern in patterns.items():
        match = re.search(pattern, line)
        if match:
            value = match.group(1)
            if value and value != "NULL":
                setattr(node, attr, value)

    rows_match = re.search(r"\brows=(\d+)", line)
    if rows_match:
        node.rows_estimated = int(rows_match.group(1))

    access_type = node.access_type.upper()
    if access_type == "ALL":
        node.operation = "Seq Scan"
    elif access_type in _INDEX_ACCESS_TYPES:
        node.operation = "Index Scan"
    elif access_type == "CONST":
        node.operation = "Const Lookup"
    elif access_type:
        node.operation = f"{access_type} Scan"
    else:
        select_match = re.search(r"select_type=([^\s,]+)", line)
        node.operation = select_match.group(1) if select_match else "Unknown"
    return node


def _walk(roots: list[PlanNode]) -> list[PlanNode]:
    ordered: list[PlanNode] = []

    def visit(node: PlanNode) -> None:
        ordered.append(node)
        for child in node.children:
            visit(child)

    for root in roots:
        visit(root)
    return ordered


def analyze_plan(roots: list[PlanNode]) -> PlanAnalysis:
    """对计划树做性能分析：索引使用情况、全表扫描判定、优化建议。"""

    issues: list[str] = []
    suggestions: list[str] = []
    details: list[str] = []
    index_usage: list[dict] = []
    full_scan_findings: list[dict] = []

    nodes = _walk(roots)
    for node in nodes:
        op = node.operation.lower()
        table = node.table or "Unknown"
        rows_num = node.rows_estimated

        if rows_num is not None:
            details.append(f"扫描统计：表 {table} 预估扫描 {rows_num} 行")
            if node.cost_end is not None:
                details.append(f"执行成本：cost={node.cost_start}..{node.cost_end}")

        is_full_scan = "seq scan" in op or node.access_type.upper() == "ALL"
        is_index_scan = "index scan" in op or node.access_type.upper() in {
            "REF",
            "EQ_REF",
            "RANGE",
            "INDEX",
        }

        if is_full_scan:
            if rows_num is not None and rows_num > _FULL_SCAN_SEVERE_ROWS:
                severity = "high"
                issues.append(f"严重性能问题：表 {table} 全表扫描 {rows_num} 行")
                suggestion = f"为表 {table} 创建索引以避免全表扫描 {rows_num} 行数据"
            elif rows_num is not None and rows_num > _FULL_SCAN_WARNING_ROWS:
                severity = "medium"
                issues.append(f"性能问题：表 {table} 全表扫描 {rows_num} 行")
                suggestion = f"考虑为表 {table} 创建索引，当前全表扫描 {rows_num} 行"
            elif rows_num is not None and rows_num > _FULL_SCAN_HINT_ROWS:
                severity = "low"
                suggestion = f"表 {table} 扫描 {rows_num} 行，数据量中等，建议评估是否需要索引"
            else:
                severity = "info"
                suggestions.append(f"表 {table} 数据量较小（{rows_num} 行），全表扫描效率可接受")
                details.append("小表优化：百行以内全表扫描通常比索引扫描更高效")
                suggestion = ""
            full_scan_findings.append(
                {
                    "table_name": table,
                    "rows_estimated": rows_num,
                    "severity": severity,
                    "issue": f"表 {table} 使用全表扫描（Seq Scan/ALL）",
                    "suggestion": suggestion or "数据量小，可暂不优化",
                }
            )
            index_usage.append(
                {
                    "table_name": table,
                    "access_type": node.access_type or "ALL",
                    "key_used": node.key_used or None,
                    "used_index": False,
                    "assessment": "未使用索引，执行全表扫描",
                }
            )
        elif is_index_scan:
            suggestions.append(f"性能良好：表 {table} 使用索引扫描")
            details.append(f"扫描类型：{node.access_type.upper() or op}，使用索引优化查询")
            if node.access_type.upper() in {"REF", "EQ_REF"}:
                details.append("高效访问：索引等值查找，性能最佳")
            elif node.access_type.upper() == "RANGE":
                details.append("范围扫描：索引范围查询，性能良好")
            index_usage.append(
                {
                    "table_name": table,
                    "access_type": node.access_type or node.operation,
                    "key_used": node.key_used or None,
                    "used_index": True,
                    "assessment": f"使用索引 {node.key_used or '(未命名)'} 访问数据",
                }
            )
        elif node.access_type.upper() == "CONST" or op == "const":
            details.append("常量优化：单行查找，性能极佳")
            index_usage.append(
                {
                    "table_name": table,
                    "access_type": node.access_type or "const",
                    "key_used": node.key_used or None,
                    "used_index": True,
                    "assessment": "常量级查找，性能极佳",
                }
            )

        if "nested loop" in op:
            issues.append("嵌套循环连接：大数据量时性能较差")
            suggestions.append("检查 JOIN 条件和索引，确保连接字段有索引")
            details.append("连接类型：Nested Loop，适合小结果集")

        if node.cost_end is not None:
            if node.cost_end > _HIGH_COST:
                issues.append(f"高成本查询：cost={node.cost_end}")
                suggestions.append("查询成本极高，强烈建议优化 SQL 语句")
            elif node.cost_end > _MEDIUM_COST:
                suggestions.append(f"查询成本较高（cost={node.cost_end}），可考虑优化")
            details.append(
                f"成本分析：{node.cost_end:.2f}，"
                + ("成本较高" if node.cost_end > _MEDIUM_COST else "成本适中")
            )

        if rows_num is not None:
            if rows_num > _LARGE_SCAN_ROWS:
                issues.append(f"大数据扫描：预估扫描 {rows_num} 行")
                suggestions.append("查询扫描大量数据，建议添加 WHERE 条件缩小范围")
            elif rows_num > _FULL_SCAN_SEVERE_ROWS:
                suggestions.append(f"查询扫描 {rows_num} 行，可优化查询条件")

    if not issues and not suggestions and not details:
        suggestions.append("查询执行计划分析完成，未发现明显问题")
        details.append("执行计划已解析，请查看详细执行步骤")

    return PlanAnalysis(
        roots=roots,
        index_usage=index_usage,
        full_scan_findings=full_scan_findings,
        issues=issues,
        suggestions=suggestions,
        details=details,
        node_count=len(nodes),
        max_estimated_rows=max((n.rows_estimated or 0 for n in nodes), default=0),
        max_cost=max((n.cost_end or 0.0 for n in nodes), default=0.0),
    )
