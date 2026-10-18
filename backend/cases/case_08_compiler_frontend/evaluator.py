# -*- coding: utf-8 -*-
"""案例 8 静态评测：检查提交的 Python 文件是否实现词法/语法分析接口并给出质量分。

设计原则（与案例 3/5/7 保持一致）：

* **只做静态分析**，不执行学生代码（执行在沙箱里由 ``runtime_harness`` 完成）；
* 每个检查项都是"可从源码判定"的客观事实，避免猜测；
* 产出的三个列表直接对应数据集 ``functional_tests`` / ``quality_scores`` / ``code_issues``。
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

MAX_FILE_LINES = 1200
MAX_FUNCTION_LINES = 40
MAX_LINE_LENGTH = 100

REQUIRED_TOKENIZE = ("tokenize", "analyze")
REQUIRED_PARSE = ("parse", "analyze")


@dataclass
class EvaluationReport:
    """静态评测结果（与数据集一一对应）。"""

    syntax_valid: bool = False
    functional_checks: list[dict] = field(default_factory=list)
    quality_scores: list[dict] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    pep8_score: float = 0.0
    modularity_score: float = 0.0

    @property
    def tests_total(self) -> int:
        return len(self.functional_checks)

    @property
    def tests_passed(self) -> int:
        return sum(1 for item in self.functional_checks if item["passed"])

    @property
    def pass_rate(self) -> float:
        return self.tests_passed / self.tests_total * 100 if self.tests_total else 0.0

    @property
    def functionality_score(self) -> float:
        """功能分（满分 80）：按权重加权。"""
        total = sum(float(item["weight"]) for item in self.functional_checks) or 1.0
        earned = sum(float(item["earned"]) for item in self.functional_checks)
        return earned / total * 80


def _issue(severity: str, line: int | None, code: str, message: str, suggestion: str) -> dict:
    return {
        "severity": severity,
        "line": line,
        "code": code,
        "message": message,
        "suggestion": suggestion,
    }


def _check(check_id: str, title: str, passed: bool, weight: float,
           evidence: str, suggestion: str = "") -> dict:
    return {
        "check_id": check_id,
        "title": title,
        "passed": bool(passed),
        "weight": float(weight),
        "earned": float(weight) if passed else 0.0,
        "evidence": evidence[:300],
        "suggestion": "" if passed else suggestion[:300],
    }


def _function_names(tree: ast.AST) -> dict[str, ast.AST]:
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _is_snake(name: str) -> bool:
    return bool(re.fullmatch(r"_?[a-z][a-z0-9_]*", name))


def _is_camel(name: str) -> bool:
    return bool(re.fullmatch(r"_?[A-Z][A-Za-z0-9]*", name))


def _annotation_ratio(functions: dict[str, ast.AST]) -> float:
    if not functions:
        return 0.0
    annotated = 0
    total = 0
    for fn in functions.values():
        args = list(fn.args.args) + list(fn.args.kwonlyargs)
        for arg in args:
            if arg.arg in ("self", "cls"):
                continue
            total += 1
            annotated += 1 if arg.annotation is not None else 0
        total += 1
        annotated += 1 if fn.returns is not None else 0
    return annotated / total if total else 0.0


def _has_docstring(tree: ast.Module, functions: dict[str, ast.AST]) -> bool:
    if ast.get_docstring(tree):
        return True
    return any(ast.get_docstring(fn) for fn in functions.values())


def evaluate_python_source(source: str) -> EvaluationReport:
    """对提交的源码做静态评测。"""
    report = EvaluationReport()
    lines = source.splitlines()

    # ---------------- 1. 语法检查 ----------------
    try:
        tree = ast.parse(source)
        report.syntax_valid = True
    except SyntaxError as exc:
        report.syntax_valid = False
        report.functional_checks.append(_check(
            "PYTHON_SYNTAX", "Python 源码可被解析（无语法错误）", False, 20,
            f"第 {exc.lineno} 行：{exc.msg}",
            "先修复 Python 语法错误再提交",
        ))
        report.issues.append(_issue(
            "error", exc.lineno, "PYTHON_SYNTAX_ERROR",
            exc.msg or "Python 语法错误", "按提示修复该行后重新提交",
        ))
        report.quality_scores.append({
            "dimension": "可解析性", "score": 0.0, "max_score": 10.0,
            "summary": "源码无法解析", "details": f"第 {exc.lineno} 行：{exc.msg}",
        })
        return report

    functions = _function_names(tree)
    class_count = sum(1 for node in ast.walk(tree) if isinstance(node, ast.ClassDef))
    has_tokenize = any(name in functions for name in REQUIRED_TOKENIZE)
    has_parse = any(name in functions for name in REQUIRED_PARSE)
    has_doc = _has_docstring(tree, functions)
    annotation_ratio = _annotation_ratio(functions)

    # ---------------- 2. 安全与规范扫描 ----------------
    banned_calls: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id
            if name in ("eval", "exec"):
                banned_calls.append((getattr(node, "lineno", 0), name))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in ("subprocess", "os"):
                    banned_calls.append((node.lineno, f"import {alias.name}"))
    wildcard_imports = [
        node.lineno for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and any(alias.name == "*" for alias in node.names)
    ]
    bare_excepts = [
        node.lineno for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler) and node.type is None
    ]
    long_lines = [i for i, text in enumerate(lines, 1) if len(text) > MAX_LINE_LENGTH]
    tab_lines = [i for i, text in enumerate(lines, 1) if "\t" in text]
    trailing = [i for i, text in enumerate(lines, 1) if text != text.rstrip()]
    snake_violations = [
        fn.name for fn in functions.values()
        if not _is_snake(fn.name) and not (fn.name.startswith("__") and fn.name.endswith("__"))
    ]
    class_violations = [
        node.name for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and not _is_camel(node.name)
    ]

    # ---------------- 3. 功能检查（静态） ----------------
    report.functional_checks.extend([
        _check("PYTHON_SYNTAX", "Python 源码可被解析（无语法错误）", True, 20,
               f"共 {len(lines)} 行，解析成功"),
        _check("API_TOKENIZE", "定义了 tokenize(source) 或 analyze(source)",
               has_tokenize, 15,
               "已定义：" + "、".join(n for n in REQUIRED_TOKENIZE if n in functions)
               if has_tokenize else "未找到 tokenize/analyze 函数",
               "按契约实现 tokenize(source) -> list[dict]"),
        _check("API_PARSE", "定义了 parse(source) 或 analyze(source)",
               has_parse, 15,
               "已定义：" + "、".join(n for n in REQUIRED_PARSE if n in functions)
               if has_parse else "未找到 parse/analyze 函数",
               "按契约实现 parse(source) -> {'ast':..., 'errors':[...]}"),
        _check("HELPER_STRUCTURE", "至少定义 2 个函数（含辅助函数，便于分模块）",
               len(functions) >= 2, 10,
               f"共定义 {len(functions)} 个函数：{', '.join(list(functions)[:6])}",
               "把词法、语法分析拆成独立函数"),
        _check("NO_UNSAFE_CALL", "未使用 eval/exec 或导入 subprocess/os",
               not banned_calls, 10,
               "未发现不安全调用" if not banned_calls
               else f"发现：{banned_calls[:3]}",
               "移除 eval/exec 与系统调用，改用标准解析逻辑"),
        _check("NO_WILDCARD_IMPORT", "未使用 from x import *",
               not wildcard_imports, 5,
               "未发现通配符导入" if not wildcard_imports else f"第 {wildcard_imports} 行",
               "显式导入所需名称"),
        _check("HAS_DOCSTRING", "模块或函数包含说明文档（docstring）",
               has_doc, 5,
               "存在 docstring" if has_doc else "未找到 docstring",
               "为模块与关键函数补充 docstring"),
        _check("HAS_TYPE_HINTS", "参数/返回值带类型注解（覆盖率 ≥ 50%）",
               annotation_ratio >= 0.5, 5,
               f"注解覆盖率 {annotation_ratio:.0%}",
               "为 tokenize/parse 的入参与返回值补类型注解"),
    ])

    # ---------------- 4. 代码质量评分（PEP8 风格，满分 10） ----------------
    pep8_items: list[tuple[str, bool, str]] = [
        (f"每行不超过 {MAX_LINE_LENGTH} 字符", not long_lines,
         "全部符合" if not long_lines else f"第 {long_lines[:5]} 行超长"),
        ("使用空格缩进（无 Tab）", not tab_lines,
         "未发现 Tab" if not tab_lines else f"第 {tab_lines[:5]} 行含 Tab"),
        ("无行尾多余空白", not trailing,
         "未发现行尾空白" if not trailing else f"第 {trailing[:5]} 行"),
        ("函数名符合 snake_case", not snake_violations,
         "命名规范" if not snake_violations else f"不规范：{snake_violations[:5]}"),
        ("类名符合 CamelCase", not class_violations,
         "命名规范" if not class_violations else f"不规范：{class_violations[:5]}"),
        ("无通配符导入", not wildcard_imports,
         "未发现" if not wildcard_imports else f"第 {wildcard_imports[:5]} 行"),
        ("无裸 except", not bare_excepts,
         "未发现" if not bare_excepts else f"第 {bare_excepts[:5]} 行"),
        ("文件以换行结尾", source.endswith("\n") if source else True,
         "符合" if source.endswith("\n") or not source else "文件末尾缺少换行"),
    ]
    pep8_weight = 10.0 / len(pep8_items)
    pep8_score = sum(pep8_weight for _, ok, _ in pep8_items if ok)
    report.pep8_score = round(pep8_score, 2)
    report.quality_scores.append({
        "dimension": "PEP8 规范", "score": report.pep8_score, "max_score": 10.0,
        "summary": f"{sum(1 for _, ok, _ in pep8_items if ok)}/{len(pep8_items)} 项符合",
        "details": "；".join(f"{name}：{'√' if ok else '×（' + detail + '）'}"
                            for name, ok, detail in pep8_items),
    })

    # ---------------- 5. 模块化评分（满分 10） ----------------
    fn_lengths = [
        (fn.end_lineno or fn.lineno) - fn.lineno + 1
        for fn in functions.values()
        if getattr(fn, "end_lineno", None)
    ]
    avg_len = sum(fn_lengths) / len(fn_lengths) if fn_lengths else 0.0
    modularity_items = [
        ("函数数量 ≥ 3", len(functions) >= 3, f"共 {len(functions)} 个函数"),
        ("存在类或函数数量 ≥ 5", class_count >= 1 or len(functions) >= 5,
         f"{class_count} 个类 / {len(functions)} 个函数"),
        (f"平均函数长度 ≤ {MAX_FUNCTION_LINES} 行", 0 < avg_len <= MAX_FUNCTION_LINES,
         f"平均 {avg_len:.1f} 行"),
        ("类型注解覆盖率 ≥ 50%", annotation_ratio >= 0.5, f"{annotation_ratio:.0%}"),
        ("具备 docstring", has_doc, "有" if has_doc else "无"),
    ]
    modularity_weight = 10.0 / len(modularity_items)
    modularity_score = sum(modularity_weight for _, ok, _ in modularity_items if ok)
    report.modularity_score = round(modularity_score, 2)
    report.quality_scores.append({
        "dimension": "模块化程度", "score": report.modularity_score, "max_score": 10.0,
        "summary": f"{sum(1 for _, ok, _ in modularity_items if ok)}/{len(modularity_items)} 项符合",
        "details": "；".join(f"{name}：{'√' if ok else '×（' + detail + '）'}"
                            for name, ok, detail in modularity_items),
    })
    report.quality_scores.append({
        "dimension": "文件规模", "score": 10.0 if len(lines) <= MAX_FILE_LINES else 0.0,
        "max_score": 10.0,
        "summary": f"{len(lines)} 行" + ("（规模合理）" if len(lines) <= MAX_FILE_LINES else "（过长）"),
        "details": f"上限建议 {MAX_FILE_LINES} 行；单文件过大建议拆分模块",
    })

    # ---------------- 6. 问题清单 ----------------
    for line, name in banned_calls:
        report.issues.append(_issue(
            "error", line, "UNSAFE_CALL",
            f"使用了不允许的 {name}",
            "沙箱中禁止 eval/exec/subprocess，请用标准解析实现",
        ))
    for line in bare_excepts[:5]:
        report.issues.append(_issue(
            "warning", line, "BARE_EXCEPT", "裸 except 会吞掉所有异常",
            "改为 except Exception as exc 并记录原因",
        ))
    for line in wildcard_imports[:5]:
        report.issues.append(_issue(
            "warning", line, "WILDCARD_IMPORT", "from x import * 会污染命名空间",
            "显式导入所需名称",
        ))
    for line in long_lines[:5]:
        report.issues.append(_issue(
            "info", line, "LINE_TOO_LONG", f"该行超过 {MAX_LINE_LENGTH} 字符",
            "拆分表达式或提取局部变量",
        ))
    for line in tab_lines[:3]:
        report.issues.append(_issue(
            "info", line, "TAB_INDENT", "使用了 Tab 缩进",
            "统一改为 4 个空格",
        ))
    for name in snake_violations[:5]:
        report.issues.append(_issue(
            "info", None, "FUNC_NAMING", f"函数名 {name!r} 不符合 snake_case",
            "改为小写字母加下划线",
        ))
    for name in class_violations[:3]:
        report.issues.append(_issue(
            "info", None, "CLASS_NAMING", f"类名 {name!r} 不符合 CamelCase",
            "改为大驼峰命名",
        ))
    if not has_tokenize:
        report.issues.append(_issue(
            "error", None, "MISSING_TOKENIZE",
            "未实现 tokenize/analyze，词法分析接口缺失",
            "按契约实现 tokenize(source) -> list[dict]",
        ))
    if not has_parse:
        report.issues.append(_issue(
            "error", None, "MISSING_PARSE",
            "未实现 parse/analyze，语法分析接口缺失",
            "按契约实现 parse(source) -> {'ast':..., 'errors':[...]}",
        ))

    return report
