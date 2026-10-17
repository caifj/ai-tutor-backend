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
    containers: set[str] = field(default_factory=set)

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
        return min(100.0, self.functionality_score + self.pep8_score + self.modularity_score)


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
            normalized = " ".join(node.value.lower().split())
            if normalized:
                self.facts.strings.add(normalized[:300])

    def visit_Import(self, node: ast.Import) -> None:
        self.facts.imports.update(alias.name.lower() for alias in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = (node.module or "").lower()
        self.facts.imports.add(module)
        self.facts.imports.update(f"{module}.{alias.name.lower()}" for alias in node.names)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.facts.functions.append(node)
        self.facts.names.add(node.name.lower())
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.facts.functions.append(node)
        self.facts.names.add(node.name.lower())
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.facts.classes.append(node)
        self.facts.names.add(node.name.lower())
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        self.facts.containers.add("dict")
        self.generic_visit(node)

    def visit_Set(self, node: ast.Set) -> None:
        self.facts.containers.add("set")
        self.generic_visit(node)


def _collect_facts(tree: ast.AST, source: str) -> SourceFacts:
    facts = SourceFacts(tree=tree, source=source)
    FactVisitor(facts).visit(tree)
    return facts


def _has_any(haystack: str, needles: tuple[str, ...]) -> bool:
    return any(needle in haystack for needle in needles)


def _evidence(names: list[str], success: str, failure: str) -> str:
    return f"{success}：{', '.join(names[:4])}" if names else failure


def _found_functions(facts: SourceFacts, keywords: tuple[str, ...]) -> list[str]:
    return [
        function.name
        for function in facts.functions
        if _has_any(function.name.lower(), keywords)
    ]


CHECK_DEFINITIONS = (
    ("BUBBLE_SORT", "实现冒泡排序", 9.0),
    ("SELECTION_SORT", "实现选择排序", 9.0),
    ("QUICK_SORT", "实现快速排序", 9.0),
    ("MERGE_SORT", "实现归并排序", 9.0),
    ("LINEAR_SEARCH", "实现顺序（线性）查找", 8.0),
    ("BINARY_SEARCH", "实现二分查找", 8.0),
    ("DATA_SCALES", "在多个数据规模下采样", 8.0),
    ("TIMING", "对算法执行进行计时", 10.0),
    ("COMPLEXITY_ANALYSIS", "输出时间-规模数据并拟合复杂度曲线", 10.0),
)


def _feature_checks(facts: SourceFacts) -> list[dict[str, Any]]:
    text = facts.searchable

    bubble = _found_functions(facts, ("bubble", "冒泡"))
    selection = _found_functions(facts, ("selection", "选择"))
    quick = _found_functions(facts, ("quick", "快速", "partition"))
    merge = _found_functions(facts, ("merge", "归并"))
    linear = _found_functions(facts, ("linear_search", "linearsearch", "linear", "顺序查找", "线性查找"))
    binary = _found_functions(facts, ("binary_search", "binarysearch", "binary", "二分"))

    scales = (
        _has_any(text, ("size", "sizes", "规模", "max_size", "n_values", "dataset_size"))
        and ("range" in facts.calls or "len" in facts.calls)
    )
    timing_calls = sorted(
        call
        for call in facts.calls
        if _has_any(
            call,
            ("timeit", "perf_counter", "process_time", "time.time", "default_timer", "perf"),
        )
    )
    timing = bool(timing_calls) or bool(facts.imports & {"time", "timeit"})

    fitting = _has_any(
        text,
        (
            "polyfit",
            "curve_fit",
            "log2",
            "math.log",
            "numpy",
            "np.log",
            "拟合",
            "复杂度",
            "r_squared",
            "least_squares",
            "complexity",
        ),
    )
    serializers = sorted(
        call
        for call in facts.calls
        if _has_any(call, ("json.dump", "json.dumps", "csv.writer", "to_csv", "savefig", "print"))
    )
    analysis = fitting and (bool(serializers) or "plot" in text or "return" in text)

    definitions: list[tuple[str, str, float, bool, str, str]] = [
        (
            "BUBBLE_SORT",
            "实现冒泡排序",
            9.0,
            bool(bubble),
            _evidence(bubble, "检测到冒泡排序函数", "未定位到冒泡排序实现"),
            "提供 bubble_sort 或等价函数，并正确交换相邻逆序元素。",
        ),
        (
            "SELECTION_SORT",
            "实现选择排序",
            9.0,
            bool(selection),
            _evidence(selection, "检测到选择排序函数", "未定位到选择排序实现"),
            "提供 selection_sort，每轮选出最小值放到当前位置。",
        ),
        (
            "QUICK_SORT",
            "实现快速排序",
            9.0,
            bool(quick),
            _evidence(quick, "检测到快速排序函数", "未定位到快速排序/分区实现"),
            "提供 quick_sort 与分区逻辑，明确选取基准并递归左右子区间。",
        ),
        (
            "MERGE_SORT",
            "实现归并排序",
            9.0,
            bool(merge),
            _evidence(merge, "检测到归并排序函数", "未定位到归并排序实现"),
            "提供 merge_sort 与合并函数，对两个有序子序列做归并。",
        ),
        (
            "LINEAR_SEARCH",
            "实现顺序（线性）查找",
            8.0,
            bool(linear),
            _evidence(linear, "检测到顺序查找函数", "未定位到顺序/线性查找实现"),
            "逐个比较元素，找到目标返回下标，否则返回 -1。",
        ),
        (
            "BINARY_SEARCH",
            "实现二分查找",
            8.0,
            bool(binary),
            _evidence(binary, "检测到二分查找函数", "未定位到二分查找实现"),
            "在有序序列上使用双指针 mid 折半查找。",
        ),
        (
            "DATA_SCALES",
            "在多个数据规模下采样",
            8.0,
            scales,
            "检测到按数据规模生成/遍历样本" if scales else "未发现按不同数据规模取样的逻辑",
            "用 sizes/range 生成多组不同规模的随机数据，覆盖从较小到较大的 n。",
        ),
        (
            "TIMING",
            "对算法执行进行计时",
            10.0,
            timing,
            f"计时调用：{', '.join(timing_calls[:4])}" if timing_calls else "未发现计时调用",
            "使用 timeit 或 time.perf_counter 记录每个规模下的执行耗时。",
        ),
        (
            "COMPLEXITY_ANALYSIS",
            "输出时间-规模数据并拟合复杂度曲线",
            10.0,
            analysis,
            (
                f"拟合/输出：{', '.join((*serializers[:3], '拟合'))}"
                if analysis
                else "未发现时间-规模数据输出与复杂度拟合逻辑"
            ),
            "输出各规模的运行时间，并用 polyfit/对数变换等方法拟合复杂度曲线。",
        ),
    ]
    return [
        {
            "check_id": check_id,
            "title": title,
            "passed": passed,
            "weight": weight,
            "earned": weight if passed else 0.0,
            "evidence": evidence,
            "suggestion": "已识别到对应实现。" if passed else suggestion,
        }
        for check_id, title, weight, passed, evidence, suggestion in definitions
    ]


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
            issues.extend(_issue("style", line, code, message, suggestion) for line in positions[:8])

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
    summary = "规范良好" if score >= 8 else "存在可改进的格式问题"
    details = (
        f"长行 {len(long_lines)}，Tab 缩进 {len(tabs)}，行尾空白 {len(trailing)}，"
        f"通配符导入 {len(wildcard)}。"
    )
    return _quality_row("PEP8 规范", score, summary, details), issues


def _modularity_quality(facts: SourceFacts) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    count = len(facts.functions)
    score = 0.0 if count == 0 else 4.0 if count == 1 else 6.0 if count <= 3 else 8.0
    issues: list[dict[str, Any]] = []
    documented = sum(bool(ast.get_docstring(function)) for function in facts.functions)
    score += 1.0 if facts.classes else 0.0
    score += 1.0 if count and documented / count >= 0.5 else 0.0
    long_functions: list[tuple[str, int, int]] = []
    for function in facts.functions:
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
                    "把排序、查找、计时和拟合逻辑拆分成独立函数。",
                )
            )
    if count < 4:
        issues.append(
            _issue(
                "quality",
                None,
                "MOD001",
                "可识别的函数数量偏少，职责可能未充分拆分",
                "为排序、查找、基准测试和复杂度拟合分别提供函数或类。",
            )
        )
    score = max(0.0, min(10.0, round(score, 1)))
    summary = "职责拆分清晰" if score >= 8 else "模块化程度仍可提升"
    details = (
        f"函数 {count} 个，类 {len(facts.classes)} 个，有文档字符串的函数 {documented} 个，"
        f"超过 60 行的函数 {len(long_functions)} 个。"
    )
    return _quality_row("模块化程度", score, summary, details), issues


