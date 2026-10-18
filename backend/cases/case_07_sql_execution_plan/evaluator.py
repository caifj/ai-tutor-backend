"""案例7 学生代码静态分析（AST 解析）。

检查学生是否实现了：
- SQL 执行计划解析器（parse_explain）
- B+ 树构建（build_btree）
- B+ 树查找（lookup）
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourceFacts:
    tree: ast.AST
    source: str
    calls: set[str] = field(default_factory=set)
    names: set[str] = field(default_factory=set)
    strings: set[str] = field(default_factory=set)
    imports: set[str] = field(default_factory=set)
    functions: list[ast.FunctionDef | ast.AsyncFunctionDef] = field(default_factory=list)
    classes: list[ast.ClassDef] = field(default_factory=list)

    @property
    def searchable(self) -> str:
        values = self.calls | self.names | self.strings | self.imports
        return " ".join(sorted(values)).lower()


@dataclass
class EvaluationReport:
    syntax_valid: bool
    functional_checks: list[dict[str, Any]]
    quality_scores: list[dict[str, Any]]
    issues: list[dict[str, Any]]

    @property
    def tests_total(self) -> int:
        return len(self.functional_checks)

    @property
    def tests_passed(self) -> int:
        return sum(bool(item["passed"]) for item in self.functional_checks)

    @property
    def pass_rate(self) -> float:
        return self.tests_passed / self.tests_total * 100 if self.tests_total else 0.0

    @property
    def functionality_score(self) -> float:
        return sum(float(item["earned"]) for item in self.functional_checks)

    def quality_score(self, dimension: str) -> float:
        return next(
            (float(row["score"]) for row in self.quality_scores if row["dimension"] == dimension),
            0.0,
        )

    @property
    def pep8_score(self) -> float:
        return self.quality_score("PEP8 规范")

    @property
    def modularity_score(self) -> float:
        return self.quality_score("模块化程度")

    @property
    def overall_score(self) -> float:
        return min(
            100.0,
            self.functionality_score + self.pep8_score + self.modularity_score,
        )


def _qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


class FactVisitor(ast.NodeVisitor):
    def __init__(self, facts: SourceFacts) -> None:
        self.facts = facts

    def visit_Call(self, node: ast.Call) -> None:
        name = _qualified_name(node.func)
        if name:
            self.facts.calls.add(name.lower())
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        self.facts.names.add(node.id.lower())

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.facts.names.add(node.attr.lower())
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            self.facts.strings.add(node.value.lower())
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.facts.imports.add(alias.name.lower())
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in node.names:
            self.facts.imports.add(f"{module}.{alias.name}".lower())
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.facts.functions.append(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.facts.functions.append(node)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.facts.classes.append(node)
        self.generic_visit(node)


def evaluate_python_source(source: str) -> EvaluationReport:
    """静态分析学生代码，检查功能实现和代码质量。"""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return EvaluationReport(
            syntax_valid=False,
            functional_checks=[],
            quality_scores=[],
            issues=[
                {
                    "severity": "error",
                    "line": exc.lineno,
                    "code": "SYNTAX_ERROR",
                    "message": f"语法错误：{exc.msg}",
                    "suggestion": "请修复语法错误后重新提交",
                }
            ],
        )

    facts = SourceFacts(tree=tree, source=source)
    FactVisitor(facts).visit(tree)

    functional_checks = _check_functionality(facts)
    quality_scores = _check_quality(facts, source)
    issues = _check_issues(facts, source)

    return EvaluationReport(
        syntax_valid=True,
        functional_checks=functional_checks,
        quality_scores=quality_scores,
        issues=issues,
    )


def _check_functionality(facts: SourceFacts) -> list[dict[str, Any]]:
    """检查功能实现。"""
    checks = []

    # 检查1：是否实现 parse_explain 函数
    has_parse_explain = any(f.name == "parse_explain" for f in facts.functions)
    checks.append(
        {
            "check_id": "PARSE_EXPLAIN",
            "title": "实现 SQL 执行计划解析函数 parse_explain",
            "passed": has_parse_explain,
            "weight": 30.0,
            "earned": 30.0 if has_parse_explain else 0.0,
            "evidence": "找到 parse_explain 函数定义" if has_parse_explain else "未找到 parse_explain 函数",
            "suggestion": "实现 parse_explain(plan_text) 函数，解析 EXPLAIN 输出" if not has_parse_explain else "",
        }
    )

    # 检查2：是否实现 build_btree 函数
    has_build_btree = any(f.name == "build_btree" for f in facts.functions)
    checks.append(
        {
            "check_id": "BUILD_BTREE",
            "title": "实现 B+ 树构建函数 build_btree",
            "passed": has_build_btree,
            "weight": 25.0,
            "earned": 25.0 if has_build_btree else 0.0,
            "evidence": "找到 build_btree 函数定义" if has_build_btree else "未找到 build_btree 函数",
            "suggestion": "实现 build_btree(keys, order) 函数，构建 B+ 树" if not has_build_btree else "",
        }
    )

    # 检查3：是否实现 lookup 函数
    has_lookup = any(f.name in ("lookup", "btree_lookup", "search") for f in facts.functions)
    checks.append(
        {
            "check_id": "LOOKUP",
            "title": "实现 B+ 树查找函数",
            "passed": has_lookup,
            "weight": 25.0,
            "earned": 25.0 if has_lookup else 0.0,
            "evidence": "找到查找函数定义" if has_lookup else "未找到查找函数",
            "suggestion": "实现 lookup(root, key) 函数，返回查找路径" if not has_lookup else "",
        }
    )

    # 检查4：是否处理索引使用分析
    has_index_analysis = any(
        keyword in facts.searchable
        for keyword in ["index", "key", "索引", "type", "all", "ref", "range"]
    )
    checks.append(
        {
            "check_id": "INDEX_ANALYSIS",
            "title": "实现索引使用情况分析",
            "passed": has_index_analysis,
            "weight": 10.0,
            "earned": 10.0 if has_index_analysis else 0.0,
            "evidence": "代码中包含索引分析相关逻辑" if has_index_analysis else "未找到索引分析逻辑",
            "suggestion": "分析执行计划中的 type 字段，判断是否使用索引" if not has_index_analysis else "",
        }
    )

    # 检查5：是否处理全表扫描检测
    has_full_scan = any(
        keyword in facts.searchable
        for keyword in ["all", "full", "scan", "全表", "扫描"]
    )
    checks.append(
        {
            "check_id": "FULL_SCAN",
            "title": "实现全表扫描检测",
            "passed": has_full_scan,
            "weight": 10.0,
            "earned": 10.0 if has_full_scan else 0.0,
            "evidence": "代码中包含全表扫描检测逻辑" if has_full_scan else "未找到全表扫描检测",
            "suggestion": "检测 type=ALL 或 Seq Scan，标记为全表扫描" if not has_full_scan else "",
        }
    )

    return checks


def _check_quality(facts: SourceFacts, source: str) -> list[dict[str, Any]]:
    """检查代码质量。"""
    scores = []

    # PEP8 规范检查（简化版）
    lines = source.split("\n")
    long_lines = sum(1 for line in lines if len(line) > 100)
    has_docstring = any(facts.strings) and any('"""' in s or "'''" in s for s in facts.strings)
    pep8_score = max(0, 10 - long_lines * 0.5 - (0 if has_docstring else 2))
    scores.append(
        {
            "dimension": "PEP8 规范",
            "score": round(pep8_score, 1),
            "max_score": 10.0,
            "summary": f"超长行 {long_lines} 处，{'有' if has_docstring else '无'}文档字符串",
            "details": f"代码行数：{len(lines)}，函数数：{len(facts.functions)}",
        }
    )

    # 模块化程度
    modularity_score = min(10.0, len(facts.functions) * 2.0 + len(facts.classes) * 3.0)
    scores.append(
        {
            "dimension": "模块化程度",
            "score": round(modularity_score, 1),
            "max_score": 10.0,
            "summary": f"{len(facts.functions)} 个函数，{len(facts.classes)} 个类",
            "details": "函数和类的数量越多，模块化程度越高",
        }
    )

    return scores


