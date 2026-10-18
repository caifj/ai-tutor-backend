from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any

from .models import ColumnSpec, Dataset, DataType


@dataclass(frozen=True, slots=True)
class PythonStaticEvaluation:
    """Case-independent Python source quality evaluation."""

    syntax_valid: bool
    quality_scores: list[dict[str, Any]]
    issues: list[dict[str, Any]]

    def score(self, dimension: str) -> float:
        return next(
            (float(row["score"]) for row in self.quality_scores if row["dimension"] == dimension),
            0.0,
        )

    @property
    def pep8_score(self) -> float:
        return self.score("PEP8 规范")

    @property
    def modularity_score(self) -> float:
        return self.score("模块化程度")


def _issue(
    severity: str,
    line: int | None,
    code: str,
    message: str,
    suggestion: str,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "line": line,
        "code": code,
        "message": message,
        "suggestion": suggestion,
    }


def _quality_row(dimension: str, score: float, summary: str, details: str) -> dict[str, Any]:
    return {
        "dimension": dimension,
        "score": score,
        "max_score": 10.0,
        "summary": summary,
        "details": details,
    }


def _pep8_quality(source: str, tree: ast.AST) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    score = 10.0
    issues: list[dict[str, Any]] = []
    lines = source.splitlines()
    long_lines = [number for number, line in enumerate(lines, 1) if len(line) > 100]
    tabs = [
        number
        for number, line in enumerate(lines, 1)
        if "\t" in line[: len(line) - len(line.lstrip())]
    ]
    trailing = [number for number, line in enumerate(lines, 1) if line.rstrip() != line]
    wildcard = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names)
    ]
    checks = [
        (long_lines, 3.0, "E501", "行长度超过 100 个字符", "拆分长表达式或长字符串。"),
        (tabs, 1.5, "W191", "缩进中使用了制表符", "统一使用 4 个空格缩进。"),
        (trailing, 1.0, "W291", "行尾存在多余空白", "删除行尾空白。"),
        (wildcard, 1.5, "F403", "使用了通配符导入", "显式导入所需名称。"),
    ]
    for positions, deduction, code, message, suggestion in checks:
        if positions:
            score -= min(deduction, len(positions) * 0.5)
            issues.extend(
                _issue("style", line, code, message, suggestion) for line in positions[:8]
            )

    bad_names = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not re.fullmatch(r"[a-z_][a-z0-9_]*", node.name)
    ]
    if bad_names:
        score -= min(2.0, len(bad_names) * 0.5)
        issues.extend(
            _issue(
                "style",
                node.lineno,
                "N802",
                f"函数名 {node.name!r} 不符合 snake_case",
                "使用小写字母和下划线命名函数。",
            )
            for node in bad_names[:5]
        )

    score = max(0.0, round(score, 1))
    return (
        _quality_row(
            "PEP8 规范",
            score,
            "规范良好" if score >= 8 else "存在可改进的格式问题",
            f"长行 {len(long_lines)}，Tab 缩进 {len(tabs)}，行尾空白 {len(trailing)}，"
            f"通配符导入 {len(wildcard)}。",
        ),
        issues,
    )


def _modularity_quality(tree: ast.AST) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    functions = [
        node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    count = len(functions)
    score = 0.0 if count == 0 else 4.0 if count == 1 else 6.0 if count <= 3 else 8.0
    documented = sum(bool(ast.get_docstring(function)) for function in functions)
    score += 1.0 if classes else 0.0
    score += 1.0 if count and documented / count >= 0.5 else 0.0
    issues: list[dict[str, Any]] = []
    long_functions: list[tuple[str, int, int]] = []
    for function in functions:
        end = getattr(function, "end_lineno", function.lineno) or function.lineno
        length = end - function.lineno + 1
        if length > 60:
            long_functions.append((function.name, function.lineno, length))
            score -= 1.5
            issues.append(
                _issue(
                    "quality",
                    function.lineno,
                    "C901",
                    f"函数 {function.name!r} 长达 {length} 行",
                    "将较长函数按输入、处理和输出等职责拆分。",
                )
            )
    if count < 2:
        issues.append(
            _issue(
                "quality",
                None,
                "MOD001",
                "可识别的函数数量偏少，职责可能未充分拆分",
                "将独立职责提取为命名清晰、便于测试的函数或类。",
            )
        )
    score = max(0.0, min(10.0, round(score, 1)))
    return (
        _quality_row(
            "模块化程度",
            score,
            "职责拆分清晰" if score >= 8 else "模块化程度仍可提升",
            f"函数 {count} 个，类 {len(classes)} 个，有文档字符串的函数 {documented} 个，"
            f"超过 60 行的函数 {len(long_functions)} 个。",
        ),
        issues,
    )


def evaluate_python_static(source: str, filename: str = "submission.py") -> PythonStaticEvaluation:
    """Evaluate only generic Python quality; never import or execute the source."""

    try:
        tree = ast.parse(source, filename=filename)
    except (SyntaxError, ValueError) as exc:
        line = exc.lineno if isinstance(exc, SyntaxError) else 1
        message = exc.msg if isinstance(exc, SyntaxError) else str(exc)
        return PythonStaticEvaluation(
            syntax_valid=False,
            quality_scores=[
                _quality_row("PEP8 规范", 0.0, "无法评分", "Python 语法无效。"),
                _quality_row("模块化程度", 0.0, "无法评分", "Python 语法无效。"),
            ],
            issues=[
                _issue(
                    "error",
                    line,
                    "E999",
                    f"Python 语法错误：{message}",
                    "根据行号修复语法后重新提交。",
                )
            ],
        )

    pep8, pep8_issues = _pep8_quality(source, tree)
    modularity, modularity_issues = _modularity_quality(tree)
    return PythonStaticEvaluation(
        syntax_valid=True,
        quality_scores=[pep8, modularity],
        issues=pep8_issues + modularity_issues,
    )


def quality_dataset(evaluation: PythonStaticEvaluation) -> Dataset:
    return Dataset(
        name="quality_scores",
        title="基座通用静态测评",
        columns=[
            ColumnSpec(key="dimension", title="维度", data_type=DataType.STRING),
            ColumnSpec(key="score", title="得分", data_type=DataType.NUMBER),
            ColumnSpec(key="max_score", title="满分", data_type=DataType.NUMBER),
            ColumnSpec(key="summary", title="结论", data_type=DataType.STRING),
            ColumnSpec(key="details", title="评分依据", data_type=DataType.STRING),
        ],
        rows=evaluation.quality_scores,
    )


def issues_dataset(evaluation: PythonStaticEvaluation) -> Dataset:
    return Dataset(
        name="code_issues",
        title="通用代码问题与建议",
        columns=[
            ColumnSpec(key="severity", title="级别", data_type=DataType.STRING),
            ColumnSpec(key="line", title="行号", data_type=DataType.INTEGER, nullable=True),
            ColumnSpec(key="code", title="规则", data_type=DataType.STRING),
            ColumnSpec(key="message", title="问题", data_type=DataType.STRING),
            ColumnSpec(key="suggestion", title="建议", data_type=DataType.STRING),
        ],
        rows=evaluation.issues,
    )
