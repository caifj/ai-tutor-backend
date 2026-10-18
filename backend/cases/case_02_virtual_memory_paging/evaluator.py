"""案例2 学生代码静态分析（AST 解析，不执行学生代码）。

按虚拟内存分页模拟器的功能要求逐项检查学生提交的实现：

1. 页表与物理页框管理
2. 逻辑地址到物理地址的转换（页号 / 页内偏移）
3. 缺页中断处理
4. FIFO（先进先出）页面置换
5. LRU（最近最久未使用）页面置换
6. OPT（最佳置换）页面置换
7. 缺页次数与缺页率统计
8. 扫描多档内存页框数并输出缺页率曲线数据

判定依据只取自 AST 结构（函数名、参数名、属性名、字符串字面量、运算节点、循环结构），
文档字符串不参与关键词匹配，避免"注释里写了 OPT 就得分"。
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any

#: 功能检查满分，与案例 3 / 5 / 7 保持一致（80 + PEP8 10 + 模块化 10）。
FUNCTIONALITY_MAX_SCORE = 80.0

#: 判定"多档内存页框数扫描"的循环变量名。
FRAME_SWEEP_TOKENS = frozenset(
    {
        "frame_count",
        "frames",
        "frame_total",
        "frame_num",
        "frame_number",
        "frame_size",
        "frame_capacity",
        "num_frames",
        "memory_frames",
        "page_frames",
    }
)


@dataclass
class SourceFacts:
    """从 AST 抽取的、与本案例判定相关的事实集合。"""

    tree: ast.AST
    source: str
    calls: set[str] = field(default_factory=set)
    names: set[str] = field(default_factory=set)
    attributes: set[str] = field(default_factory=set)
    strings: set[str] = field(default_factory=set)
    imports: set[str] = field(default_factory=set)
    decorators: set[str] = field(default_factory=set)
    functions: list[ast.FunctionDef | ast.AsyncFunctionDef] = field(default_factory=list)
    classes: list[ast.ClassDef] = field(default_factory=list)
    for_loops: list[ast.For] = field(default_factory=list)
    if_statements: int = 0
    comparisons: int = 0
    divisions: int = 0
    floor_divisions: int = 0
    modulo_ops: int = 0
    divmod_calls: int = 0
    annotated_definitions: int = 0
    global_statements: int = 0
    try_statements: int = 0
    raise_statements: int = 0
    small_integer_literals: set[int] = field(default_factory=set)

    @property
    def function_names(self) -> set[str]:
        return {node.name.lower() for node in self.functions}

    @property
    def class_names(self) -> set[str]:
        return {node.name.lower() for node in self.classes}

    @property
    def parameter_names(self) -> set[str]:
        values: set[str] = set()
        for node in self.functions:
            arguments = node.args
            candidates = (
                list(arguments.posonlyargs)
                + list(arguments.args)
                + list(arguments.kwonlyargs)
            )
            values.update(argument.arg.lower() for argument in candidates)
            for extra in (arguments.vararg, arguments.kwarg):
                if extra is not None:
                    values.add(extra.arg.lower())
        return values

    @property
    def identifiers(self) -> set[str]:
        """参与关键词匹配的标识符集合（含局部变量名）。"""

        return (
            self.function_names
            | self.class_names
            | self.parameter_names
            | {name.lower() for name in self.names}
            | {name.lower() for name in self.attributes}
            | {name.lower() for name in self.decorators}
        )

    @property
    def haystack(self) -> str:
        """除文档字符串外的全部可搜索文本，统一转小写。"""

        values = self.identifiers | self.strings | self.imports | self.calls
        return " ".join(sorted(values)).lower()


@dataclass
class EvaluationReport:
    """案例专有的评测结论。

    PEP8 与模块化由基座 ``ai_tutor_backend.static_evaluation`` 统一评估，这里不重复实现；
    ``overall_score`` 仅表示案例功能得分（满分 :data:`FUNCTIONALITY_MAX_SCORE`），
    基座会再叠加 PEP8 与模块化分数得到 100 分制的总分。
    """

    syntax_valid: bool
    functional_checks: list[dict[str, Any]]
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

    @property
    def overall_score(self) -> float:
        """案例功能得分；基座会把它与 PEP8、模块化分数相加。"""

        return self.functionality_score

    def check(self, check_id: str) -> dict[str, Any]:
        return next(item for item in self.functional_checks if item["check_id"] == check_id)

    def codes(self) -> set[str]:
        return {str(issue["code"]) for issue in self.issues}


def _qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _docstring_node_ids(tree: ast.AST) -> set[int]:
    """收集所有文档字符串常量节点的 id，便于与普通字符串区分。"""

    holders = (
        ast.Module,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
    )
    identifiers: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, holders):
            continue
        body = getattr(node, "body", [])
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            identifiers.add(id(first.value))
    return identifiers


class FactVisitor(ast.NodeVisitor):
    """把与分页模拟相关的 AST 结构抽取为 :class:`SourceFacts`。"""

    def __init__(self, facts: SourceFacts, docstring_ids: set[int]) -> None:
        self.facts = facts
        self._docstring_ids = docstring_ids

    def visit_Call(self, node: ast.Call) -> None:
        name = _qualified_name(node.func)
        if name:
            self.facts.calls.add(name.lower())
        if name.lower().split(".")[-1] == "divmod":
            self.facts.divmod_calls += 1
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        self.facts.names.add(node.id.lower())

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.facts.attributes.add(node.attr.lower())
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            if id(node) not in self._docstring_ids:
                self.facts.strings.add(node.value.lower())
        elif (
            isinstance(node.value, int)
            and not isinstance(node.value, bool)
            and 1 <= node.value <= 64
        ):
            self.facts.small_integer_literals.add(node.value)
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
        if node.returns is not None:
            self.facts.annotated_definitions += 1
        for decorator in node.decorator_list:
            self.facts.decorators.add(_qualified_name(decorator).lower())
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.facts.classes.append(node)
        for decorator in node.decorator_list:
            self.facts.decorators.add(_qualified_name(decorator).lower())
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.facts.for_loops.append(node)
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        self.facts.if_statements += 1
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        self.facts.comparisons += 1
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if isinstance(node.op, ast.Div):
            self.facts.divisions += 1
        elif isinstance(node.op, ast.FloorDiv):
            self.facts.floor_divisions += 1
        elif isinstance(node.op, ast.Mod):
            self.facts.modulo_ops += 1
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> None:
        self.facts.global_statements += 1
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        self.facts.try_statements += 1
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        self.facts.raise_statements += 1
        self.generic_visit(node)


def evaluate_python_source(source: str) -> EvaluationReport:
    """静态分析学生代码，检查分页模拟器各项功能要求与代码质量。"""

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return EvaluationReport(
            syntax_valid=False,
            functional_checks=[],
            issues=[
                {
                    "severity": "error",
                    "line": exc.lineno,
                    "code": "SYNTAX_ERROR",
                    "message": f"语法错误：{exc.msg}",
                    "suggestion": "请先修复语法错误，确保文件可被 Python 解析，再重新提交",
                }
            ],
        )

    facts = SourceFacts(tree=tree, source=source)
    FactVisitor(facts, _docstring_node_ids(tree)).visit(tree)

    detectors = {
        "PAGE_TABLE": _detect_page_table,
        "ADDRESS_TRANSLATION": _detect_address_translation,
        "PAGE_FAULT": _detect_page_fault,
        "FIFO_REPLACEMENT": _detect_fifo,
        "LRU_REPLACEMENT": _detect_lru,
        "OPT_REPLACEMENT": _detect_opt,
        "FAULT_RATE_STATISTIC": _detect_fault_rate,
        "FRAME_SWEEP": _detect_frame_sweep,
    }
    weights = {
        "PAGE_TABLE": 12.0,
        "ADDRESS_TRANSLATION": 15.0,
        "PAGE_FAULT": 10.0,
        "FIFO_REPLACEMENT": 9.0,
        "LRU_REPLACEMENT": 12.0,
        "OPT_REPLACEMENT": 8.0,
        "FAULT_RATE_STATISTIC": 7.0,
        "FRAME_SWEEP": 7.0,
    }

    functional_checks: list[dict[str, Any]] = []
    for check_id, detector in detectors.items():
        passed, evidence, suggestion = detector(facts)
        weight = weights[check_id]
        functional_checks.append(
            {
                "check_id": check_id,
                "title": _CHECK_TITLES[check_id],
                "passed": passed,
                "weight": weight,
                "earned": weight if passed else 0.0,
                "evidence": evidence,
                "suggestion": "" if passed else suggestion,
            }
        )

    return EvaluationReport(
        syntax_valid=True,
        functional_checks=functional_checks,
        issues=_check_issues(facts, functional_checks),
    )


_CHECK_TITLES: dict[str, str] = {
    "PAGE_TABLE": "建立页表并管理物理页框",
    "ADDRESS_TRANSLATION": "实现逻辑地址到物理地址的转换",
    "PAGE_FAULT": "实现缺页中断处理流程",
    "FIFO_REPLACEMENT": "实现 FIFO（先进先出）页面置换",
    "LRU_REPLACEMENT": "实现 LRU（最近最久未使用）页面置换",
    "OPT_REPLACEMENT": "实现 OPT（最佳置换）页面置换",
    "FAULT_RATE_STATISTIC": "统计缺页次数并计算缺页率",
    "FRAME_SWEEP": "扫描多档内存页框数输出曲线数据",
}

_PAGE_TABLE_WORDS = (
    "page_table",
    "pagetable",
    "page table",
    "页表",
    "frame",
    "页框",
    "free_frame",
    "block_table",
    "物理块",
)
_TRANSLATION_WORDS = (
    "translate",
    "address",
    "logical",
    "physical",
    "page_no",
    "page_num",
    "page_id",
    "page_index",
    "offset",
    "逻辑地址",
    "物理地址",
    "页号",
    "页内偏移",
    "偏移量",
)
_FAULT_WORDS = (
    "page_fault",
    "pagefault",
    "fault",
    "缺页",
    "中断",
    "interrupt",
    "swap_in",
    "page_in",
    "load_page",
    "置换",
    "淘汰",
)
_FIFO_TOKENS = ("fifo", "queue", "deque", "popleft", "appendleft")
_FIFO_WORDS = ("先进先出", "先来先出", "首次进入", "最早装入")
_LRU_TOKENS = ("lru", "used_at", "last_used", "last_access", "used_time", "timestamp", "clock")
_LRU_WORDS = ("最近最少使用", "最近最久未使用", "最久未用", "least_recently")
_OPT_TOKENS = (
    "opt",
    "optimal",
    "belady",
    "next_use",
    "next_reference",
    "next_access",
    "furthest",
    "never_used",
)
_OPT_WORDS = ("最佳置换", "最优置换", "未来最晚", "最久不再", "最远使用", "最晚被访问")
_FAULT_RATE_TOKENS = ("fault_rate", "fault_count", "faults", "page_fault", "fault_number")
_FAULT_RATE_WORDS = ("缺页率", "缺页次数", "命中率")


def _matches_word(haystack: str, words: tuple[str, ...]) -> bool:
    return any(word in haystack for word in words)


def _matches_token(facts: SourceFacts, tokens: tuple[str, ...]) -> bool:
    """短标识符按完整词匹配，避免 opt 误命中 option、faults 误命中 fault_count。"""

    values = facts.identifiers | facts.calls | facts.strings
    for token in tokens:
        if any(
            value == token
            or value.startswith(f"{token}_")
            or value.endswith(f"_{token}")
            or f"_{token}_" in value
            for value in values
        ):
            return True
    return False


def _first_symbol(facts: SourceFacts, predicate) -> str:
    """返回第一个满足条件的符号描述，用于生成可核对的判定证据。"""

    for node in facts.functions:
        if predicate(node.name.lower()):
            return f"找到函数 {node.name}（第 {node.lineno} 行）"
    for node in facts.classes:
        if predicate(node.name.lower()):
            return f"找到类 {node.name}（第 {node.lineno} 行）"
    return ""


def _detect_page_table(facts: SourceFacts) -> tuple[bool, str, str]:
    haystack = facts.haystack
    if not _matches_word(haystack, _PAGE_TABLE_WORDS):
        return False, "未找到页表或页框相关的数据结构与命名", "用页表（或页框数组）记录逻辑页到物理页框的映射关系"
    evidence = _first_symbol(
        facts,
        lambda name: any(word in name for word in ("page_table", "pagetable", "frame", "页表", "页框")),
    )
    symbol_count = len(facts.classes) + len(facts.functions)
    if evidence:
        return True, f"{evidence}；全文共定义 {symbol_count} 个函数/类", ""
    return (
        True,
        f"代码中出现页表/页框相关标识或字符串；全文共定义 {symbol_count} 个函数/类",
        "",
    )


def _detect_address_translation(facts: SourceFacts) -> tuple[bool, str, str]:
    haystack = facts.haystack
    if not _matches_word(haystack, _TRANSLATION_WORDS):
        return (
            False,
            "未找到逻辑地址 / 物理地址转换相关代码",
            "实现 translate_address(logical, page_size) 用整除求页号、取模求页内偏移",
        )
    has_split_operator = bool(facts.floor_divisions or facts.modulo_ops or facts.divmod_calls)
    evidence = _first_symbol(
        facts,
        lambda name: any(word in name for word in ("translate", "address", "页号", "偏移")),
    )
    detail = "页号与偏移使用整除 / 取模拆分" if has_split_operator else "未发现整除或取模运算"
    if evidence:
        return True, f"{evidence}；{detail}", ""
    return True, f"地址转换相关标识已出现；{detail}", ""


def _detect_page_fault(facts: SourceFacts) -> tuple[bool, str, str]:
    haystack = facts.haystack
    if not _matches_word(haystack, _FAULT_WORDS):
        return (
            False,
            "未找到缺页判断或页面换入处理代码",
            "在页面不在内存时进入缺页处理：先找空闲页框，否则触发页面置换",
        )
    evidence = _first_symbol(
        facts,
        lambda name: any(word in name for word in ("fault", "缺页", "swap_in", "page_in", "interrupt")),
    )
    branch_count = facts.if_statements + facts.comparisons
    detail = f"包含 {branch_count} 处条件判断用于区分命中与缺页"
    if evidence:
        return True, f"{evidence}；{detail}", ""
    return True, f"出现缺页相关标识；{detail}", ""


def _detect_fifo(facts: SourceFacts) -> tuple[bool, str, str]:
    haystack = facts.haystack
    if not (_matches_token(facts, _FIFO_TOKENS) or _matches_word(haystack, _FIFO_WORDS)):
        return False, "未找到 FIFO 页面置换实现", "用队列记录装入顺序，置换时换出队首页框"
    evidence = _first_symbol(
        facts,
        lambda name: any(word in name for word in ("fifo", "queue", "deque")),
    )
    return True, evidence or "出现 FIFO / 队列相关标识", ""


def _detect_lru(facts: SourceFacts) -> tuple[bool, str, str]:
    haystack = facts.haystack
    if not (_matches_token(facts, _LRU_TOKENS) or _matches_word(haystack, _LRU_WORDS)):
        return (
            False,
            "未找到 LRU 页面置换实现",
            "记录每个页框最近一次访问时间，置换时换出时间最小的页框",
        )
    evidence = _first_symbol(
        facts,
        lambda name: any(word in name for word in ("lru", "used_at", "last_used", "last_access")),
    )
    return True, evidence or "出现 LRU / 访问时间相关标识", ""


def _detect_opt(facts: SourceFacts) -> tuple[bool, str, str]:
    haystack = facts.haystack
    if not (_matches_token(facts, _OPT_TOKENS) or _matches_word(haystack, _OPT_WORDS)):
        return (
            False,
            "未找到 OPT（最佳置换）实现",
            "在引用串已知时，换出未来最长时间不再被访问的页框",
        )
    evidence = _first_symbol(
        facts,
        lambda name: any(word in name for word in ("opt", "optimal", "belady", "next_use")),
    )
    return True, evidence or "出现 OPT / 未来访问相关标识", ""


def _detect_fault_rate(facts: SourceFacts) -> tuple[bool, str, str]:
    haystack = facts.haystack
    if not (
        _matches_token(facts, _FAULT_RATE_TOKENS) or _matches_word(haystack, _FAULT_RATE_WORDS)
    ):
        return (
            False,
            "未找到缺页率统计相关代码",
            "累计缺页次数后除以总访问次数，得到缺页率 = 缺页次数 / 总访问次数",
        )
    has_ratio = facts.divisions > 0 or facts.floor_divisions > 0
    detail = "存在除法运算可用于计算比率" if has_ratio else "未发现除法运算，缺页率可能无法计算"
    evidence = _first_symbol(
        facts,
        lambda name: any(word in name for word in ("fault_rate", "fault_count", "faults")),
    )
    if evidence:
        return True, f"{evidence}；{detail}", ""
    return True, f"缺页率相关标识已出现；{detail}", ""


def _loop_target_names(node: ast.For) -> set[str]:
    target = node.target
    if isinstance(target, ast.Name):
        return {target.id.lower()}
    if isinstance(target, (ast.Tuple, ast.List)):
        return {element.id.lower() for element in target.elts if isinstance(element, ast.Name)}
    return set()


def _iterable_is_range(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "range"
    return isinstance(func, ast.Attribute) and func.attr == "range"


def _detect_frame_sweep(facts: SourceFacts) -> tuple[bool, str, str]:
    """检测是否存在 `for frame_count in range(...)` 形式的多档内存扫描。"""

    for node in facts.for_loops:
        if _loop_target_names(node) & FRAME_SWEEP_TOKENS and _iterable_is_range(node.iter):
            return True, f"第 {node.lineno} 行存在以内存页框数为变量的 range 扫描", ""
    if facts.for_loops and _matches_token(facts, ("frame_count", "num_frames")):
        return (
            True,
            f"包含 {len(facts.for_loops)} 处循环并使用内存页框数变量，未确认为 range 扫描",
            "",
        )
    return (
        False,
        "未发现针对内存页框数的多档扫描循环",
        (
            "用 for frame_count in range(1, 页数 + 1) 扫描不同内存页框数，"
            "输出每个页框数对应的缺页次数与缺页率"
        ),
    )


def _check_issues(
    facts: SourceFacts,
    functional_checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """检查分页模拟器特有的实现缺陷与通用代码问题。"""

    issues: list[dict[str, Any]] = []
    passed = {item["check_id"]: bool(item["passed"]) for item in functional_checks}

    if not any(
        passed[check_id] for check_id in ("FIFO_REPLACEMENT", "LRU_REPLACEMENT", "OPT_REPLACEMENT")
    ):
        issues.append(
            {
                "severity": "error",
                "line": None,
                "code": "NO_REPLACEMENT_ALGORITHM",
                "message": "未检测到任何一种页面置换算法实现",
                "suggestion": "至少实现 FIFO、LRU、OPT 中的两种，并保证同一段引用串下可横向比较",
            }
        )

    if not passed["PAGE_FAULT"]:
        issues.append(
            {
                "severity": "error",
                "line": None,
                "code": "MISSING_FAULT_HANDLING",
                "message": "缺少缺页中断处理逻辑",
                "suggestion": "命中页表时直接返回物理块号，未命中时触发缺页并选择页框",
            }
        )

    uses_integer_split = bool(facts.floor_divisions or facts.modulo_ops or facts.divmod_calls)
    if facts.divisions and not uses_integer_split and (
        passed["ADDRESS_TRANSLATION"] or passed["PAGE_TABLE"]
    ):
        issues.append(
            {
                "severity": "error",
                "line": None,
                "code": "FLOAT_DIVISION_FOR_PAGE",
                "message": "全文只有浮点除法 /，没有出现 //、% 或 divmod，页号很可能被算成了小数",
                "suggestion": "页号与页内偏移用 divmod 或 // 与 % 拆分，缺页率再用 / 计算",
            }
        )

    if not passed["FRAME_SWEEP"] and facts.small_integer_literals:
        largest = max(facts.small_integer_literals)
        issues.append(
            {
                "severity": "warning",
                "line": None,
                "code": "FIXED_FRAME_COUNT",
                "message": f"疑似硬编码内存页框数（1 ~ {largest} 的整数常量），且未扫描多档页框数",
                "suggestion": "把页框数作为参数或循环变量，从 1 扫描到逻辑页总数",
            }
        )

    if not passed["FRAME_SWEEP"]:
        issues.append(
            {
                "severity": "warning",
                "line": None,
                "code": "NO_FRAME_SWEEP",
                "message": "没有生成内存页框数与缺页率的对应关系",
                "suggestion": "对每种置换算法输出一组 (内存页框数, 缺页率) 数据，才能画出变化曲线",
            }
        )

    if not passed["FAULT_RATE_STATISTIC"]:
        issues.append(
            {
                "severity": "warning",
                "line": None,
                "code": "MISSING_FAULT_RATE",
                "message": "没有找到缺页率统计逻辑",
                "suggestion": "输出缺页次数、总访问次数与缺页率百分比",
            }
        )

    if facts.global_statements > 3:
        issues.append(
            {
                "severity": "warning",
                "line": None,
                "code": "GLOBAL_VARS",
                "message": f"使用 {facts.global_statements} 处 global 声明",
                "suggestion": "把页表和计数器作为对象属性或函数参数传递，避免全局状态",
            }
        )

    if facts.divisions and facts.try_statements == 0 and facts.raise_statements == 0:
        issues.append(
            {
                "severity": "warning",
                "line": None,
                "code": "NO_EXCEPTION_HANDLING",
                "message": "存在除法运算，但既没有 try-except 也没有显式 raise 校验",
                "suggestion": "对页框数为 0、访问序列为空等边界情况用 try-except 或 raise 显式处理",
            }
        )

    unsafe_calls = facts.calls & {"eval", "exec", "os.system", "subprocess.run", "compile"}
    if unsafe_calls:
        issues.append(
            {
                "severity": "error",
                "line": None,
                "code": "UNSAFE_DYNAMIC_EXECUTION",
                "message": f"检测到高风险调用：{', '.join(sorted(unsafe_calls))}",
                "suggestion": "分页模拟器不需要动态执行代码，请改用普通函数调用",
            }
        )

    if "__main__" not in facts.strings:
        issues.append(
            {
                "severity": "style",
                "line": None,
                "code": "MISSING_MAIN_GUARD",
                "message": "缺少 `if __name__ == \"__main__\":` 入口保护",
                "suggestion": "把演示与输出逻辑放进主入口，便于被其他模块导入复用",
            }
        )

    if facts.annotated_definitions == 0 and len(facts.functions) > 2:
        issues.append(
            {
                "severity": "quality",
                "line": None,
                "code": "MISSING_TYPE_ANNOTATION",
                "message": "所有函数都没有类型注解",
                "suggestion": "为参考串、页框数和缺页率等参数补充类型标注，便于自检",
            }
        )

    if re.search(r"while\s+True\s*:", facts.source):
        issues.append(
            {
                "severity": "warning",
                "line": None,
                "code": "UNBOUNDED_LOOP",
                "message": "存在 while True 循环，若退出条件依赖被测代码可能出现死循环",
                "suggestion": "改写为 for 循环遍历引用串，或为 while 循环设置明确的终止条件",
            }
        )

    return issues