def _security_issues(facts: SourceFacts) -> list[dict[str, Any]]:
    risky = {
        "eval": "eval 会执行动态表达式",
        "exec": "exec 会执行动态代码",
        "os.system": "os.system 会启动外部命令",
        "subprocess.run": "subprocess.run 会启动外部进程",
        "subprocess.popen": "subprocess.Popen 会启动外部进程",
    }
    issues: list[dict[str, Any]] = []
    for node in ast.walk(facts.tree):
        if isinstance(node, ast.Call) and _qualified_name(node.func).lower() in risky:
            name = _qualified_name(node.func).lower()
            issues.append(
                _issue(
                    "warning",
                    node.lineno,
                    "SEC001",
                    risky[name],
                    "避免在复杂度分析任务中执行不受信任的代码或系统命令。",
                )
            )
    return issues


def _syntax_failure(exc: SyntaxError) -> EvaluationReport:
    checks = [
        {
            "check_id": check_id,
            "title": title,
            "passed": False,
            "weight": weight,
            "earned": 0.0,
            "evidence": "Python 语法解析失败，无法继续静态分析。",
            "suggestion": "先修复语法错误，再重新提交。",
        }
        for check_id, title, weight in CHECK_DEFINITIONS
    ]
    issue = _issue(
        "error",
        exc.lineno,
        "E999",
        f"Python 语法错误：{exc.msg}",
        "根据行号修复语法后重新提交。",
    )
    quality = [
        _quality_row("PEP8 规范", 0.0, "无法评分", "语法无效。"),
        _quality_row("模块化程度", 0.0, "无法评分", "语法无效。"),
    ]
    return EvaluationReport(False, checks, quality, [issue])


def evaluate_python_source(source: str) -> EvaluationReport:
    """Evaluate a submission without importing or executing it."""

    try:
        tree = ast.parse(source, filename="submission.py")
    except SyntaxError as exc:
        return _syntax_failure(exc)
    except ValueError as exc:
        return _syntax_failure(SyntaxError(str(exc), ("submission.py", 1, 1, "")))

    facts = _collect_facts(tree, source)
    pep8, pep8_issues = _pep8_quality(source, tree)
    modularity, modularity_issues = _modularity_quality(facts)
    return EvaluationReport(
        syntax_valid=True,
        functional_checks=_feature_checks(facts),
        quality_scores=[pep8, modularity],
        issues=pep8_issues + modularity_issues + _security_issues(facts),
    )