def _check_issues(facts: SourceFacts, source: str) -> list[dict[str, Any]]:
    """检查代码问题。"""
    issues = []

    # 检查是否有全局变量滥用
    global_vars = [node for node in ast.walk(facts.tree) if isinstance(node, ast.Global)]
    if len(global_vars) > 3:
        issues.append(
            {
                "severity": "warning",
                "line": None,
                "code": "GLOBAL_VARS",
                "message": f"使用 {len(global_vars)} 个全局变量",
                "suggestion": "尽量减少全局变量使用，改用参数传递",
            }
        )

    # 检查是否有未处理的异常
    try_except = [node for node in ast.walk(facts.tree) if isinstance(node, ast.Try)]
    if not try_except and "open" in facts.calls:
        issues.append(
            {
                "severity": "warning",
                "line": None,
                "code": "NO_EXCEPTION_HANDLING",
                "message": "文件操作未使用异常处理",
                "suggestion": "使用 try-except 处理可能的 IO 错误",
            }
        )

    # 检查是否有硬编码密码
    if re.search(r'password\s*=\s*["\'][^"\']+["\']', source, re.IGNORECASE):
        issues.append(
            {
                "severity": "warning",
                "line": None,
                "code": "HARDCODED_PASSWORD",
                "message": "代码中可能包含硬编码密码",
                "suggestion": "使用环境变量或配置文件存储敏感信息",
            }
        )

    return issues
